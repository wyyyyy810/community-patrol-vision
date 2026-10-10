"""中国车牌识别（模块三）—— 定位 → 摆正 → 切字 → 逐字识别 → 输出字符串。

设计要点（每一条都是实测逼出来的，不是拍脑袋）：
  1. 定位用「一排等高等距横向相邻的亮笔画」而不是「暗块」。车牌底是深藏青（灰度 11~30），
     但大片黑色路面也是暗的（13~15），暗块法会把车牌和路面连成一片。
  2. 摆正：用车牌自身的亮边框定内区，再拉伸到固定长宽比 3.17（官方 9.5/3 cm）。
     贴图本身 200x81（AR 2.47）贴在 AR 3.17 的板上 → 横向被拉 1.28 倍，
     所以字库与实拍必须走同一条归一化路径。
  3. 切字：分位数相对阈值（不是 Otsu，实拍字密 + 渲染模糊，直方图没有干净的谷）。
     必须丢掉车牌左右边框细条，否则会顶掉第 1 位、整串错位一格（实测踩过）。
  4. 识别：**灰度归一化互相关**，不是二值 IoU。实拍车牌只有 18~19 px 高，
     二值化后笔画只剩 2~3 px，「D 的竖笔」和「Q 的尾巴」这种差别会被二值化抹掉；
     灰度图上做零均值互相关能把这一档差别留住（实测 D/Q、8/B 的误判就是这么做掉的）。
     匹配时允许 ±3 px 平移 + ±12% 宽度缩放（横向拉伸没完全对齐时也能咬上）。
  5. 字库双轨：
       真字轨 = 从真实车牌图上切出的字（和仿真同一个字体，近乎像素级精确）；
       字体轨 = 系统字体渲染的全字符集（省份汉字 + A-Z + 0-9），负责没见过的字。
     国赛车牌未知 → 必须有字体轨兜底；仿真里的固定车牌 → 真字轨保准确率。
  6. 版面先验：第 1 位必是省份汉字、第 2 位必是字母、后 5 位是字母/数字（无 I、O），
     按位置砍小候选集，误识率明显下降。
"""
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------ 定位参数
STROKE_BANDS = ((50, 175), (58, 175), (66, 175), (74, 175), (82, 175),
                (58, 200), (66, 200))
GLYPH_H_MIN, GLYPH_H_MAX = 5, 40
GLYPH_AR_MIN, GLYPH_AR_MAX = 1.15, 4.5
GLYPH_MIN_AREA = 6
ROW_DY, ROW_DH = 0.40, 0.45
ROW_MAX_GAP = 2.0
ROW_MIN_GLYPHS = 4
SPAN_MIN, SPAN_MAX = 2.30, 9.00
PLATE_AR_MIN, PLATE_AR_MAX = 2.30, 4.30
PLATE_BG_MAX = 62
FRAME_T = 74

# ------------------------------------------------------------------ 识别参数
RENDER_AR = 3.17
GH, CW, PAD = 40, 44, 8
SHIFT_TOL = 3
WIDTH_SCALES = (0.88, 1.0, 1.12)
DOT_MAX_ROWFRAC = 0.40
CHAR_MIN_SCORE = 0.45          # 灰度互相关低于此分 → 该位输出 '?'
BIN_FRAC = 0.62

PROVINCES = '京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川贵云藏陕甘青宁新'
LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
DIGITS = '0123456789'
CHARSET = PROVINCES + DIGITS + LETTERS

FONT_DIR = 'C:/Windows/Fonts'
CJK_FONTS = ['FZYTK.TTF', 'simhei.ttf', 'msyhbd.ttc', 'dengb.ttf']
LATIN_FONTS = ['simhei.ttf', 'FZYTK.TTF', 'msgothic.ttc', 'arialbd.ttf']
FONT_SIZES = (110, 150, 190)


# ================================================================ 定位
def _row_clusters(boxes):
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
            gap = max(rx0 - (x + w), x - rx1)
            if gap > ROW_MAX_GAP * max(hh, h):
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = r, gap
        (rows.append([b]) if best is None else best.append(b))
    return rows


def find_plates(frame):
    """返回 (gray, [(bbox, 字块数, 字高, 灰度带, 底灰)])。"""
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
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
    for c in out:
        if any(abs(c[0][0] - k[0][0]) < 14 and abs(c[0][1] - k[0][1]) < 10 for k in keep):
            continue
        keep.append(c)
    return gray, keep


# ================================================================ 摆正 + 切字
def plate_interior(gray, frame_t=FRAME_T):
    m = (gray > frame_t)
    rows = np.where(m.mean(axis=1) > 0.55)[0]
    if len(rows) < 2:
        return None
    top, bot = int(rows.min()), int(rows.max())
    if bot - top < 6:
        return None
    band = m[top:bot + 1]
    cols = np.where(band.mean(axis=0) > 0.60)[0]
    left, right = (int(cols.min()), int(cols.max())) if len(cols) >= 2 else (0, gray.shape[1] - 1)
    return top, bot, left, right


