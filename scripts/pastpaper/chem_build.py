# -*- coding: utf-8 -*-
"""化学原卷 -> 页图 + OCR（仿 scripts/pastpaper/pp_build.py，路径换成 G 盘化学卷）

用法:
  python scripts/pastpaper/chem_build.py 2012          # 只做 2012 卷一 + MS
  python scripts/pastpaper/chem_build.py 2012 --no-ms  # 只做卷一

产出:
  scratch/_chem_pages/<key>/p001.jpg ...         (200 dpi 页图)
  scratch/_chem_pages/<key>/ocr.json             [{page,W,H,blocks:[...]}]
  scratch/_chem_pages/<key>/ms/p001.jpg ...
  scratch/_chem_pages/<key>/ms/ocr.json

已存在的页图会跳过；ocr.json 每次重算。
"""
import io
import json
import os
import sys
import time

import pymupdf
from rapidocr_onnxruntime import RapidOCR

SRC = (r"G:\.shortcut-targets-by-id\1j-j-2gxdrFRBPz-Pnuv31FRi8n_Fx_MA"
       r"\DSE Past Paper（持續更新中）\7. 化學")
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(_ROOT, "scratch", "_chem_pages")
DPI = 200

# key -> (卷一 PDF 相对路径列表, MS PDF 相对路径)
BOOKS = {
    "2012": (["2012/2012 P1.pdf"], "2012/2012 MS.pdf"),
    "2013": (["2013/2013 P1.pdf"], "2013/2013 MS.pdf"),
    "2014": (["2014/2014 P1.pdf"], "2014/2014 MS.pdf"),
    "2015": (["2015/2015 P1.pdf"], "2015/2015 MS.pdf"),
    "2016": (["2016/2016 P1.pdf"], "2016/2016 MS.pdf"),
    "2017": (["2017/2017 P1.pdf"], "2017/2017 MS.pdf"),
    "2018": (["2018/2018 P1.pdf"], "2018/2018 MS.pdf"),
    "2019": (["2019/2019 P1.pdf"], "2019/2019 MS.pdf"),
    "2020": (["2020/2020 P1.pdf"], "2020/2020 MS.pdf"),
    "2021": (["2021/2021 P1.pdf"], "2021/2021 MS.pdf"),
    "2022": (["2022/2022 P1.pdf"], "2022/2022 MS.pdf"),
    "2023": (["2023/2023 P1.pdf"], "2023/2023 MS.pdf"),
    "2024": (["2024/2024 P1.pdf"], "2024/2024 MS.pdf"),
    "2025": (["2025/2025 P1A.pdf", "2025/2025 P1B.pdf"], "2025/2025 MS+CP.pdf"),
    "PP": (["Practice Paper/PP P1.pdf"], "Practice Paper/PP MS.pdf"),
    "SP": (["Sample Paper/SP P1.pdf"], None),
}

_eng = None


def eng():
    global _eng
    if _eng is None:
        _eng = RapidOCR()
    return _eng


def build(pdfs, outdir, label):
    os.makedirs(outdir, exist_ok=True)
    from PIL import Image

    pages = []
    n = 0
    t0 = time.time()
    for pdf_rel in pdfs:
        pdf = os.path.join(SRC, pdf_rel.replace("/", os.sep))
        if not os.path.exists(pdf):
            print("  !! missing:", pdf)
            continue
        doc = pymupdf.open(pdf)
        for page in doc:
            n += 1
            jpg = os.path.join(outdir, "p%03d.jpg" % n)
            if not os.path.exists(jpg):
                pix = page.get_pixmap(dpi=DPI)
                if hasattr(pix, "pil_save"):
                    pix.pil_save(jpg, quality=92)
                else:
                    pix.save(jpg)
                print("  render p%03d" % n, flush=True)
            with Image.open(jpg) as im:
                W, H = im.size
            res, _ = eng()(jpg)
            blocks = []
            for item in res or []:
                box, txt, score = item[0], item[1], item[2]
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                blocks.append({
                    "x": int(min(xs)), "y": int(min(ys)),
                    "x2": int(max(xs)), "y2": int(max(ys)),
                    "txt": txt, "score": float(score),
                })
            blocks.sort(key=lambda b: (b["y"], b["x"]))
            pages.append({"page": n, "W": W, "H": H, "blocks": blocks})
            print("  ocr p%03d: %d blocks" % (n, len(blocks)), flush=True)
        doc.close()
    with io.open(os.path.join(outdir, "ocr.json"), "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=1)
    print("  %s: %d pages, %.1fs" % (label, len(pages), time.time() - t0))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    keys = sys.argv[1:]
    no_ms = "--no-ms" in keys
    keys = [k for k in keys if not k.startswith("--")]
    for key in keys:
        if key not in BOOKS:
            print("unknown key:", key)
            continue
        qpdfs, mspdf = BOOKS[key]
        base = os.path.join(OUT, key)
        print("== %s 卷一 ==" % key)
        build(qpdfs, base, key + " Q")
        if mspdf and not no_ms:
            print("== %s MS ==" % key)
            build([mspdf], os.path.join(base, "ms"), key + " MS")


if __name__ == "__main__":
    main()
