import cv2
import numpy as np
import math

src = cv2.imread('_p_s09.png')
print('image', src.shape)

gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
edges = cv2.Canny(gray, 50, 150, apertureSize=3)

lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40,
                        minLineLength=30, maxLineGap=8)
print('lines found:', 0 if lines is None else len(lines))

if lines is not None:
    vert, horiz = [], []
    for l in lines.reshape(-1, 4):
        x1, y1, x2, y2 = map(int, l)
        dx, dy = x2 - x1, y2 - y1
        if dy == 0:
            continue
        ang = math.degrees(math.atan2(dx, -dy))  # 0 = 正竖直, 正=顺时针歪
        length = math.hypot(dx, dy)
        if length < 30:
            continue
        if abs(ang) < 35:
            vert.append(ang)
        elif abs(abs(ang) - 90) < 35:
            horiz.append(ang - math.copysign(90, ang))

    def stat(name, arr):
        if not arr:
            print('%s: none' % name)
            return
        a = np.array(arr)
        print('%s: n=%d  mean=%+.2f deg  median=%+.2f  std=%.2f  '
              'min=%+.2f max=%+.2f  |ang|>3deg占比=%.1f%%'
              % (name, len(a), a.mean(), np.median(a), a.std(),
                 a.min(), a.max(), 100.0 * (np.abs(a) > 3).mean()))
        hist, _ = np.histogram(np.round(a), bins=np.arange(-20, 21, 5))
        centers = [x + 2 for x in np.arange(-20, 20, 5)]
        print('   直方图(度):', ', '.join('%d~%d:%d' % (c - 2, c + 2, h)
                                        for c, h in zip(centers, hist) if h))

    stat('近竖直线(相对竖直) ', vert)
    stat('近水平线(相对水平) ', horiz)

# 直接看三块已知立牌区域的边缘走向
boxes = {'左(橙夹克)': (58, 308, 135, 510),
         '中(黑大衣)': (228, 300, 280, 425),
         '右(双臂交叉)': (398, 305, 445, 470)}
print('\n=== 逐块立牌边缘走向 ===')
for name, (x1, y1, x2, y2) in boxes.items():
    roi = gray[max(0, y1 - 6):y2 + 6, max(0, x1 - 6):x2 + 6]
    if roi.size == 0:
        continue
    e = cv2.Canny(roi, 40, 120)
    ls = cv2.HoughLinesP(e, 1, np.pi / 180, threshold=15,
                         minLineLength=max(12, roi.shape[0] // 4), maxLineGap=6)
    if ls is None:
        print('%-12s 无线段' % name)
        continue
    angs = []
    for l in ls.reshape(-1, 4):
        ax, ay, bx, by = map(int, l)
        dx, dy = bx - ax, by - ay
        if dy == 0:
            continue
        ang = math.degrees(math.atan2(dx, -dy))
        if abs(ang) < 40:
            angs.append(ang)
    if not angs:
        print('%-12s 无近竖直线段' % name)
        continue
    a = np.array(angs)
    print('%-12s 尺寸=%dx%d  竖边角=%+.2f deg (n=%d, std=%.2f)'
          % (name, x2 - x1, y2 - y1, np.median(a), len(a), a.std()))
