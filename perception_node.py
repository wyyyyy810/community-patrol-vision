#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perception_node.py  ——  B 的感知节点（红绿灯 + 人物立牌 + 全街区人数统计）

契约依据：A/B/C 最小接口契约 v0.1（FROZEN 2026-09-22）第 3、6 节
  * 节点名            : /perception                       （冻结）
  * 输出话题          : /perception/results   (community_interfaces/msg/PerceptionResult, R, depth 10)
  * header.stamp      : 原图采集时间（直接沿用 image msg 的 stamp）
  * header.frame_id   : camera_optical_frame
  * class_name        : traffic_light / person / license_plate
  * result            : RED|YELLOW|GREEN|UNKNOWN ；COMMUNITY|NON_COMMUNITY|UNKNOWN
  * confidence        : [0,1] 有限，由实测相似度计算，不编造高分
  * bbox              : 原始图像像素坐标，轴对齐 theta=0，尺寸为正
  * run_id / task_id  : 由 C 通过 /perception/set_parameters_atomically 原子设置
  * 调试图像          : /perception/annotated_image（sensor_msgs/Image，画框+名称+置信度+累计人数）

================================ 模块一：红绿灯 ================================
离线验证 4/4（红/黄/绿近景 + 一张远景）；在线验证 RED→GREEN→YELLOW 完整轮转通过。
  1. 暗色横条定位灯箱：V 阈值扫描 {60,75,90,105} → 闭运算 → 连通域，
     保留 面积∈[300, 25%画面]、宽度>40 px、长宽比∈(1.5,7.0) 的候选。
  2. 候选按“强彩色像素密度 = 强彩色像素数 / 连通域面积”降序排。
     （不能用像素总数：远景时真灯箱只有 91x21，而放宽阈值后背景大块黑影连成 595x269，
      像素总数反而更多；实测密度差一个数量级 0.14 vs 0.003。）
  3. 结构校验：灯箱内缩进 4%(x)/10%(y) 后横向三等分，必须恰好一格亮、
     其余两格彩色像素数 < 亮格的 25%。不满足则换下一个候选。
  4. 左=红、中=黄、右=绿（位置定位，不用颜色——实测红灯 hue≈14°、黄灯 hue≈26° 仅差 12°，
     仿真里的绿灯实测 hue≈146° 是青绿色）。
  5. confidence = 0.55 + 优势度，优势度 = (n1 - n2)/n1，上限 0.95。

================================ 模块二：人物立牌 ================================
  1. 贴图即模板：从 A 的 assets/textures 读 person_01..16（COMMUNITY）与
     visitor_1,2（NON_COMMUNITY），共 18 张，**不需要训练**。
     立牌在仿真里就是把整张矩形贴图贴在竖板上（贴图透明区实测 RGB≈251 白色），
     因此用“整矩形灰度模板 + TM_CCOEFF_NORMED”即可，无需 mask。
  2. 多尺度：把画面缩到 0.5 倍，模板高度按 1.13 倍比例从 32 递增到 157 px
     （对应原图 64~314 px）共 14 档。
  3. 每个模板保留 TOP-4 个响应峰（不是只留 1 个）。
  4. 几何 + 纹理过滤（逐条都是线上实测踩出来的）：
       * 长宽比 H/W ∈ [1.5, 6.0]（立牌实测 2.1~3.8）
       * 原图宽 ≥ 12 px、高 ≥ 40 px
       * 框内灰度标准差 ≥ 22（立牌实测 32~94；纯色墙面/杆体只有 ~21）
       * 行均值标准差 ≥ 3.0、列均值标准差 ≥ 3.0 —— **“两个方向都要有内容”**
  5. 非极大值抑制（NMS）：交叠/较小框面积 > 0.5 或 IoU > 0.30 即视为重复。
  6. confidence = 匹配分数（真实相似度，诚实值）；target_id = 贴图文件名。

  ==== v8（2026-10-08 晚）针对线上两个实测故障的三处修改 ====
  故障①「红绿灯杆被识别成社区人员」：把误检框的灰度矩阵打出来发现，灯杆那一框
     14 行**完全一样**（灰度 93/108/148 三条竖直色带），也就是沿竖直方向零变化，
     rowstd 只有 0.4~0.5；而所有真立牌框 rowstd ≥ 5.5（多数 10~30）。
     → 新增「行/列均值标准差」判据，专治灯杆、立柱、阴影、纯色墙这类“一维条纹”。
     实测：live 截图里的灯杆框（0.709 分、长宽比 2.31、std 26.6，能骗过旧的全部判据）
     现在被 rowstd=0.4 直接挡掉。
  故障②「画面左下角的社区人员没被识别」：v7 只留“每模板跨尺度最优的那 1 个峰”，
     尺度变密后，背景里某个平坦区域的伪峰分数会高于真峰，把真峰挤掉 → 真人反而漏检。
     → 改为每模板保留 TOP-4 峰，再统一过滤 + NMS，真峰不会因为一个伪峰而消失；
       同时把尺度阶梯由 7 档加密到 14 档（比例 1.34 → 1.13），消除尺度空档导致的掉分。
     实测：live 截图上 4 块立牌全部找到（含左下角那块），且红绿灯杆/灯箱的框全部消失。
  故障③「一块立牌周围围四五个框」：每模板跨尺度最优 + 包含/IoU 双条件 NMS。

  离线回归（人工核对过的真值，person_min_score = 0.65）：
     _p_s15 → 4/4（person_14、15、1、16）
     _p_s09 → 3/3（person_07、08、visitor_1）
     _p_s02 → 6 框：5 块立牌全中 + 画面右缘确实存在的半个人
     线上截图 → 4/4：person_06（画面左下角那块）、07、08、visitor_F1，
                红绿灯杆与灯箱的误检框全部消失
     速度 ≈0.40 s/帧（比 v7 的 0.2 s 慢一倍，代价换召回率；相机 1.8 Hz 仍跟得上）
  阈值选择依据：四张图的真值最低分是 0.655（_p_s15 那块远景小人），
     而误检最高分是 0.633（车道白线）、0.623（灯杆）；0.65 正好卡在中间。
     现场若发现漏检，把 person_min_score 降到 0.62；若发现零星误检，升到 0.68。

================================ 模块三：全街区人数统计（2026-10-08 新增）========
组委会要求：终端要输出「检查到社区人员 x 名，非社区人员 y 名」，且**对整个街区统计**。
  * 去重依据：18 张贴图与 18 块立牌一一对应 → 用 target_id（贴图名）当身份 ID；
    同一块立牌被连续多帧看到，只计一次；换到下一处再看到，也不会重复计数。
  * 三行输出（互为补充，便于评审对照）：
      1) 新识别个体：`[统计] 新增 person_07 (COMMUNITY) conf=0.83 → 检查到社区人员 1 名，非社区人员 0 名`
      2) 周期性汇总：`[统计] 检查到社区人员 x 名，非社区人员 y 名 (本帧画面 n 人: ...)`
      3) 画框图像左上角叠加同样的累计数字（供演示视频与终端一一对应）。
  * 换区域重新计数：`ros2 param set /perception reset_counters 1`（数字每次递增即可，
    每变一次清零一回），用于“每到一处检测区分别统计该方向人数”。

已知限制（如实记录，不隐藏）：
  * 立牌离镜头极近、下半身被画面裁掉时（只剩头肩），整矩形模板匹配会失败 → 漏检。
    绕开办法：巡看时保持 0.5 m 以上距离；后续可加入“上半身模板”（会同时抬高误检率，暂不加）。
  * 尺度阶梯下限 32（原图 64 px）：比这更小的立牌（远景）检不到；上限 157（原图 314 px）：
    比这更大的（贴脸）检不到。
  * 车道白线、墙角这类“有斜边的高对比纹理”偶尔仍能凑到 0.6 出头的分数（实测 1/4 画面 1 个），
    把 person_min_score 加到 0.68 即可清掉（当前默认 0.65 已经能挡住）。
  * 若现场同一张贴图被立在两处，按贴图名去重会把两处算成一个人 → 把参数
    target_id_mode 设为 empty 可退回“不去重”，但那样又无法统计总数。

时间一致性投票（2026-10-09 新增，用来治“画面看着静止，识别结果却在变”）：
  同一帧喂给同一个检测函数，结果必然相同；所以识别结果会变，一定是**画面本身在变**
  （Gazebo 软件渲染滞后 / 纹理异步加载 / 红绿灯周期变色都会造成前几秒的画面和稳态不同）。
  对策：目标必须在最近 person_window_frames 帧里命中 ≥ person_confirm_frames 帧，
  才会发布、画框、计入统计。默认 3/5，相机 1.8 Hz 下约等于“连续稳定 1.7 s 才认定”。
  每帧会算一个 16x16 灰度指纹并打印在 [变化] 日志里：
      画面未变 → 说明是稳定的稳态画面；画面已变 → 说明输入在动，误检来自渲染/灯色变化。

运行示例：
    python3 ~/perception_node.py
    ros2 param set /perception run_id  demo-run-1
    ros2 param set /perception task_id demo-task-1
    ros2 param set /perception reset_counters 1        # 换区域时清零重新统计
    ros2 param set /perception person_confirm_frames 1 # 关掉去抖（目标一帧即出，但会抖）
    ros2 param set /perception person_confirm_frames 4 # 更严格：5 帧里要中 4 帧才认
    ros2 param set /perception person_min_score 0.62   # 现场有漏检时下调
    ros2 param set /perception person_min_score 0.68   # 现场有零星误检时上调
