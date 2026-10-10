"""Step 5: FINAL algorithm - dark housing bar -> 3 strips -> brightest strip -> colour by position."""
import cv2
import numpy as np

CROP = (136, 247, 876, 808)
FILES = {
    'RED': r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-734Z-cf17ae7f.png',
    'GREEN': r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-735Z-80635efb.png',
    'YELLOW': r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-738Z-c00d1bef.png',
}
ORDER = ('RED', 'YELLOW', 'GREEN')


def find_lamp_bar(hsv):
    H, S, V = cv2.split(hsv)
    strong = ((S > 120) & (V > 50)).astype(np.uint8)
    best, best_score = None, -1.0
    for vt in (60, 75, 90, 105):
        m = (V < vt).astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
        cnt, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        for i in range(1, cnt):
            a = int(stats[i, cv2.CC_STAT_AREA])
            if a < 300:
                continue
            x, y, w, h = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                          int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
            ar = 1.0 * w / max(1, h)
            if not (1.8 < ar < 8.0) or w < 50:
                continue
            score = float(strong[y:y + h, x:x + w].sum())
            if score > best_score:
                best_score, best = score, (x, y, w, h)
    return best, best_score


def detect(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)
    bar, score = find_lamp_bar(hsv)
    if bar is None:
        return None
    x, y, w, h = bar
    ix = int(0.04 * w)
    iy = int(0.10 * h)
    x0, y0, ww, hh = x + ix, y + iy, w - 2 * ix, h - 2 * iy
    sw = ww // 3
    stats = []
    for k in range(3):
        sx = x0 + k * sw
        sub_v = V[y0:y0 + hh, sx:sx + sw]
        sub_s = S[y0:y0 + hh, sx:sx + sw]
        sub_h = H[y0:y0 + hh, sx:sx + sw]
        litmask = (sub_s > 120) & (sub_v > 50)
        nlit = int(litmask.sum())
        mh = int(np.median(sub_h[litmask]) * 2) if nlit > 50 else -1
        stats.append((float(sub_v.mean()), nlit, mh))
    vals = [s[0] for s in stats]
    nlits = [s[1] for s in stats]
    k = int(np.argmax(nlits))
    first = max(vals)
    rest = [v for i, v in enumerate(vals) if i != k]
    second = max(rest)
    margin = (first - second) / max(1e-6, (first + second))
    conf = min(0.95, 0.55 + margin)
    return dict(bar=bar, score=score, stats=stats, idx=k, first=first, second=second,
                margin=margin, conf=conf, litpx=nlits[k])


for tag in ('RED', 'GREEN', 'YELLOW'):
    im = cv2.imread(FILES[tag], cv2.IMREAD_COLOR)
    x0, y0, x1, y1 = CROP
    img = im[y0:y1, x0:x1].copy()
    r = detect(img)
    print('=== %s' % tag)
    if r is None:
        print('   NO BAR')
        continue
    print('   bar=%s  strongSat=%.0f' % (r['bar'], r['score']))
    for i, s in enumerate(r['stats']):
        print('      strip%d  meanV=%6.2f  litPx=%5d  medHue=%4d' % (i, s[0], s[1], s[2]))
    print('   -> decided idx=%d = %s   margin=%.3f  conf=%.2f   (expect %s)  %s'
          % (r['idx'], ORDER[r['idx']], r['margin'], r['conf'], tag,
             'OK' if ORDER[r['idx']] == tag else '*** WRONG ***'))

    # annotated output
    vis = img.copy()
    x, y, w, h = r['bar']
    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 255), 2)
    ix, iy = int(0.04 * w), int(0.10 * h)
    bx, by, bw, bh = x + ix, y + iy, w - 2 * ix, h - 2 * iy
    sw = bw // 3
    kk = r['idx']
    cv2.rectangle(vis, (bx + kk * sw, by), (bx + (kk + 1) * sw, by + bh), (0, 255, 0), 2)
    cv2.putText(vis, '%s %.2f' % (ORDER[kk], r['conf']), (x, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imwrite('_proto_out_%s.png' % tag, vis)
