"""字体排序：允许 ±15% 宽度缩放后再算 IoU，挑出最接近车牌字体的候选。

之前用「不缩宽度的 IoU」比对时，SimHei 只有 0.30 —— 那是因为实测字形带 1.28 倍横向拉伸
（贴图 AR 2.47 → 实拍板 AR 3.17），形状对得上但宽度对不上，IoU 被系统性拉低。
"""
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import plate_proto as pp

D = r'D:\BaiduNetdiskDownload\复赛资料\车辆识别'
SPEC = [('车牌一.png', '苏A·B8Q62'), ('车牌二.png', '鄂D·7B5Q2'), ('车牌三.png', '苏A·PL12A')]
GH, CW, PAD = 40, 44, 8


def norm_bin(b, gh=GH, cw=CW, pad=PAD, wx=1.0):
    """裁内容外框 → 按高度（可选宽度缩放）归一 → 居中贴到固定画布。"""
    ys, xs = np.where(b > 0)
    if len(ys) == 0:
        return None
    c = b[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8)
    h, w = c.shape
    W = max(2, int(round(w * wx * gh / float(h))))
    r = cv2.resize(c, (W, gh), interpolation=cv2.INTER_AREA)
    cn = np.zeros((gh + 2 * pad, cw + 2 * pad), np.uint8)
    if W <= cw:
        x = pad + (cw - W) // 2
        cn[pad:pad + gh, x:x + W] = r
    else:
        st = (W - cw) // 2
        cn[pad:pad + gh, pad:pad + cw] = r[:, st:st + cw]
    return cn


def iou(a, b, tol=3):
    """b 当大图、a 当模板滑一遍，取最大 IoU（OpenCV 的 filter2D 做的是相关，正好是交集）。"""
    A = (a > 0).astype(np.float32)
    B = (b > 0).astype(np.float32)
    big = np.zeros((B.shape[0] + 2 * tol, B.shape[1] + 2 * tol), np.float32)
    big[tol:tol + B.shape[0], tol:tol + B.shape[1]] = B
    inter = cv2.filter2D(big, -1, A, borderType=cv2.BORDER_CONSTANT)
    union = A.sum() + B.sum() - inter
    with np.errstate(invalid='ignore', divide='ignore'):
        r = np.where(union > 0, inter / union, 0.0)
    return float(r.max())


def queries():
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
            q.setdefault(chars[idx], []).append(sub)
            idx += 1
    return q


def render(ch, fp, size=160):
    try:
        f = ImageFont.truetype(fp, size)
    except Exception:
        return None
    img = Image.new('L', (size * 3, size * 3), 0)
    ImageDraw.Draw(img).text((size, size), ch, 255, font=f)
    a = np.array(img)
    return a if (a > 127).sum() > 20 else None


FONTS = ['simhei.ttf', 'msyhbd.ttc', 'msyh.ttc', 'simsun.ttc', 'simkai.ttf', 'msgothic.ttc',
         'arialbd.ttf', 'tahomabd.ttf', 'verdanab.ttf', 'FZYTK.TTF', 'AGENCYB.TTF', 'dengb.ttf',
         'calibrib.ttf', 'trebucbd.ttf', 'ariblk.ttf', 'impact.ttf', 'STXIHEI.TTF', 'msjhbd.ttc']


def main():
    Q = queries()
    print('考卷 %d 类' % len(Q))
    rows = []
    for fn in FONTS:
        fp = os.path.join('C:/Windows/Fonts', fn)
        if not os.path.exists(fp):
            continue
        per = []
        for ch, subs in sorted(Q.items()):
            best = 0.0
            for size in (110, 150, 190):
                a = render(ch, fp, size)
                if a is None:
                    break
                for wx in (0.85, 1.0, 1.15):
                    g2 = norm_bin((a > 127).astype(np.uint8) * 255, wx=wx)
                    if g2 is None:
                        continue
                    for s in subs:
                        for wx2 in (0.9, 1.0, 1.1):
                            g1 = norm_bin((s > 0).astype(np.uint8) * 255, wx=wx2)
                            if g1 is not None:
                                best = max(best, iou(g1, g2))
            per.append((ch, best))
        rows.append((float(np.mean([p[1] for p in per])), fn, per))
    rows.sort(reverse=True)
    for m, fn, per in rows:
        print('%-16s %.3f  %s' % (fn, m, ' '.join('%s%.2f' % (c, v) for c, v in per)))


if __name__ == '__main__':
    main()
