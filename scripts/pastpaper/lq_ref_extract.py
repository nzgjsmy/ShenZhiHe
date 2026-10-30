# -*- coding: utf-8 -*-
"""从官方「評卷參考」的**卷二**部分，提取每道大题各小题的分值。

前置认知（都是踩过坑换来的）
--------------------------
1. 参考 PDF 里**卷一和卷二混在一起**。2012 的 p001–p005 是卷一（MC 答案表 +
   卷一评分参考），p006–p009 才是卷二。按页眉「卷二」或页脚 `BIO 2-x` 区分。
2. **版式分两代**：
   * 旧版（2012–2023、SP）：得分点分值印在正文里，**每行最右端**还有一个
     `(1)`；**每道大题结束处独占一行印着 `N 分` 的总分**。
   * 新版（PP）：分值只在最右列，且是**裸数字**（`1` / `2` / `2×2`），
     题末**没有**总分标记。
3. **左右两份重复**：旧版正文里和右列都有 `(1)`，只能取右列那份，否则翻倍。
4. 页码（`43`、`46`…）在页脚，会被误当成题号；页脚要单独剔掉。

产出
----
  scratch/_ref_extract/<年份>.json
      {"1": {"total": 11,
              "parts": {"a": {"subs": {"i": 4, "ii": 3}, "total": 7},
                        "b": {"subs": {"i": 1, "ii": 2}, "total": 3}}},
       ...}
"""
import json
import os
import re
import sys
from collections import Counter

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.environ.get("LQ_PAGES_DIR") or os.path.join(ROOT, "scratch", "_ref_pages")
OUT = os.environ.get("LQ_EXTRACT_DIR") or os.path.join(ROOT, "scratch", "_ref_extract")

QNUM = re.compile(r"^\s*(\d{1,2})\s*[.．]\s*$")
# 一个框里可能只装一个标记，也可能装 '(a)(i)' 这种两个连排
ONE_MARK = re.compile(r"^\s*[（(]\s*([a-z]{1,3}|\d{1,2})\s*[）)]\s*$")
ONLY_MARKS = re.compile(r"^\s*(?:[（(]\s*[a-z]{1,3}\s*[）)]\s*)+$")
MARK = re.compile(r"^\s*[（(]?\s*(\d{1,2})\s*[）)]?\s*$")
MARKX = re.compile(r"^\s*[（(]?\s*(\d{1,2})\s*[×xX]\s*(\d{1,2})\s*[）)]?\s*$")
# 「(最高 3)」= 该小题的**满分上限**，出现在小题的最后一行 —— 比逐得分点
# 累加可靠得多：一个得分点占两行时，累加会多算 1 分。
MAXMK = re.compile(r"^\s*[（(]?\s*最高\s*(\d{1,2})\s*[）)]?\s*$")
TOTAL = re.compile(r"^\s*[（(]?\s*(\d{1,2})\s*分\s*[）)]?\s*$")
ROMAN = re.compile(r"^[ivx]{1,4}$", re.I)

_eng = None


def eng():
    global _eng
    if _eng is None:
        from rapidocr_onnxruntime import RapidOCR
        _eng = RapidOCR()
    return _eng


def _rows(path):
    """OCR 一页 → 按 y 聚成行，并剔除页脚。"""
    import cv2
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    page_w = img.shape[1] if img is not None else 0
    res, _ = eng()(path)
    boxes = []
    for box, txt, sc in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        boxes.append({"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys),
                      "t": (txt or "").strip()})
    if not boxes:
        return [], page_w, 0
    boxes.sort(key=lambda b: (b["y0"], b["x0"]))
    rows = []
    for b in boxes:
        cy = (b["y0"] + b["y1"]) / 2
        hit = None
        for r in rows:
            if abs((r["y0"] + r["y1"]) / 2 - cy) <= 14:
                hit = r
                break
        if hit is None:
            rows.append({"y0": b["y0"], "y1": b["y1"], "items": [b]})
        else:
            hit["y0"] = min(hit["y0"], b["y0"])
            hit["y1"] = max(hit["y1"], b["y1"])
            hit["items"].append(b)
    rows.sort(key=lambda r: r["y0"])
    ph = max(b["y1"] for b in boxes)
    for r in rows:
        r["items"].sort(key=lambda b: b["x0"])
    rows = [r for r in rows
            if (r["y0"] + r["y1"]) / 2 <= ph * 0.90]
    return rows, page_w, ph


