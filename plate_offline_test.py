"""车牌识别的离线回归测试 / 字库构建脚本（在 Windows 上跑，虚拟机不需要）。

它从 perception_node.py 里把 PLATE-BLOCK-A/B 之间的整段代码 exec 出来，
所以**测的就是节点里线上跑的那一份**，不存在“测试通过但线上不一样”的问题。

用法：
    python plate_offline_test.py            # 跑回归，打印每张图的识别结果
    python plate_offline_test.py --build    # 顺带生成 plate_glyphs.npz（要 scp 进虚拟机）

真值（人工放大核对过）：
    shot2      → 苏D·77H8J
    shot3      → 皖A·PJ8H1
    vcar19 近车 → 苏D·77H8J
    vcar19 远车 → 冀B·7H1K9   ← 2026-10-09 用户截图放大核对订正：是 冀 不是 皖！
                                  （标错会污染字库：把 冀 的字模存进「皖」这一类，
                                    之后所有 冀 都被读成 皖）
    三张官方贴图 → 苏A·B8Q62 / 鄂D·7B5Q2 / 苏A·PL12A

NEW = 用户在虚拟机里实跑时截的三张（框是节点画的，抹掉黄框/标签底色才能当标定源）：
    now1 → 皖A·PJ8H1（这张定位框短了一截，只框到「8」）
    now2 → 苏D·77H8J（这张读对了）
    now3 → 冀B·7H1K9（这张读错，因为字库里 冀 被错标成 皖）
"""
import os
import re
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
NODE = os.path.join(HERE, 'perception_node.py')

CLIP = r'C:\Users\wyyyyy\.workbuddy\clipboard-images'
REF = r'D:\BaiduNetdiskDownload\复赛资料\车辆识别'
SHOT2 = os.path.join(CLIP, 'clipboard-2026-10-09T08-52-53-020Z-6b676d9b.png')
SHOT3 = os.path.join(CLIP, 'clipboard-2026-10-09T08-52-53-021Z-16c6f12b.png')
VCAR = os.path.join(HERE, '_v_car19.png')

FRAMES = [('shot2', SHOT2, (296, 259, 104, 31), '苏D77H8J'),
          ('shot3', SHOT3, (376, 288, 101, 31), '皖APJ8H1'),
          ('vcar近', VCAR, (532, 352, 86, 29), '苏D77H8J'),
          ('vcar远', VCAR, (176, 332, 47, 18), '冀B7H1K9')]

# 用户实跑截图（原图带黄框 + 青色标签，用 _clean_overlay 抹掉才能当标定/回归素材）
SHOT4 = os.path.join(CLIP, 'clipboard-2026-10-09T09-40-38-465Z-5dbe172c.png')
SHOT5 = os.path.join(CLIP, 'clipboard-2026-10-09T09-40-38-498Z-309573ab.png')
SHOT6 = os.path.join(CLIP, 'clipboard-2026-10-09T09-40-38-499Z-5810c518.png')
# 框是真值框（now1 是节点框短了，这里用人工量出的完整车牌框）
NEW = [('now1', SHOT4, (163, 137, 102, 32), '皖APJ8H1'),
       ('now2', SHOT5, (150, 171, 103, 31), '苏D77H8J'),
       ('now3', SHOT6, (121, 147, 102, 32), '冀B7H1K9')]

# 节点 plate_dump 落盘的**相机原帧**（40 帧 / 三块固定车牌），这是目前质量最好的素材。
# 真值是逐帧放大人工核对过的（见 _sel_truth.png）：冀B·7H1K9 / 苏D·77H8J / 皖A·PJ8H1。
DUMP_DIR = os.path.join(HERE, 'plate_frames')
DUMP = [('190855_0', '冀B7H1K9'), ('190902_1', '冀B7H1K9'),
        ('191211_18', '苏D77H8J'), ('191301_26', '苏D77H8J'),
        ('191429_29', '皖APJ8H1'), ('191442_31', '皖APJ8H1')]


