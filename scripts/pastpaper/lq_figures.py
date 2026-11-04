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
# 這三個路徑可以用環境變數覆蓋，讓同一支腳本同時服務卷二（預設）與卷一乙部：
#   LQ_JSON=data/bio/_lq_p1.json LQ_PAGES_DIR=scratch/_pp_pages LQ_IMG_REL=img/lq1 \
#       python scripts/pastpaper/lq_figures.py 2019
LQ_JSON = os.environ.get('LQ_JSON') or os.path.join(ROOT, 'data', 'bio', '_lq.json')
PAGES_DIR = os.environ.get('LQ_PAGES_DIR') or os.path.join(ROOT, 'scratch', '_lq_pages')
IMG_REL = os.environ.get('LQ_IMG_REL') or 'img/lq'
OUT_DIR = os.path.join(ROOT, 'site', *IMG_REL.split('/'))

MAX_W = 1000        # 输出宽度上限
WEBP_Q = 78
PAD = 26            # 裁切后保留的空白边（像素，原图尺度）

# 识别产物目录：用来查「该页哪里开始是下一道大题」，好把下一题从页图里裁掉
VL_DIR = os.environ.get('LQ_OUT_DIR') or os.path.join(ROOT, 'scratch', '_p1_vl')
RE_QNUM = re.compile(r'^\s*(\d{1,2})\s*[\.．、]\s*\S')
# 两个题号块至少隔这么远才认定是「下一题」，否则可能是表格里的「1.」这类误判
NEXT_Q_MIN_GAP = 300


def page_q_ys(year, page):
    """该页所有「大题题号块」的 (y, 题号)，按 y 升序。读不到就返回空。"""
    p = os.path.join(VL_DIR, year, 'p%03d.json' % page)
    if not os.path.exists(p):
        return []
    try:
        d = json.load(open(p, encoding='utf-8'))
    except Exception:
        return []
    out = []
    for b in (d.get('res') or {}).get('parsing_res_list') or []:
        t = (b.get('block_content') or '').strip()
        m = RE_QNUM.match(t)
        if m:
            bb = b.get('block_bbox') or [0, 0, 0, 0]
            out.append((int(bb[1]), int(m.group(1))))
    return sorted(out)


def next_q_ylimit(year, page, qnum):
    """同一页上排在本题之后、且够远的那道大题的起始 y；没有就 None。

    不裁的话，前一题的页图会把下一题的题干和表格一起带进来 —— 2012 Q1 就是这样，
    图底部露出「2. 登革熱是由蚊子作媒介來傳播的疾病…」。
    """
    ys = page_q_ys(year, page)
    if not ys:
        return None
    mine = [y for y, n in ys if n == qnum]
    if not mine:
        return None
    base = mine[0]
    later = [y for y, n in ys if y > base + NEXT_Q_MIN_GAP and n != qnum]
    # 多留 34px：识别框（bbox）顶边比实际字形略低，只减 12 会留下半行字
    return (min(later) - 34) if later else None


def qkey(q):
    """题号排序键：1(a) < 1(b) < 2(a) … 不依赖数组顺序。"""
    m = re.match(r'\s*(\d+)\s*\(?([a-zA-Z])?', q.get('qnum') or '')
    if not m:
        return (999, '')
    return (int(m.group(1)), (m.group(2) or 'a').lower())


def trim_page(src, dst, y_limit=None):
    """裁掉页面四周空白边，缩到 MAX_W 宽，存 webp。返回 (w, h, kb)。

    y_limit（原图尺度像素）给定时只保留 y < y_limit 的内容，
    用来把「同一页里的下一道大题」裁掉。
    """
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

    # 把「下一道大题」整块抹掉，包围盒自然就只包住本题
    if y_limit is not None:
        bw[max(0, int(y_limit)):, :] = 0

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
            # 起始页若同页还有下一道大题，裁到下一题之前 —— 否则图里会露出下一题。
            # 这种「裁过的版本」必须单独命名：同一页的另一题还要用整页图，
            # 否则两者共用一个文件名，后写的会把前面的覆盖掉（2012 p012 踩过）。
            ylim = None
            if p == start:
                try:
                    ylim = next_q_ylimit(year, p, int(q['qnum']))
                except (TypeError, ValueError):
                    ylim = None
            name = ('p%03d_q%s.webp' % (p, q['qnum'])) if ylim is not None else ('p%03d.webp' % p)
            rel = '%s/%s/%s' % (IMG_REL, year, name)
            if dry:
                imgs.append(rel); continue
            w, h, kb = trim_page(pgs[p], os.path.join(ROOT, 'site', rel), y_limit=ylim)
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
