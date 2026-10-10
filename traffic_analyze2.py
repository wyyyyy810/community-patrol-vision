import numpy as np
from PIL import Image

BOX = (136, 247, 876, 808)  # rqt image display area inside the screenshot
IMGS = {
    "RED": r"C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-734Z-cf17ae7f.png",
    "GREEN": r"C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-735Z-80635efb.png",
    "YELLOW": r"C:\Users\wyyyyy\.workbuddy\clipboard-images\clipboard-2026-10-05T17-27-19-738Z-c00d1bef.png",
}


def load(name):
    im = Image.open(IMGS[name]).convert("RGB").crop(BOX)
    return np.asarray(im).astype(np.int16)


data = {k: load(k) for k in IMGS}
keys = list(IMGS)
a, b, c = (data[k] for k in keys)

d = np.maximum(np.maximum(np.abs(a - b).sum(2), np.abs(a - c).sum(2)), np.abs(b - c).sum(2))
ys, xs = np.where(d > 120)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
print("lamp bbox in camera frame: x %d..%d y %d..%d (w=%d h=%d)" % (x0, x1, y0, y1, x1 - x0 + 1, y1 - y0 + 1))

w = x1 - x0 + 1
edges = [x0, x0 + w // 3, x0 + 2 * w // 3, x1]
labels = ["LEFT(red)", "MID(yellow)", "RIGHT(green)"]

print("")
print("area      panel        mean_lum   p90_lum   bright_RGB")
for k in keys:
    img = data[k].astype(np.float32)
    for i in range(3):
        sub = img[y0:y1 + 1, edges[i]:edges[i + 1] + 1]
        lum = sub.mean(axis=2)
        flat = sub.reshape(-1, 3)
        l = lum.reshape(-1)
        p90 = np.percentile(l, 90)
        sel = flat[l >= p90]
        r, g, bl = sel[:, 0].mean(), sel[:, 1].mean(), sel[:, 2].mean()
        print("%-9s %-13s %8.1f  %8.1f   (%5.1f,%5.1f,%5.1f)" % (k, labels[i], lum.mean(), p90, r, g, bl))

print("")
print("--- per-panel brightest pixel stats (contrast against dark panels) ---")
for k in keys:
    img = data[k].astype(np.float32)
    lums = []
    for i in range(3):
        sub = img[y0:y1 + 1, edges[i]:edges[i + 1] + 1]
        lums.append(float(sub.mean(axis=2).max()))
    print("%-9s max lum per panel: %s" % (k, " ".join("%6.1f" % v for v in lums)))

# save the lamp area crops for visual confirmation
for k in keys:
    Image.fromarray(data[k][max(0, y0 - 15):y1 + 16, max(0, x0 - 15):x1 + 16].astype(np.uint8)).save("_lamp_%s.png" % k)
print("saved _lamp_RED.png / _lamp_GREEN.png / _lamp_YELLOW.png")