def clean_overlay(path):
    """抹掉截图上的黄框（画在车牌边框上）和青色标签底，还原成接近原始帧的图。"""
    img = cv2.imread(path)
    if img is None:
        return None
    img = img.copy()
    yellow = (img[:, :, 2] > 200) & (img[:, :, 1] > 200) & (img[:, :, 0] < 80)
    cyan = (img[:, :, 0] > 200) & (img[:, :, 1] > 200) & (img[:, :, 2] < 80)
    img[yellow] = (200, 200, 200)          # 黄线压在车牌亮边框上 → 填亮灰
    ys, xs = np.where(cyan)                # 标签是整块矩形的 → 整片填成暗色，别留黑字当笔画
    if len(xs):
        img[ys.min():ys.max() + 1, xs.min():xs.max() + 1] = (35, 35, 35)
    cv2.imwrite(os.path.join(HERE, '_clean_%s' % os.path.basename(path)), img)
    return img
TEXTURES = [(os.path.join(REF, '车牌一.png'), '苏A·B8Q62'),
            (os.path.join(REF, '车牌二.png'), '鄂D·7B5Q2'),
            (os.path.join(REF, '车牌三.png'), '苏A·PL12A')]

FONT_DIR = 'C:/Windows/Fonts'
# 由 font_rank.py 实测排序得出：FZYTK 的汉字最像、simhei 的拉丁最像
CJK_FONTS = ['FZYTK.TTF', 'simhei.ttf', 'msyhbd.ttc', 'dengb.ttf']
LATIN_FONTS = ['simhei.ttf', 'FZYTK.TTF', 'msgothic.ttc', 'arialbd.ttf']
FONT_SIZES = (190,)
# ↑ 只留一档：plate_norm 会按「墨迹高度」把模板归一化，所以 110/150/190 三档渲染出来
#   是同一个东西（只差抗锯齿），实测三档 vs 一档的精度完全一样（A 1/4 B 2/4 部署 3/4），
#   但模板数从 258 降到 128 → OCR 耗时直接减半。


def load_node_block():
    """把 perception_node.py 的 PLATE 段落 exec 进一个命名空间并返回。"""
    src = open(NODE, encoding='utf-8').read()
    i = src.index('# ==== BEGIN PLATE-BLOCK-A')
    j = src.index('# ==== END PLATE-BLOCK-B ====')
    code = src[i:j]
    # 和节点里的 import 对齐：PIL 也要喂进去，否则 plate_draw_label 会走降级分支，
    # 验收图上中文省份就变成 "?"，看着像算法错了其实是画字的问题。
    ns = {'os': os, 'glob': __import__('glob'), 'cv2': cv2, 'np': np,
          '_PILImage': Image, '_PILDraw': ImageDraw, '_PILFont': ImageFont}
    exec(compile(code, 'PLATE-BLOCK', 'exec'), ns)
    return ns


def render_char(ch, font_path, size):
    try:
        f = ImageFont.truetype(font_path, size)
    except Exception:                                                  # noqa: BLE001
        return None
    img = Image.new('L', (size * 3, size * 3), 0)
    ImageDraw.Draw(img).text((size, size), ch, 255, font=f)
    a = np.array(img)
    return a if (a > 127).sum() > 20 else None


def ink_aspect(gray):
    """一块灰度图里「墨迹」外接框的宽高比（用于标定字体的压扁系数）。"""
    p = gray.astype(np.float32)
    lo, hi = np.percentile(p, 12), np.percentile(p, 97)
    if hi - lo < 2:
        return None
    p = np.clip((p - lo) / (hi - lo), 0, 1)
    ys, xs = np.where(p > 0.5)
    if len(ys) < 3:
        return None
    return (xs.max() - xs.min() + 1) / float(ys.max() - ys.min() + 1)


