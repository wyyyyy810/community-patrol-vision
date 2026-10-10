"""Step 2: can we separate the three lamp colours by hue / find the off lamps too?"""
import cv2
import numpy as np

CROP = (136, 247, 876, 808)
FILES = {
    'RED': r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-734Z-cf17ae7f.png',
    'GREEN': r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-735Z-80635efb.png',
    'YELLOW': r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-738Z-c00d1bef.png',
}


def load(tag):
    im = cv2.imread(FILES[tag], cv2.IMREAD_COLOR)
    x0, y0, x1, y1 = CROP
    return im[y0:y1, x0:x1].copy()


for tag in ('RED', 'GREEN', 'YELLOW'):
    img = load(tag)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)
    print('=== %s' % tag)

    # A) how much coloured stuff do we get at very low saturation thresholds?
    for st in (10, 20, 30, 45):
        m = ((S > st) & (V > 40))
        nz = int(m.sum())
        mm = cv2.morphologyEx((m.astype(np.uint8) * 255), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
        cnt, lab, stats, cent = cv2.connectedComponentsWithStats(mm, 8)
        big = [(int(stats[i, cv2.CC_STAT_AREA]), int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])) for i in range(1, cnt)
               if stats[i, cv2.CC_STAT_AREA] > 60]
        big.sort(key=lambda c: -c[0])
        print('   S>%2d : %6d px  comps=%d  top=%s' % (st, nz, len(big), big[:4]))

    # B) hue profile of the strongly coloured pixels (the lit lamp)
    m = (S > 60) & (V > 40)
    hs = H[m]
    hs180 = (hs.astype(np.int32) * 2)          # OpenCV H is 0..179 -> degrees
    hist = np.bincount(hs180, minlength=360)
    top10 = np.argsort(hist)[::-1][:10]
    print('   lit px=%d   top hues(deg): %s' % (int(m.sum()), sorted([int(t) for t in top10])))
    for lo, hi, name in ((0, 15, 'red'), (15, 40, 'yellow/orange'), (40, 90, 'green'), (90, 150, 'cyan/blue')):
        frac = 100.0 * np.histogram(hs180, bins=[lo, hi])[0][0] / max(1, hs180.size)
        print('      %-14s %5.1f%%' % (name, frac))
    med_deg = int(np.median(hs180))
    print('   median hue = %d deg, mean S=%.0f, mean V=%.0f' % (med_deg, S[m].mean(), V[m].mean()))
