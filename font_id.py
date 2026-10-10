"""车牌字体鉴定：用参考贴图里切出的高清单字当考卷，比对系统字体。

为什么要做这一步：国赛车牌未知，如果官网生成器用的是某个系统字体，
就能直接渲染出「全字符集」（省份汉字 + A-Z + 0-9）当模板库，识别率接近 100%；
如果对不上，就只能退回到「实测切片 + 有限字库」。

实现要点（性能）：
  * 两侧都先按高度归一化 → 字号大小基本没影响，只需 3 个字号即可代表一整族；
  * 位移容错用 cv2.matchTemplate(TM_CCOEFF_NORMED) 一次算完全部平移，
    而不是 for 循环 np.roll（后者在 400 字体 × 15 字上要几十万次，会被超时杀掉）。
"""
import glob
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import plate_proto as pp

D = r'D:\BaiduNetdiskDownload\复赛资料\车辆识别'
SPEC = [('车牌一.png', '苏A·B8Q62'), ('车牌二.png', '鄂D·7B5Q2'), ('车牌三.png', '苏A·PL12A')]

GH, CW = 32, 28          # 归一化高度 / 画布宽
PAD = 6                  # 滑窗余量


def norm(binimg, gh=GH, cw=CW):
    ys, xs = np.where(binimg > 0)
    if len(ys) == 0:
        return None
    c = binimg[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = c.shape
    W = max(2, int(round(w * gh / float(h))))
    r = cv2.resize(c, (W, gh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((gh + 2 * PAD, cw + 2 * PAD), np.float32)
    if W <= cw:
        x = PAD + (cw - W) // 2
        canvas[PAD:PAD + gh, x:x + W] = (r > 0)
    else:
        st = (W - cw) // 2
        canvas[PAD:PAD + gh, PAD:PAD + cw] = (r[:, st:st + cw] > 0)
    return canvas


def score(a, b, tol=3):
    """把 b 当大图、a 当模板滑窗，取最大归一化相关（一次算完全部平移）。"""
    big = np.zeros((b.shape[0] + 2 * tol, b.shape[1] + 2 * tol), np.float32)
    big[tol:tol + b.shape[0], tol:tol + b.shape[1]] = b
    res = cv2.matchTemplate(big, a, cv2.TM_CCOEFF_NORMED)
    return float(res.max())


def build_queries():
    q = {}
    for fn, lab in SPEC:
        im = cv2.cvtColor(np.array(Image.open(os.path.join(D, fn)).convert('RGB')),
                          cv2.COLOR_RGB2BGR)
        plate = pp.canonicalize(im)
        chars = lab.replace('·', '')
        idx = 0
        for a, b, rf, sub in pp.segment_chars(plate):
            if rf < 0.40 or (b - a) < 10:
                continue
            if idx >= len(chars):
                break
            g = norm(((sub > 0).astype(np.uint8) * 255))
            if g is not None:
                q.setdefault(chars[idx], []).append(g)
            idx += 1
    return q


def font_list():
    seen, out = set(), []
    for base in ['C:/Windows/Fonts',
                 os.path.expanduser('~/AppData/Local/Microsoft/Windows/Fonts')]:
        for p in ['*.ttf', '*.ttc', '*.otf', '*.TTF', '*.TTC']:
            for fp in glob.glob(os.path.join(base, p)):
                k = os.path.basename(fp).lower()
                if k not in seen:
                    seen.add(k)
                    out.append(fp)
    return sorted(out)


def render(ch, fp, size):
    try:
        f = ImageFont.truetype(fp, size)
    except Exception:
        return None
    img = Image.new('L', (size * 3, size * 3), 0)
    ImageDraw.Draw(img).text((size, size), ch, 255, font=f)
    a = np.array(img)
    return a if (a > 127).sum() > 20 else None


def main():
    q = build_queries()
    print('考卷 %d 类：%s' % (len(q), ' '.join('%s x%d' % (c, len(v)) for c, v in sorted(q.items()))))
    fonts = font_list()
    print('候选字体 %d 个，开始比对…\n' % len(fonts))
    rows = []
    for i, fp in enumerate(fonts):
        per, ok = [], 0
        for ch, gs in q.items():
            best = 0.0
            for size in (48, 72, 96):
                a = render(ch, fp, size)
                if a is None:
                    break
                g2 = norm((a > 127).astype(np.uint8) * 255)
                if g2 is None:
                    continue
                for g1 in gs:
                    best = max(best, score(g1, g2))
            per.append(best)
            if best >= 0.68:
                ok += 1
        rows.append((ok, float(np.mean(per)), min(per), os.path.basename(fp)))
        sys.stderr.write('\r  %d/%d' % (i + 1, len(fonts)))
    sys.stderr.write('\n')
    rows.sort(key=lambda r: (-r[0], -r[1]))
    print('%-32s 命中(≥0.68)  平均   最低' % '字体')
    for ok, m, mn, nm in rows[:20]:
        print('  %-30s %2d/%d      %.3f  %.3f' % (nm, ok, len(q), m, mn))


if __name__ == '__main__':
    main()