# 真实车牌字形的墨迹宽高比（在 plate_frames 的相机原帧上实测）：
#   汉字 冀0.50 皖0.54 ；拉丁 B0.56 D0.59 H0.57 K0.56 9.57 J0.59 ；「1」0.10
PLATE_FONT_TARGET_AR = {'cjk': 0.52, 'latin': 0.575}


def font_squeeze(font_path, probe, target):
    """求「把这个字体横向压扁到目标宽高比」的系数（每个字体不一样）。"""
    im = render_char(probe, font_path, 190)
    if im is None:
        return 1.0
    a = ink_aspect(im.astype(np.float32) * 255.0)
    if not a:
        return 1.0
    return target / a


def build_font_library(NS):
    """系统字体渲染全字符集 → {字符: [归一化灰度模板, ...]}（这一步只在 Windows 上做）。

    ❗必须横向压扁：真实车牌的字是窄的（宽/高≈0.52，官方 440×140 mm 车牌上
    字高约 90 mm、字距约 55 mm），而系统字体渲染出来是方的（simhei 0.97 / FZYTK 0.69）。
    不压扁的话字体模板和真字根本对不上 —— 实测「冀」的真实字形只能和字体「冀」
    匹配到 0.674，反倒被「皖」的一张糊模板（0.785）顶到第一，
    于是冀B·7H1K9 被读成 皖DHH1K7。
    压扁系数不写死，而是每个字体各探一次（探针字：汉字用「冀」、拉丁用「B」）。
    """
    lib = {}
    for ch in NS['PLATE_CHARSET']:
        cjk = ch in NS['PLATE_PROVINCES']
        fonts = CJK_FONTS if cjk else LATIN_FONTS
        probe = '冀' if cjk else 'B'
        target = PLATE_FONT_TARGET_AR['cjk' if cjk else 'latin']
        variants = []
        for fn in fonts:
            fp = os.path.join(FONT_DIR, fn)
            if not os.path.exists(fp):
                continue
            sq = font_squeeze(fp, probe, target)
            for size in FONT_SIZES:
                m = render_char(ch, fp, size)
                if m is None:
                    continue
                m = cv2.resize(m, (max(2, int(round(m.shape[1] * sq))), m.shape[0]),
                               interpolation=cv2.INTER_AREA)
                g = NS['plate_norm'](m.astype(np.float32) * 255.0)
                if g is not None:
                    variants.append(g)
            break
        if variants:
            lib[ch] = variants
    return lib


def texture_library(NS, ref_lib=None):
    lib = {}
    for path, label in TEXTURES:
        if not os.path.exists(path):
            continue
        img = cv2.cvtColor(np.array(Image.open(path).convert('RGB')), cv2.COLOR_RGB2BGR)
        n = NS['plate_harvest_from_plate'](NS['plate_canonicalize'](img), label, lib,
                                           ref_lib=ref_lib)
        print('   [贴图] %-10s %s → 挖到 %d 字' % (os.path.basename(path), label, n))
    return lib


def frame_library(NS, entries, ref_lib=None):
    lib = {}
    for path, bbox, label in entries:
        img = cv2.imread(path)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        n = NS['plate_harvest_from_plate'](NS['plate_crop'](gray, bbox), label, lib,
                                           ref_lib=ref_lib)
        if n < 7:
            print('   [帧]   %-10s %s → 对齐没过（只挖到 %d 字），跳过' % (label, label, n))
    return lib


def frame_library_img(NS, entries, ref_lib=None):
    """entries: [(img, bbox, label)] —— img 是已洗过的 numpy 图。"""
    lib = {}
    for img, bbox, label in entries:
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        NS['plate_harvest_from_plate'](NS['plate_crop'](gray, bbox), label, lib,
                                       ref_lib=ref_lib)
    return lib


