"""车牌识别原型（模块三）：定位 → 摆正 → 切字 → 逐字匹配。

全部参数来自实测，不是猜的：
  * 近景车牌（车距 ~0.4 m）在 640x480 画面里 82x25 px，长宽比 3.28 ≈ 官方 9.5/3 = 3.17；
  * 官方贴图是 200x81（AR 2.47），渲染出来却是 AR 3.17 —— 说明贴图被横向拉伸了 1.28 倍，
    所以建字符库时必须先把 200x81 预拉伸到 3.17，否则模板和实拍对不上；
  * 车牌底色深藏青（灰度 11~30）、车身中蓝（33~75）、路面黑（13~15）：单靠"暗块"分不开
    （大片黑路面会把车牌吞掉），所以定位靠**一排等高等距横向相邻的亮笔画**；
  * 车牌上的字是亮笔画（灰度 85~110），字高占板高 65%，字宽/字高 ≈ 0.41。
"""
import glob
import os

import cv2
import numpy as np
from PIL import Image

# ------------------------------------------------------------------ 定位参数
STROKE_BANDS = ((50, 175), (58, 175), (66, 175), (74, 175), (82, 175),
                (58, 200), (66, 200))       # 多灰度带并联，提高召回
GLYPH_H_MIN, GLYPH_H_MAX = 5, 36
GLYPH_AR_MIN, GLYPH_AR_MAX = 1.15, 4.5      # 字块 高/宽
GLYPH_MIN_AREA = 6
ROW_DY, ROW_DH = 0.40, 0.45                 # 同行：中心高差 / 字高、高度相对差
ROW_MAX_GAP = 2.0                           # 同行：横向净间隙上限 / 字高
ROW_MIN_GLYPHS = 4
SPAN_MIN, SPAN_MAX = 2.30, 9.00             # 字行总宽 / 字高
PLATE_AR_MIN, PLATE_AR_MAX = 2.30, 4.30     # 实测 3.28（官方 3.17）
PLATE_BG_MAX = 62                           # 框内非笔画像素中位灰度上限（暗底）

# ------------------------------------------------------------------ 识别参数
RENDER_AR = 3.17                            # 实拍车牌长宽比（官方 9.5/3）
GLYPH_CANVAS = 64
GLYPH_H = 64
SHIFT_TOL = 4                               # 逐字匹配允许的位移（像素）
DOT_MAX_ROWFRAC = 0.40                      # 行占有比低于此 → 判为分隔圆点
CHAR_MIN_SCORE = 0.45                       # 低于此分 → 该位输出 '?'
BIN_FRAC = 0.62                             # 二值化阈值 = p20 + frac*(p99-p20)

REF_DIRS = [(r'D:\BaiduNetdiskDownload\复赛资料\车辆识别',
             ['车牌一.png', '车牌二.png', '车牌三.png'])]
REF_LABELS = {'车牌一.png': '苏A·B8Q62', '车牌二.png': '鄂D·7B5Q2', '车牌三.png': '苏A·PL12A'}


# ================================================================ 定位
def _row_clusters(boxes):
    """字块聚成字行：基线对齐 + 字高相近 + **横向相邻**。

    只按 y 对齐不够：画面左右两头各有一个字块时会被错误地并成一行
    （实测近景车牌的 5 个字块跟 170 px 外的背景亮块并到一起，span/H 冲到 24）。
    """
    rows = []
    for b in sorted(boxes, key=lambda t: t[0]):
        x, y, w, h = b[0], b[1], b[2], b[3]
        cy = y + h / 2.0
        best, best_gap = None, None
        for r in rows:
            hh = float(np.median([t[3] for t in r]))
            cc = float(np.mean([t[1] + t[3] / 2.0 for t in r]))
            if abs(cy - cc) > ROW_DY * max(hh, h) or abs(h - hh) > ROW_DH * max(hh, h):
                continue
            rx0 = min(t[0] for t in r)
            rx1 = max(t[0] + t[2] for t in r)
            gap = max(rx0 - (x + w), x - rx1)          # 横向净间隙（负=重叠）
            if gap > ROW_MAX_GAP * max(hh, h):
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = r, gap
        if best is None:
            rows.append([b])
        else:
            best.append(b)
    return rows