def canonicalize(plate_gray, out_h=96):
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


def _inner_gray(plate_img):
    g = plate_img if plate_img.ndim == 2 else cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    h, _w = g.shape
    return g[int(h * 0.15):int(h * 0.85), :]


def _binarize(inner):
    """分位数相对阈值二值化，并清掉「横贯整行的亮线」。

    车牌上下边框是贯穿全宽的亮线，会落进字带里（实测「D」的上方、「8」的下方各有一条），
    它是强对比的水平亮带，灰度互相关会死死咬住它，把「D」判成「Q」。
    返回 (二值掩膜, 去掉亮线后的灰度图)——灰度图也要一起去掉，否则归一化时又会把它圈回来。
    """
    p20 = float(np.percentile(inner, 20))
    p99 = float(np.percentile(inner, 99))
    t = p20 + BIN_FRAC * (p99 - p20)
    _t, bw = cv2.threshold(inner, t, 255, cv2.THRESH_BINARY)
    rowfrac = bw.mean(axis=1) / 255.0
    full = np.where(rowfrac > 0.72)[0]
    clean_gray = inner.copy()
    if len(full):
        bw[full, :] = 0
        clean_gray[full, :] = int(np.percentile(inner, 20))
    return cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)), clean_gray


class Segment(object):
    """一个字符段：x 范围、行占有比、二值掩膜、灰度子图。"""

    __slots__ = ('x0', 'x1', 'rowfrac', 'bw', 'gray')

    def __init__(self, x0, x1, rowfrac, bw, gray):
        self.x0, self.x1, self.rowfrac, self.bw, self.gray = x0, x1, rowfrac, bw, gray

    @property
    def width(self):
        return self.x1 - self.x0


def segment_chars(plate_img, expect=7):
    """切字。返回 Segment 列表（含分隔圆点）。

    三步清洗（每一步都是被实测坑出来的）：
      ① 丢掉车牌左右边框：贯穿内区的细亮条（宽 2~7 px、rowfrac≈1.0），
         不清掉会顶掉「第 1 位」，整串车牌号错位一格；
      ② 丢掉分隔圆点（rowfrac < 0.40）；
      ③ 段数与版面先验（7 个字符位）不符时：多了按面积留前 7 个、少了劈最宽的那个。
    """
    inner = _inner_gray(plate_img)
    Hh, W = inner.shape
    bw, gray_clean = _binarize(inner)
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

    clean = []
    for a, b in merged:
        if b - a < 3:
            continue
        if (b - a) <= max(6, int(0.035 * W)) and rf(a, b) >= 0.90:   # 车牌左右边框
            continue
        clean.append([a, b])

    non_dot = [s for s in clean if rf(*s) >= DOT_MAX_ROWFRAC]
    if len(non_dot) > expect:
        area = {id(s): int(bw[:, s[0]:s[1]].sum()) for s in non_dot}
        keep = set(id(s) for s in sorted(non_dot, key=lambda s: -area[id(s)])[:expect])
        clean = [s for s in clean if id(s) in keep or rf(*s) < DOT_MAX_ROWFRAC]
    clean = _split_to_expect(clean, col, bw, expect, rf)

    out = []
    for a, b in clean:
        sub = bw[:, a:b]
        n, _lab, st, _ce = cv2.connectedComponentsWithStats(sub, 8)
        if n > 1:
            hs = st[1:, cv2.CC_STAT_HEIGHT]
            hmax = int(hs.max()) if len(hs) else 0
            keep = [i for i in range(1, n)
                    if st[i, cv2.CC_STAT_HEIGHT] >= 0.45 * hmax
                    and st[i, cv2.CC_STAT_AREA] >= 3]
            if not keep:
                keep = [1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))]
            y0 = min(st[i, cv2.CC_STAT_TOP] for i in keep)
            y1 = max(st[i, cv2.CC_STAT_TOP] + st[i, cv2.CC_STAT_HEIGHT] for i in keep)
            x0 = min(st[i, cv2.CC_STAT_LEFT] for i in keep)
            x1 = max(st[i, cv2.CC_STAT_LEFT] + st[i, cv2.CC_STAT_WIDTH] for i in keep)
        else:
            rows = np.where(sub.any(axis=1))[0]
            if not len(rows):
                continue
            y0, y1, x0, x1 = rows.min(), rows.max() + 1, 0, sub.shape[1]
        out.append(Segment(a + x0, a + x1, rf(a, b), sub[y0:y1, x0:x1],
                           gray_clean[y0:y1, a + x0:a + x1]))
    return out


def _split_to_expect(merged, col, bw, expect, rf):
    """段数不够时劈开最宽的那段（汉字常与后一位字母粘连，实测「苏D」「皖A」都粘）。"""
    def n_non_dot(ms):
        return sum(1 for a, b in ms if rf(a, b) >= DOT_MAX_ROWFRAC)

    guard = 0
    while n_non_dot(merged) < expect and guard < 8:
        wi, widest = -1, -1
        for i, (a, b) in enumerate(merged):
            if rf(a, b) < DOT_MAX_ROWFRAC:
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


