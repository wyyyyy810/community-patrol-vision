"""验收图：对整张图跑节点里那条 plate 流程，画框 + 写车牌号，存成 png 给你直接看。

两段：
  ① 相机原帧实跑（节点 plate_dump 落盘的那 6 帧，每块车牌取一帧）—— 这就是"拍一张→框住→输出"。
  ② 留出验证（4 张旧机位帧，**没参与标定**，用来证明不是靠记住机位）。
"""
import os

import cv2
import numpy as np

import plate_offline_test as T

HERE = os.path.dirname(os.path.abspath(__file__))
NS = T.load_node_block()

# 和 plate_offline_test.main() 完全一致的建库口径：
# 字体轨（压扁标定）→ 官方贴图（以字体库为参照做对齐校验）→ 相机原帧（同样校验）
flib = T.build_font_library(NS)
tlib = T.texture_library(NS, ref_lib=flib)
dlib = T.dump_library(NS, T.DUMP, ref_lib=T.merge(flib, tlib))
lib = T.merge(flib, tlib, dlib)

font = NS['plate_find_cjk_font']()
HDR = 30


def render(frame, truth, title, truth_bbox=None):
    dets, _g = NS['plate_detect'](frame, lib, 7, 0.45)
    vis = frame.copy()
    for d in dets:
        x, y, w, h = d['bbox']
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 255), 2)
        NS['plate_draw_label'](vis, '%s %.2f' % (d['result'], d['confidence']),
                               (x, max(0, y - 22)), (0, 255, 255), font)
    if truth_bbox:
        cv2.rectangle(vis, (truth_bbox[0], truth_bbox[1]),
                      (truth_bbox[0] + truth_bbox[2], truth_bbox[1] + truth_bbox[3]),
                      (0, 200, 0), 1)
    ok = any(d['result'] == truth for d in dets)
    bar = np.full((HDR, vis.shape[1], 3), 25, np.uint8)
    cv2.putText(bar, '%s  truth=%s  %s' % (title, truth, 'OK' if ok else 'MISS'),
                (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (120, 255, 120) if ok else (80, 80, 255), 1, cv2.LINE_AA)
    return np.vstack([bar, vis]), ok


rows, hits = [], 0
print('① 相机原帧实跑（plate_dump 落盘）')
for fid, truth in [T.DUMP[0], T.DUMP[2], T.DUMP[4]]:
    p = os.path.join(T.DUMP_DIR, fid + '_raw.png')
    frame = cv2.imread(p) if os.path.exists(p) else None
    if frame is None:
        continue
    tile, ok = render(frame, truth, 'dump %s' % fid)
    hits += ok
    rows.append(tile)
    print('   %-10s truth=%-9s %s' % (fid, truth, 'OK' if ok else 'MISS'))
print('   → %d/%d' % (hits, len(rows)))

print('② 留出验证（未参与标定的旧机位帧）')
sub = []
for name, path, bbox, truth in T.FRAMES:
    frame = cv2.imread(path)
    if frame is None:
        continue
    tile, ok = render(frame, truth, 'holdout %s' % name, bbox)
    sub.append(tile)
    print('   %-7s truth=%-9s %s' % (name, truth, 'OK' if ok else 'MISS'))

W = max(t.shape[1] for t in rows + sub)


def pad(t):
    return cv2.copyMakeBorder(t, 0, 0, 0, W - t.shape[1], cv2.BORDER_CONSTANT, value=(25, 25, 25))


# 排成两列，省得图太高看不过来
tiles = [pad(t) for t in rows + sub]
H = max(t.shape[0] for t in tiles)
tiles = [cv2.copyMakeBorder(t, 0, H - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(25, 25, 25))
         for t in tiles]
cols, gap = 2, 8
grid = []
for i in range(0, len(tiles), cols):
    line = tiles[i:i + cols]
    while len(line) < cols:
        line.append(np.full((H, W, 3), 25, np.uint8))
    grid.append(np.hstack([np.hstack([line[0], np.zeros((H, gap, 3), np.uint8), line[1]])]))
allp = os.path.join(HERE, '_plate_verify_all.png')
out = np.vstack(grid)
if out.shape[1] > 1400:
    s = 1400.0 / out.shape[1]
    out = cv2.resize(out, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
cv2.imwrite(allp, out)
print('总览图 → %s  %s' % (allp, out.shape))
