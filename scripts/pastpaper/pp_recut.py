# -*- coding: utf-8 -*-
"""按人工指定的题目区域重裁配图，自动收紧到墨迹包络

用法:
  python scratch/_pp_recut.py recut.json
  python scratch/_pp_recut.py --one 2012 4 660 1130 site/img/pp/2012/f16.webp

recut.json: [{"key":"2012","page":4,"q":11,"y1":1100,"y2":1830,"out":"site/img/pp/2012/f11.webp"}, ...]
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageOps

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(_ROOT, "scratch", "_pp_pages")
INK = 178
PAD = 14
MINW = 1000  # 输出至少这么宽，太窄就放大


def tight(arr, y1, y2, x1=None, x2=None):
    h, w = arr.shape
    y1, y2 = max(0, y1), min(h, y2)
    x1 = 0 if x1 is None else max(0, x1)
    x2 = w if x2 is None else min(w, x2)
    sub = arr[y1:y2, x1:x2] < INK
    if sub.sum() < 200:
        return None
    rows = np.where(sub.sum(axis=1) > 2)[0]
    cols = np.where(sub.sum(axis=0) > 1)[0]
    return (
        x1 + int(cols[0]),
        y1 + int(rows[0]),
        x1 + int(cols[-1]),
        y1 + int(rows[-1]),
    )


def one(key, page, y1, y2, out, x1=None, x2=None, pad=PAD):
    p = os.path.join(BASE, key, "p%03d.jpg" % page)
    im = Image.open(p).convert("L")
    arr = np.array(im)
    bb = tight(arr, y1, y2, x1, x2)
    if not bb:
        print("!! %s q? p%d y%d..%d 无墨迹" % (key, page, y1, y2))
        return None
    X1, Y1, X2, Y2 = bb
    X1, Y1 = max(0, X1 - pad), max(0, Y1 - pad)
    X2, Y2 = min(im.width - 1, X2 + pad), min(im.height - 1, Y2 + pad)
    sub = im.crop((X1, Y1, X2 + 1, Y2 + 1))
    if sub.width < MINW:
        sc = MINW / sub.width
        sub = sub.resize((MINW, int(sub.height * sc)), Image.LANCZOS)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sub.convert("RGB").save(out, "WEBP", quality=88, method=6)
    print("%-34s %dx%d  (crop x%d..%d y%d..%d)" % (out, sub.width, sub.height, X1, X2, Y1, Y2))
    return (X1, Y1, X2, Y2)


if __name__ == "__main__":
    if sys.argv[1] == "--one":
        one(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6])
    else:
        spec = json.load(open(sys.argv[1], encoding="utf-8"))
        for it in spec:
            one(it["key"], it["page"], it["y1"], it["y2"], it["out"], it.get("x1"), it.get("x2"), it.get("pad", PAD))
