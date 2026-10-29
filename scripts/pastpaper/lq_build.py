# -*- coding: utf-8 -*-
"""LQ（卷二）原卷 -> 页图 + OCR

背景
----
生物 DSE 卷二 = 长题目（LQ / Part A、B、C）。本站此前只收录了卷一（MC），
446 道全是选择题。本脚本把卷二也渲染成页图并 OCR，为解析 LQ 题结构做准备。

为什么必须 OCR（不能直接抽 PDF 文本层）
--------------------------------------
实测 13 份卷二 PDF 的文本层：
  2012/2013/2015/2017/sp  有几千字符，但内容是**乱码**（扫描件自带自定义编码，
      形如 ``)ii'`` / ``j,fc;j,fc;`` / ``[[``），不是真文字；
  2014/2016/2018–2022/pp 每页仅约 20 字符（页眉水印）；
  2023 完全没有文本层（纯图像）。
→ 结论：卷二一律走 OCR，文本层不可用。

依赖（Python 3.12；3.15 无 onnxruntime 轮子）
----------------------------------------------
  C:\\Users\\guomi\\AppData\\Local\\Python\\pythoncore-3.12-64\\python.exe -m pip install \\
      rapidocr-onnxruntime opencv-python numpy pymupdf pillow

用法
----
  python scripts/pastpaper/lq_build.py            # 全部
  python scripts/pastpaper/lq_build.py 2019       # 只做某年
  python scripts/pastpaper/lq_build.py 2019 pp    # 多个

产出
----
  scratch/_lq_pages/<key>/p001.jpg … pNNN.jpg   (200dpi)
  scratch/_lq_pages/<key>/ocr.json               [{page,W,H,blocks:[{x,y,x2,y2,txt}]}]

可中断续跑：已存在 ocr.json 的年份自动跳过。
"""
import json
import os
import sys
import time

import pymupdf
from rapidocr_onnxruntime import RapidOCR

SRC = "D:/生物DSE Past Paper"
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(_ROOT, "scratch", "_lq_pages")
DPI = 200

# key -> PDF 相对路径（卷二 = LQ）
BOOKS = {
    "2012": "2012/2012 卷二.pdf",
    "2013": "2013/2013 卷二.pdf",
    "2014": "2014/2014 卷二.pdf",
    "2015": "2015/2015 卷二.pdf",
    "2016": "2016/2016 卷二.pdf",
    "2017": "2017/2017 卷二.pdf",
    "2018": "2018/2018 卷二.pdf",
    "2019": "2019/2019 卷二.pdf",
    "2020": "2020/2020 卷二.pdf",
    "2021": "2021/2021 卷二.pdf",
    "2022": "2022/2022 卷二.pdf",
    "2023": "2023/2023 卷二.pdf",
    "PP": "pp/PP 卷二.pdf",
    "SP": "sp/SP 卷二.pdf",
}

_eng = None


def eng():
    global _eng
    if _eng is None:
        _eng = RapidOCR()
    return _eng


def run(key):
    pdf = os.path.join(SRC, BOOKS[key])
    if not os.path.exists(pdf):
        print("[miss] %s -> %s" % (key, pdf))
        return
    outdir = os.path.join(OUT, key)
    os.makedirs(outdir, exist_ok=True)
    doc = pymupdf.open(pdf)
    pages = []
    t0 = time.time()
    from PIL import Image

    for i, page in enumerate(doc):
        png = os.path.join(outdir, "p%03d.jpg" % (i + 1))
        if not os.path.exists(png):
            pix = page.get_pixmap(dpi=DPI)
            if hasattr(pix, "pil_save"):
                pix.pil_save(png, quality=92)
            else:
                pix.save(png)
        with Image.open(png) as im:
            W, H = im.size
        res, _ = eng()(png)
        blocks = []
        for item in res or []:
            box, txt = item[0], item[1]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            blocks.append({
                "x": int(min(xs)),
                "y": int(min(ys)),
                "x2": int(max(xs)),
                "y2": int(max(ys)),
                "txt": txt,
            })
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
