# -*- coding: utf-8 -*-
"""从官方「評卷參考」扫描件提取**每道大题的总分**。

关键版式事实
------------
2012–2023 与 SP 用的是**旧版**评分参考：得分点后面直接印「（1）」，
而且**每道大题结束的那一行行末印着该题总分**「—— 7 分」：

    5.  (c)  •  顯示氧生產線下的面積代表 24 小時內的食物生產（1）   (1)
             • 顯示二氧化碳碳生產線下的面積代表 24 小時內的食物消耗 (1)
             • 食物生產大過食物消耗，才有淨食物產生（1），這對植物   (1)
             • 因此才有能量供植物生長、生長和生產果實（1）      (1)
             ────────────────────────────────────────────────
                                                                   7 分

**题号在行首、总分在同一行的行末** —— 所以不需要知道小题边界，
单行 OCR 就能把「题号 → 总分」配起来。

PP 练习卷用的是**新版**版式（分值只在右列、题末无总分），本脚本不覆盖，
那部分走 `lq_ref_marks.py` + VLM 的块级 bbox。

用法
----
  python scripts/pastpaper/lq_ref_totals.py                # 全部年份
  python scripts/pastpaper/lq_ref_totals.py 2012 PP        # 指定年份
  python scripts/pastpaper/lq_ref_totals.py --workers 4

产出
----
  scratch/_ref_totals/<年份>.json   {"5": 7, "6": 6, ...}
"""
import argparse
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.environ.get("LQ_PAGES_DIR") or os.path.join(ROOT, "scratch", "_ref_pages")
OUT = os.environ.get("LQ_TOTALS_DIR") or os.path.join(ROOT, "scratch", "_ref_totals")

# 行首题号：'5.' / '6.(a)' / '8'。后面不跟数字，避免把 '5.25' 误判成题 5。
# 只取 1–20，DSE 卷二大题号不会超过这个量级。
QNUM = re.compile(r"^\s*(\d{1,2})\s*[.．]?(?!\d)")
# 行末总分：'7 分' / '7分' / '（7 分）' —— 整行独占时用 fullmatch
TOTAL = re.compile(r"[（(]?\s*(\d{1,2})\s*分\s*[）)]?")
# 右列得分点分值：'(1)' / '（1）' / '2×2'
MARK = re.compile(r"^[（(]?\s*(\d{1,2})\s*[×xX]\s*(\d{1,2})\s*[）)]?$")
MARK1 = re.compile(r"^[（(]\s*(\d{1,2})\s*[）)]$")

_eng = None


def eng():
    global _eng
    if _eng is None:
        from rapidocr_onnxruntime import RapidOCR
        _eng = RapidOCR()
    return _eng


def _lines_of(path, page_h=None):
    """OCR 一页 → 把框按 y 聚成视觉行。page_h 用来剔除页脚区的页码。"""
    res, _ = eng()(path)
    boxes = []
    for box, txt, sc in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        boxes.append({"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys),
                      "t": (txt or "").strip()})
    if not boxes:
        return []
    boxes.sort(key=lambda b: (b["y0"], b["x0"]))
    rows = []
    for b in boxes:
        cy = (b["y0"] + b["y1"]) / 2
        placed = False
        for r in rows:
            rcy = (r["y0"] + r["y1"]) / 2
            if abs(rcy - cy) <= 14:
                r["y0"] = min(r["y0"], b["y0"])
                r["y1"] = max(r["y1"], b["y1"])
                r["x0"] = min(r["x0"], b["x0"])
                r["x1"] = max(r["x1"], b["x1"])
                r["items"].append(b)
                placed = True
                break
        if not placed:
            rows.append({"y0": b["y0"], "y1": b["y1"], "x0": b["x0"],
                         "x1": b["x1"], "items": [b]})
    rows.sort(key=lambda r: r["y0"])
    for r in rows:
        r["items"].sort(key=lambda b: b["x0"])
        r["text"] = " ".join(b["t"] for b in r["items"])
        # 页脚区（页码、dse.life 水印）不算内容
        r["footer"] = bool(page_h and (r["y0"] + r["y1"]) / 2 > page_h * 0.90)
    return rows


def _scan(key):
    """扫一份卷的所有页 → ({题号: 总分}, 每页题号列表)。"""
    d = os.path.join(PAGES, key)
    if not os.path.isdir(d):
        return key, {}, []
    out = {}
    page_qs = []
    cur_q = None          # 当前大题号
    seen_q = []           # 本卷出现过的大题号（按出现顺序）
    for pg in sorted(f for f in os.listdir(d)
                     if f.lower().endswith((".jpg", ".png", ".jpeg"))):
        # p001 是卷一 MC 答案表（题号+答案+答对率），对卷二毫无用处，
        # 而且那种「大片空白 + 稀疏表格」的版面最容易把页码误判成题号。
        if pg.lower() in ("p001.jpg", "p001.png"):
            continue
        path = os.path.join(d, pg)
        import cv2 as _cv2
        im = _cv2.imread(path, _cv2.IMREAD_GRAYSCALE)
        ph = im.shape[0] if im is not None else None
        page_w = im.shape[1] if im is not None else 0
        rows = _lines_of(path, ph)
        page_q = []
        for r in rows:
            if r.get("footer"):
                continue
            head = r["items"][0]
            # ---- 行首题号：必须靠左，且这一行有正文（不是孤零零一个数字）
            m = QNUM.match(head["t"])
            if m and head["x0"] < page_w * 0.30 and len(r["items"]) >= 2:
                q = int(m.group(1))
                # 只在题号「前进」时才切换当前题；否则视为同题的延续
                # （子题行、得分点行也可能以数字开头）
                if cur_q is None or q > cur_q:
                    cur_q = q
                    if q not in seen_q:
                        seen_q.append(q)
                        page_q.append(q)
            # ---- 题末总分：**独占一行**、靠右、格式 '7 分'
            # （2012 版式里总分下面还压着一条横线，所以它单独成行）
            if len(r["items"]) == 1 and cur_q is not None:
                b = r["items"][0]
                mt = TOTAL.fullmatch(b["t"].strip())
                if mt and b["x0"] > page_w * 0.50:
                    v = int(mt.group(1))
                    if cur_q not in out or v > out[cur_q]:
                        out[cur_q] = v
        page_qs.append((pg, page_q))
    return key, out, page_qs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    keys = args.keys
    if not keys:
        base = PAGES
        keys = sorted(d for d in os.listdir(base)
                      if os.path.isdir(os.path.join(base, d)))
    os.makedirs(OUT, exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_scan, k) for k in keys]
        for fu in as_completed(futs):
            key, out, page_qs = fu.result()
            dst = os.path.join(OUT, key + ".json")
            with open(dst, "w", encoding="utf-8") as f:
                json.dump({"totals": out, "pages": page_qs}, f,
                          ensure_ascii=False, indent=1)
            print("  %-5s 题号 %2d 个  总分合计 %3d  %s"
                  % (key, len(out), sum(out.values()),
                     {str(k): out[k] for k in sorted(out)}), flush=True)
            for pg, qs in page_qs:
                if qs:
                    print("        %s  新题号 %s" % (pg, qs), flush=True)


if __name__ == "__main__":
    main()
