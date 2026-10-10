# ---------------------------------------------------------------- 车牌识别
# ==== BEGIN PLATE-BLOCK-A（离线测试 plate_offline_test.py 会整段 exec 这段代码，
#      所以模块三的参数与函数都放在这两个标记之间，保证“测的就是线上跑的那份”）====
# ============================== 车牌参数 ==============================
PLATE_STROKE_BANDS = ((50, 175), (58, 175), (66, 175), (74, 175), (82, 175),
                      (58, 200), (66, 200))
PLATE_GLYPH_H_MIN, PLATE_GLYPH_H_MAX = 5, 40
PLATE_GLYPH_AR_MIN, PLATE_GLYPH_AR_MAX = 1.15, 4.5
PLATE_GLYPH_MIN_AREA = 6
PLATE_ROW_DY, PLATE_ROW_DH = 0.40, 0.45
PLATE_ROW_MAX_GAP = 2.0
PLATE_ROW_MIN_GLYPHS = 4
PLATE_SPAN_MIN, PLATE_SPAN_MAX = 2.30, 9.00
PLATE_AR_MIN, PLATE_AR_MAX = 2.30, 4.30
PLATE_BG_MAX = 62
PLATE_FRAME_T = 74

PLATE_RENDER_AR = 3.17          # 官方车牌 9.5/3 cm；贴图会被横向拉到这个比例
PLATE_GH, PLATE_CW, PLATE_PAD = 40, 44, 8
PLATE_SHIFT_TOL = 3
PLATE_WIDTH_SCALES = (0.88, 1.0, 1.12)
PLATE_DOT_ROWFRAC = 0.40        # 行占有比低于此 → 判为分隔圆点
PLATE_MIN_SCORE = 0.45          # 灰度互相关低于此 → 该位输出 '?'
PLATE_BIN_FRAC = 0.62

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


def plate_segments(plate_img, expect=7):
    """切字。三步清洗：
      ① 丢掉车牌左右边框（贯穿内区的细亮条，宽 2~7 px、rowfrac≈1.0），
         不清掉会顶掉「第 1 位」，整串车牌号错位一格；
      ② 丢掉分隔圆点（rowfrac < 0.40）；
      ③ 按连通域裁剪每个字（车牌下边缘的亮带会粘进字块里，不裁就会污染模板）。
    段数与版面先验不符时：多了按面积留前 expect 个、少了劈最宽的那个。
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

    clean = []
    for a, b in merged:
        if b - a < 3:
            continue
        if (b - a) <= max(6, int(0.035 * W)) and rf(a, b) >= 0.90:      # 车牌左右边框
            continue
        clean.append([a, b])

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


def plate_harvest_from_plate(plate_gray, label, lib, min_h=10):
    """从一块已知车牌的图上切出真字，追加进 lib。"""
    chars = label.replace('·', '')
    idx = 0
    for s in plate_segments(plate_gray, expect=len(chars)):
        if s.rowfrac < PLATE_DOT_ROWFRAC or s.width < 8:
            continue
        if idx >= len(chars):
            break
        if s.gray.shape[0] >= min_h:
            g = plate_norm(s.gray)
            if g is not None:
                lib.setdefault(chars[idx], []).append(g)
        idx += 1


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
        if cands:
            plate_harvest_from_plate(plate_crop(gray, cands[0][0]), label, lib)
        else:
            plate_harvest_from_plate(plate_canonicalize(gray), label, lib)
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
# ==== END PLATE-BLOCK-B ====

