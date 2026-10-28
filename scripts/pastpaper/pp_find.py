# -*- coding: utf-8 -*-
"""在 OCR 结果里按关键词找位置

用法: python scratch/_pp_find.py 2018 氣泡的釋出停止
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(_ROOT, "scratch", "_pp_pages")


def main():
    key = sys.argv[1]
    kws = sys.argv[2:]
    pgs = json.load(open(os.path.join(BASE, key, "ocr.json"), encoding="utf-8"))
    for pg in pgs:
        for b in pg["blocks"]:
            if any(k in b["txt"] for k in kws):
                print("p%02d y=%4d..%4d x=%4d..%4d  %s" % (pg["page"], b["y"], b["y2"], b["x"], b["x2"], b["txt"][:60]))


if __name__ == "__main__":
    main()
