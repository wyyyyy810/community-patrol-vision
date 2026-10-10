"""Test 2: what do the transparent areas contain, and does whole-rect matching work?"""
import cv2
import numpy as np
import os
import glob
from PIL import Image

D = r'D:\BaiduNetdiskDownload\复赛资料\人员\社区人员\1.png'
arr = np.array(Image.open(D).convert('RGBA'))
rgb, a = arr[:, :, :3], arr[:, :, 3]
tr = rgb[a < 25]
print('template 1.png size', arr.shape, ' opaque=%.1f%%' % (100.0 * (a > 25).mean()))
print('transparent-area RGB: mean=%s  min=%s  max=%s  unique~%d'
      % (tr.mean(0).round(1), tr.min(0), tr.max(0), len(np.unique(tr.reshape(-1, 3), axis=0))))
op = rgb[a > 25]
print('opaque-area RGB:      mean=%s' % (op.mean(0).round(1),))

# bounding box of the opaque region
ys, xs = np.where(a > 25)
print('opaque bbox: x %d..%d  y %d..%d  (w=%d h=%d  ar=%.2f)'
      % (xs.min(), xs.max(), ys.min(), ys.max(), xs.max() - xs.min() + 1,
         ys.max() - ys.min() + 1, (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1)))

# ---- match the FULL rect (all pixels, sim-like) with CCOEFF_NORMED
TL = [(r'D:\BaiduNetdiskDownload\复赛资料\人员\社区人员', 'COMMUNITY'),
      (r'D:\BaiduNetdiskDownload\复赛资料\人员\非社区人员', 'NON_COMMUNITY')]
frame = cv2.imread(r'C:\Users\wyyyyy\WorkBuddy\2026-09-27-16-11-06\_p_s09.png', cv2.IMREAD_COLOR)
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
print('\nframe', frame.shape)

hits = []
for d, cls in TL:
    for p in sorted(glob.glob(os.path.join(d, '*.png'))):
        arr = np.array(Image.open(p).convert('RGBA'))
        bgr = arr[:, :, 2::-1].copy()
        name = os.path.splitext(os.path.basename(p))[0]
        th0, tw0 = bgr.shape[:2]
        for H in (60, 90, 120, 150, 180, 210):
            W = max(10, int(round(tw0 * H / th0)))
            t = cv2.cvtColor(cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            r = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
            _mn, mx, _ml, ml = cv2.minMaxLoc(r)
            hits.append((float(mx), name, cls, ml[0], ml[1], W, H))
hits.sort(key=lambda h: -h[0])
print('top 12 full-rect CCOEFF_NORMED:')
for h in hits[:12]:
    print('   %.3f  %-6s %-14s at (%4d,%4d) %3dx%3d' % h)

vis = frame.copy()
used = []
for sc, name, cls, x, y, w, h in hits:
    if sc < 0.4:
        break
    if any(abs(x - ux) < 0.5 * w and abs(y - uy) < 0.5 * h for ux, uy, uw, uh in used):
        continue
    used.append((x, y, w, h))
    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 3)
    cv2.putText(vis, '%s %.2f' % (name, sc), (x, max(16, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    print('   KEEP %.3f %s %s at (%d,%d) %dx%d' % (sc, cls, name, x, y, w, h))
cv2.imwrite('_p_match2.png', vis)
