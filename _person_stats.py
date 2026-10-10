import glob, os
import numpy as np
from PIL import Image

base = r'D:\BaiduNetdiskDownload\复赛资料\人员'
rows = []
for cls, d in (('居民', '社区人员'), ('访客', '非社区人员')):
    for p in sorted(glob.glob(os.path.join(base, d, '*.png'))):
        im = Image.open(p).convert('RGBA')
        a = np.array(im)
        rgb = a[:, :, :3].astype(np.float32)
        al = a[:, :, 3]
        m = al > 128
        gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        v = gray[m]
        h, w = np.where(m)[0], np.where(m)[1]
        H = h.max() - h.min() + 1
        W = w.max() - w.min() + 1
        rows.append((cls, os.path.basename(p), float(v.mean()),
                     float((v < 60).mean()), float(H / W)))
rows.sort(key=lambda r: r[2])
print('%-4s %-12s %8s %8s %8s' % ('cls', 'file', 'mean_lum', 'dark%', 'H/W'))
for c, f, lm, dk, ar in rows:
    print('%-4s %-12s %8.1f %8.1f %8.2f' % (c, f, lm, dk * 100, ar))
res = [r[2] for r in rows if r[0] == '居民']
vis = [r[2] for r in rows if r[0] == '访客']
print('居民 mean_lum 区间 %.1f ~ %.1f' % (min(res), max(res)))
print('访客 mean_lum %.1f ~ %.1f' % (min(vis), max(vis)))
print('居民 H/W 区间 %.2f ~ %.2f' % (min(r[4] for r in rows if r[0]=='居民'), max(r[4] for r in rows if r[0]=='居民')))
print('访客 H/W %.2f ~ %.2f' % (min(r[4] for r in rows if r[0]=='访客'), max(r[4] for r in rows if r[0]=='访客')))
