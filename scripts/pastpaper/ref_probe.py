# -*- coding: utf-8 -*-
"""探针：比较「整页 OCR 的分值列」与「分值列窄条单独 OCR」的差异。

目的
----
PaddleOCR-VL 读不出评分参考最右侧那一列孤立的小分值数字（它把整列吞进了
正文块），而整页 RapidOCR 虽然能读出大多数，却仍会零星漏读 —— 分值列漏一个
数字，该小题的分就少 1 分，比正文漏字后果严重得多。

这一探针把两种取法并排输出，直接看差在哪儿、差多少，为最终解析策略定依据。

用法：python scripts/pastpaper/ref_probe.py PP p011 p012
"""
import os
import sys

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.path.join(ROOT, "scratch", "_ref_pages")
_eng = None


def eng():
    global _eng
    if _eng is None:
        _eng = RapidOCR()
    return _eng


def ocr(img):
    res, _ = eng()(img)
    out = []
    for box, txt, sc in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append((min(ys), min(xs), max(xs), txt, sc))
    return out


def is_mark(t):
    """分值列里的记号：单个数字，或 '2x2' 这种乘算。"""
    t = t.strip().replace("×", "x").replace("X", "x").replace("*", "x")
    if t.isdigit():
        return int(t)
    if "x" in t:
        a, _, b = t.partition("x")
        if a.isdigit() and b.isdigit():
            return int(a) * int(b)
    return None


def main():
    keys = sys.argv[1:] or ["PP"]
    for key in keys:
        d = os.path.join(PAGES, key)
        pages = sorted(f for f in os.listdir(d) if f.lower().endswith(".jpg"))
        for pg in pages:
            path = os.path.join(d, pg)
            im = Image.open(path)
            w, h = im.size
            full = ocr(path)
            # 整页取法：x 靠右 + 是数字记号
            a = sorted((y, x0, is_mark(t)) for y, x0, x1, t, sc in full
                       if x0 > w * 0.855 and is_mark(t) is not None)
            # 窄条取法：裁出分值列后放大再 OCR
            strip = im.crop((int(w * 0.855), int(h * 0.06), int(w * 0.93), int(h * 0.94)))
            strip = strip.resize((strip.width * 3, strip.height * 3), Image.LANCZOS)
            sp = os.path.join(ROOT, "scratch", "_tmp_strip.png")
            strip.save(sp)
            sb = ocr(sp)
            b = sorted((y / 3.0 + h * 0.06, is_mark(t)) for y, x0, x1, t, sc in sb
                       if is_mark(t) is not None)
            av = [v for _, _, v in a]
            bv = [v for _, v in b]
            print("%s %s  整页:%d(%s)  窄条:%d(%s)" % (
                key, pg, len(av), sum(av), len(bv), sum(bv)))
            if len(av) != len(bv) or sum(av) != sum(bv):
                print("   整页 y:", [round(y) for y, _, _ in a])
                print("   窄条 y:", [round(y) for y, _ in b])
    if os.path.exists(os.path.join(ROOT, "scratch", "_tmp_strip.png")):
        os.remove(os.path.join(ROOT, "scratch", "_tmp_strip.png"))


if __name__ == "__main__":
    main()
