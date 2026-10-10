"""Step 6: why does the node miss the light in the NEW screenshot? (same thresholds as the node)"""
import cv2
import numpy as np

CROP = (20, 145, 622, 594)          # rqt 窗口里的图像区域（本次截图布局）
FILE = r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-06T15-27-01-667Z-915636b8.png'

V_THRESHOLDS = (60, 75, 90, 105)
MIN_AREA = 300
MIN_WIDTH = 50
AR_MIN, AR_MAX = 1.8, 8.0
STRONG_S, STRONG_V = 120, 50
INSET_X, INSET_Y = 0.04, 0.10

im = cv2.imread(FILE, cv2.IMREAD_COLOR)
print('screenshot', im.shape)
x0, y0, x1, y1 = CROP
img = im[y0:y1, x0:x1].copy()
print('camera area crop', img.shape)
cv2.imwrite('_new_cam_area.png', img)

hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
H, S, V = cv2.split(hsv)
strong = ((S > STRONG_S) & (V > STRONG_V)).astype(np.uint8)
print('strong-colour pixels (S>%d & V>%d): %d' % (STRONG_S, STRONG_V, int(strong.sum())))

# where are the strong pixels?
if strong.sum() > 0:
    ys, xs = np.where(strong > 0)
    print('   their bbox: x %d..%d  y %d..%d' % (xs.min(), xs.max(), ys.min(), ys.max()))
    # sample colours
    for i in range(0, min(len(xs), 400), max(1, len(xs) // 5)):
        b, g, r = img[ys[i], xs[i]]
        print('   px(%d,%d) BGR=(%d,%d,%d) S=%d V=%d H=%d'
              % (xs[i], ys[i], b, g, r, S[ys[i], xs[i]], V[ys[i], xs[i]], H[ys[i], xs[i]] * 2))
else:
    print('   --> NO strong-colour pixel at all: the lit lamp is not saturated enough!')

print()
print('--- dark-bar candidates (same loop as the node) ---')
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
for vt in V_THRESHOLDS:
    binary = (V < vt).astype(np.uint8) * 255
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    rows = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < MIN_AREA:
            continue
        x, y, w, h = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                      int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
        sc = float(strong[y:y + h, x:x + w].sum())
        ar = 1.0 * w / max(1, h)
        ok = (w >= MIN_WIDTH) and (AR_MIN < ar < AR_MAX)
        rows.append((sc, area, x, y, w, h, ar, ok))
    rows.sort(key=lambda r: -r[0])
    print('V<%3d  %d comps' % (vt, len(rows)))
    for r in rows[:4]:
        print('     strongSat=%5d area=%6d box=(%4d,%4d,%4d,%4d) ar=%4.2f  %s'
              % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], 'PASS' if r[7] else 'reject'))

# also: where is the lit lamp by simple row/col profile of strong pixels?
if strong.sum() > 0:
    ys, xs = np.where(strong > 0)
    print()
    print('lit-lamp cluster: x %d..%d (w=%d), y %d..%d (h=%d), centre=(%.0f,%.0f)'
          % (xs.min(), xs.max(), xs.max() - xs.min(), ys.min(), ys.max(), ys.max() - ys.min(),
             xs.mean(), ys.mean()))
