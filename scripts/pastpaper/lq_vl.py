# -*- coding: utf-8 -*-
"""LQ（卷二）PaddleOCR-VL 端到端识别。

为什么需要它
------------
PP-OCR（v4/v6）在这批扫描件上会**成片漏检**：2019 p4 的 `2(a)` 题干首行
（含题号那行，共三行）两版引擎都没识别出来，块 y 从 313 直接跳到 517。
调参数、提 DPI 都救不回（已实测排除）。

PaddleOCR-VL（0.9B，端到端 VLM）实测同一页：
  · 那三行**完整读出**，`2(a)` 保留在行首
  · 表格输出为 `<table>` HTML（PP-OCR 完全没识别）
  · 全页 11 块，一个不漏，且每块是完整语义单元（题号在行首）

代价：CPU 上约 **4 分钟/页**（0.9B 自回归生成），模型加载约 80 秒。
→ 所以本脚本设计为「可中断续跑」，适合挂后台批量跑。

用法
----
  python scripts/pastpaper/lq_vl.py 2019
  python scripts/pastpaper/lq_vl.py 2019 2021 2020

产出
----
  scratch/_lq_vl/<key>/pNNN.json   每页一个，含 parsing_res_list
  scratch/_lq_vl/<key>/_done.json  进度标记

依赖
----
  pip install paddlepaddle paddleocr "paddlex[ocr]"
  首次运行会自动下载 PP-DocLayoutV3 + PaddleOCR-VL-1.6（约 2GB）
  模型缓存在 C:\\Users\\<user>\\.paddlex\\official_models\\
"""
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 页图输入目录与识别产物输出目录。默认是卷二（LQ）原卷；
# 用环境变量可以指向别的来源 —— 例如官方「参考答案.pdf」的评分参考：
#   LQ_PAGES_DIR=scratch/_ref_pages LQ_OUT_DIR=scratch/_ref_vl \
#       python scripts/pastpaper/lq_vl.py 2019
PAGES = os.environ.get("LQ_PAGES_DIR") or os.path.join(_ROOT, "scratch", "_lq_pages")
OUT = os.environ.get("LQ_OUT_DIR") or os.path.join(_ROOT, "scratch", "_lq_vl")
# 起始頁。官方「參考答案.pdf」的前幾頁是**卷一 MC 答案表**（題號+答案+答對率），
# 對本站毫無用處（MC 答案早已在 _mc_answers.json 裡），而且那種「大片空白 + 稀疏表格」
# 的版面反而是 VLM 最慢的一類。實測跳過它們可省 15 頁、約 1.5 小時。
#   · 一般年份：p001 = MC 答案表 → 卷二評分參考從 p002 起
#   · PP：p001 = 封面聲明、p002 = MC 答案表 → 從 p003 起
FIRST_PAGE = int(os.environ.get("LQ_FIRST_PAGE", "1"))

# 各年份的页数（与 _lq_pages/<key>/pNNN.jpg 一致）
PAGE_COUNT = {
    "2012": 9, "2013": 7, "2014": 6, "2015": 7, "2016": 7, "2017": 7,
    "2018": 9, "2019": 10, "2020": 11, "2021": 8, "2022": 10, "2023": 11,
    "PP": 30, "SP": 9,
}

_pipe = None


def pipe():
    global _pipe
    if _pipe is None:
        from paddleocr import PaddleOCRVL
        t0 = time.time()
        _pipe = PaddleOCRVL()
        print("[init] 模型加载 %.1fs" % (time.time() - t0), flush=True)
    return _pipe


def run_page(key, n):
    src = os.path.join(PAGES, key, "p%03d.jpg" % n)
    if not os.path.exists(src):
        return None
    dst = os.path.join(OUT, key, "p%03d.json" % n)
    if os.path.exists(dst):
        return "skip"
    t0 = time.time()
    out = pipe().predict(src)
    payload = None
    for res in out:
        d = None
        for attr in ("json", "to_json"):
            v = getattr(res, attr, None)
            if v is None:
                continue
            d = v() if callable(v) else v
            break
        if d is None:
            continue
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except Exception:
                continue
        payload = d
    if payload is None:
        return None
    os.makedirs(os.path.join(OUT, key), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    blocks = (payload.get("res") or payload).get("parsing_res_list", [])
    print("  %s p%02d  %2d blocks  %.0fs" % (key, n, len(blocks), time.time() - t0),
          flush=True)
    return "ok"


def run_year(key):
    total = PAGE_COUNT.get(key, 0)
    if not total:
        # PAGE_COUNT 表里没有的来源（例如参考资料），按实际页图数推导
        d = os.path.join(PAGES, key)
        if os.path.isdir(d):
            total = len([f for f in os.listdir(d)
                         if f.lower().endswith((".jpg", ".png"))])
        if not total:
            print("[miss] 未知年份且没有页图：", key)
            return
    os.makedirs(os.path.join(OUT, key), exist_ok=True)
    t0 = time.time()
    done = 0
    for n in range(FIRST_PAGE, total + 1):
        r = run_page(key, n)
        if r == "ok":
            done += 1
        elif r is None:
            print("  %s p%02d  失败" % (key, n), flush=True)
    print("[done] %s  %d/%d 页  用时 %.0f 分钟" % (
        key, done, total, (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    keys = sys.argv[1:] or ["2019"]
    for k in keys:
        run_year(k)
