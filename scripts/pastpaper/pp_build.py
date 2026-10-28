# -*- coding: utf-8 -*-
"""原卷 -> 页图 + OCR 题号索引

用法:
  python scratch/_pp_build.py            # 全量渲染+OCR
  python scratch/_pp_build.py 2012       # 只做某年

产出:
  scratch/_pp_pages/<key>/p001.jpg ~ pNNN.jpg   (200dpi)
  scratch/_pp_pages/<key>/ocr.json              [{page, W,H, blocks:[{y,x,y2,x2,txt,score}]}]
"""
import json
import os
import sys
import time

import pymupdf
from rapidocr_onnxruntime import RapidOCR

SRC = "D:/生物DSE Past Paper"
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(_ROOT, "scratch", "_pp_pages")
DPI = 200

# key -> pdf 相对路径（卷一）
BOOKS = {
    "2012": "2012/2012 卷一.pdf",
    "2013": "2013/2013 卷一.pdf",
    "2014": "2014/2014 卷一.pdf",
    "2015": "2015/2015 卷一.pdf",
    "2016": "2016/2016 卷一.pdf",
    "2017": "2017/2017 卷一.pdf",
    "2018": "2018/2018 卷一.pdf",
    "2019": "2019/2019 卷一.pdf",
    "2020": "2020/2020 卷一.pdf",
    "2021": "2021/2021 卷一.pdf",
    "2022": "2022/2022 卷一.pdf",
    "2023A": "2023/2023 卷一A.pdf",
    "2023B": "2023/2023 卷一B.pdf",
    "PP": "pp/PP 卷一.pdf",
    "SP": "sp/SP 卷一.pdf",
}

_eng = None


def eng():
    global _eng
    if _eng is None:
        _eng = RapidOCR()
    return _eng


def run(key):
    pdf = os.path.join(SRC, BOOKS[key])
    outdir = os.path.join(OUT, key)
    os.makedirs(outdir, exist_ok=True)
    doc = pymupdf.open(pdf)
    pages = []
    t0 = time.time()
    for i, page in enumerate(doc):
        png = os.path.join(outdir, "p%03d.jpg" % (i + 1))
        if not os.path.exists(png):
            pix = page.get_pixmap(dpi=DPI)
            pix.pil_save(png, quality=92) if hasattr(pix, "pil_save") else pix.save(png)
        from PIL import Image

        with Image.open(png) as im:
            W, H = im.size
        res, _ = eng()(png)
        blocks = []
        for item in res or []:
            box, txt, score = item[0], item[1], item[2]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            blocks.append(
                {
                    "x": int(min(xs)),
                    "y": int(min(ys)),
                    "x2": int(max(xs)),
                    "y2": int(max(ys)),
                    "txt": txt,
                }
            )
        blocks.sort(key=lambda b: (b["y"], b["x"]))
        pages.append({"page": i + 1, "W": W, "H": H, "blocks": blocks})
        print("  %s p%02d  %d blocks  %.1fs" % (key, i + 1, len(blocks), time.time() - t0), flush=True)
    with open(os.path.join(outdir, "ocr.json"), "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)
    print("[done] %s  %d pages  %.0fs" % (key, len(pages), time.time() - t0), flush=True)


if __name__ == "__main__":
    todo = sys.argv[1:] or list(BOOKS)
    for k in todo:
        if os.path.exists(os.path.join(OUT, k, "ocr.json")):
            print("[skip]", k)
            continue
        run(k)
