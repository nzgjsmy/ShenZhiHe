# -*- coding: utf-8 -*-
"""官方「評卷參考」扫描件 → 每道大题各小题的分值。

背景
----
DSE 评分参考的**最右侧有一列孤立的分值数字**（每个得分点右侧一个 1、2 或
`2×2`）。这一列是判定「每小题几分」的唯一权威来源 —— 原卷只印大题总分，
小题分值只能从评分参考反推。

为什么要两个引擎
--------------
* **PaddleOCR-VL**（此前用的）：把整页读成语义块，但**右列的小数字被整列
  吞进了正文块**，完全读不出来 —— 而这恰恰是最关键的数据。
* **RapidOCR 整页**：能读出右列大部分数字，但会**成片漏整行正文**。
* **OpenCV 连通域**：不依赖识别，只按几何把右列的孤立数字抠出来 —— 漏读
  率最低。实测 PP p011：连通域 20 个、整页 OCR 20 个，y 坐标逐一对上。

所以做法是**几何为主、OCR 为辅**：连通域定位每个数字的位置，RapidOCR 只
负责读它的值（单个小数字，识别率极高）。

用法
----
  python scripts/pastpaper/lq_ref_marks.py                 # 全部年份
  python scripts/pastpaper/lq_ref_marks.py 2019 PP         # 指定年份
  python scripts/pastpaper/lq_ref_marks.py --workers 6     # 指定并发

产出
----
  scratch/_ref_marks/<key>/pNNN.json
      { "marks": [{"y":326,"v":1,"x":1455,"src":"cc"}],
        "lines": [{"y0":317,"y1":355,"x0":163,"x1":281,"t":"1.(a) (i)"}] }
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.environ.get("LQ_PAGES_DIR") or os.path.join(ROOT, "scratch", "_ref_pages")
OUT = os.environ.get("LQ_MARKS_DIR") or os.path.join(ROOT, "scratch", "_ref_marks")

# 右列数字的横向范围（页宽比例）。不同年份版面略有出入，取一个略宽的带，
# 再靠连通域的尺寸约束把正文残留挡掉。
COL_X0 = 0.855
COL_X1 = 0.935
# 页眉页脚要排除（「分数」表头、页码、dse.life 水印）
Y_TOP = 0.055
Y_BOT = 0.945

_eng = None


def eng():
    global _eng
    if _eng is None:
        from rapidocr_onnxruntime import RapidOCR
        _eng = RapidOCR()
    return _eng


def _num_value(t):
    """把 OCR 文本读成分值。'1'→1、'2x2'→4、'3'→3；读不出返回 None。"""
    if t is None:
        return None
    t = t.strip().replace("×", "x").replace("X", "x").replace("×", "x")
    t = t.replace("＊", "*").replace("*", "x")
    if t.isdigit():
        return int(t)
    if "x" in t:
        a, _, b = t.partition("x")
        if a.strip().isdigit() and b.strip().isdigit():
            return int(a) * int(b)
    return None


def _ocr_items(img):
    res, _ = eng()(img)
    items = []
    for box, txt, sc in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append({
            "y0": min(ys), "y1": max(ys), "x0": min(xs), "x1": max(xs),
            "t": txt, "s": float(sc),
        })
    return items


def _components(col):
    """在右列窄带里找「数字状」连通域。

    数字高度 19-20px、宽 5-6px（「分数」表头是 25x26，靠尺寸和位置排除）。
    这里放宽到 4-30 x 8-45，再靠 y 范围与横向位置做二次过滤。
    """
    bw = cv2.adaptiveThreshold(col, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 31, 12)
    n, _, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if 3 <= w <= 32 and 7 <= h <= 46 and area >= 18:
            out.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h),
                        "area": int(area)})
    return out


def process(key, pg):
    path = os.path.join(PAGES, key, pg)
    dst = os.path.join(OUT, key, pg.replace(".jpg", ".json"))
    if os.path.exists(dst):
        return key, pg, "skip", 0, 0
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return key, pg, "noimg", 0, 0
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    x0, x1 = int(w * COL_X0), int(w * COL_X1)
    y0, y1 = int(h * Y_TOP), int(h * Y_BOT)

    comps = _components(gray[y0:y1, x0:x1])
    for c in comps:
        c["y"] += y0
        c["x"] += x0

    items = _ocr_items(img)
    # 右列里的 OCR 数字（用于给连通域匹配数值）
    ocr_right = []
    for it in items:
        if it["x0"] >= x0 and it["y0"] >= y0 and it["y1"] <= y1:
            v = _num_value(it["t"])
            if v is not None:
                ocr_right.append({"y": (it["y0"] + it["y1"]) / 2, "v": v,
                                  "x0": it["x0"], "x1": it["x1"], "t": it["t"],
                                  "s": it["s"]})

    # 连通域 ←→ OCR 数值 匹配（按 y 就近，容差 12px）
    marks = []
    used = set()
    for c in sorted(comps, key=lambda z: z["y"]):
        best, bd = None, 1e9
        for i, o in enumerate(ocr_right):
            if i in used:
                continue
            d = abs(o["y"] - c["y"])
            if d < bd:
                best, bd = i, d
        if best is not None and bd <= 14:
            used.add(best)
            marks.append({"y": c["y"], "v": ocr_right[best]["v"],
                          "x": c["x"], "src": "cc+ocr"})
        else:
            # 连通域找到了但 OCR 没读到值 —— 记下来，由后续人工/重识别处理
            marks.append({"y": c["y"], "v": None, "x": c["x"], "src": "cc"})
    # OCR 读到但连通域没覆盖的（罕见，数字太淡导致二值化断裂）
    for i, o in enumerate(ocr_right):
        if i not in used:
            marks.append({"y": int(o["y"]), "v": o["v"], "x": o["x0"],
                          "src": "ocr"})
    marks.sort(key=lambda z: z["y"])

    lines = []
    for it in items:
        if it["x0"] < x0:  # 只留左半边正文
            lines.append({"y0": int(it["y0"]), "y1": int(it["y1"]),
                          "x0": int(it["x0"]), "x1": int(it["x1"]),
                          "t": it["t"], "s": round(it["s"], 2)})
    lines.sort(key=lambda z: z["y0"])

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"marks": marks, "lines": lines}, f, ensure_ascii=False)
    nv = sum(m["v"] for m in marks if m["v"] is not None)
    return key, pg, "ok", len(marks), nv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    keys = args.keys
    if not keys:
        base = PAGES
        keys = sorted(d for d in os.listdir(base)
                      if os.path.isdir(os.path.join(base, d)))
    tasks = []
    for k in keys:
        d = os.path.join(PAGES, k)
        if not os.path.isdir(d):
            continue
        for pg in sorted(f for f in os.listdir(d)
                         if f.lower().endswith((".jpg", ".png", ".jpeg"))):
            tasks.append((k, pg))
    print("[plan] %d 页 / %d workers" % (len(tasks), args.workers), flush=True)

    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(process, k, p) for k, p in tasks]
        for fu in as_completed(futs):
            key, pg, st, n, nv = fu.result()
            done += 1
            print("  %-4s %s  %-6s marks=%2d sum=%3d  [%d/%d]"
                  % (key, pg, st, n, nv, done, len(tasks)), flush=True)


if __name__ == "__main__":
    main()