"""

import glob
import hashlib
import os
import time

import cv2
import numpy as np
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data, QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from community_interfaces.msg import PerceptionResult

try:                     # 画中文标签（车牌号里有省份汉字）需要 PIL；装不上就退回 ASCII
    from PIL import Image as _PILImage, ImageDraw as _PILDraw, ImageFont as _PILFont
except Exception:                                                      # noqa: BLE001
    _PILImage = _PILDraw = _PILFont = None

# ============================== 红绿灯参数 ==============================
V_THRESHOLDS = (60, 75, 90, 105)
MIN_AREA = 300
MAX_AREA_FRAC = 0.25
MIN_WIDTH = 40
AR_MIN, AR_MAX = 1.5, 7.0
STRONG_S, STRONG_V = 120, 50
DOMINANCE_MAX = 0.25
INSET_X, INSET_Y = 0.04, 0.10
LIGHT_ORDER = ('RED', 'YELLOW', 'GREEN')

# ==== BEGIN PERSON-BLOCK-A ====
# （离线测试 person_offline_test.py 会把 A、B 两段标记之间的代码整段 exec，
#   保证“离线测的就是线上跑的那一份”。改模块二时请保持这两个标记成对存在。）
# ============================== 立牌参数 ==============================
DEFAULT_TEXTURE_DIR = ('/home/aic-w/community_sim/install/community_sim/share/'
                       'community_sim/assets/textures')
PERSON_SCALE = 0.5
# 尺度阶梯：32 → 157，比例 1.13，共 14 档（对应原图 64~314 px）
#   下限 32 而不是 26 是实测结论：H=26 那一档产出的候选几乎全是背景误检
#   （车道白线、墙角、天际线），真立牌在该档的分数反而更低。
PERSON_LADDER = tuple(int(round(32 * (1.13 ** i))) for i in range(14))
PERSON_PEAKS_PER_SCALE = 10      # 每个尺度先取前 10 个响应峰
PERSON_PEAK_COVER = 0.45         # 峰间包含度超过它即视为同一处
PERSON_TOPK = 4                  # 每个模板最终保留 4 个峰（v8：不再只留 1 个）
# 几何 + 纹理过滤
PERSON_AR_MIN, PERSON_AR_MAX = 1.5, 6.0     # 立牌实测 2.1~3.8
PERSON_MIN_WIDTH = 12                        # 原图像素
PERSON_MIN_HEIGHT = 40                       # 原图像素
PERSON_MIN_STD = 22.0                        # 框内灰度标准差：立牌 32~94，纯色墙 ~21
PERSON_MIN_ROWSTD = 3.0                      # 行均值标准差：灯杆实测 0.4~0.5，立牌 ≥5.5
PERSON_MIN_COLSTD = 3.0                      # 列均值标准差：横向条纹（如马路白线）实测 ~0.4
NMS_IOU = 0.30                               # IoU 超过此值视为重复
NMS_COVER = 0.50                             # 交叠/较小框面积 超过此值视为“大框套小框”
# ==== END PERSON-BLOCK-A ====


# ---------------------------------------------------------------- 红绿灯检测
def _brightest_strip(hsv, x, y, w, h):
    hs, ss, vs = cv2.split(hsv)
    ix, iy = int(INSET_X * w), int(INSET_Y * h)
    bx, by = x + ix, y + iy
    bw, bh = w - 2 * ix, h - 2 * iy
    sw = max(1, bw // 3)
    out = []
    for k in range(3):
        sx = bx + k * sw
        sub_s = ss[by:by + bh, sx:sx + sw]
        sub_v = vs[by:by + bh, sx:sx + sw]
        sub_h = hs[by:by + bh, sx:sx + sw]
        lit = (sub_s > STRONG_S) & (sub_v > STRONG_V)
        n = int(lit.sum())
        med_hue = int(np.median(sub_h[lit]) * 2) if n > 50 else -1
        out.append({'rect': (sx, by, sw, bh), 'lit_px': n,
                    'mean_v': float(sub_v.mean()) if sub_v.size else 0.0,
                    'med_hue': med_hue})
    return out


def find_lamp_bars(hsv, shape, min_lit):
    """候选灯箱，按“强彩色像素密度”降序：[(*, 强彩色像素数, (x, y, w, h)), ...]"""
    _hs, ss, vs = cv2.split(hsv)
    strong = ((ss > STRONG_S) & (vs > STRONG_V)).astype(np.uint8)
    frame_area = shape[0] * shape[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    out = []
    for vt in V_THRESHOLDS:
        binary = cv2.morphologyEx((vs < vt).astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel)
        n, _labels, stats, _c = cv2.connectedComponentsWithStats(binary, 8)
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < MIN_AREA or area > MAX_AREA_FRAC * frame_area:
                continue
            x = int(stats[i, cv2.CC_STAT_LEFT])
            y = int(stats[i, cv2.CC_STAT_TOP])
            w = int(stats[i, cv2.CC_STAT_WIDTH])
            h = int(stats[i, cv2.CC_STAT_HEIGHT])
            if w < MIN_WIDTH or not (AR_MIN < 1.0 * w / max(1, h) < AR_MAX):
                continue
            score = float(strong[y:y + h, x:x + w].sum())
            if score < min_lit:
                continue
            out.append((score / area, score, (x, y, w, h)))
    out.sort(key=lambda c: -c[0])
    return out


def _lit_bbox(hsv, strip):
    _hs, ss, vs = cv2.split(hsv)
    x, y, w, h = strip['rect']
    lit = ((ss[y:y + h, x:x + w] > STRONG_S) & (vs[y:y + h, x:x + w] > STRONG_V))
    n, _l, stats, _c = cv2.connectedComponentsWithStats(lit.astype(np.uint8) * 255, 8)
    if n <= 1:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (int(stats[i, cv2.CC_STAT_LEFT]) + x, int(stats[i, cv2.CC_STAT_TOP]) + y,
            int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))


def detect_traffic_light(frame, min_lit):
    """返回 (detections, diag)。detections 元素为 dict。"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    bars = find_lamp_bars(hsv, frame.shape, min_lit)
    if not bars:
        return [], 'no lamp bar (画面里找不到灯箱)'
    for _dens, _score, bar in bars:
        strips = _brightest_strip(hsv, *bar)
        counts = [s['lit_px'] for s in strips]
        top = max(counts)
        if top < min_lit:
            continue
        rest = [c for i, c in enumerate(counts) if i != int(np.argmax(counts))]
        if any(c > DOMINANCE_MAX * top for c in rest):
            continue
        k = int(np.argmax(counts))
        second = max(rest + [0])
        dominance = 1.0 if top <= 0 else float(top - second) / float(top)
        bbox = _lit_bbox(hsv, strips[k]) or strips[k]['rect']
        return [{'class_name': 'traffic_light',
                 'result': LIGHT_ORDER[k],
                 'confidence': float(min(0.95, 0.55 + dominance)),
                 'bbox': bbox,
                 'target_id': '',
                 'lamp_box': bar}], ''
    return [], 'bars found but none looks like a 1-lit-of-3 lamp box'


# ---------------------------------------------------------------- 立牌检测
# ==== BEGIN PERSON-BLOCK-B ====
def load_person_templates(texture_dir):
    """person_*.png → COMMUNITY；visitor_*.png → NON_COMMUNITY。返回 [(名称, 类别, 尺度模板)]"""
    out = []
    for pattern, cls in (('person_*.png', 'COMMUNITY'), ('visitor_*.png', 'NON_COMMUNITY')):
        for path in sorted(glob.glob(os.path.join(texture_dir, pattern))):
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is None or img.ndim != 3:
                continue
            bgr = img[:, :, :3] if img.shape[2] == 4 else img
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            h0, w0 = gray.shape[:2]
            variants = []
            for H in PERSON_LADDER:
                W = max(6, int(round(w0 * H / h0)))
                if H < 8 or W < 6:
                    continue
                variants.append((H, cv2.resize(gray, (W, H), interpolation=cv2.INTER_AREA)))
            out.append((os.path.splitext(os.path.basename(path))[0], cls, variants))
    return out


