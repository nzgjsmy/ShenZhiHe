# -*- coding: utf-8 -*-
"""探查：各年份「評卷參考」扫描件的版式差异。

为什么要探查
------------
评分参考有**两代版式**，分值标法完全不同：

* **旧版（2012 等）**：得分点文字后面直接跟「(1)」，右列也是「(1)」，
  而且**每道大题末尾印着总分**「—— 7 分」。
* **新版（PP 等）**：右列是**裸数字** 1 / 2 / `2×2`，正文里不标分值。

在写正式解析器之前，先把每份卷的版式摸清楚，才能选对提取通道。
否则会像第一版那样：按新版规则去裁 2012 的右列，结果一个数字都读不到。

本脚本只做统计，不写数据。输出每页：
  · 「N 分」型总分标记的个数
  · 「(N)」型得分点标记的个数
  · 右列（x > 88% 页宽）的裸数字个数
  · 右列的「(N)」型个数

用法：python scripts/pastpaper/ref_layout_probe.py [年份...]
"""
import json
import os
import re
import sys

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.path.join(ROOT, "scratch", "_ref_pages")
_eng = None


def eng():
    global _eng
    if _eng is None:
        from rapidocr_onnxruntime import RapidOCR
        _eng = RapidOCR()
    return _eng


def main():
    keys = sys.argv[1:]
    base = PAGES
    if not keys:
        keys = sorted(d for d in os.listdir(base)
                      if os.path.isdir(os.path.join(base, d)))
    tot = re.compile(r"[（(]?\s*(\d+)\s*[）)]?\s*分")
    pt = re.compile(r"^[（(]\s*(\d+)\s*[）)]$")
    for k in keys:
        d = os.path.join(PAGES, k)
        if not os.path.isdir(d):
            continue
        pg_sum = pt_sum = bare = paren = 0
        pages = []
        for pg in sorted(f for f in os.listdir(d)
                         if f.lower().endswith((".jpg", ".png"))):
            path = os.path.join(d, pg)
            w, h = Image.open(path).size
            res, _ = eng()(path)
            a = b = c = e = 0
            for box, txt, sc in (res or []):
                t = (txt or "").strip()
                if tot.search(t):
                    a += 1
                if pt.match(t):
                    b += 1
                xs = [p[0] for p in box]
                if min(xs) > w * 0.88:
                    if t.isdigit():
                        c += 1
                    elif pt.match(t):
                        e += 1
            pg_sum += a
            pt_sum += b
            bare += c
            paren += e
            pages.append((pg, a, b, c, e))
        print("== %-5s  总分'N分'=%3d  '(N)'=%3d  右列裸数字=%3d  右列'(N)'=%3d"
              % (k, pg_sum, pt_sum, bare, paren))
        for pg, a, b, c, e in pages:
            if a or b or c or e:
                print("      %s  N分=%-3d (N)=%-3d 裸=%-3d (N)右=%-3d"
                      % (pg, a, b, c, e))


if __name__ == "__main__":
    main()
