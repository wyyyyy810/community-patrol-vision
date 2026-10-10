"""Offline prototype: tune traffic-light detection on the three real screenshots."""
import cv2
import numpy as np

# The screenshots include the rqt window border; crop the raw camera image area.
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


def analyze(tag, img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    print('=== %s   shape=%s' % (tag, img.shape))

    # 1) candidate pixels: strongly coloured (lamp face is R/Y/G, world is grey/white)
    for sat_thr in (40, 60, 80):
        m = ((s > sat_thr) & (v > 40)).astype(np.uint8) * 255
        print('   sat>%3d : %6d px   (%.2f%%)' % (sat_thr, (m > 0).sum(), 100.0 * (m > 0).sum() / m.size))

    m = ((s > 60) & (v > 40)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    comps = []
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < 20:
            continue
        x, y, w, hh = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP], stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        comps.append((a, x, y, w, hh, cent[i][0], cent[i][1]))
    comps.sort(key=lambda c: -c[0])
    print('   components(%d):' % len(comps))
    for c in comps[:8]:
        print('      area=%6d  box=(%4d,%4d,%3dx%3d)  centre=(%6.1f,%6.1f)' % (c[0], c[1], c[2], c[3], c[4], c[5], c[6]))
    return img, comps, gray


IMGS = {}
for tag in ('RED', 'GREEN', 'YELLOW'):
    im = load(tag)
    _, comps, gray = analyze(tag, im)
    IMGS[tag] = (im, comps, gray)
    cv2.imwrite('_proto_%s_src.png' % tag, im)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    cv2.imwrite('_proto_%s_mask.png' % tag, (((hsv[:, :, 1] > 60) & (hsv[:, :, 2] > 40)) * 255).astype(np.uint8))
