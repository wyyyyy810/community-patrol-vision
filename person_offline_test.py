# -*- coding: utf-8 -*-
"""人偶检测离线回归测试

关键点：**不再复制算法**。本脚本直接从 perception_node.py 里把
`==== BEGIN PERSON-BLOCK-A ====` ~ `==== END PERSON-BLOCK-B ====` 之间的代码整段 exec，
因此“离线测的就是线上跑的那一份”，改阈值/改逻辑后跑一次就知道有没有退化。

用法（Windows 本地，需要 opencv-python / pillow / numpy）：
    python person_offline_test.py
    python person_offline_test.py "C:\\some\\frame.png"        # 也可以测自己的截图

期望结果（2026-10-08 v8 定稿，person_min_score = 0.65，人工逐块核对过）：
    _p_s02.png → 6 框：5 块立牌全中 + 画面右缘露出半个身子的一块（确实存在）
    _p_s09.png → 3 框：person_07 / person_08 / visitor_1，一个不多一个不少
    _p_s15.png → 4 框：person_14 / 15 / 1 / 16，一个不多一个不少
"""
import os
import re
import sys
import time

import cv2
import numpy as np

SCORE_MIN = 0.65          # 与节点里 person_min_score 默认值保持一致
NODE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'perception_node.py')
TPL_DIRS = [(r'D:\BaiduNetdiskDownload\复赛资料\人员\社区人员', 'COMMUNITY'),
            (r'D:\BaiduNetdiskDownload\复赛资料\人员\非社区人员', 'NON_COMMUNITY')]
DEFAULT_IMAGES = ['_p_s02.png', '_p_s09.png', '_p_s15.png']


def load_person_block():
    """从 perception_node.py 抽出模块二的参数与函数（两段标记之间的代码）"""
    src = open(NODE, encoding='utf-8').read()
    parts = []
    for a, b in (('==== BEGIN PERSON-BLOCK-A ====', '==== END PERSON-BLOCK-A ===='),
                 ('==== BEGIN PERSON-BLOCK-B ====', '==== END PERSON-BLOCK-B ====')):
        i, j = src.index(a), src.index(b)
        parts.append(src[src.index('\n', i) + 1:src.rindex('\n', 0, j) + 1])
    ns = {'cv2': cv2, 'np': np, 'glob': __import__('glob'), 'os': os}
    exec(compile(''.join(parts), 'perception_node.py<person-block>', 'exec'), ns)
    return ns


NS = load_person_block()
print('从 perception_node.py 读到参数：')
for k in ('PERSON_SCALE', 'PERSON_LADDER', 'PERSON_TOPK', 'PERSON_MIN_WIDTH',
          'PERSON_MIN_STD', 'PERSON_MIN_ROWSTD', 'NMS_IOU', 'NMS_COVER'):
    print('   %-18s = %s' % (k, NS[k]))


def build_node_style_templates():
    """构造 [(名称, 类别, 尺度模板)]，与 node 里 load_person_templates 完全等价"""
    import glob
    from PIL import Image
    out = []
    for d, cls in TPL_DIRS:
        for p in sorted(glob.glob(os.path.join(d, '*.png'))):
            arr = np.array(Image.open(p).convert('RGBA'))      # D 盘是中文路径，cv2 读不了
            gray = cv2.cvtColor(arr[:, :, 2::-1].copy(), cv2.COLOR_BGR2GRAY)
            h0, w0 = gray.shape[:2]
            variants = [(H, cv2.resize(gray, (max(6, int(round(w0 * H / h0))), H),
                                       interpolation=cv2.INTER_AREA)) for H in NS['PERSON_LADDER']]
            out.append((os.path.splitext(os.path.basename(p))[0], cls, variants))
    return out


def main():
    templates = build_node_style_templates()
    print('\n模板 %d 个' % len(templates))
    images = sys.argv[1:] or DEFAULT_IMAGES
    for f in images:
        frame = cv2.imread(f)
        if frame is None:
            print('跳过（找不到文件）%s' % f)
            continue
        t0 = time.time()
        dets, detail = NS['detect_persons'](frame, templates, SCORE_MIN,
                                            NS['PERSON_MIN_ROWSTD'], NS['PERSON_MIN_COLSTD'])
        dt = time.time() - t0
        print('\n=== %s  %dx%d  %.2fs  保留 %d 框  %s'
              % (f, frame.shape[1], frame.shape[0], dt, len(dets), detail))
        vis = frame.copy()
        for d in dets:
            x, y, w, h = d['bbox']
            col = (255, 128, 0) if d['result'] == 'COMMUNITY' else (0, 0, 255)
            cv2.rectangle(vis, (x, y), (x + w, y + h), col, 2)
            cv2.putText(vis, '%s %.2f' % (d['template'], d['confidence']),
                        (max(0, x), max(14, y - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
            print('   %.3f %-8s %-14s bbox=(%3d,%3d,%3dx%d) ar=%.2f'
                  % (d['confidence'], d['template'], d['result'], x, y, w, h, h / max(1, w)))
        cv2.imwrite('_det_' + os.path.basename(f), vis)
    print('\n已保存 _det_*.png')


if __name__ == '__main__':
    main()
