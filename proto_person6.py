# -*- coding: utf-8 -*-
"""验证新版人偶检测：best-per-template + IoU NMS + 白底占比过滤 + 长宽比过滤"""
import os
import glob
import time

import cv2
import numpy as np
from PIL import Image

TL = [(r'D:\BaiduNetdiskDownload\复赛资料\人员\社区人员', 'COMMUNITY'),
      (r'D:\BaiduNetdiskDownload\复赛资料\人员\非社区人员', 'NON_COMMUNITY')]
PERSON_SCALE = 0.5
PERSON_HEIGHTS = (30, 45, 60, 75, 90, 105, 130)


def load():
    out = []
    for d, cls in TL:
        for p in sorted(glob.glob(os.path.join(d, '*.png'))):
            arr = np.array(Image.open(p).convert('RGBA'))
            bgr = arr[:, :, 2::-1].copy()
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            h0, w0 = gray.shape
            vs = []
            for H in PERSON_HEIGHTS:
                W = max(6, int(round(w0 * H / h0)))
                vs.append(cv2.resize(gray, (W, H), interpolation=cv2.INTER_AREA))
            out.append((os.path.splitext(os.path.basename(p))[0], cls, vs, w0 / h0))
    return out


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0, x2 - x1), max(0, y2 - y1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def detect(frame, tpls, thr=0.60, iou_thr=0.30, white_min=0.18,
           ar_lo=1.2, ar_hi=8.0, min_h=40):
    small = cv2.resize(frame, None, fx=PERSON_SCALE, fy=PERSON_SCALE,
                       interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    cand = []
    for name, cls, vs, _ar in tpls:
        best = None
        for tpl in vs:
            if tpl.shape[0] >= gray.shape[0] or tpl.shape[1] >= gray.shape[1]:
                continue
            r = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
            _mn, mx, _ml, ml = cv2.minMaxLoc(r)
            if mx >= thr and (best is None or mx > best[0]):
                best = (float(mx), ml[0], ml[1], tpl.shape[1], tpl.shape[0])
        if best is None:
            continue
        sc, x, y, w, h = best
        cand.append([sc, name, cls, x, y, w, h])
    cand.sort(key=lambda c: -c[0])

    keep = []
    dropped_ar = dropped_white = 0
    for c in cand:
        sc, name, cls, x, y, w, h = c
        ho, wo = h / PERSON_SCALE, w / PERSON_SCALE
        if ho < min_h:
            continue
        ar = ho / max(1.0, wo)
        if not (ar_lo <= ar <= ar_hi):
            dropped_ar += 1
            continue
        patch = gray[y:y + h, x:x + w]
        wf = float((patch > 200).mean()) if patch.size else 0.0
        if wf < white_min:
            dropped_white += 1
            continue
        if any(iou((x, y, w, h), (k[3], k[4], k[5], k[6])) > iou_thr for k in keep):
            continue
        keep.append(c)
    return keep, dropped_ar, dropped_white


T = load()
print('templates:', len(T))
for f in ['_p_s02.png', '_p_s09.png', '_p_s15.png']:
    if not os.path.exists(f):
        print('skip', f)
        continue
    fr = cv2.imread(f)
    t0 = time.time()
    keep, da, dw = detect(fr, T)
    print('=== %s  %.2fs  kept=%d  (ar过滤掉 %d, 白底过滤掉 %d)'
          % (f, time.time() - t0, len(keep), da, dw))
    vis = fr.copy()
    for sc, name, cls, x, y, w, h in keep:
        X, Y, W, H = [int(round(v / PERSON_SCALE)) for v in (x, y, w, h)]
        col = (255, 128, 0) if cls == 'COMMUNITY' else (0, 0, 255)
        cv2.rectangle(vis, (X, Y), (X + W, Y + H), col, 2)
        cv2.putText(vis, '%s %.2f' % (name, sc), (max(0, X), max(14, Y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 2)
        print('   %.3f %-10s %-14s bbox=(%d,%d,%dx%d) H=%d ar=%.1f'
              % (sc, name, cls, X, Y, W, H, H, H / max(1, W)))
    cv2.imwrite('_v6_' + f, vis)
print('saved _v6_*.png')