def _overlap(a, b):
    """两个 (x, y, w, h) 的交叠比 → (IoU, 交叠/较小框面积)"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    if inter <= 0:
        return 0.0, 0.0
    union = aw * ah + bw * bh - inter
    return (inter / union if union > 0 else 0.0), inter / float(min(aw * ah, bw * bh))


def _nms_overlap(a, b):
    """a, b 为 (x, y, w, h)。返回 True 表示二者是同一个目标的重复框。"""
    iou, cover = _overlap(a, b)
    return iou > NMS_IOU or cover > NMS_COVER


def _peaks(resp, k):
    """响应图里分数最高的前 k 个位置（在函数内做一次简单去重）"""
    flat = resp.ravel()
    k = min(k, flat.size)
    idx = np.argpartition(flat, -k)[-k:]
    cols = resp.shape[1]
    pts = sorted(((float(flat[i]), int(i % cols), int(i // cols)) for i in idx), reverse=True)
    out = []
    for sc, x, y in pts:
        if out and any(abs(x - p[1]) < 4 and abs(y - p[2]) < 4 for p in out):
            continue
        out.append((sc, x, y))
    return out


def _peak_boxes(gray, tpl, score_min):
    """一张响应图里所有过阈值的峰 → [(分数, x, y, w, h)]"""
    th, tw = tpl.shape
    resp = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
    return [(sc, x, y, tw, th) for sc, x, y in _peaks(resp, PERSON_PEAKS_PER_SCALE)
            if sc >= score_min]


def _box_ok(gray, x, y, w, h, row_min, col_min):
    """几何 + 纹理判据：返回 '' 表示通过，否则返回被拒原因（用于诊断打印）"""
    W, H = w / PERSON_SCALE, h / PERSON_SCALE
    if W < PERSON_MIN_WIDTH or H < PERSON_MIN_HEIGHT:
        return '尺寸'
    if not (PERSON_AR_MIN <= H / max(1.0, W) <= PERSON_AR_MAX):
        return '长宽比'
    sub = gray[y:y + h, x:x + w]
    if float(sub.std()) < PERSON_MIN_STD:
        return 'std'
    # 行/列均值标准差：两个方向都必须有内容，专治灯杆/立柱/纯色墙/马路白线
    if float(sub.mean(axis=1).std()) < row_min or float(sub.mean(axis=0).std()) < col_min:
        return '一维条纹'
    return ''


def detect_persons(frame, templates, score_min, row_min, col_min):
    """模块二的纯函数实现（无 ROS 依赖，离线测试直接调用同一份代码）。

    返回 (dets, detail)。dets 元素：class_name / result / confidence / bbox /
    target_id / template / _small（0.5 倍缩放图上的框，供 NMS 用）。

    流程（v8）：
      ① 逐模板、逐尺度取响应峰，**先过几何+纹理判据**（不合格的峰直接丢弃，
         不占用配额）。
      ② 同一个模板的合格峰**按分数降序**排好，再贪心去重（互相包含的只留分高的那个），
         最后取 TOP-K。这两步的顺序是踩过坑的：早期版本按“尺度由小到大”边收集边去重，
         结果是先入池的低分峰（小尺度、没对齐）把后面真正高分、对齐良好的峰挡在门外，
         真立牌反而消失了（实测 _p_s15 上 person_14/15 被 visitor 模板顶替）。
      ③ 全模板候选合并后再按分数排序，跑一遍 NMS 压重复框。
    """
    small = cv2.resize(frame, None, fx=PERSON_SCALE, fy=PERSON_SCALE,
                       interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gh, gw = gray.shape
    drop = {}

    def rej(why):
        drop[why] = drop.get(why, 0) + 1

    hits = []
    for name, cls, variants in templates:
        cand = []
        for _H, tpl in variants:
            th, tw = tpl.shape
            if th >= gh or tw >= gw:
                continue
            for sc, x, y, w, h in _peak_boxes(gray, tpl, score_min):
                why = _box_ok(gray, x, y, w, h, row_min, col_min)
                if why:
                    rej(why)
                    continue
                cand.append((sc, x, y, w, h))
        cand.sort(key=lambda c: -c[0])
        keep = []
        for c in cand:
            if any(_overlap((c[1], c[2], c[3], c[4]), (k[1], k[2], k[3], k[4]))[1] > PERSON_PEAK_COVER
                   for k in keep):
                continue                       # 与同模板已保留的候选是同一处
            keep.append(c)
            if len(keep) >= PERSON_TOPK:
                break
        hits.extend((sc, name, cls, x, y, w, h) for sc, x, y, w, h in keep)
    hits.sort(key=lambda h: -h[0])

    dets = []
    for sc, name, cls, x, y, w, h in hits:
        if any(_nms_overlap((x, y, w, h), d['_small']) for d in dets):
            rej('重复')
            continue
        bbox = tuple(int(round(v / PERSON_SCALE)) for v in (x, y, w, h))
        dets.append({'class_name': 'person', 'result': cls, 'confidence': sc,
                     'bbox': bbox, '_small': (x, y, w, h), 'target_id': name,
                     'template': name})
    detail = '候选%d → 保留%d' % (len(hits), len(dets))
    if drop:
        detail += '（' + '、'.join('%s%d' % (k, v) for k, v in drop.items()) + '）'
    return dets, detail
# ==== END PERSON-BLOCK-B ====

# ---------------------------------------------------------------- 车牌识别
# ==== BEGIN PLATE-BLOCK-A（离线测试 plate_offline_test.py 会整段 exec 这段代码，
#      所以模块三的参数与函数都放在这两个标记之间，保证“测的就是线上跑的那份”）====
# ============================== 车牌参数 ==============================
PLATE_STROKE_BANDS = ((50, 175), (58, 175), (66, 175), (74, 175), (82, 175),
                      (58, 200), (66, 200))
PLATE_GLYPH_H_MIN, PLATE_GLYPH_H_MAX = 5, 40
# AR 下限必须放到 0.80：车牌里「8H」「H1」这种相邻笔画细的字会粘成一个连通域，
# 粘住后 h/w ≈ 1.0~1.1，老的 1.15 会把这一对整块丢掉 → 行聚类提前结束 → 框短一截，
# 拿半块车牌去读数就是满嘴胡话（2026-10-09 实测「皖A·PJ8H1」只框到「8」）。
PLATE_GLYPH_AR_MIN, PLATE_GLYPH_AR_MAX = 0.80, 4.5
PLATE_GLYPH_MIN_AREA = 6
PLATE_ROW_DY, PLATE_ROW_DH = 0.40, 0.45
PLATE_ROW_MAX_GAP = 2.0
PLATE_ROW_MIN_GLYPHS = 4
PLATE_SPAN_MIN, PLATE_SPAN_MAX = 2.30, 9.00
PLATE_AR_MIN, PLATE_AR_MAX = 2.30, 4.30
PLATE_AR_FIX_LO = 2.90          # 框的长宽比低于此 → 按 3.17 先验补宽（见 plate_fix_bbox）
PLATE_EXPECT = 7                # 中国车牌位数
PLATE_BG_MAX = 62
PLATE_FRAME_T = 74

PLATE_RENDER_AR = 3.17          # 官方车牌 9.5/3 cm；贴图会被横向拉到这个比例
PLATE_GH, PLATE_CW, PLATE_PAD = 40, 44, 8
PLATE_SHIFT_TOL = 3
PLATE_WIDTH_SCALES = (0.88, 1.0, 1.12)
PLATE_DOT_ROWFRAC = 0.40        # 行占有比低于此 → 判为分隔圆点
PLATE_MIN_SCORE = 0.45          # 灰度互相关低于此 → 该位输出 '?'
PLATE_BIN_FRAC = 0.62
PLATE_HARVEST_MIN = 0.62        # 挖真字时「标签对齐」的平均相似度下限；低于此不敢发标签
PLATE_HARVEST_AR = (0.06, 3.0)  # 挖出来的字，墨迹长宽比超出这个范围就是残片，丢掉
                                # （真实「1」约 0.10，只剩一条竖笔的残片约 0.03，所以下限取 0.06）

PLATE_PROVINCES = '京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川贵云藏陕甘青宁新'
PLATE_LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ'      # 中国车牌不用 I / O
PLATE_DIGITS = '0123456789'
PLATE_LATIN = PLATE_LETTERS + PLATE_DIGITS
PLATE_CHARSET = PLATE_PROVINCES + PLATE_DIGITS + PLATE_LETTERS

PLATE_DEFAULT_LIB = os.path.expanduser('~/plate_glyphs.npz')
PLATE_DEFAULT_REFS = os.path.expanduser('~/plate_refs')


def plate_row_clusters(boxes):
    rows = []
    for b in sorted(boxes, key=lambda t: t[0]):
        x, y, w, h = b[0], b[1], b[2], b[3]
        cy = y + h / 2.0
        best, best_gap = None, None
        for r in rows:
            hh = float(np.median([t[3] for t in r]))
            cc = float(np.mean([t[1] + t[3] / 2.0 for t in r]))
            if abs(cy - cc) > PLATE_ROW_DY * max(hh, h) or \
                    abs(h - hh) > PLATE_ROW_DH * max(hh, h):
                continue
            rx0 = min(t[0] for t in r)
            rx1 = max(t[0] + t[2] for t in r)
            gap = max(rx0 - (x + w), x - rx1)
            if gap > PLATE_ROW_MAX_GAP * max(hh, h):
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = r, gap
        (rows.append([b]) if best is None else best.append(b))
    return rows


def plate_find(frame):
    """车牌定位：一排等高等距横向相邻的亮笔画。

    为什么不用「暗块」：车牌底是深藏青（灰度 11~30），但大片黑色路面也是暗的（13~15），
    暗块法会把车牌和路面连成一片（实测踩过）。
    返回 (gray, [(bbox, 字块数, 字高, 灰度带, 底灰)])。
    """
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    H_img, W_img = gray.shape
    out = []
    for lo, hi in PLATE_STROKE_BANDS:
        m = ((gray > lo) & (gray < hi)).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 1), np.uint8))
        n, _lab, st, _ce = cv2.connectedComponentsWithStats(m, 8)
        boxes = []
        for i in range(1, n):
            x, y, w, h, a = st[i, 0], st[i, 1], st[i, 2], st[i, 3], st[i, 4]
            if not (PLATE_GLYPH_H_MIN <= h <= PLATE_GLYPH_H_MAX) or a < PLATE_GLYPH_MIN_AREA:
                continue
            if not (PLATE_GLYPH_AR_MIN <= h / float(max(1, w)) <= PLATE_GLYPH_AR_MAX):
                continue
            boxes.append((x, y, w, h, a))
        for row in plate_row_clusters(boxes):
            if len(row) < PLATE_ROW_MIN_GLYPHS:
                continue
            H = float(np.median([t[3] for t in row]))
            x0 = min(t[0] for t in row)
            x1 = max(t[0] + t[2] for t in row)
            if not (PLATE_SPAN_MIN <= (x1 - x0) / H <= PLATE_SPAN_MAX):
                continue
            px0 = max(0, int(round(x0 - 0.55 * H)))
            px1 = min(W_img - 1, int(round(x1 + 0.30 * H)))
            py0 = max(0, int(round(min(t[1] for t in row) - 0.30 * H)))
            py1 = min(H_img - 1, int(round(max(t[1] + t[3] for t in row) + 0.32 * H)))
            w, h = px1 - px0, py1 - py0
            if w / float(max(1, h)) < PLATE_AR_FIX_LO:      # 疑似漏了尾巴 → 按长宽比补框
                px0, py0, w, h = plate_fix_bbox(gray, (px0, py0, w, h), PLATE_EXPECT)
                px1, py1 = px0 + w, py0 + h
            if not (PLATE_AR_MIN <= w / float(max(1, h)) <= PLATE_AR_MAX):
                continue
            s = gray[py0:py1, px0:px1]
            stroke = (s > lo) & (s < hi)
            bg = np.median(s[~stroke]) if (~stroke).any() else 255
            if bg > PLATE_BG_MAX:
                continue
            out.append(((px0, py0, w, h), len(row), H, (lo, hi), float(bg)))
    out.sort(key=lambda c: -c[1])
    keep = []
    for c in out:                    # 同一块车牌被多个灰度带命中 → 去重
        if any(abs(c[0][0] - k[0][0]) < 14 and abs(c[0][1] - k[0][1]) < 10 for k in keep):
            continue
        keep.append(c)
    return gray, keep


def plate_interior(gray, frame_t=PLATE_FRAME_T):
    """用车牌自身的亮边框把内区框出来 → (top, bot, left, right)。"""
    m = (gray > frame_t)
    rows = np.where(m.mean(axis=1) > 0.55)[0]
    if len(rows) < 2:
        return None
    top, bot = int(rows.min()), int(rows.max())
    if bot - top < 6:
        return None
    band = m[top:bot + 1]
    cols = np.where(band.mean(axis=0) > 0.60)[0]
    left, right = ((int(cols.min()), int(cols.max())) if len(cols) >= 2
                   else (0, gray.shape[1] - 1))
    return top, bot, left, right


def plate_canonicalize(plate_gray, out_h=96):
    """摆正：先按亮边框裁内区，再拉伸到固定长宽比（字库与实拍必须走同一条路）。"""
    if plate_gray.ndim == 3:
        plate_gray = cv2.cvtColor(plate_gray, cv2.COLOR_BGR2GRAY)
    p99 = float(np.percentile(plate_gray, 99))
    p20 = float(np.percentile(plate_gray, 20))
    inner = plate_interior(plate_gray, frame_t=max(64.0, p20 + 0.45 * (p99 - p20)))
    if inner is not None:
        t, b, l, r = inner
        plate_gray = plate_gray[max(0, t):b + 1, max(0, l):r + 1]
    return cv2.resize(plate_gray, (int(round(out_h * PLATE_RENDER_AR)), out_h),
                      interpolation=cv2.INTER_CUBIC)


def plate_crop(gray, bbox, out_h=96):
    x, y, w, h = bbox
    pad = 0.10
    x0 = max(0, int(x - pad * w))
    x1 = min(gray.shape[1], int(x + w + pad * w))
    y0 = max(0, int(y - pad * h))
    y1 = min(gray.shape[0], int(y + h + pad * h))
    return plate_canonicalize(gray[y0:y1, x0:x1], out_h)


def plate_binarize(inner):
    """分位数相对阈值二值化，并清掉「横贯整行的亮线」。

    车牌上下边框是贯穿全宽的亮线，会落进字带里（实测「D」的上方、「8」的下方各有一条），
    它是强对比的水平亮带，灰度互相关会死死咬住它（把 D 判成 Q）。
    返回 (二值掩膜, 去掉亮线后的灰度图)——灰度图也要一起去掉，否则归一化时又把它圈回来。
    """
    p20 = float(np.percentile(inner, 20))
    p99 = float(np.percentile(inner, 99))
    t = p20 + PLATE_BIN_FRAC * (p99 - p20)
    _t, bw = cv2.threshold(inner, t, 255, cv2.THRESH_BINARY)
    rowfrac = bw.mean(axis=1) / 255.0
    full = np.where(rowfrac > 0.72)[0]
    clean_gray = inner.copy()
    if len(full):
        bw[full, :] = 0
        clean_gray[full, :] = int(np.percentile(inner, 20))
    return cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)), clean_gray


class PlateSeg(object):
    __slots__ = ('x0', 'x1', 'rowfrac', 'gray')

    def __init__(self, x0, x1, rowfrac, gray):
        self.x0, self.x1, self.rowfrac, self.gray = x0, x1, rowfrac, gray

    @property
    def width(self):
        return self.x1 - self.x0


def plate_prep(plate_img):
    """切字前的公共前处理：二值化 + 列投影 + 合并 + 清洗。

    返回 (clean, col, bw, gray_clean, Hh, W, rf)。`clean` 是**原始**段（含圆点），
    还没做「段数不够就劈开」的强行对齐 —— 所以它的段数可以当"这个框对不对"的判据。
    """
    g = plate_img if plate_img.ndim == 2 else cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    h, _w = g.shape
    inner = g[int(h * 0.15):int(h * 0.85), :]
    Hh, W = inner.shape
    bw, gray_clean = plate_binarize(inner)
    col = (bw > 0).sum(axis=0)
    thr = max(1, int(0.06 * Hh))
    raw, s = [], None
    for i, v in enumerate(col):
        if v > thr and s is None:
            s = i
        elif v <= thr and s is not None:
            raw.append([s, i])
            s = None
    if s is not None:
        raw.append([s, len(col)])
    merged = []
    for a, b in raw:
        if merged and a - merged[-1][1] <= 0.10 * Hh:
            merged[-1][1] = b
        else:
            merged.append([a, b])

    def rf(a, b):
        rows = np.where(bw[:, a:b].any(axis=1))[0]
        return (rows.max() - rows.min() + 1) / float(Hh) if len(rows) else 0.0

    # 最窄的真字符是「1」，它的宽度随整体尺度变化（实测 3~7 px），所以门槛必须**相对**算。
    # 写死 5 会把劣化帧里的「1」整根丢掉 → 段数少一段 → 后面的对齐全乱（实测踩过）。
    clean = []
    for a, b in merged:
        if b - a < 5:                # 真字符最窄的是「1」（实测 6~7 px）
            continue
        if (b - a) <= max(6, int(0.035 * W)) and rf(a, b) >= 0.90:      # 细边框（老判据，保留）
            continue
        clean.append([a, b])
    return clean, col, bw, gray_clean, Hh, W, rf


def plate_trim_frame(segs, bw, Hh):
    """把车牌自身的亮边框、以及两端粘上的碎块，从段列表里摘掉。

    ① 边框是「实心」亮条 —— 每一列几乎全亮（列内像素数 ≥ 0.55×内区高），
       而真字符的列很少这么满（实测「9」填充 0.32、「K」0.51、「B」0.54）。
       框偏大时边框会和相邻的省字粘成一段（实测用户那张：30~86 里混着 边框+冀+B），
       不削掉就会顶掉「第 1 位」→ 整串错位一格，而段数正好还是 7，段数校验也拦不住。
    ② 只削「实心亮条」是刻意的：车牌结尾的「1」也很窄（实测 7 px），
       按宽度去丢两端碎块会把这根「1」误杀 → 整串少一段 → 后面重新对齐全乱（实测踩过）。
    """
    out = [list(t) for t in segs]
    if not out:
        return out
    for idx, rev in ((0, False), (len(out) - 1, True)):
        if idx < 0 or idx >= len(out):
            continue
        a, b = out[idx]
        w = b - a
        if w < 8:
            continue
        cols = [int(bw[:, x].sum()) >= 0.55 * Hh for x in range(a, b)]
        if rev:
            cols = cols[::-1]
        run = 0
        while run < len(cols) and cols[run]:
            run += 1
        if run >= 3 and run <= 0.35 * w and w - run >= 5:
            out[idx] = [a, b - run] if rev else [a + run, b]
    return out


def plate_fix_bbox(gray, bbox, expect=7):
    """框窄了 → 按「车牌长宽比恒为 3.17」把宽度补够，方向看框外哪一侧还有笔画。

    为什么需要补：车牌里「8H」「H1」这种细笔画会粘成一个连通域（h/w≈1.0），
    老的 AR 下限 1.15 会把它整块丢掉 → 行聚类提前收尾 → 框只有半块车牌
    （实测「皖A·PJ8H1」框宽 82 px，真实 ~102 px），拿半块去读数整串都错。
    补的方向：行聚类是从左往右扫的，漏的通常是尾巴 → 先看右边；右边没笔画才往左补。

    安全性：补宽是无害的（实测远处小车牌 47→57 px 依旧读对，逐字分只掉 0.03），
    因为 plate_canonicalize 靠车牌自身亮边框定位内区，框大一点不影响归一化。
    """
    x, y, w, h = bbox
    tw = int(round(PLATE_RENDER_AR * h))
    if tw <= w or h <= 6:
        return bbox
    y0, y1 = max(0, y), min(gray.shape[0], y + h)
    gap = max(3, int(round(0.6 * h)))

    def n_stroke(a, b):
        a, b = max(0, a), min(gray.shape[1], b)
        if b <= a:
            return 0
        p = gray[y0:y1, a:b]
        return int(((p > 52) & (p < 190)).sum())

    right, left = n_stroke(x + w + 1, x + w + 1 + gap), n_stroke(x - gap, x)
    if right >= left and right > 0:
        return (x, y, tw, h)
    if left > 0:
        return (max(0, x + w - tw), y, tw, h)
    return (max(0, int(round(x + w / 2.0 - tw / 2.0))), y, tw, h)


def plate_segments(plate_img, expect=7):
    """切字。三步清洗：
      ① 丢掉车牌左右边框（贯穿内区的细亮条，宽 2~7 px、rowfrac≈1.0），
         不清掉会顶掉「第 1 位」，整串车牌号错位一格；
      ② 丢掉分隔圆点（rowfrac < 0.40）；
      ③ 按连通域裁剪每个字（车牌下边缘的亮带会粘进字块里，不裁就会污染模板）。
    段数与版面先验不符时：多了按面积留前 expect 个、少了劈最宽的那个。
    """
    clean, col, bw, gray_clean, Hh, W, rf = plate_prep(plate_img)
    clean = plate_trim_frame(clean, bw, Hh)          # 先削掉车牌自身的实心亮边框
    non_dot = [t for t in clean if rf(*t) >= PLATE_DOT_ROWFRAC]
    if len(non_dot) > expect:
        area = {id(t): int(bw[:, t[0]:t[1]].sum()) for t in non_dot}
        keep = set(id(t) for t in sorted(non_dot, key=lambda t: -area[id(t)])[:expect])
        clean = [t for t in clean if id(t) in keep or rf(*t) < PLATE_DOT_ROWFRAC]
    clean = plate_split_to_expect(clean, col, bw, expect, rf)

    out = []
    for a, b in clean:
        sub = bw[:, a:b]
        n, _lab, st, _ce = cv2.connectedComponentsWithStats(sub, 8)
        if n > 1:
            hs = st[1:, cv2.CC_STAT_HEIGHT]
            hmax = int(hs.max()) if len(hs) else 0
            keepi = [i for i in range(1, n)
                     if st[i, cv2.CC_STAT_HEIGHT] >= 0.45 * hmax and st[i, cv2.CC_STAT_AREA] >= 3]
            if not keepi:
                keepi = [1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))]
            y0 = min(st[i, cv2.CC_STAT_TOP] for i in keepi)
            y1 = max(st[i, cv2.CC_STAT_TOP] + st[i, cv2.CC_STAT_HEIGHT] for i in keepi)
            x0 = min(st[i, cv2.CC_STAT_LEFT] for i in keepi)
            x1 = max(st[i, cv2.CC_STAT_LEFT] + st[i, cv2.CC_STAT_WIDTH] for i in keepi)
        else:
            rows = np.where(sub.any(axis=1))[0]
            if not len(rows):
                continue
            y0, y1, x0, x1 = rows.min(), rows.max() + 1, 0, sub.shape[1]
        out.append(PlateSeg(a + x0, a + x1, rf(a, b),
                            gray_clean[y0:y1, a + x0:a + x1]))
    return out


def plate_split_to_expect(merged, col, bw, expect, rf):
    """段数不够时劈开最宽那段（汉字常与后一位字母粘连，实测「苏D」「皖A」都粘）。"""
    def n_non_dot(ms):
        return sum(1 for a, b in ms if rf(a, b) >= PLATE_DOT_ROWFRAC)

    guard = 0
    while n_non_dot(merged) < expect and guard < 8:
        wi, widest = -1, -1
        for i, (a, b) in enumerate(merged):
            if rf(a, b) < PLATE_DOT_ROWFRAC:
                continue
            if b - a > widest:
                wi, widest = i, b - a
        if wi < 0:
            break
        a, b = merged[wi]
        m = max(2, int(0.18 * (b - a)))
        lo, hi = a + m, b - m
        if hi - lo < 2:
            break
        k = int(np.argmin(col[lo:hi])) + lo
        if k - a < 2 or b - k < 2:
            break
        merged[wi:wi + 1] = [[a, k], [k, b]]
        guard += 1
    return merged


def plate_norm(gray_patch, gh=PLATE_GH, cw=PLATE_CW, pad=PLATE_PAD, wx=1.0):
    """把一小块灰度归一成固定画布上的浮点模板（局部对比度拉伸 + 居中）。"""
    if gray_patch is None or gray_patch.size == 0:
        return None
    p = gray_patch.astype(np.float32)
    lo, hi = np.percentile(p, 12), np.percentile(p, 97)
    if hi - lo < 2.0:
        hi = lo + 2.0
    p = np.clip((p - lo) / (hi - lo), 0.0, 1.0)
    ys, xs = np.where(p > 0.5)
    if len(ys) < 3:
        return None
    c = p[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = c.shape
    if h < 3 or w < 2:
        return None
    W = min(cw, max(2, int(round(w * wx * gh / float(h)))))
    r = cv2.resize(c, (W, gh), interpolation=cv2.INTER_AREA)
    cn = np.zeros((gh + 2 * pad, cw + 2 * pad), np.float32)
    x = pad + (cw - W) // 2
    cn[pad:pad + gh, x:x + W] = r
    return cn


def plate_sim(a, b, tol=PLATE_SHIFT_TOL):
    """零均值归一化互相关（NCC）的最大值：b 当大图、a 当模板滑一遍。

    为什么不用二值 IoU：实拍车牌只有 18~19 px 高，二值化后笔画只剩 2~3 px，
    「D 的竖笔」和「Q 的尾巴」这种差别会被抹掉；灰度互相关能把这档差别留住。
    """
    A = a - float(a.mean())
    B = b - float(b.mean())
    na = float(np.sqrt((A * A).sum()))
    nb = float(np.sqrt((B * B).sum()))
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    big = np.zeros((B.shape[0] + 2 * tol, B.shape[1] + 2 * tol), np.float32)
    big[tol:tol + B.shape[0], tol:tol + B.shape[1]] = B
    res = cv2.filter2D(big, -1, A, borderType=cv2.BORDER_CONSTANT)
    return float(res.max() / (na * nb))


def plate_harvest_from_plate(plate_gray, label, lib, min_h=10, ref_lib=None):
    """从一块已知车牌的图上切出真字，追加进 lib。返回实际挖到的字数。

    ❗为什么不能「按顺序硬发标签」：切分偶尔会把两个字粘成一段、或把圆点当成字，
    段数一不对，后面所有字就整体串位 —— 曾经把「7」存进 H 类、把「9」存进 7 类、
    把一条竖线存进 冀 类，结果线上把「冀B7H1K9」稳稳读成「皖DHH1K7」（置信度还不低）。
    所以这里先枚举 ±2 的偏移，挑「与参照库最像」的那个对齐；对不上就整块丢掉。
    """
    chars = label.replace('·', '')
    segs = list(plate_segments(plate_gray, expect=len(chars)))
    dots = [i for i, s in enumerate(segs) if s.rowfrac < PLATE_DOT_ROWFRAC]
    if len(segs) == len(chars) + 1 and len(dots) == 1:      # 圆点被当成一段留下来了
        segs = segs[:dots[0]] + segs[dots[0] + 1:]
    glyphs = [s.gray for s in segs
              if s.rowfrac >= PLATE_DOT_ROWFRAC and s.width >= 3
              and s.gray.shape[0] >= min_h]
    if len(glyphs) != len(chars):
        return 0                                            # 段数对不上 → 一个都不敢发

    def pool_of(ch):
        for src in (ref_lib, lib):
            for t in (src or {}).get(ch, ()):
                yield t

    if sum(1 for _ in pool_of(chars[0])) == 0:
        best_off, best_sc = 0, 1.0                          # 参照库还空着 → 只能按原顺序
    else:
        best_off, best_sc = None, -1.0
        for off in (0, -1, 1, -2, 2):
            tot, cnt = 0.0, 0
            for i, g in enumerate(glyphs):
                j = i + off
                if j < 0 or j >= len(chars):
                    break
                q = plate_norm(g)
                if q is None:
                    break
                tot += max((plate_sim(q, t) for t in pool_of(chars[j])), default=0.0)
                cnt += 1
            if cnt < len(chars):
                continue
            if tot / cnt > best_sc:
                best_off, best_sc = off, tot / cnt
        if best_off is None or best_sc < PLATE_HARVEST_MIN:
            return 0                                        # 对不齐 → 宁可少挖，不可挖错

    n = 0
    for i, g in enumerate(glyphs):
        h, w = g.shape
        if not (PLATE_HARVEST_AR[0] <= w / float(max(1, h)) <= PLATE_HARVEST_AR[1]):
            continue                                        # 残片（只剩一条竖笔之类）
        t = plate_norm(g)
        if t is None:
            continue
        lib.setdefault(chars[i + best_off], []).append(t)
        n += 1
    return n


def plate_library_save(lib, path):
    """把字库存成 npz（量化成 uint8，体积减 4 倍）。模板在 VM 里不需要字体文件。"""
    names, counts, data = [], [], []
    for ch in sorted(lib):
        for t in lib[ch]:
            names.append(ch)
            counts.append(0)
            data.append(np.clip(t * 255.0, 0, 255).astype(np.uint8))
    if not data:
        return 0
    np.savez_compressed(path, names=np.array(names), data=np.array(data))
    return len(data)


def plate_library_load(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        z = np.load(path, allow_pickle=False)
    except Exception:                                                 # noqa: BLE001
        return {}
    lib = {}
    for nm, arr in zip(z['names'], z['data']):
        lib.setdefault(str(nm), []).append(arr.astype(np.float32) / 255.0)
    return lib


def plate_library_from_refs(refs_dir):
    """refs_dir 下每张图片按「文件名 = 车牌号」命名（如 苏D77H8J.png），切真字建库。"""
    lib = {}
    if not refs_dir or not os.path.isdir(refs_dir):
        return lib
    for p in sorted(glob.glob(os.path.join(refs_dir, '*'))):
        stem = os.path.splitext(os.path.basename(p))[0]
        label = stem.replace('-', '').replace('_', '').replace(' ', '')
        if len(label) != 7 or label[0] not in PLATE_PROVINCES:
            continue
        img = cv2.imread(p)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _g, cands = plate_find(img)
        plate = plate_crop(gray, cands[0][0]) if cands else plate_canonicalize(gray)
        n = plate_harvest_from_plate(plate, label, lib, ref_lib=lib)
        if n < 7:
            # 对齐没通过 → 这张标定图不作数，报出来别让人以为标定成功了
            print('[车牌标定] %s 未通过对齐校验（只挖到 %d 个字），已跳过'
                  % (os.path.basename(p), n))
    return lib


def plate_classify(gray_patch, pool, lib):
    """在候选字集 pool 里找最像的字，返回 [(字符, 分数), ...]（降序）。"""
    qs = [plate_norm(gray_patch, wx=w) for w in PLATE_WIDTH_SCALES]
    qs = [q for q in qs if q is not None]
    if not qs:
        return []
    rank = []
    for ch in pool:
        best = 0.0
        for tpl in lib.get(ch, ()):
            for q in qs:
                v = plate_sim(q, tpl)
                if v > best:
                    best = v
        rank.append((ch, best))
    rank.sort(key=lambda t: -t[1])
    return rank


def plate_read(plate_img, lib, expect=7, min_score=PLATE_MIN_SCORE):
    """返回 (车牌字符串, 每位分数, 诊断串)。"""
    chars, scores, diag = [], [], []
    for s in plate_segments(plate_img, expect=expect):
        if s.rowfrac < PLATE_DOT_ROWFRAC:
            diag.append('·')
            continue
        if len(chars) == 0:
            pool = PLATE_PROVINCES
        elif len(chars) == 1:
            pool = PLATE_LETTERS
        else:
            pool = PLATE_LATIN
        rank = plate_classify(s.gray, pool, lib)
        ch, sc = (rank[0] if rank else ('?', 0.0))
        if sc < min_score:
            ch = '?'
        chars.append(ch)
        scores.append(sc)
        diag.append('%s%.2f' % (ch, sc))
    return ''.join(chars), scores, ' '.join(diag)


def plate_detect(frame, lib, expect=7, min_score=PLATE_MIN_SCORE):
    """整帧入口：返回 dets 列表（class_name='license_plate'，result 就是车牌号）。"""
    gray, cands = plate_find(frame)
    out = []
    for bbox, n, H, band, bg in cands:
        text, scores, diag = plate_read(plate_crop(gray, bbox), lib,
                                        expect=expect, min_score=min_score)
        if not text:
            continue
        conf = float(min(scores)) if scores else 0.0
        out.append({'class_name': 'license_plate', 'result': text,
                    'confidence': conf, 'bbox': bbox, 'target_id': text,
                    'chars': scores, 'diag': diag, 'n_glyph': n, 'glyph_h': H})
    return out, gray
PLATE_CJK_FONTS = (
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/truetype/arphic/uming.ttc',
    '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    # Windows 上跑离线验收图时用得到（虚拟机里用不到，留着不占事）
    'C:/Windows/Fonts/simhei.ttf',
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/simsun.ttc',
)


def plate_find_cjk_font():
    """找一个能在画框图上写中文的字体（车牌号第一位是省份汉字）。"""
    for p in PLATE_CJK_FONTS:
        if os.path.exists(p):
            return p
    for root in ('/usr/share/fonts', '/usr/local/share/fonts'):
        if not os.path.isdir(root):
            continue
        for dirpath, _dn, fns in os.walk(root):
            for fn in fns:
                low = fn.lower()
                if low.endswith(('.ttf', '.ttc', '.otf')) and \
                        ('cjk' in low or 'wqy' in low or 'droid' in low):
                    return os.path.join(dirpath, fn)
    return None


def plate_draw_label(vis, text, org, color, font_path=None, size=18):
    """在图上写一行标签；有中文字体就用 PIL，否则退回 cv2 的 ASCII（汉字显示为 ?）。"""
    pil_font = globals().get('_PILFont')
    pil_image = globals().get('_PILImage')
    pil_draw = globals().get('_PILDraw')
    x, y = org
    if pil_font is not None and pil_image is not None and font_path:
        try:
            font = pil_font.truetype(font_path, size)
        except Exception:                                              # noqa: BLE001
            font = None
        if font is not None:
            img = pil_image.fromarray(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
            dr = pil_draw.Draw(img)
            box = dr.textbbox((0, 0), text, font=font)
            tw, th = box[2] - box[0], box[3] - box[1]
            x0 = max(0, min(x, vis.shape[1] - tw - 6))
            y0 = max(0, min(y - th - 6, vis.shape[0] - th - 6))
            dr.rectangle([x0, y0, x0 + tw + 6, y0 + th + 6],
                         fill=tuple(int(c) for c in color))
            dr.text((x0 + 3, y0 + 3 - box[1]), text, font=font, fill=(0, 0, 0))
            vis[:] = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            return
    safe = text.encode('ascii', 'replace').decode('ascii')
    cv2.putText(vis, safe, (max(0, x), max(14, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


# ==== END PLATE-BLOCK-B ====



class Perception(Node):
    def __init__(self):
        super().__init__('perception')          # 节点名冻结为 perception
        self.bridge = CvBridge()

        self.declare_parameter('run_id', '')
        self.declare_parameter('task_id', '')
        self.declare_parameter('min_lit_pixels', 60)
        self.declare_parameter('person_min_score', 0.65)
        self.declare_parameter('person_min_rowstd', PERSON_MIN_ROWSTD)
        self.declare_parameter('person_min_colstd', PERSON_MIN_COLSTD)
        # ---- 时间一致性投票（2026-10-09 新增）----
        # 现象：画面看静止，前几秒把红绿灯杆框成社区人员，几秒后又正常。
        # 对策：目标必须在最近 window 帧里命中 ≥ confirm 帧才发布/画框/计数。
        #       相机实测 1.8 Hz → confirm=3 约等于连续稳定 1.7 s 才认定。
        self.declare_parameter('person_confirm_frames', 3)
        self.declare_parameter('person_window_frames', 5)
        self.declare_parameter('person_match_dist', 0.18)  # 同一目标相邻帧中心位移容差（×画面长边）
        self.declare_parameter('person_enable', True)
        self.declare_parameter('textures_dir', DEFAULT_TEXTURE_DIR)
        self.declare_parameter('target_id_mode', 'texture')   # texture | empty
        self.declare_parameter('publish_annotated', True)
        self.declare_parameter('require_context', False)      # 联调置 true：无上下文不发布
        self.declare_parameter('log_every_sec', 2.0)
        self.declare_parameter('diag_sec', 5.0)
        self.declare_parameter('summary_sec', 10.0)           # 累计人数周期性打印间隔
        self.declare_parameter('reset_counters', 0)           # 每变一次数字 → 累计清零
        # ---- 模块三：车牌识别（2026-10-09 新增）----
        self.declare_parameter('plate_enable', True)
        self.declare_parameter('plate_lib_path', PLATE_DEFAULT_LIB)   # 字体渲染的字库 npz
        self.declare_parameter('plate_refs_dir', PLATE_DEFAULT_REFS)  # 标定图目录（文件名=车牌号）
        self.declare_parameter('plate_min_score', PLATE_MIN_SCORE)
        self.declare_parameter('plate_expect', 7)             # 中国车牌 7 位
        self.declare_parameter('plate_period', 0.6)           # OCR 节流秒数（定位每帧都做，只有 OCR 节流）
        # 留证据：画面里出现车牌时把「原始帧 + 车牌切片 + 读数诊断」落盘，
        # 方便回头在 Windows 上精确复盘（默认开，存满 plate_dump_max 张就停）。
        self.declare_parameter('plate_dump', True)
        self.declare_parameter('plate_dump_dir', os.path.expanduser('~/plate_frames'))
        self.declare_parameter('plate_dump_max', 40)

        result_qos = QoSProfile(depth=10,
                                reliability=ReliabilityPolicy.RELIABLE,
                                durability=DurabilityPolicy.VOLATILE)
        self.results_pub = self.create_publisher(PerceptionResult, '/perception/results', result_qos)
        self.image_pub = self.create_publisher(Image, '/perception/annotated_image',
                                               qos_profile_sensor_data)
        # 相机话题 QoS 是 best-effort（契约 15Hz/BE/depth5），订阅必须匹配否则连不上
        self.create_subscription(Image, '/camera/image_raw', self.on_image, qos_profile_sensor_data)

        self.templates = []
        if self.get_parameter('person_enable').value:
            self.templates = load_person_templates(self.get_parameter('textures_dir').value)
            if self.templates:
                self.get_logger().info('person templates: %d  (%s)'
                                       % (len(self.templates),
                                          ', '.join(t[0] for t in self.templates)))
            else:
                self.get_logger().warning('no person template found under %s'
                                          % self.get_parameter('textures_dir').value)

        # ------- 模块三：车牌字库 -------
        self.plate_lib = {}
        self.cjk_font = plate_find_cjk_font()
        self.last_plate = ('', -1e9)
        self.plate_cache = None       # OCR 结果缓存（见 _plate_frame）
        self.plate_dump_n = 0
        self.plate_dump_t = -1e9
        if self.get_parameter('plate_enable').value:
            self.plate_lib = plate_library_load(self.get_parameter('plate_lib_path').value)
            n_font = sum(len(v) for v in self.plate_lib.values())
            refs = plate_library_from_refs(self.get_parameter('plate_refs_dir').value)
            n_ref = sum(len(v) for v in refs.values())
            for k, v in refs.items():
                self.plate_lib.setdefault(k, []).extend(v)
            if self.plate_lib:
                self.get_logger().info('车牌字库: %d 类 / %d 模板（字体 %d + 标定 %d） 中文字体=%s'
                                       % (len(self.plate_lib), n_font + n_ref, n_font, n_ref,
                                          self.cjk_font or '无(标签退回 ASCII)'))
            else:
                self.get_logger().warning(
                    '车牌字库为空：把 plate_glyphs.npz 放到 %s，'
                    '或把标定图（文件名=车牌号，如 苏D77H8J.png）放进 %s'
                    % (self.get_parameter('plate_lib_path').value,
                       self.get_parameter('plate_refs_dir').value))

        # ------- 全街区统计状态 -------
        self.counted = {}            # target_id -> {'cls':..., 'score':...}
        self.visible_ids = frozenset()
        self.last_summary_s = 0.0
        self._reset_nonce = int(self.get_parameter('reset_counters').value)
        self.add_on_set_parameters_callback(self._on_set_params)

        # ---- 时间一致性投票状态 ----
        self.frame_no = 0
        self.tracks = {}          # key -> {'tid','hits':[帧号],'bbox','score','cls','template'}
        self.last_fp = None       # 上一帧指纹
        self.last_sig = None      # 上一帧的原始命中集合（用于只在变化时打日志）
        self.last_log = {}
        self.last_diag = 0.0
        self.seq = 0
        self.get_logger().info('perception ready: waiting for /camera/image_raw ...')

    # -------------------------------------------------------------- 参数
    def _on_set_params(self, params):
        for p in params:
            if p.name == 'reset_counters':
                try:
                    v = int(p.value)
                except (TypeError, ValueError):
                    continue
                if v != self._reset_nonce:
                    self._reset_nonce = v
                    n = len(self.counted)
                    self.counted = {}
                    self.visible_ids = frozenset()
                    self.get_logger().info('[统计] 计数已清零（上一区域共 %d 人）→ '
                                           '检查到社区人员 0 名，非社区人员 0 名' % n)
        return SetParametersResult(successful=True)

    # -------------------------------------------------------------- 统计
    def _counts(self):
        nc = sum(1 for v in self.counted.values() if v['cls'] == 'COMMUNITY')
        nn = sum(1 for v in self.counted.values() if v['cls'] == 'NON_COMMUNITY')
        return nc, nn

    def _summary_text(self):
        nc, nn = self._counts()
        return '检查到社区人员 %d 名，非社区人员 %d 名' % (nc, nn)

    def _update_counts(self, person_dets):
        """把本帧识别到的人并按 target_id 去重计入全街区统计，返回本帧可见 ID 集合。"""
        visible = set()
        new_ids = []
        for d in person_dets:
            tid = d.get('target_id') or ''
            if not tid:
                continue
            visible.add(tid)
            if tid not in self.counted:
                self.counted[tid] = {'cls': d['result'], 'score': float(d['confidence'])}
                new_ids.append(tid)
            elif d['confidence'] > self.counted[tid]['score']:
                self.counted[tid]['score'] = float(d['confidence'])
        for tid in new_ids:
            self.get_logger().info('[统计] 新增 %s (%s) conf=%.2f  →  %s'
                                   % (tid, self.counted[tid]['cls'], self.counted[tid]['score'],
                                      self._summary_text()))
        return frozenset(visible)

    # -------------------------------------------------------------- 回调
    def on_image(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:                                     # noqa: BLE001
            self.get_logger().warning('cv_bridge failed: %s' % exc)
            return

        dets, diag_tl = detect_traffic_light(frame, self.get_parameter('min_lit_pixels').value)
        person_dets, diag_p = [], ''
        if self.templates:
            raw_dets, diag_p = self._detect_persons(frame)
            person_dets = self._stabilize(raw_dets, frame)
            self._log_change(raw_dets, person_dets, frame, diag_p)

        # ------- 模块三：车牌 -------
        plate_dets = self._plate_frame(frame)

        dets = dets + person_dets + plate_dets

        visible = self._update_counts(person_dets)
        if person_dets:
            now_s = self.get_clock().now().nanoseconds / 1e9
            if visible != self.visible_ids or \
                    now_s - self.last_summary_s >= self.get_parameter('summary_sec').value:
                self.visible_ids = visible
                self.last_summary_s = now_s
                self.get_logger().info('[统计] %s   (本帧画面 %d 人: %s)'
                                       % (self._summary_text(), len(person_dets),
                                          ', '.join(sorted(visible)) or '-'))

        # 画框图像：只要有人在看这个话题就每帧都发（无目标也发，方便 rqt_image_view 里
        # 常驻显示累计人数；之前“无目标不发”会让话题在话题列表里时隐时现）
        if self.get_parameter('publish_annotated').value and \
                self.image_pub.get_subscription_count() > 0:
            self._publish_annotated(frame, dets, msg)

        if not dets:
            self._diag(frame, diag_tl, diag_p)
            return

        if self.get_parameter('require_context').value:
            if not self.get_parameter('run_id').value or not self.get_parameter('task_id').value:
                return

        for d in dets:
            self._publish(d, msg)
        self.seq += 1

    # -------------------------------------------------------------- 立牌识别
    def _detect_persons(self, frame):
        """薄封装：真正的算法在模块级 detect_persons()，离线测试跑的是同一份代码。"""
        dets, detail = detect_persons(
            frame, self.templates,
            float(self.get_parameter('person_min_score').value),
            float(self.get_parameter('person_min_rowstd').value),
            float(self.get_parameter('person_min_colstd').value))
        if self.get_parameter('target_id_mode').value != 'texture':
            for d in dets:
                d['target_id'] = ''
        return dets, detail

    # -------------------------------------------------------------- 去抖
    @staticmethod
    def _fingerprint(frame):
        """16x16 灰度缩略图的 md5 前 8 位：画面内容没变，指纹就不变。"""
        tiny = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (16, 16),
                          interpolation=cv2.INTER_AREA)
        return hashlib.md5(tiny.tobytes()).hexdigest()[:8]

    def _stabilize(self, raw_dets, frame):
        """时间一致性投票：最近 window 帧里命中 ≥ confirm 帧的目标才算数。

        同一帧喂给同一个检测函数，结果必然相同；所以“画面静止但识别在变”
        只可能是画面其实在变（渲染滞后/纹理异步加载/红绿灯周期变色）。
        投票把这种只持续几帧的伪目标挡住，代价是目标出现后要等 confirm 帧才显示。
        """
        need = max(1, int(self.get_parameter('person_confirm_frames').value))
        win = max(need, int(self.get_parameter('person_window_frames').value))
        self.frame_no += 1
        tol = float(self.get_parameter('person_match_dist').value) * max(frame.shape[:2])

        for d in raw_dets:
            x, y, w, h = d['bbox']
            cx, cy = x + w / 2.0, y + h / 2.0
            hit_key = None
            for k, tr in self.tracks.items():
                if tr['tid'] != d['target_id']:
                    continue
                tx, ty, tw, th = tr['bbox']
                dist = ((cx - (tx + tw / 2.0)) ** 2 + (cy - (ty + th / 2.0)) ** 2) ** 0.5
                # 位置接近 + 尺度不能差太多（防止大框并掉小框）
                if dist <= tol and abs(h - th) <= 0.5 * max(h, th):
                    hit_key = k
                    break
            if hit_key is None:
                hit_key = (d['target_id'], self.frame_no)
                self.tracks[hit_key] = {'tid': d['target_id'], 'hits': []}
            tr = self.tracks[hit_key]
            tr['hits'].append(self.frame_no)
            tr['bbox'] = d['bbox']
            tr['score'] = float(d['confidence'])
            tr['cls'] = d['result']
            tr['template'] = d.get('template', d['target_id'])

        cutoff = self.frame_no - win
        for k in list(self.tracks):
            self.tracks[k]['hits'] = [f for f in self.tracks[k]['hits'] if f > cutoff]
            if not self.tracks[k]['hits']:
                del self.tracks[k]

        out = []
        for _k, tr in self.tracks.items():
            if len(tr['hits']) < need:
                continue
            out.append({'class_name': 'person', 'result': tr['cls'],
                        'confidence': tr['score'], 'bbox': tr['bbox'],
                        'target_id': tr['tid'], 'template': tr['template']})
        out.sort(key=lambda d: -d['confidence'])
        return out

    def _log_change(self, raw_dets, confirmed, frame, diag_p):
        """只在“本帧命中情况变了”时打一条，顺带报画面指纹是否变化。"""
        sig = tuple(sorted((d['target_id'], d['bbox'][0] // 24, d['bbox'][1] // 24)
                           for d in raw_dets))
        fp = self._fingerprint(frame)
        same_frame = (fp == self.last_fp)
        self.last_fp = fp
        if sig == self.last_sig:
            return
        self.last_sig = sig
        raw_ids = sorted({d['target_id'] for d in raw_dets})
        ok_ids = sorted({d['target_id'] for d in confirmed})
        pend = [i for i in raw_ids if i not in ok_ids]
        self.get_logger().info(
            '[变化] 画面%s(fp=%s) 本帧命中%d→确认%d | 已确认:%s | 待确认:%s | %s'
            % ('未变' if same_frame else '已变', fp, len(raw_dets), len(confirmed),
               ','.join(ok_ids) or '-', ','.join(pend) or '-', diag_p or ''))

    # -------------------------------------------------------------- 车牌
    def _plate_frame(self, frame):
        """整帧车牌识别。

        分两步是因为实测耗时差 20 倍：
          * plate_find（定位）  0.02 s/帧 —— 每帧都跑，画面里没车牌时 0 候选直接返回；
          * plate_read（OCR）   0.42 s/帧 —— 太贵，必须节流。
        节流方式：plate_period 秒内复用上一次的字符串，但框用当前帧刚算出来的位置，
        所以框永远跟着车走，不会出现「字对了框飘了」。
        """
        if not self.plate_lib:
            return []
        gray, cands = plate_find(frame)
        if not cands:                       # 画面里没有车牌 → 只花了 0.02 s
            self.plate_cache = None
            return []
        now_s = self.get_clock().now().nanoseconds / 1e9
        period = float(self.get_parameter('plate_period').value)
        dets = []
        for bbox, n, H, band, bg in cands:
            x, y, w, h = bbox
            cx, cy = x + w / 2.0, y + h / 2.0
            cache = self.plate_cache
            if cache is not None and now_s - cache['t'] < period and \
                    abs(cx - cache['cx']) < 0.5 * max(w, 1) + 20 and \
                    abs(cy - cache['cy']) < 0.5 * max(h, 1) + 20:
                text, scores, diag = cache['text'], cache['chars'], cache['diag']
            else:
                text, scores, diag = plate_read(
                    plate_crop(gray, bbox), self.plate_lib,
                    expect=int(self.get_parameter('plate_expect').value),
                    min_score=float(self.get_parameter('plate_min_score').value))
                if text:
                    self.plate_cache = {'t': now_s, 'cx': cx, 'cy': cy,
                                        'text': text, 'chars': scores, 'diag': diag}
            if not text:
                continue
            dets.append({'class_name': 'license_plate', 'result': text,
                         'confidence': float(min(scores)) if scores else 0.0,
                         'bbox': bbox, 'target_id': text, 'chars': scores,
                         'diag': diag, 'n_glyph': n, 'glyph_h': H})
        self._log_plates(dets, frame)
        self._plate_dump(frame, gray, cands, dets)
        return dets

    # -------------------------------------------------------------- 车牌留证据
    def _plate_dump(self, frame, gray, cands, dets):
        """把原始帧 + 车牌切片 + 读数诊断落盘，间隔 1.5 s、最多 plate_dump_max 张。"""
        if not self.get_parameter('plate_dump').value:
            return
        now_s = self.get_clock().now().nanoseconds / 1e9
        if not cands or now_s - self.plate_dump_t < 1.5 or \
                self.plate_dump_n >= int(self.get_parameter('plate_dump_max').value):
            return
        d = self.get_parameter('plate_dump_dir').value
        try:
            if not os.path.isdir(d):
                os.makedirs(d)
            tag = time.strftime('%H%M%S', time.localtime()) + '_%d' % self.plate_dump_n
            cv2.imwrite(os.path.join(d, tag + '_raw.png'), frame)
            lines = []
            for i, (bbox, n, H, band, bg) in enumerate(cands):
                cv2.imwrite(os.path.join(d, '%s_c%d.png' % (tag, i)),
                            plate_crop(gray, bbox))
                lines.append('cand%d bbox=%s n=%d glyph_h=%.1f band=%s bg=%.1f'
                             % (i, tuple(int(v) for v in bbox), n, H, band, bg))
            for dd in dets:
                lines.append('read "%s" conf=%.2f chars=%s diag=%s'
                             % (dd['result'], dd['confidence'],
                                [round(float(c), 2) for c in dd.get('chars', [])], dd['diag']))
            with open(os.path.join(d, tag + '_info.txt'), 'w') as fh:
                fh.write('\n'.join(lines) + '\n')
            self.plate_dump_n += 1
            self.plate_dump_t = now_s
            if self.plate_dump_n == 1:
                self.get_logger().info('车牌留证据已开启 → %s（最多 %d 张）'
                                       % (d, int(self.get_parameter('plate_dump_max').value)))
        except Exception as exc:                                      # noqa: BLE001
            self.get_logger().warning('车牌留证据失败: %s' % exc)

    # -------------------------------------------------------------- 车牌日志
    def _log_plates(self, plate_dets, frame):
        """车牌号变了、或距上次打印超过 1 s 才打一条，避免 1.8 Hz 刷屏。"""
        if not plate_dets:
            return
        now_s = self.get_clock().now().nanoseconds / 1e9
        text = plate_dets[0]['result']
        if text == self.last_plate[0] and now_s - self.last_plate[1] < 1.0:
            return
        self.last_plate = (text, now_s)
        for d in plate_dets:
            x, y, w, h = d['bbox']
            self.get_logger().info('[车牌] %s  conf=%.2f  bbox=(%d,%d,%dx%d)  字高=%d  | %s'
                                   % (d['result'], d['confidence'], x, y, w, h,
                                      d['glyph_h'], d['diag']))

    # -------------------------------------------------------------- 输出
    def _publish(self, d, msg):
        out = PerceptionResult()
        out.run_id = self.get_parameter('run_id').value
        out.task_id = self.get_parameter('task_id').value
        out.header.stamp = msg.header.stamp            # 原图采集时间
        out.header.frame_id = 'camera_optical_frame'   # 契约固定
        out.class_name = d['class_name']
        out.result = d['result']
        out.confidence = float(min(1.0, max(0.0, d['confidence'])))
        x, y, w, h = d['bbox']
        out.bbox.center.position.x = float(x + w / 2.0)
        out.bbox.center.position.y = float(y + h / 2.0)
        out.bbox.center.theta = 0.0
        out.bbox.size_x = float(max(1, w))
        out.bbox.size_y = float(max(1, h))
        out.target_id = d['target_id']
        self.results_pub.publish(out)

        key = (d['class_name'], d['result'], d['target_id'])
        now_s = self.get_clock().now().nanoseconds / 1e9
        if now_s - self.last_log.get(key, 0.0) > self.get_parameter('log_every_sec').value:
            self.last_log[key] = now_s
            self.get_logger().info('[%03d] %-14s %-14s conf=%.2f bbox=(%d,%d,%dx%d)%s'
                                   % (self.seq, d['class_name'], d['result'], out.confidence,
                                      x, y, w, h,
                                      ('  id=%s' % d['target_id']) if d['target_id'] else ''))

    def _publish_annotated(self, frame, dets, msg):
        vis = frame.copy()
        for d in dets:
            x, y, w, h = d['bbox']
            if d['class_name'] == 'traffic_light':
                col = (0, 255, 0)
                anchor = d.get('lamp_box')
                if anchor:
                    cv2.rectangle(vis, (anchor[0], anchor[1]),
                                  (anchor[0] + anchor[2], anchor[1] + anchor[3]),
                                  (0, 255, 255), 1)
            elif d['class_name'] == 'license_plate':
                col = (0, 255, 255)
            else:
                col = (255, 128, 0) if d['result'] == 'COMMUNITY' else (0, 0, 255)
            cv2.rectangle(vis, (x, y), (x + w, y + h), col, 2)
            if d['class_name'] == 'license_plate':
                plate_draw_label(vis, '%s %.2f' % (d['result'], d['confidence']),
                                 (x, y), col, self.cjk_font)
                continue
            label = '%s %s %.2f' % (d['class_name'], d['result'], d['confidence'])
            if d.get('target_id'):
                label += ' ' + d['target_id']
            cv2.putText(vis, label, (max(0, x), max(14, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)

        # 左上角叠加全街区累计人数（与终端打印一一对应）
        cv2.rectangle(vis, (0, 0), (vis.shape[1], 34), (32, 32, 32), -1)
        cv2.putText(vis, self._summary_text(), (8, 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        try:
            self.image_pub.publish(self.bridge.cv2_to_imgmsg(vis, encoding='bgr8',
                                                            header=msg.header))
        except Exception as exc:                                       # noqa: BLE001
            self.get_logger().warning('annotated image failed: %s' % exc)

    def _diag(self, frame, diag_tl, diag_p):
        now_s = self.get_clock().now().nanoseconds / 1e9
        if now_s - self.last_diag < self.get_parameter('diag_sec').value:
            return
        self.last_diag = now_s
        h, w = frame.shape[:2]
        self.get_logger().info('diag %dx%d  [light] %s  [person] %s'
                               % (w, h, diag_tl, diag_p or 'n/a'))


def main():
    rclpy.init()
    node = Perception()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    try:
        node.destroy_node()
        rclpy.shutdown()
    except Exception:                                                  # noqa: BLE001
        pass          # 连按两次 Ctrl+C 时 ROS 抱怨 shutdown 已调用，忽略即可


if __name__ == '__main__':
    main()
