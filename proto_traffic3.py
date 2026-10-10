"""Step 3: how many lamp blobs survive WITHOUT morphological closing, at low saturation?"""
import cv2
import numpy as np
import os

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
    for st in (12, 15, 20, 25):
        m = ((S > st) & (V > 30)).astype(np.uint8) * 255
        cnt, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
        rows = []
        for i in range(1, cnt):
            a = int(stats[i, cv2.CC_STAT_AREA])
            if a < 25:
                continue
            x, y, w, h = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                          int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
            yy, xx = np.where(lab == i)
            mv = float(V[yy, xx].mean())
            ms = float(S[yy, xx].mean())
            mh = int(np.median(H[yy, xx]) * 2)
            rows.append((x, a, x, y, w, h, mv, ms, mh))
        rows.sort()
        print('   S>%2d  blobs=%d' % (st, len(rows)))
        for r in rows[:6]:
            print('      x=%4d area=%5d box=(%4d,%4d,%3dx%3d) meanV=%5.1f meanS=%5.1f medH=%3d'
                  % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]))

# ground truth: what colour are A's official textures?
print()
print('=== official lamp textures (Windows source) ===')
d = r'D:\BaiduNetdiskDownload\复赛资料\红绿灯\红绿灯图片'
if os.path.isdir(d):
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        t = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        if t is None:
            continue
        if t.ndim == 3 and t.shape[2] == 4:
            b, g, r, a = cv2.split(t)
            op = a > 25
            px = cv2.merge([b, g, r])[op]
            cov = 100.0 * op.sum() / a.size
        else:
            px = t.reshape(-1, 3)
            cov = 100.0
        if px.size == 0:
            print('   %-16s empty' % f)
            continue
        hsvp = cv2.cvtColor(px.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV).reshape(-1, 3)
        print('   %-16s cov=%5.1f%%  medH=%3d  meanS=%5.1f  meanV=%5.1f'
              % (f, cov, int(np.median(hsvp[:, 0]) * 2), hsvp[:, 1].mean(), hsvp[:, 2].mean()))
else:
    print('   (dir not found)', d)