def dump_library(NS, entries, ref_lib=None):
    """从 plate_dump 落盘的相机原帧挖真字：**不给人工框**，让 plate_find 自己定位。

    这是目前最好的标定源（原生像素、同一块车牌多个尺度、不经过 rqt 截图链路）。
    """
    lib = {}
    for fid, label in entries:
        p = os.path.join(DUMP_DIR, fid + '_raw.png')
        img = cv2.imread(p) if os.path.exists(p) else None
        if img is None:
            print('   [dump] %s 缺原帧，跳过' % fid)
            continue
        _g, cands = NS['plate_find'](img)
        if not cands:
            print('   [dump] %s 没定位到车牌，跳过' % fid)
            continue
        bbox, n_glyph, gh = cands[0][0], cands[0][1], cands[0][2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        n = NS['plate_harvest_from_plate'](NS['plate_crop'](gray, bbox), label, lib,
                                          ref_lib=ref_lib)
        print('   [dump] %-10s %s 候选 %d 段 字高 %.0f → 挖到 %d 字'
              % (fid, label, n_glyph, gh, n))
    return lib


def load_new():
    """读用户那三张实跑截图（洗掉黄框/标签）。返回 [(name, img, bbox, truth)]。"""
    out = []
    for name, path, bbox, truth in NEW:
        if not os.path.exists(path):
            continue
        img = clean_overlay(path)
        if img is not None:
            out.append((name, img, bbox, truth))
    return out


def merge(*libs):
    out = {}
    for l in libs:
        for k, v in l.items():
            out.setdefault(k, []).extend(v)
    return out


def read(NS, path, bbox, lib):
    gray = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2GRAY)
    return NS['plate_read'](NS['plate_crop'](gray, bbox), lib)


def read_img(NS, img, bbox, lib):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return NS['plate_read'](NS['plate_crop'](gray, bbox), lib)


def evaluate(NS, tag, get_lib, targets=None):
    print('#### %s' % tag)
    hit = 0
    ts = targets if targets is not None else [(n, p, b, t) for n, p, b, t in FRAMES]
    for name, path, bbox, truth in ts:
        if not os.path.exists(path):
            continue
        t0 = time.time()
        text, scores, diag = read(NS, path, bbox, get_lib(name))
        ok = text == truth
        hit += ok
        print('   %-7s 读出 "%-9s" 真值 "%-9s" %s  %.2fs | %s'
              % (name, text, truth, 'OK' if ok else '×  ', time.time() - t0, diag))
    print('   → %d/%d\n' % (hit, len(ts)))
    return hit, len(ts)


def coverage(NS, lib, real_keys):
    """报告字库覆盖情况：哪些字符有「真字」，哪些只能靠系统字体兜底。"""
    prov = set(NS['PLATE_PROVINCES'])
    latin = set(NS['PLATE_LATIN'])
    rp, rl = prov & real_keys, latin & real_keys
    print('字库覆盖：真字 %d 类（省份 %d / 字母数字 %d）'
          % (len(real_keys), len(rp), len(rl)))
    print('   有真字的省份：%s' % ''.join(sorted(rp)))
    print('   有真字的字母数字：%s' % ''.join(sorted(rl)))
    print('   仅字体兜底：省份 %d 个、字母数字 %d 个\n'
          % (len(prov - rp), len(latin - rl)))


def evaluate_repair(NS, tag, lib):
    """模拟「定位框只框到一半」——实测踩过：皖A·PJ8H1 只框到「8」，右边 H1 在框外。

    把真值框右侧砍掉 22% 再交给 plate_fix_bbox，看它能不能按长宽比先验补回来。
    """
    print('#### %s' % tag)
    cases = [('shot2', SHOT2, (296, 259, 104, 31), '苏D77H8J'),
             ('shot3', SHOT3, (376, 288, 101, 31), '皖APJ8H1'),
             ('vcar近', VCAR, (532, 352, 86, 29), '苏D77H8J')]
    for name, path, bbox, truth in cases:
        if not os.path.exists(path):
            continue
        gray = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2GRAY)
        x, y, w, h = bbox
        short = (x, y, max(10, int(round(w * 0.78))), h)
        fixed = NS['plate_fix_bbox'](gray, short, 7)
        t0, _s0, _d0 = NS['plate_read'](NS['plate_crop'](gray, short), lib, 7, PLATE_MIN)
        t1, _s1, d1 = NS['plate_read'](NS['plate_crop'](gray, fixed), lib, 7, PLATE_MIN)
        print('   %-6s 截短框 %s AR=%.2f → 读出 "%-8s" %s'
              % (name, short, short[2] / float(short[3]), t0, 'OK' if t0 == truth else '×'))
        print('          自愈后 %s AR=%.2f → 读出 "%-8s" %s  (真值 %s)'
              % (fixed, fixed[2] / float(fixed[3]), t1, 'OK' if t1 == truth else '×', truth))
    print()


