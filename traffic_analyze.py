import sys
import numpy as np
from PIL import Image

RED_IMG = r"C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-734Z-cf17ae7f.png"
GRN_IMG = r"C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-735Z-80635efb.png"
YEL_IMG = r"C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-738Z-c00d1bef.png"


def load(p):
    im = Image.open(p).convert("RGB")
    return np.asarray(im).astype(np.int16)


def main():
    a = load(RED_IMG)
    b = load(GRN_IMG)
    c = load(YEL_IMG)
    print("shapes:", a.shape, b.shape, c.shape)

    # difference map: where the three shots disagree
    d1 = np.abs(a - b).sum(axis=2)
    d2 = np.abs(a - c).sum(axis=2)
    d3 = np.abs(b - c).sum(axis=2)
    d = np.maximum(np.maximum(d1, d2), d3)
    ys, xs = np.where(d > 60)
    if len(xs) == 0:
        print("no difference found")
        return
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    print("diff bbox: x %d..%d  y %d..%d  (w=%d h=%d)" % (x0, x1, y0, y1, x1 - x0 + 1, y1 - y0 + 1))

    # crop that region and save for visual check
    pad = 20
    cx0 = max(0, x0 - pad)
    cy0 = max(0, y0 - pad)
    cx1 = min(a.shape[1], x1 + pad)
    cy1 = min(a.shape[0], y1 + pad)
    Image.fromarray(a[cy0:cy1, cx0:cx1].astype(np.uint8)).save("_crop_red.png")
    Image.fromarray(b[cy0:cy1, cx0:cx1].astype(np.uint8)).save("_crop_green.png")
    Image.fromarray(c[cy0:cy1, cx0:cx1].astype(np.uint8)).save("_crop_yellow.png")
    print("saved _crop_red.png / _crop_green.png / _crop_yellow.png  region x", cx0, cy0, cx1, cy1)

    # split into 3 horizontal thirds and report per-panel brightness
    names = [("RED shot", a), ("GREEN shot", b), ("YELLOW shot", c)]
    w = x1 - x0 + 1
    thirds = [(x0, x0 + w // 3), (x0 + w // 3, x0 + 2 * w // 3), (x0 + 2 * w // 3, x1)]
    for name, img in names:
        print("---", name)
        for i, (t0, t1) in enumerate(thirds):
            sub = img[y0:y1 + 1, t0:t1 + 1].astype(np.float32)
            lum = sub.mean(axis=2)
            flat = sub.reshape(-1, 3)
            # brightest 15% pixels drive the "lamp colour"
            thr = np.percentile(lum, 85)
            mask = lum >= thr
            sel = flat[mask.reshape(-1)]
            r, g, bb = sel[:, 0].mean(), sel[:, 1].mean(), sel[:, 2].mean()
            print("  panel%d  mean_lum=%6.1f  top15%%_RGB=(%6.1f,%6.1f,%6.1f)" % (i, lum.mean(), r, g, bb))


if __name__ == "__main__":
    main()