def is_paper2(text):
    """这一页属于卷二吗？"""
    if "卷二" in text or "試卷二" in text or "试卷二" in text:
        return True
    if "PAPER 2" in text.upper():
        return True
    # 页脚 'BIO 2-3' / 'PP-DSE-BIO 2-5'
    if re.search(r"BIO\s*2\s*-\s*\d+", text, re.I):
        return True
    return False


def parse_head_marks(text):
    """从一个框里解析 part / 子题标记。

    '(a)'    → part='a'
    '(i)'    → sub='i'   （罗马数字是小题号，不是部分）
    '(a)(i)' → part='a', sub='i'
    '(1)'    → sub='#1'
    '(ii）下列任何两项：' → sub='ii'   （标记后面常跟着题干文字）
    """
    text = (text or "").strip()
    if not text or not text[0] in "（(":
        return None, None
    toks = re.findall(r"[（(]\s*([a-z]{1,3}|\d{1,2})\s*[）)]", text)
    if not toks:
        return None, None
    part = sub = None
    for t in toks:
        if t.isdigit():
            sub = "#" + t
        elif ROMAN.match(t):
            sub = t.lower()
        else:
            part = t.lower()
    return part, sub


def extract_year(key, pages):
    """pages: 该卷卷二部分的页码列表。

    输出的结构刻意保留**顺序**，因为官方扫描件里的小题标记经常被 OCR 读错
    （'(ii)' → '(i)'），直接采信 OCR 会把小题边界弄乱。所以：
      · part 与小题一律**按出现顺序**编号，不信 OCR 读到的罗马数字；
      · OCR 读到的原始标记只作为参考存在 'ocrMark' 里，供人工核对。
    """
    res = {}
    cur_q = None
    cur_part = None
    part_seq = 0
    sub_seq = 0
    subsub_seq = 0
    cur_sub = None
    cur_subsub = None

    def bucket():
        if cur_q is None:
            return None
        q = res.setdefault(cur_q, {"total": None, "parts": [], "sum": 0})
        if not q["parts"] or q["parts"][-1]["part"] != cur_part:
            q["parts"].append({"part": cur_part, "subs": [], "sum": 0})
        return q["parts"][-1]

    def subbucket():
        p = bucket()
        if p is None:
            return None
        if not p["subs"] or p["subs"][-1]["idx"] != cur_sub:
            p["subs"].append({"idx": cur_sub, "ocrMark": None, "marks": None,
                               "sum": 0, "subsubs": []})
        return p["subs"][-1]

    for pg in pages:
        path = os.path.join(PAGES, key, pg)
        rows, page_w, ph = _rows(path)
        # 右列 x：所有行末「像分值」的框的 x 众数
        xs = Counter()
        for r in rows:
            for b in r["items"][::-1]:
                if (MARK.match(b["t"]) or MARKX.match(b["t"])
                        or MAXMK.match(b["t"])):
                    xs[b["x0"]] += 1
                    break
        col_x = xs.most_common(1)[0][0] if xs else None

        for r in rows:
            if not r["items"]:
                continue
            head = r["items"][0]
            ht = head["t"]
            # ---- 独占一行的 'N 分' = 该大题总分
            row_txt = "".join(b["t"] for b in r["items"]).strip()
            if len(r["items"]) <= 3 and head["x0"] > page_w * 0.40:
                mt = TOTAL.match(row_txt)
                if mt:
                    if cur_q is not None:
                        q = res.setdefault(cur_q, {"total": None, "parts": [],
                                                  "sum": 0})
                        if q["total"] is None or int(mt.group(1)) > q["total"]:
                            q["total"] = int(mt.group(1))
                    continue
            # ---- 行首：题号 / 部分 / 小题
            m = QNUM.match(ht)
            if m and head["x0"] < page_w * 0.30 and len(r["items"]) >= 2:
                cur_q = m.group(1)
                cur_part = None
                cur_sub = None
                cur_subsub = None
                part_seq = 0
                sub_seq = 0
                subsub_seq = 0
                res.setdefault(cur_q, {"total": None, "parts": [], "sum": 0})
            # 行首可能有两三个小标记框：'(a)' '(i)'。
            # 注意这不能放进题号分支的 else 里 —— 题号行后面往往紧跟
            # '(a)(i)' 这样的标记框，两个都要处理。
            for b in r["items"][:3]:
                if b["x0"] > page_w * 0.30:
                    break
                if QNUM.match(b["t"]):
                    continue
                p, s = parse_head_marks(b["t"])
                if p is None and s is None:
                    continue
                if p:
                    cur_part = p
                    part_seq += 1
                    sub_seq = 0
                    subsub_seq = 0
                    cur_sub = None
                    cur_subsub = None
                    bucket()
                if s:
                    if s.startswith("#"):
                        subsub_seq += 1
                        cur_subsub = s
                    else:
                        sub_seq += 1
                        subsub_seq = 0
                        cur_sub = sub_seq
                        cur_subsub = None
                    sb = subbucket()
                    if sb is not None and sb["ocrMark"] is None:
                        sb["ocrMark"] = b["t"]
                break
            # ---- 右列分值
            if col_x is None or cur_q is None or cur_sub is None:
                continue
            for b in r["items"][::-1]:
                # 「(最高 N)」印得比右列略靠左，单独放宽一点容差
                tol = 90 if MAXMK.match(b["t"]) else 60
                if abs(b["x0"] - col_x) > tol:
                    continue
                t = b["t"]
                v = None
                is_max = False
                mm = MAXMK.match(t)
                if mm:
                    v = int(mm.group(1))
                    is_max = True
                else:
                    mm = MARKX.match(t)
                    if mm:
                        v = int(mm.group(1)) * int(mm.group(2))
                    else:
                        mm = MARK.match(t)
                        if mm:
                            v = int(mm.group(1))
                if v is None:
                    break
                sb = subbucket()
                if sb is None:
                    break
                if is_max:
                    # 「(最高 N)」是小题满分，一个小题只有一个；先到先得
                    if sb["marks"] is None:
                        sb["marks"] = v
                else:
                    sb["sum"] += v            # 逐得分点累加（可能跨行多算）
                break
    # 收尾：算每题 / 每 part 的分值
    for q in res.values():
        qsum = 0
        for p in q["parts"]:
            psum = 0
            for s in p["subs"]:
                s["marks"] = s["marks"] if s["marks"] is not None else s["sum"]
                psum += s["marks"]
            p["sum"] = psum
            qsum += psum
        q["sum"] = qsum
    return res