PLATE_MIN = 0.45


def evaluate_oversize(NS, tag, lib, pad=0.32):
    """模拟「框比车牌大一圈」—— 实测用户截图里就是这个状态（框 116×36，车牌只有 ~87×27）。

    框偏大时车牌自身那圈亮边框会留在归一化图里。老版本会把它当成一个字，
    顶掉「第 1 位」；同时「按面积留前 expect 个」又把面积最小的「1」挤掉 ——
    一进一出，段数正好还是 7，段数校验也拦不住 →
    冀B·7H1K9 被读成 鄂A·B7HK9（就是用户报的那张截图）。
    """
    print('#### %s' % tag)
    cases = []
    for name, path, bbox, truth in FRAMES:          # 手给框 → 人为放大 32%
        if not os.path.exists(path):
            continue
        x, y, w, h = bbox
        big = (max(0, int(round(x - pad * w / 2))), max(0, int(round(y - pad * h / 2))),
               int(round(w * (1 + pad))), int(round(h * (1 + pad))))
        cases.append((name + ' 框放大32%', path, big, truth))
    for fid, truth in DUMP:                          # 落盘帧 → 用 plate_find 原始框就够（它本身就大 1.3~1.6 倍）
        p = os.path.join(DUMP_DIR, fid + '_raw.png')
        frame = cv2.imread(p) if os.path.exists(p) else None
        if frame is None:
            continue
        _g, cands = NS['plate_find'](frame)
        if cands:
            cases.append((fid + ' 原始框', p, cands[0][0], truth))
    hit = 0
    for name, path, bbox, truth in cases:
        gray = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2GRAY)
        txt, _s, _d = NS['plate_read'](NS['plate_crop'](gray, bbox), lib, 7, PLATE_MIN)
        ok = (txt == truth)
        hit += ok
        print('   %-18s %-20s → 读出 "%-8s" %s  (真值 %s)'
              % (name, str(bbox), txt, 'OK' if ok else '×', truth))
    print('   → %d/%d\n' % (hit, len(cases)))


def foreground_ratio(NS, gray, bbox):
    """同一套二值化下，车牌内区前景像素占比 —— 用它量"这张图的笔画还在不在"。"""
    plate = NS['plate_crop'](gray, bbox)
    h = plate.shape[0]
    inner = plate[int(h * 0.15):int(h * 0.85), :]
    bw, _gc = NS['plate_binarize'](inner)
    return float((bw > 0).mean())


def probe_shot_quality(NS):
    """用户截图是「显示 + 截图」链路再采样出来的，笔画被糊掉一半，不能当像素标定源。

    量法：同一个车牌切图，相机原帧的前景占比 0.21~0.28，截图只有 0.06~0.08。
    差 3~4 倍 → 灰度 NCC 自然全 0 分。所以截图只用来**读真值 / 看框位**，
    要复盘算法必须拿相机原帧（节点里的 plate_dump 会把原帧落盘）。
    """
    print('#### J) 为什么用户截图不能当标定源（同一套二值化的前景占比）')
    for name, path, bbox in [('shot2', SHOT2, (296, 259, 104, 31)),
                             ('shot3', SHOT3, (376, 288, 101, 31)),
                             ('vcar近', VCAR, (532, 352, 86, 29))]:
        if not os.path.exists(path):
            continue
        g = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2GRAY)
        print('   相机原帧 %-6s 前景占比 %.3f' % (name, foreground_ratio(NS, g, bbox)))
    for name, path, bbox, _truth in NEW:
        if not os.path.exists(path):
            continue
        img = clean_overlay(path)
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        txt, _s, diag = read_img(NS, img, bbox, {})
        print('   用户截图 %-6s 前景占比 %.3f  （像素被劣化，仅用于读真值）'
              % (name, foreground_ratio(NS, g, bbox)))
    print()


