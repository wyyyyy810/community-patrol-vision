"""Test 4: bigger scales + alpha-masked NCC verification (stage 2) to kill false positives."""
import time
import cv2
import numpy as np
import os
import glob
from PIL import Image

TPL_DIRS = [(r'D:\BaiduNetdiskDownload\复赛资料\人员\社区人员', 'COMMUNITY'),
            (r'D:\BaiduNetdiskDownload\复赛资料\人员\非社区人员', 'NON_COMMUNITY')]
FRAMES = ['_p_s02.png', '_p_s09.png', '_p_s15.png']
PROC_SCALE = 0.5
HEIGHTS = [30, 45, 60, 75, 90, 105, 130, 170, 220]     # 处理图高度 → 原图 60~440 px
RAW_MIN = 0.52
NCC_MIN = 0.55


def load_templates():
    out = []
    for d, cls in TPL_DIRS:
        for p in sorted(glob.glob(os.path.join(d, '*.png'))):
            arr = np.array(Image.open(p).convert('RGBA'))
            bgr = arr[:, :, 2::-1].copy()
            alpha = arr[:, :, 3].copy()
            name = os.path.splitext(os.path.basename(p))[0]
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            variants = []
            th0, tw0 = gray.shape[:2]
            for H in HEIGHTS:
                W = max(6, int(round(tw0 * H / th0)))
                variants.append((H, cv2.resize(gray, (W, H), interpolation=cv2.INTER_AREA)))
            out.append((name, cls, gray, alpha, variants))
    return out


TPLS = load_templates()


def masked_ncc(gray_tpl, alpha_tpl, box, gray_img):
    """Pearson 相关系数，只统计贴图不透明像素（忽略白底）。"""
    x, y, w, h = box
    if x < 0 or y < 0 or x + w > gray_img.shape[1] or y + h > gray_img.shape[0]:
        return -1.0
    t = cv2.resize(gray_tpl, (w, h), interpolation=cv2.INTER_AREA)
    a = cv2.resize(alpha_tpl, (w, h), interpolation=cv2.INTER_NEAREST)
    m = a > 25
    if m.sum() < 0.15 * m.size:
        return -1.0
    p = gray_img[y:y + h, x:x + w]
    tv = t[m].astype(np.float32)
    pv = p[m].astype(np.float32)
    tv -= tv.mean()
    pv -= pv.mean()
    d = np.sqrt((tv * tv).sum() * (pv * pv).sum())
    return float((tv * pv).sum() / d) if d > 1e-6 else -1.0


def detect(frame):
    small = cv2.resize(frame, None, fx=PROC_SCALE, fy=PROC_SCALE, interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    raw = []
    for name, cls, gtpl, atpl, variants in TPLS:
        for H, t in variants:
            if t.shape[0] >= g.shape[0] or t.shape[1] >= g.shape[1]:
                continue
            r = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
            _mn, mx, _ml, ml = cv2.minMaxLoc(r)
            if mx >= RAW_MIN:
                raw.append((float(mx), name, cls, gtpl, atpl,
                            ml[0], ml[1], t.shape[1], t.shape[0]))
    raw.sort(key=lambda h: -h[0])
    out = []
    for sc, name, cls, gtpl, atpl, x, y, w, h in raw:
        bx, by, bw, bh = [int(v / PROC_SCALE) for v in (x, y, w, h)]
        n = masked_ncc(gtpl, atpl, (bx, by, bw, bh), cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        if n < NCC_MIN:
            continue
        dup = False
        for o in out:
            ox, oy, ow, oh = o[1]
            if abs((bx + bw / 2) - (ox + ow / 2)) < 0.6 * max(bw, ow) and \
               abs((by + bh / 2) - (oy + oh / 2)) < 0.6 * max(bh, oh):
                dup = True
                break
        if not dup:
            out.append((n, (bx, by, bw, bh), name, cls, sc))
    return out, len(raw)


for f in FRAMES:
    frame = cv2.imread(f, cv2.IMREAD_COLOR)
    t0 = time.time()
    keep, nraw = detect(frame)
    dt = time.time() - t0
    print('\n=== %s   %.2f s   raw=%d  kept=%d' % (f, dt, nraw, len(keep)))
    vis = frame.copy()
    for ncc, (bx, by, bw, bh), name, cls, sc in keep:
        col = (0, 255, 0) if cls == 'COMMUNITY' else (0, 0, 255)
        cv2.rectangle(vis, (bx, by), (bx + bw, by + bh), col, 2)
        cv2.putText(vis, '%s %.2f/%.2f' % (name, sc, ncc), (bx, max(14, by - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
        print('   ncc=%.3f raw=%.2f  %-8s %-14s bbox=(%4d,%4d,%3d,%3d)' % (ncc, sc, name, cls, bx, by, bw, bh))
    cv2.imwrite('_p_det2_%s' % f, vis)
