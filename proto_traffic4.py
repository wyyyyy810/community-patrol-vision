"""Step 4: is the lamp HOUSING detectable as a dark horizontal bar? (much more robust than saturation)"""
import cv2
import numpy as np

CROP = (136, 247, 876, 808)
FILES = {
    'RED': r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-734Z-cf17ae7f.png',
    'GREEN': r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-735Z-80635efb.png',
    'YELLOW': r'C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-738Z-c00d1bef.png',
}

for tag in ('RED', 'GREEN', 'YELLOW'):
    im = cv2.imread(FILES[tag], cv2.IMREAD_COLOR)
    x0, y0, x1, y1 = CROP
    img = im[y0:y1, x0:x1].copy()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)
    print('=== %s' % tag)
    print('   frame V stats: min=%d med=%d max=%d' % (V.min(), int(np.median(V)), V.max()))
    for vt in (60, 80, 100, 120, 150):
        m = (V < vt).astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
        cnt, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
        rows = []
        for i in range(1, cnt):
            a = int(stats[i, cv2.CC_STAT_AREA])
            x, y, w, h = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                          int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
            rows.append((a, x, y, w, h, (1.0 * w / max(1, h))))
        rows.sort(key=lambda r: -r[0])
        keep = [r for r in rows if r[0] > 400 and 1.8 < r[5] < 8.0 and r[3] > 80]
        print('   V<%3d  comps=%d  wide-bar candidates=%s' % (vt, len(rows), [(r[1], r[2], r[3], r[4]) for r in keep[:3]]))

    # visual crop for inspection
    cv2.imwrite('_proto_ctx_%s.png' % tag, cv2.resize(img[50:210, 240:700], (460 * 2, 160 * 2), interpolation=cv2.INTER_NEAREST))
