# -*- coding: utf-8 -*-
"""把图片拼成网格，便于快速目检

用法:
  python scratch/_pp_sheet.py out.png 640 site/img/pp/2016/f19.webp site/img/pp/2016/f20.webp ...
  python scratch/_pp_sheet.py out.png 640 --year 2016        # 某年全部
"""
import os
import sys

from PIL import Image, ImageDraw

PAD = 10
LABEL = 22


def build(out, cell_w, files, max_h=520):
    ims = []
    for f in files:
        im = Image.open(f).convert("RGB")
        sc = cell_w / im.width
        w, h = cell_w, int(im.height * sc)
        if h > max_h:
            sc2 = max_h / im.height
            w, h = int(im.width * sc2), max_h
        ims.append((os.path.basename(os.path.dirname(f)) + "/" + os.path.basename(f), im.resize((w, h), Image.LANCZOS)))
    cols = max(1, min(3, int(2000 / (cell_w + PAD))))
    rows = (len(ims) + cols - 1) // cols
    cell_h = max(h for _, (_, h) in [(0, (0, i.height)) for _, i in ims]) + LABEL + PAD
    W = cols * (cell_w + PAD) + PAD
    H = rows * cell_h + PAD
    canvas = Image.new("RGB", (W, H), "#f5f5f5")
    d = ImageDraw.Draw(canvas)
    x = y = PAD
    for i, (name, im) in enumerate(ims):
        c, r = i % cols, i // cols
        x = PAD + c * (cell_w + PAD)
        y = PAD + r * cell_h
        canvas.paste(im, (x, y + LABEL))
        d.rectangle([x, y + LABEL, x + im.width - 1, y + LABEL + im.height - 1], outline="#bbb")
        d.text((x + 2, y + 4), name, fill="#c00")
    canvas.save(out)
    print(out, canvas.size, len(ims), "imgs")


if __name__ == "__main__":
    out, cw = sys.argv[1], int(sys.argv[2])
    if sys.argv[3] == "--year":
        y = sys.argv[4]
        d = "site/img/pp/" + y
        files = [os.path.join(d, f) for f in sorted(os.listdir(d))]
    else:
        files = sys.argv[3:]
    build(out, cw, files)