def _run_one(key):
    d = os.path.join(PAGES, key)
    if not os.path.isdir(d):
        return key, None, []
    pages = []
    for pg in sorted(f for f in os.listdir(d)
                     if f.lower().endswith((".jpg", ".png"))):
        p = os.path.join(ROOT, "scratch", "_ref_text", key,
                         pg.replace(".jpg", ".txt"))
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        if is_paper2(txt):
            pages.append(pg)
    if not pages:
        return key, None, []
    return key, extract_year(key, pages), pages


def main():
    import argparse
    from concurrent.futures import ProcessPoolExecutor, as_completed
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    keys = args.keys
    base = PAGES
    if not keys:
        keys = sorted(d for d in os.listdir(base)
                      if os.path.isdir(os.path.join(base, d)))
    os.makedirs(OUT, exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_run_one, k): k for k in keys}
        for fu in as_completed(futs):
            key, res, pages = fu.result()
            dst = os.path.join(OUT, key + ".json")
            if res is None:
                print("  %-5s 没找到卷二页" % key, flush=True)
                continue
            if os.path.exists(dst) and not args.force:
                print("  %-5s 已存在，跳过" % key, flush=True)
                res = json.load(open(dst, encoding="utf-8"))
            else:
                with open(dst, "w", encoding="utf-8") as f:
                    json.dump(res, f, ensure_ascii=False, indent=1)
            tot = sum(v["sum"] for v in res.values())
            print("  %-5s 卷二页 %s  题 %d 个  分值合计 %d" %
                  (key, [p[:4] for p in pages], len(res), tot), flush=True)
            for q in sorted(res, key=lambda z: int(z) if z.isdigit() else 99):
                v = res[q]
                desc = []
                for p in v["parts"]:
                    subs = ", ".join("%s%s=%s" % (
                        (s["ocrMark"] or "?")[:6],
                        "" if s["marks"] == s["sum"] else "*",
                        s["marks"]) for s in p["subs"])
                    desc.append("%s[%s]=%d" % (p["part"], subs, p["sum"]))
                print("      题%s  总分=%-5s 小题和=%-3d %s"
                      % (q, v["total"], v["sum"], " ".join(desc)), flush=True)


if __name__ == "__main__":
    main()