def evaluate_img(NS, tag, lib, news):
    """用「洗过的 numpy 图 + 真值框」评估读数。"""
    print('#### %s' % tag)
    hit = 0
    for name, img, bbox, truth in news:
        text, scores, diag = read_img(NS, img, bbox, lib)
        ok = text == truth
        hit += ok
        print('   %-6s 读出 "%-9s" 真值 "%-9s" %s | %s'
              % (name, text, truth, 'OK' if ok else '×  ', diag))
    print('   → %d/%d\n' % (hit, len(news)))
    return hit, len(news)


def evaluate_detect_img(NS, tag, lib, news):
    """整图跑 plate_detect：这是线上真正走的那条路（定位 + 修框 + OCR）。"""
    print('#### %s' % tag)
    for name, img, bbox, truth in news:
        t0 = time.time()
        dets, _g = NS['plate_detect'](img, lib, 7, 0.45)
        dt = time.time() - t0
        got = [d for d in dets if d['result'] == truth]
        if got:
            d = got[0]
            print('   %-6s 命中 "%s" conf=%.2f 框=%s IoU=%.2f  %d 个候选  %.2fs'
                  % (name, d['result'], d['confidence'], tuple(int(v) for v in d['bbox']),
                     _iou(d['bbox'], bbox), len(dets), dt))
        else:
            print('   %-6s 未命中（候选 %d：%s）  框真值 %s  %.2fs'
                  % (name, len(dets), [x['result'] for x in dets], bbox, dt))
    print()


NEG = [('_p_s02', os.path.join(HERE, '_p_s02.png')),
       ('_p_s09', os.path.join(HERE, '_p_s09.png')),
       ('_p_s15', os.path.join(HERE, '_p_s15.png'))]


def evaluate_detect(NS, tag, lib):
    """整图跑 plate_detect：不人工给框，完全等价于节点里 on_image 那条路。"""
    print('#### %s' % tag)
    for name, path, bbox, truth in FRAMES:
        if not os.path.exists(path):
            continue
        frame = cv2.imread(path)
        t0 = time.time()
        dets, _g = NS['plate_detect'](frame, lib, 7, 0.45)
        dt = time.time() - t0
        got = [d for d in dets if d['result'] == truth]
        if got:
            d = got[0]
            iou = _iou(d['bbox'], bbox)
            print('   %-7s 命中 "%s" conf=%.2f 框 IoU=%.2f  %d 个候选 %.2fs'
                  % (name, d['result'], d['confidence'], iou, len(dets), dt))
        else:
            print('   %-7s 未命中（候选 %d：%s）  %.2fs'
                  % (name, len(dets), [x['result'] for x in dets], dt))
    for name, path in NEG:
        if not os.path.exists(path):
            continue
        frame = cv2.imread(path)
        dets, _g = NS['plate_detect'](frame, lib, 7, 0.45)
        print('   %-7s 误报 %d 个 %s' % (name, len(dets), 'OK' if not dets else '×'))
    print()


