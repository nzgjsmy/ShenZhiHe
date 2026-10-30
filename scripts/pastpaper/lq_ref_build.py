#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把官方「参考答案.pdf」转成页图，供 lq_vl.py 识别。

背景
----
卷二（LQ）的**官方评分参考（Marking Scheme）**在每年的「参考答案.pdf」里。
这些 PDF 同样是扫描件：
  · 2019  文本层只有 "Provided by dse.life" 水印
  · 2022  文本层 0 字符
  · 2012  文本层有 15647 字符但是乱码（扫描件自定义编码）
所以只能走 OCR。

本脚本只做「PDF → 页图」，识别交给 lq_vl.py（用环境变量指向本脚本的输出）：
    python scripts/pastpaper/lq_ref_build.py            # 生成全部年份页图
    LQ_PAGES_DIR=scratch/_ref_pages LQ_OUT_DIR=scratch/_ref_vl \\
        python scripts/pastpaper/lq_vl.py 2019 2020

页数：参考答案比卷二原卷薄（9–14 页/年，含卷一 MC 答案与卷二评分参考）。
"""
import os
import sys

import pymupdf

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = "D:/生物DSE Past Paper"
OUT = os.path.join(_ROOT, "scratch", "_ref_pages")

YEARS = ["2012", "2013", "2014", "2015", "2016", "2017", "2018",
         "2019", "2020", "2021", "2022", "2023", "PP", "SP"]

DPI = 200


def find_pdf(year):
    """在年份目录里找参考答案 PDF。

    2023 有两份：「2023 参考答案(原卷).pdf」與「2023 参考答案.pdf」——
    後者才是答案，前者「原卷」是題目卷的掃描副本，必須排除。
    """
    d = os.path.join(SRC, year)
    if not os.path.isdir(d):
        return None
    cands = []
    for f in os.listdir(d):
        if not f.lower().endswith(".pdf"):
            continue
        if ("参考" not in f) and ("參考" not in f):
            continue
        if "原卷" in f or "原題" in f:
            continue
        cands.append(f)
    if not cands:
        return None
    # 优先「参考答案」（不带后缀）
    cands.sort(key=lambda f: (len(f), f))
    return os.path.join(d, cands[0])


def main():
    only = sys.argv[1:]
    years = [y for y in YEARS if not only or y in only]
    os.makedirs(OUT, exist_ok=True)

    for y in years:
        pdf = find_pdf(y)
        if not pdf:
            print("[miss] %s 找不到参考答案 PDF" % y)
            continue
        outdir = os.path.join(OUT, y)
        os.makedirs(outdir, exist_ok=True)
        doc = pymupdf.open(pdf)
        # 已有页图就跳过（可续跑）
        done = len([f for f in os.listdir(outdir) if f.endswith(".jpg")])
        if done >= len(doc):
            print("[skip] %s 已有 %d 页" % (y, done))
            continue
        for i in range(len(doc)):
            dst = os.path.join(outdir, "p%03d.jpg" % (i + 1))
            if os.path.exists(dst):
                continue
            pix = doc[i].get_pixmap(dpi=DPI)
            pix.pil_save(dst, quality=92)
        print("[ok]   %s  %d 页  <- %s" % (y, len(doc), os.path.basename(pdf)))
        doc.close()

    total = sum(len([f for f in os.listdir(os.path.join(OUT, y)) if f.endswith(".jpg")])
                 for y in YEARS if os.path.isdir(os.path.join(OUT, y)))
    print("\n页图输出：%s  共 %d 页" % (OUT, total))


if __name__ == "__main__":
    main()
