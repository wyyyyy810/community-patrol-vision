"""Feasibility test: can the 18 official textures be matched against a real camera frame?"""
import cv2
import numpy as np
import os
import glob
from PIL import Image            # OpenCV 读不了中文路径，模板用 PIL 读

TPL_DIRS = [(r'D:\BaiduNetdiskDownload\复赛资料\人员\社区人员', 'COMMUNITY'),
            (r'D:\BaiduNetdiskDownload\复赛资料\人员\非社区人员', 'NON_COMMUNITY')]
FRAME = r'C:\Users\wyyyyy\WorkBuddy\2026-09-27-16-11-06\_p_s09.png'   # 相机画面（3 个人偶）
HEIGHTS = [60, 90, 120, 150, 180, 210]


def load_templates():
    out = []
    for d, cls in TPL_DIRS:
        for p in sorted(glob.glob(os.path.join(d, '*.png'))):
            arr = np.array(Image.open(p).convert('RGBA'))
            bgr = arr[:, :, 2::-1].copy()               # RGB -> BGR
            alpha = arr[:, :, 3].copy()
            out.append((os.path.splitext(os.path.basename(p))[0], cls, bgr, alpha))
    return out


tpls = load_templates()
print('templates loaded: %d' % len(tpls))
for name, cls, bgr, a in tpls[:3]:
    print('   %-6s %-14s %s  opaque=%5.1f%%' % (name, cls, bgr.shape, 100.0 * (a > 25).mean()))

frame = cv2.imread(FRAME, cv2.IMREAD_COLOR)
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
print('frame', frame.shape)

hits = []
for name, cls, bgr, alpha in tpls:
    th0, tw0 = bgr.shape[:2]
    for H in HEIGHTS:
        s = 1.0 * H / th0
        W = max(8, int(round(tw0 * s)))
        t = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA)
        a = cv2.resize(alpha, (W, H), interpolation=cv2.INTER_NEAREST)
        if (a > 25).sum() < 0.2 * a.size:
            continue
        tg = cv2.cvtColor(t, cv2.COLOR_BGR2GRAY)
        r = cv2.matchTemplate(gray, tg, cv2.TM_CCORR_NORMED, mask=(a > 25).astype(np.uint8))
        _mn, mx, _ml, ml = cv2.minMaxLoc(r)
        hits.append((mx, name, cls, ml[0], ml[1], W, H))

hits.sort(key=lambda h: -h[0])
print()
print('top 15 matches (score, template, class, x, y, w, h):')
for h in hits[:15]:
    print('   %.3f  %-6s %-14s  at (%4d,%4d)  %3dx%3d' % h)

# draw the best non-overlapping ones
vis = frame.copy()
used = []
for sc, name, cls, x, y, w, h in hits:
    if sc < 0.45:
        break
    if any(abs(x - ux) < 40 and abs(y - uy) < 60 for ux, uy in used):
        continue
    used.append((x, y))
    color = (0, 255, 0) if cls == 'COMMUNITY' else (0, 0, 255)
    cv2.rectangle(vis, (x, y), (x + w, y + h), color, 3)
    cv2.putText(vis, '%s %s %.2f' % (cls[:4], name, sc), (x, max(16, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    print('   KEEP %.3f %s %s at (%d,%d) %dx%d' % (sc, cls, name, x, y, w, h))
cv2.imwrite('_p_match.png', vis)