def evaluate_detect_dump(NS, tag, lib):
    """整图自动定位，跑本次落盘的相机原帧（不给任何人工框/人工坐标）。"""
    print('#### %s' % tag)
    hit = 0
    for fid, truth in DUMP:
        p = os.path.join(DUMP_DIR, fid + '_raw.png')
        frame = cv2.imread(p) if os.path.exists(p) else None
        if frame is None:
            continue
        t0 = time.time()
        dets, _g = NS['plate_detect'](frame, lib, 7, 0.45)
        dt = time.time() - t0
        got = [d for d in dets if d['result'] == truth]
        hit += bool(got)
        if got:
            d = got[0]
            print('   %-10s 命中 "%s" conf=%.2f  %d 个候选 %.2fs'
                  % (fid, d['result'], d['confidence'], len(dets), dt))
        else:
            print('   %-10s 未命中（候选 %d：%s） 真值 %s  %.2fs'
                  % (fid, len(dets), [x['result'] for x in dets], truth, dt))
    print('   → %d/%d\n' % (hit, len(DUMP)))
    return hit, len(DUMP)


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    uni = aw * ah + bw * bh - inter
    return inter / uni if uni else 0.0


def main():
    NS = load_node_block()
    print('节点车牌模块已加载：%d 个函数' % sum(1 for k in NS if k.startswith('plate_')))
    print('渲染全字符集字库（Windows 才有字体；压扁系数按字体自动标定）…')
    t0 = time.time()
    flib = build_font_library(NS)
    print('字体库 %d 类 / %d 模板，%.1fs\n'
          % (len(flib), sum(len(v) for v in flib.values()), time.time() - t0))

    print('挖官方贴图真字（以字体库为参照做「标签对齐」校验）：')
    tlib = texture_library(NS, ref_lib=flib)
    print('→ 贴图真字 %d 类：%s\n' % (len(tlib), ' '.join(sorted(tlib))))

    evaluate(NS, 'A) 只有系统字体渲染（模拟国赛「完全没见过的车牌」）', lambda n: flib)
    evaluate(NS, 'B) 字体库 + 官方贴图真字（零标定）', lambda n: merge(flib, tlib))

    print('挖本次落盘的相机原帧真字（40 帧里挑 6 帧，真值逐帧放大核对过）：')
    dlib = dump_library(NS, DUMP, ref_lib=merge(flib, tlib))

    # 部署态 = 字体兜底 + 官方贴图真字 + 相机原帧真字
    DEPLOY = merge(flib, tlib, dlib)
    print('\n部署态字库：%d 类 / %d 模板（字体 %d + 贴图 %d + 相机帧 %d）\n'
          % (len(DEPLOY), sum(len(v) for v in DEPLOY.values()),
             sum(len(v) for v in flib.values()), sum(len(v) for v in tlib.values()),
             sum(len(v) for v in dlib.values())))

    # 留出验证：标定只喂了「本次落盘的 6 帧」，这里读的是 4 张不同机位/尺度的旧帧
    evaluate(NS, 'C) 部署态字库，读 4 张【没参与标定】的旧机位帧（跨机位泛化）',
             lambda n: DEPLOY)
    evaluate_detect(NS, 'D) 整图自动定位 + 读数（不人工给框，就是线上跑的那条路）', DEPLOY)
    evaluate_detect_dump(NS, 'E) 整图自动定位，跑本次落盘的 6 帧相机原帧', DEPLOY)

    # ---- 定位框被截断时能不能自愈 ----
    evaluate_repair(NS, 'F) 把框人为截短到 78%，看 plate_fix_bbox 能不能救回来', DEPLOY)

    evaluate_oversize(NS, 'G) 框比车牌大 1.3~1.6 倍时能否读对（用户报的那张就是这种框）', DEPLOY)

    # ---- 用户实跑那三张：只能读真值，不能当像素标定源 ----
    probe_shot_quality(NS)

    coverage(NS, DEPLOY, set(tlib) | set(dlib))

    if '--build' in sys.argv:
        out = os.path.join(HERE, 'plate_glyphs.npz')
        n = NS['plate_library_save'](DEPLOY, out)
        print('已写出 %s（%d 类 / %d 模板，%.0f KB）'
              % (out, len(DEPLOY), n, os.path.getsize(out) / 1024.0))
        back = NS['plate_library_load'](out)
        print('回读校验：%d 类 / %d 模板'
              % (len(back), sum(len(v) for v in back.values())))


if __name__ == '__main__':
    main()
