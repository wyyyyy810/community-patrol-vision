"""Step 7: FIXED bar selection (density + area bounds + single-lit-strip structure).
Regression on all 4 screenshots (3 old + the new far-distance one)."""
import cv2
import numpy as np

V_THRESHOLDS = (60, 75, 90, 105)
MIN_AREA, MAX_AREA_FRAC = 300, 0.25
MIN_WIDTH = 40
AR_MIN, AR_MAX = 1.5, 7.0
STRONG_S, STRONG_V = 120, 50
INSET_X, INSET_Y = 0.04, 0.10
ORDER = ('RED', 'YELLOW', 'GREEN')

CASES = [
    ('RED   (near)', (136, 247, 876, 808), r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-734Z-cf17ae7f.png', 'RED'),
    ('GREEN (near)', (136, 247, 876, 808), r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-735Z-80635efb.png', 'GREEN'),
    ('YELLOW(near)', (136, 247, 876, 808), r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-738Z-c00d1bef.png', 'YELLOW'),
    ('FAR   (new)', (20, 145, 622, 594), r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-06T15-27-01-667Z-915636b8.png', 'GREEN'),
]


def strip_counts(hsv, bar):
    hs, ss, vs = cv2.split(hsv)
    x, y, w, h = bar
    ix, iy = int(INSET_X * w), int(INSET_Y * h)
    bx, by, bw, bh = x + ix, y + iy, w - 2 * ix, h - 2 * iy
    sw = max(1, bw // 3)
    out = []
    for k in range(3):
        sx = bx + k * sw
        s = ss[by:by + bh, sx:sx + sw]
        v = vs[by:by + bh, sx:sx + sw]
        out.append(int(((s > STRONG_S) & (v > STRONG_V)).sum()))
    return out


def find_bar(hsv, shape, min_lit):
    hs, ss, vs = cv2.split(hsv)
    strong = ((ss > STRONG_S) & (vs > STRONG_V)).astype(np.uint8)
    frame_area = shape[0] * shape[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    cands = []
    for vt in V_THRESHOLDS:
        binary = cv2.morphologyEx((vs < vt).astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < MIN_AREA or area > MAX_AREA_FRAC * frame_area:
                continue
            x, y, w, h = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                          int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
            if w < MIN_WIDTH or not (AR_MIN < 1.0 * w / max(1, h) < AR_MAX):
                continue
            sc = float(strong[y:y + h, x:x + w].sum())
            if sc < min_lit:
                continue
            cands.append((sc / area, sc, area, (x, y, w, h)))
    cands.sort(key=lambda c: -c[0])
    return cands


for name, crop, path, expect in CASES:
    im = cv2.imread(path, cv2.IMREAD_COLOR)
    x0, y0, x1, y1 = crop
    img = im[y0:y1, x0:x1].copy()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    cands = find_bar(hsv, img.shape, 40)
    print('=== %s   %s' % (name, img.shape))
    if not cands:
        print('    no candidate')
        continue
    shown = 0
    decided = None
    for dens, sc, area, bar in cands:
        cnts = strip_counts(hsv, bar)
        mx = max(cnts)
        valid = (mx >= 60) and all(c <= 0.25 * mx for c in cnts if c != mx)
        if shown < 3 or (valid and decided is None):
            print('    dens=%.4f strongSat=%5d area=%6d bar=%s strips=%s %s'
                  % (dens, sc, area, bar, cnts, 'VALID' if valid else 'reject(多格亮/太暗)'))
            shown += 1
        if valid and decided is None:
            decided = (ORDER[int(np.argmax(cnts))], bar, cnts, mx)
    if decided:
        d, bar, cnts, mx = decided
        print('    -> %s   (expect %s)  %s' % (d, expect, 'OK' if d == expect else '*** WRONG ***'))
    else:
        print('    -> nothing valid')