def find_plates(frame):
    """返回 (gray, [(bbox, 字块数, 字高, 灰度带, 底灰)])。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    H_img, W_img = gray.shape
    out = []
    for lo, hi in STROKE_BANDS:
        m = ((gray > lo) & (gray < hi)).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 1), np.uint8))
        n, _lab, st, _ce = cv2.connectedComponentsWithStats(m, 8)
        boxes = []
        for i in range(1, n):
            x, y, w, h, a = st[i, 0], st[i, 1], st[i, 2], st[i, 3], st[i, 4]
            if not (GLYPH_H_MIN <= h <= GLYPH_H_MAX) or a < GLYPH_MIN_AREA:
                continue
            if not (GLYPH_AR_MIN <= h / float(max(1, w)) <= GLYPH_AR_MAX):
                continue
            boxes.append((x, y, w, h, a))
        for row in _row_clusters(boxes):
            if len(row) < ROW_MIN_GLYPHS:
                continue
            H = float(np.median([t[3] for t in row]))
            x0 = min(t[0] for t in row)
            x1 = max(t[0] + t[2] for t in row)
            if not (SPAN_MIN <= (x1 - x0) / H <= SPAN_MAX):
                continue
            px0 = max(0, int(round(x0 - 0.55 * H)))
            px1 = min(W_img - 1, int(round(x1 + 0.30 * H)))
            py0 = max(0, int(round(min(t[1] for t in row) - 0.30 * H)))
            py1 = min(H_img - 1, int(round(max(t[1] + t[3] for t in row) + 0.32 * H)))
            w, h = px1 - px0, py1 - py0
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
    for c in out:                       # 同一块车牌被多个灰度带命中 → 去重
        if any(abs(c[0][0] - k[0][0]) < 14 and abs(c[0][1] - k[0][1]) < 10 for k in keep):
            continue
        keep.append(c)
    return gray, keep


# ================================================================ 摆正 + 切字
FRAME_T = 74          # 车牌亮边框（含字）的灰度下限；车身最高约 70，用它把板外切掉


def plate_interior(gray, frame_t=FRAME_T):
    """用车牌自身的亮边框把内区框出来，返回 (top, bot, left, right)。

    为什么必须这么做：车牌框是从字行外扩出来的，上下会多带 2~6 px 的车身/保险杠。
    直接对内区做 Otsu，会把灰 50~70 的车身也算成"亮"的一类，列投影糊成一片
    （实测近景车牌因此只切出 1 段）。车牌的边框本身是贯穿全宽的亮线，拿它定位最稳。
    """
    m = (gray > frame_t)
    rows = np.where(m.mean(axis=1) > 0.55)[0]        # 横贯全宽的亮行 = 上下边框
    if len(rows) < 2:
        return None
    top, bot = int(rows.min()), int(rows.max())
    if bot - top < 6:
        return None
    band = m[top:bot + 1]
    cols = np.where(band.mean(axis=0) > 0.60)[0]     # 贯穿板高的亮列 = 左右边框
    left, right = (int(cols.min()), int(cols.max())) if len(cols) >= 2 else (0, gray.shape[1] - 1)
    return top, bot, left, right


def canonicalize(plate_gray, out_h=96):
    """把车牌统一成标准图：先用亮边框定内区，再拉伸到固定尺寸。

    字库和实拍走**同一条**归一化路径，这样"字符在标准图里的位置"两边一致，
    后面可以直接用版面先验（7 个字符位）去切字，不依赖每一帧都切得干净。
    """
    if plate_gray.ndim == 3:
        plate_gray = cv2.cvtColor(plate_gray, cv2.COLOR_BGR2GRAY)
    p99 = float(np.percentile(plate_gray, 99))
    p20 = float(np.percentile(plate_gray, 20))
    inner = plate_interior(plate_gray, frame_t=max(64.0, p20 + 0.45 * (p99 - p20)))
    if inner is not None:
        t, b, l, r = inner
        plate_gray = plate_gray[max(0, t):b + 1, max(0, l):r + 1]
    return cv2.resize(plate_gray, (int(round(out_h * RENDER_AR)), out_h),
                      interpolation=cv2.INTER_CUBIC)


def crop_plate(gray, bbox, out_h=96):
    x, y, w, h = bbox
    pad = 0.10
    x0 = max(0, int(x - pad * w))
    x1 = min(gray.shape[1], int(x + w + pad * w))
    y0 = max(0, int(y - pad * h))
    y1 = min(gray.shape[0], int(y + h + pad * h))
    return canonicalize(gray[y0:y1, x0:x1], out_h)


def segment_chars(plate_img):
    """在归一化车牌图上切字，返回 [(x0, x1, 行占有比, 位图)]。

    先用**行中位数**把字带框出来：车牌底色很暗（行中位数 15~30），
    而车牌上下边框和板外的车身都更亮。固定按百分比裁会切到车身，
    导致 Otsu 把车身也当成"亮"的一类，列投影全糊（实测踩过）。
    """
    g = plate_img
    if g.ndim == 3:
        g = cv2.cvtColor(g, cv2.COLOR_BGR2GRAY)
    h, _w = g.shape
    inner = g[int(h * 0.15):int(h * 0.85), :]
    # 分位数相对阈值：实拍车牌字太密 + 渲染模糊，直方图没有干净的谷，Otsu 会切到背景
    p20 = float(np.percentile(inner, 20))
    p99 = float(np.percentile(inner, 99))
    t = p20 + BIN_FRAC * (p99 - p20)
    _t, bw = cv2.threshold(inner, t, 255, cv2.THRESH_BINARY)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    col = (bw > 0).sum(axis=0)
    thr = max(1, int(0.06 * inner.shape[0]))
    segs, s = [], None
    for i, v in enumerate(col):
        if v > thr and s is None:
            s = i
        elif v <= thr and s is not None:
            segs.append([s, i])
            s = None
    if s is not None:
        segs.append([s, len(col)])
    Hh = inner.shape[0]
    merged = []
    for a, b in segs:                    # 合并被笔画间隙切碎的字
        if merged and a - merged[-1][1] <= 0.10 * Hh:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        if b - a < 2:
            continue
        sub = bw[:, a:b]
        rows = np.where(sub.any(axis=1))[0]
        rowfrac = (rows.max() - rows.min() + 1) / float(Hh)
        out.append((a, b, rowfrac, sub))
    return out


# ================================================================ 字库
def norm_glyph(binimg, canvas=GLYPH_CANVAS, gh=GLYPH_H):
    ys, xs = np.where(binimg > 0)
    if len(ys) == 0:
        return None
    c = binimg[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = c.shape
    W = max(2, int(round(w * gh / float(h))))
    r = cv2.resize(c, (W, gh), interpolation=cv2.INTER_NEAREST)
    canvas_img = np.zeros((gh, canvas), np.uint8)
    if W <= canvas:
        x = (canvas - W) // 2
        canvas_img[:, x:x + W] = r
    else:
        st = (W - canvas) // 2
        canvas_img[:] = r[:, st:st + canvas]
    return canvas_img


def stretch_to_render_ar(im):
    """官方贴图 AR=2.47，实拍渲染 AR=3.17 → 先横向预拉伸，让字库与实拍同比例。"""
    h, _w = im.shape[:2]
    return cv2.resize(im, (int(round(h * RENDER_AR)), h), interpolation=cv2.INTER_CUBIC)


def load_glyph_library(dirs=REF_DIRS):
    """从官方车牌贴图切出高清单字，建 {字符: [位图, ...]}。"""
    lib = {}
    for d, files in dirs:
        for fn in files:
            p = os.path.join(d, fn)
            if not os.path.exists(p):
                continue
            im = cv2.cvtColor(np.array(Image.open(p).convert('RGB')), cv2.COLOR_RGB2BGR)
            plate = stretch_to_render_ar(im)
            chars = REF_LABELS[fn].replace('·', '')
            idx = 0
            for a, b, rowfrac, sub in segment_chars(plate):
                if rowfrac < DOT_MAX_ROWFRAC:
                    continue                      # 分隔圆点不占字符位
                if idx >= len(chars):
                    break
                gl = norm_glyph(sub)
                if gl is not None:
                    lib.setdefault(chars[idx], []).append(gl)
                idx += 1
    return lib


# ================================================================ 逐字识别
def _iou_shift(a, b, tol=SHIFT_TOL):
    best = 0.0
    A = (a > 0)
    for dy in range(-tol, tol + 1):
        for dx in range(-tol, tol + 1):
            B = np.roll(np.roll(b > 0, dy, axis=0), dx, axis=1)
            inter = np.logical_and(A, B).sum()
            union = np.logical_or(A, B).sum()
            if union:
                best = max(best, inter / float(union))
    return best


def recognize_plate(plate_img, lib):
    """返回 (车牌号, 每位分数, 诊断串)。"""
    chars, scores, diag = [], [], []
    for a, b, rowfrac, sub in segment_chars(plate_img):
        if rowfrac < DOT_MAX_ROWFRAC:
            diag.append('·')                       # 分隔圆点
            continue
        gl = norm_glyph(sub)
        if gl is None:
            continue
        rank = sorted(((_iou_shift(gl, t), c) for c, ts in lib.items() for t in ts),
                      key=lambda t: -t[0])
        sc, ch = (rank[0] if rank else (0.0, '?'))
        if sc < CHAR_MIN_SCORE:
            ch = '?'
        chars.append(ch)
        scores.append(sc)
        diag.append('%s%.2f' % (ch, sc))
    return ''.join(chars), scores, ' '.join(diag)


# ================================================================ 主流程
def recognize_frame(frame, lib):
    gray, cands = find_plates(frame)
    res = []
    for bbox, n, H, band, bg in cands:
        plate = crop_plate(gray, bbox)
        text, scores, diag = recognize_plate(plate, lib)
        res.append({'bbox': bbox, 'text': text,
                    'conf': float(min(scores)) if scores else 0.0,
                    'chars': scores, 'diag': diag,
                    'n_glyph': n, 'glyph_h': H, 'band': band, 'bg': bg})
    return res


def main():
    lib = load_glyph_library()
    print('字库 %d 类：%s' % (len(lib), ' '.join('%s x%d' % (c, len(v)) for c, v in sorted(lib.items()))))
    for path in ['_v_car19.png'] + sorted(glob.glob('_p_s*.png')):
        if not os.path.exists(path):
            continue
        frame = cv2.imread(path)
        rs = recognize_frame(frame, lib)
        print('=== %-13s %s  车牌 %d' % (path, frame.shape[:2], len(rs)))
        for r in rs:
            x, y, w, h = r['bbox']
            print('     bbox=(%3d,%3d,%3dx%-3d) 号="%s" 置信=%.2f 字块=%d 字高=%.0f | %s'
                  % (x, y, w, h, r['text'], r['conf'], r['n_glyph'], r['glyph_h'], r['diag']))
            vis = frame.copy()
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(vis, '%s %.2f' % (r['text'], r['conf']), (x, max(14, y - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imwrite('_pl_%s_%d_%d.png' % (path.replace('.png', ''), x, y), vis)
            cv2.imwrite('_plcrop_%s_%d_%d.png' % (path.replace('.png', ''), x, y),
                        cv2.resize(crop_plate(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), r['bbox']),
                                   None, fx=4, fy=4, interpolation=cv2.INTER_LANCZOS4))


if __name__ == '__main__':
    main()
