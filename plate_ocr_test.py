"""车牌识别回归测试。

真值来自人工放大核对：
  shot2            → 苏D·77H8J  （距离最近，字高 19 px）
  shot3            → 皖A·PJ8H1
  vcar19 近车      → 苏D·77H8J
  vcar19 远车      → 皖B·7H1K9（字号只有 9 px，人工判读也有把握不足的地方）
三张官方贴图        → 苏A·B8Q62 / 鄂D·7BQ52 / 苏A·PL12A

分三档评估：
  A 只用系统字体渲染的字库 —— 模拟国赛「完全没见过的车牌」；
  B 字体库 + 官方贴图真字；
  C 留一法：从其它所有真实车牌图里切真字建库，再识别当前这张
    （同一字体的跨图泛化能力，这是仿真里实际会发生的场景）。
"""
import os
import time

import cv2
import numpy as np

import plate_ocr as po

CLIP = r'C:\Users\wyyyyy\.workbuddy\clipboard-images'
REF = r'D:\BaiduNetdiskDownload\复赛资料\车辆识别'

SHOT2 = os.path.join(CLIP, 'clipboard-2026-10-09T08-52-53-020Z-6b676d9b.png')
SHOT3 = os.path.join(CLIP, 'clipboard-2026-10-09T08-52-53-021Z-16c6f12b.png')
VCAR = '_v_car19.png'

FRAMES = [
    ('shot2', SHOT2, (296, 259, 104, 31), '苏D77H8J'),
    ('shot3', SHOT3, (376, 288, 101, 31), '皖APJ8H1'),
    ('vcar近', VCAR, (532, 352, 86, 29), '苏D77H8J'),
    ('vcar远', VCAR, (176, 332, 47, 18), '皖B7H1K9'),
]
TEXTURES = [(os.path.join(REF, '车牌一.png'), '苏A·B8Q62'),
            (os.path.join(REF, '车牌二.png'), '鄂D·7B5Q2'),
            (os.path.join(REF, '车牌三.png'), '苏A·PL12A')]


def plate_of(path, bbox):
    gray = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2GRAY)
    return po.crop_plate(gray, bbox)


def eval_frame_lib(tag, get_lib):
    print('#### %s' % tag)
    hit, tot = 0, 0
    for name, path, bbox, truth in FRAMES:
        if not os.path.exists(path):
            continue
        lib = get_lib(name)
        t0 = time.time()
        text, scores, diag = po.read_plate(plate_of(path, bbox), lib)
        dt = time.time() - t0
        ok = text == truth
        hit += ok
        tot += 1
        print('   %-7s 读出 "%-8s" 真值 "%-8s" %s %.2fs | %s'
              % (name, text, truth, 'OK' if ok else '× ', dt, diag))
    print('   → %d/%d\n' % (hit, tot))


def main():
    print('渲染全字符集字库…')
    t0 = time.time()
    flib = po.build_font_library()
    print('字体库 %d 类，%.1fs\n' % (len(flib), time.time() - t0))

    tlib = po.harvest_texture_library(TEXTURES)
    print('官方贴图真字库 %d 类：%s\n' % (len(tlib), ' '.join(sorted(tlib))))

    real_all = []
    for name, path, bbox, truth in FRAMES:
        if os.path.exists(path):
            real_all.append((name, path, bbox, truth))

    eval_frame_lib('A) 只有系统字体渲染（模拟国赛未知车牌）',
                   lambda n: flib)
    eval_frame_lib('B) 字体库 + 官方贴图真字',
                   lambda n: po.merge_library(flib, tlib))

    def loo(name):
        entries = [(p, b, t) for nm, p, b, t in real_all if nm != name]
        return po.merge_library(flib, tlib, po.harvest_frame_library(entries))

    eval_frame_lib('C) 留一法：用其它真实车牌图的真字建库', loo)

    # 全量真字库（实际部署时会把看到的都收进去）
    full = po.merge_library(flib, tlib,
                            po.harvest_frame_library([(p, b, t) for _, p, b, t in real_all]))
    print('真字库覆盖：%s' % ' '.join(sorted(k for k in full if k in tlib or True)))


if __name__ == '__main__':
    main()
