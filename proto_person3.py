"""Test 3: multi-template multi-scale person detection, timed, on 3 real frames."""
import time
import cv2
import numpy as np
import os
import glob

TPL_DIRS = [(r'D:\BaiduNetdiskDownload\复赛资料\人员\社区人员', 'COMMUNITY'),
            (r'D:\BaiduNetdiskDownload\复赛资料\人员\非社区人员', 'NON_COMMUNITY')]
FRAMES = ['_p_s02.png', '_p_s09.png', '_p_s15.png']
PROC_SCALE = 0.5
HEIGHTS = [30, 45, 60, 75, 90, 105]      # 处理图（0.5x）里的模板高度 = 原图 60~210 px
SCORE_MIN = 0.60


def load_templates():
    out = []
    for d, cls in TPL_DIRS:
        for p in sorted(glob.glob(os.path.join(d, '*.png'))):
            arr = np.array(cv2.imread(p, cv2.IMREAD_UNCHANGED)) if False else None
            from PIL import Image
            arr = np.array(Image.open(p).convert('RGBA'))
            bgr = arr[:, :, 2::-1].copy()
            name = os.path.splitext(os.path.basename(p))[0]
            gray_full = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            variants = []
            th0, tw0 = gray_full.shape[:2]
            for H in HEIGHTS:
                W = max(6, int(round(tw0 * H / th0)))
                variants.append((H, cv2.resize(gray_full, (W, H), interpolation=cv2.INTER_AREA)))
            out.append((name, cls, variants))
    return out


TPLS = load_templates()
print('templates: %d' % len(TPLS))


def detect(frame):
    small = cv2.resize(frame, None, fx=PROC_SCALE, fy=PROC_SCALE, interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hits = []
    for name, cls, variants in TPLS:
        for H, t in variants:
            if t.shape[0] >= g.shape[0] or t.shape[1] >= g.shape[1]:
                continue
            r = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
            _mn, mx, _ml, ml = cv2.minMaxLoc(r)
            if mx >= SCORE_MIN:
                hits.append((float(mx), name, cls, ml[0], ml[1], t.shape[1], t.shape[0]))
    hits.sort(key=lambda h: -h[0])
    keep = []
    for h in hits:
        sc, name, cls, x, y, w, hh = h
        # 与已保留框中心距离过近则视为同一个目标
        dup = False
        for k in keep:
            if abs((x + w / 2) - (k[3] + k[5] / 2)) < 0.6 * max(w, k[5]) and \
               abs((y + hh / 2) - (k[4] + k[6] / 2)) < 0.6 * max(hh, k[6]):
                dup = True
                break
        if not dup:
            keep.append(h)
    return keep, len(hits)


for f in FRAMES:
    frame = cv2.imread(f, cv2.IMREAD_COLOR)
    t0 = time.time()
    keep, nhit = detect(frame)
    dt = time.time() - t0
    print('\n=== %s  %s   %.2f s   (%d raw hits)' % (f, frame.shape, dt, nhit))
    vis = frame.copy()
    for sc, name, cls, x, y, w, hh in keep:
        X, Y, W, H = [int(v / PROC_SCALE) for v in (x, y, w, hh)]
        col = (0, 255, 0) if cls == 'COMMUNITY' else (0, 0, 255)
        cv2.rectangle(vis, (X, Y), (X + W, Y + H), col, 2)
        cv2.putText(vis, '%s %s %.2f' % (name, cls[:4], sc), (X, max(14, Y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
        print('   %.3f  %-8s %-14s bbox=(%4d,%4d,%3d,%3d)' % (sc, name, cls, X, Y, W, H))
    cv2.imwrite('_p_det_%s' % f, vis)
