# -*- coding: utf-8 -*-
"""从页图裁剪区域，方便读图

用法:
  python scratch/_pp_crop.py 2012 4 1000 2324 out.png     # 绝对像素
  python scratch/_pp_crop.py 2012 4 q11                   # 按题号自动定界
  python scratch/_pp_crop.py 2012 4-5 q11                # 跨页
加 --scale 1.6 可放大输出
"""
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from _pp_locate import locate  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(_ROOT, "scratch", "_pp_pages")


def crop(key, page, y1, y2, out, scale=1.0):
    im = Image.open(os.path.join(BASE, key, "p%03d.jpg" % page))
    y2 = min(y2, im.height)
    box = (0, max(0, y1), im.width, y2)
    sub = im.crop(box)
    if scale != 1.0:
        sub = sub.resize((int(sub.width * scale), int(sub.height * scale)), Image.LANCZOS)
    sub.save(out)
    print(out, sub.size)


def auto(key, pages_spec, qnum, out, scale=1.0):
    """按题号定界：从该题题号到下一题题号（可能跨页）"""
    pages, seq = locate(key)
    byn = {m["n"]: m for m in seq}
    if qnum not in byn:
        raise SystemExit("找不到 q%d" % qnum)
    start = byn[qnum]
    nxt = byn.get(qnum + 1)
    p1 = start["page"]
    y1 = max(0, start["y"] - 18)
    if nxt and nxt["page"] == p1:
        y2 = nxt["y"] - 18
        im = Image.open(os.path.join(BASE, key, "p%03d.jpg" % p1))
        sub = im.crop((0, y1, im.width, min(y2, im.height)))
        if scale != 1.0:
            sub = sub.resize((int(sub.width * scale), int(sub.height * scale)), Image.LANCZOS)
        sub.save(out)
        print(out, sub.size)
        return
    # 跨页：拼接
    ims = []
    for p in range(p1, (nxt["page"] if nxt else len(pages)) + 1):
        im = Image.open(os.path.join(BASE, key, "p%03d.jpg" % p))
        top = y1 if p == p1 else 0
        bot = (nxt["y"] - 18) if (nxt and p == nxt["page"]) else im.height
        ims.append(im.crop((0, top, im.width, bot)))
    W = max(i.width for i in ims)
    Hh = sum(i.height for i in ims)
    canvas = Image.new("RGB", (W, Hh), "white")
    y = 0
    for i in ims:
        canvas.paste(i, (0, y))
        y += i.height
    if scale != 1.0:
        canvas = canvas.resize((int(canvas.width * scale), int(canvas.height * scale)), Image.LANCZOS)
    canvas.save(out)
    print(out, canvas.size)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scale = 1.0
    for a in sys.argv[1:]:
        if a.startswith("--scale"):
            scale = float(a.split("=")[1])
    key, page, spec, out = args[0], args[1], args[2], args[3] if len(args) > 3 else "scratch/_pp_ocr/crop.png"
    if spec.startswith("q"):
        auto(key, page, int(spec[1:]), out, scale)
    else:
        y1, y2 = spec.split("-")
        crop(key, int(page), int(y1), int(y2), out, scale)
