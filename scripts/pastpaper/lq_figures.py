# -*- coding: utf-8 -*-
"""卷二 LQ 原卷页图：裁掉四周空白 → webp → 写入 _lq.json 的 imgs 字段。

用法：
    python scripts/pastpaper/lq_figures.py 2019            # 只处理某年
    python scripts/pastpaper/lq_figures.py                 # 全部年份
    python scripts/pastpaper/lq_figures.py 2019 --dry      # 只算不写

设计取舍（2026-11-01）：
  不做「自动裁出单个图」——实测长直线/墨迹密度判据在曲线图与表格上会互相误判，
  裁错比没有图更糟（学生会看着错的图作答）。改为**整页原卷图**：
  只裁掉页面四周的空白边（含扫描站水印），内容一个字不少。

⚠️ 页范围必须按**题号顺序**算，不能按数组顺序：
   2018 的 1(b) 是后来补录的，追加在数组末尾但 page=2；
   按数组顺序算会把 1(a) 当成跨 8 页、把 1(b) 配到第 9 页（实测踩过）。
"""
import os
import re
import sys
import json
import glob

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LQ_JSON = os.path.join(ROOT, 'data', 'bio', '_lq.json')
PAGES_DIR = os.path.join(ROOT, 'scratch', '_lq_pages')
OUT_DIR = os.path.join(ROOT, 'site', 'img', 'lq')

MAX_W = 1000        # 输出宽度上限
WEBP_Q = 78
PAD = 26            # 裁切后保留的空白边（像素，原图尺度）


def qkey(q):
    """题号排序键：1(a) < 1(b) < 2(a) … 不依赖数组顺序。"""
    m = re.match(r'\s*(\d+)\s*\(?([a-zA-Z])?', q.get('qnum') or '')
    if not m:
        return (999, '')
    return (int(m.group(1)), (m.group(2) or 'a').lower())


def trim_page(src, dst):
    """裁掉页面四周空白边，缩到 MAX_W 宽，存 webp。返回 (w, h, kb)。"""
    import cv2
    img = cv2.imread(src)
    if img is None:
        raise RuntimeError('读不到 ' + src)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bw = cv2.threshold(gray, 205, 255, cv2.THRESH_BINARY_INV)[1]
    # 去掉孤立噪点，避免包围盒被一个脏点撑满整页
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    H, W = gray.shape

    # 剔除「与主体分离的底部孤行」——扫描站水印 / 页脚。
    # 不剔的话包围盒会被撑到页底，图下面留一大片空白（实测 2019 p001 多出 40% 高度）。
    rows = bw.sum(axis=1) > 0
    segs, s = [], None
    for i, v in enumerate(rows):
        if v and s is None:
            s = i
        elif not v and s is not None:
            segs.append((s, i - 1)); s = None
    if s is not None:
        segs.append((s, len(rows) - 1))
    real = [g for g in segs if g[1] - g[0] + 1 >= 12]   # 跳过 <12px 的噪点段
    if len(real) >= 2:
        last_s, prev_e = real[-1][0], real[-2][1]
        if last_s > H * 0.86 and (last_s - prev_e) > 40:
            bw[last_s:, :] = 0

    ys, xs = bw.nonzero()
    if len(xs) == 0:
        x0, y0, x1, y1 = 0, 0, W, H
    else:
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
    x0 = max(0, x0 - PAD); y0 = max(0, y0 - PAD)
    x1 = min(W, x1 + PAD); y1 = min(H, y1 + PAD)
    crop = img[y0:y1, x0:x1]
    h, w = crop.shape[:2]
    if w > MAX_W:
        crop = cv2.resize(crop, (MAX_W, int(h * MAX_W / w)), interpolation=cv2.INTER_AREA)
        h, w = crop.shape[:2]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    cv2.imwrite(dst, crop, [cv2.IMWRITE_WEBP_QUALITY, WEBP_Q])
    return w, h, os.path.getsize(dst) / 1024.0


def page_files(year):
    out = {}
    for f in sorted(glob.glob(os.path.join(PAGES_DIR, year, 'p*.jpg'))):
        m = re.search(r'p(\d+)\.jpg$', f)
        if m:
            out[int(m.group(1))] = f
    return out


def build_year(year, dry=False):
    data = json.load(open(LQ_JSON, encoding='utf-8'))
    qs = data['years'][year]
    pgs = page_files(year)
    if not pgs:
        print('  %s：没有页图，跳过' % year)
        return
    maxp = max(pgs)

    order = sorted(qs, key=qkey)          # ← 逻辑顺序，不是数组顺序
    ranges = {}
    for i, q in enumerate(order):
        start = q.get('page')
        if not isinstance(start, int) or start < 1 or start > maxp:
            ranges[q['id']] = (None, None)      # 原卷页图缺失（如 2014 丁部）
            continue
        nxt = order[i + 1].get('page') if i + 1 < len(order) else None
        if isinstance(nxt, int) and nxt > start:
            end = nxt - 1
        else:
            end = maxp if i + 1 >= len(order) else start   # 最後一題要喫到末頁
        ranges[q['id']] = (start, min(end, maxp))

    total_kb, n_img, missing = 0, 0, []
    for q in qs:
        start, end = ranges[q['id']]
        if start is None:
            q['imgs'] = []
            q['imgMissing'] = True      # 原卷掃描件本身缺這幾頁（如 2014 丁部）
            missing.append(q['qnum'])
            continue
        q.pop('imgMissing', None)
        imgs = []
        for p in range(start, end + 1):
            if p not in pgs:
                continue
            rel = 'img/lq/%s/p%03d.webp' % (year, p)
            if dry:
                imgs.append(rel); continue
            w, h, kb = trim_page(pgs[p], os.path.join(ROOT, 'site', rel))
            total_kb += kb; n_img += 1
            imgs.append(rel)
        q['imgs'] = imgs
        if len(imgs) > 1:
            print('  %-6s 跨 %d 页（p%d–p%d）' % (q['qnum'], len(imgs), start, end))
    print('  %s：%d 题 · %d 张图 · %.1f MB%s'
          % (year, len(qs), n_img, total_kb / 1024,
             (' ｜ 无原卷页图：' + '、'.join(missing)) if missing else ''))
    if not dry:
        json.dump(data, open(LQ_JSON, 'w', encoding='utf-8'),
                  ensure_ascii=False, separators=(',', ':'))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry = '--dry' in sys.argv
    data = json.load(open(LQ_JSON, encoding='utf-8'))
    for y in (args or list(data['years'].keys())):
        print('===', y, '===')
        build_year(y, dry=dry)


if __name__ == '__main__':
    main()