# ================================================================ 字库
def norm_glyph(gray_patch, gh=GH, cw=CW, pad=PAD, wx=1.0):
    """把一小块灰度图归一成固定画布上的浮点模板（局部对比度拉伸 + 居中）。"""
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


def sim_max(a, b, tol=SHIFT_TOL):
    """零均值归一化互相关（NCC）的最大值，b 当大图、a 当模板滑一遍。"""
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


def _render(ch, font_path, size):
    try:
        f = ImageFont.truetype(font_path, size)
    except Exception:
        return None
    img = Image.new('L', (size * 3, size * 3), 0)
    ImageDraw.Draw(img).text((size, size), ch, 255, font=f)
    a = np.array(img)
    return a if (a > 127).sum() > 20 else None


def build_font_library(font_dir=FONT_DIR):
    """系统字体渲染全字符集 → {字符: [归一化灰度模板, ...]}。"""
    lib = {}
    for ch in CHARSET:
        fonts = CJK_FONTS if ch in PROVINCES else LATIN_FONTS
        variants = []
        for fn in fonts:
            fp = os.path.join(font_dir, fn)
            if not os.path.exists(fp):
                continue
            for size in FONT_SIZES:
                m = _render(ch, fp, size)
                if m is None:
                    continue
                g = norm_glyph(m.astype(np.float32) * 255.0)
                if g is not None:
                    variants.append(g)
            break
        if variants:
            lib[ch] = variants
    return lib


def _harvest_from_plate(plate_gray, label, lib):
    chars = label.replace('·', '')
    idx = 0
    for s in segment_chars(plate_gray, expect=len(chars)):
        if s.rowfrac < DOT_MAX_ROWFRAC or s.width < 8:
            continue
        if idx >= len(chars):
            break
        g = norm_glyph(s.gray)
        if g is not None:
            lib.setdefault(chars[idx], []).append(g)
        idx += 1


def harvest_texture_library(entries):
    """entries = [(贴图路径, 车牌字符串), ...]：对官方贴图切字建库。"""
    lib = {}
    for path, label in entries:
        if not os.path.exists(path):
            continue
        img = cv2.cvtColor(np.array(Image.open(path).convert('RGB')), cv2.COLOR_RGB2BGR)
        _harvest_from_plate(canonicalize(img), label, lib)
    return lib


def harvest_frame_library(entries):
    """entries = [(帧图片路径, bbox, 车牌字符串), ...]：从实拍帧已知框里切字建库。"""
    lib = {}
    for path, bbox, label in entries:
        img = cv2.imread(path)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _harvest_from_plate(crop_plate(gray, bbox), label, lib)
    return lib


# ================================================================ 逐字识别
LATIN_POS = LETTERS + DIGITS


def classify(gray_patch, pool, lib):
    """在候选字集 pool 里找最像的字，返回 [(字符, 分数), ...]（降序）。"""
    qs = [norm_glyph(gray_patch, wx=w) for w in WIDTH_SCALES]
    qs = [q for q in qs if q is not None]
    if not qs:
        return []
    rank = []
    for ch in pool:
        best = 0.0
        for tpl in lib.get(ch, ()):
            for q in qs:
                best = max(best, sim_max(q, tpl))
        rank.append((ch, best))
    rank.sort(key=lambda t: -t[1])
    return rank


def read_plate(plate_img, lib, expect=7):
    """返回 (车牌字符串, 每位分数, 诊断串)。"""
    chars, scores, diag = [], [], []
    for s in segment_chars(plate_img, expect=expect):
        if s.rowfrac < DOT_MAX_ROWFRAC:
            diag.append('·')
            continue
        if len(chars) == 0:
            pool = PROVINCES
        elif len(chars) == 1:
            pool = LETTERS
        else:
            pool = LATIN_POS
        rank = classify(s.gray, pool, lib)
        ch, sc = (rank[0] if rank else ('?', 0.0))
        if sc < CHAR_MIN_SCORE:
            ch = '?'
        chars.append(ch)
        scores.append(sc)
        diag.append('%s%.2f' % (ch, sc))
    return ''.join(chars), scores, ' '.join(diag)


def merge_library(*libs):
    out = {}
    for l in libs:
        for k, v in l.items():
            out.setdefault(k, []).extend(v)
    return out


def recognize_frame(frame, lib):
    gray, cands = find_plates(frame)
    res = []
    for bbox, n, H, band, bg in cands:
        plate = crop_plate(gray, bbox)
        text, scores, diag = read_plate(plate, lib)
        res.append({'bbox': bbox, 'text': text,
                    'conf': float(min(scores)) if scores else 0.0,
                    'chars': scores, 'diag': diag, 'n_glyph': n, 'glyph_h': H})
    return res
