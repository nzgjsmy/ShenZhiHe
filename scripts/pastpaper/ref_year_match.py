# -*- coding: utf-8 -*-
"""核对：官方「参考答案.pdf」里的卷一 MC 答案表，和我们 `_mc_answers.json`
里的同一年数据，是否真的是同一份卷。

为什么必须先做这一步
--------------------
在做「用官方评分参考校正卷二分值」之前，得先确认**参考 PDF 和我们收录的
年份是同一份卷**。卷一 MC 答案表带「答对率」（%），那是极强的手指纹 ——
两个年份的答案/答对率不可能同时吻合十几题。

用法
----
  python scripts/pastpaper/ref_year_match.py            # 全部参考 PDF
  python scripts/pastpaper/ref_year_match.py 2012 PP    # 指定

产出
----
  scratch/_ref_mcmatch.json
      {"2012": {"matched": "2012", "score": 18, "total": 20}, ...}
"""
import json
import os
import re
import sys

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.path.join(ROOT, "scratch", "_ref_pages")
MCA = os.path.join(ROOT, "data", "bio", "_mc_answers.json")
OUT = os.path.join(ROOT, "scratch", "_ref_mcmatch.json")

_eng = None


def eng():
    global _eng
    if _eng is None:
        from rapidocr_onnxruntime import RapidOCR
        _eng = RapidOCR()
    return _eng


def ocr_text(path):
    res, _ = eng()(path)
    items = []
    for box, txt, sc in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append((min(ys), min(xs), (txt or "").strip()))
    items.sort()
    return items


RE_NUM = re.compile(r"^(\d{1,2})\.?$")
RE_ANS = re.compile(r"^([A-D])")
RE_PCT = re.compile(r"^\(?(\d{1,3})\s*%?\)?$")


def parse_mc_table(items):
    """从 MC 答案表里抽 (题号, 答案字母, 答对率%) 三元组。

    扫描件里表格被拆成独立小框，版式是「题号 | 答案 | 答对率」三列、
    而且左右两栏并排（1–20 在左、21–40 在右）。所以先按 y 聚成行，
    再在**每一行内**按 x 顺序把「题号→答案→答对率」配起来；
    一行里出现两组时，左右各算一条。
    """
    cells = []
    for y, x, t in items:
        t = (t or "").replace(" ", "")
        if not t:
            continue
        m = RE_NUM.match(t)
        if m and int(m.group(1)) <= 60:
            cells.append((y, x, "num", m.group(1)))
            continue
        m = RE_ANS.match(t)
        if m and len(t) <= 2:
            cells.append((y, x, "ans", m.group(1)))
            continue
        m = RE_PCT.match(t)
        if m and "%" in t:
            cells.append((y, x, "pct", m.group(1)))
    if not cells:
        return []
    cells.sort()
    # 按 y 聚行
    rows = []
    for c in cells:
        if rows and abs(c[0] - rows[-1][-1][0]) <= 13:
            rows[-1].append(c)
        else:
            rows.append([c])
    out = []
    for r in rows:
        r.sort(key=lambda c: c[1])
        # 行内按 x 顺序扫：题号 后跟 答案 后跟 百分比
        i = 0
        while i < len(r):
            if r[i][2] == "num":
                num = r[i][3]
                ans = pct = None
                j = i + 1
                while j < len(r):
                    if r[j][2] == "ans" and ans is None:
                        ans = r[j][3]
                    elif r[j][2] == "pct" and pct is None:
                        pct = r[j][3]
                    j += 1
                if ans and pct is not None:
                    try:
                        out.append((int(num), ans, int(pct)))
                    except ValueError:
                        pass
                i = j
            else:
                i += 1
    out.sort()
    return out


def main():
    keys = sys.argv[1:] or sorted(
        d for d in os.listdir(PAGES)
        if os.path.isdir(os.path.join(PAGES, d)))
    mc = json.load(open(MCA, encoding="utf-8"))["years"]
    mc_map = {}
    for y, lst in mc.items():
        mc_map[y] = {str(e["qnum"]): (e.get("answer"), e.get("pct")) for e in lst}

    result = {}
    for k in keys:
        d = os.path.join(PAGES, k)
        rows = []
        for pg in sorted(f for f in os.listdir(d)
                         if f.lower().endswith((".jpg", ".png")))[:3]:
            items = ocr_text(os.path.join(d, pg))
            t = parse_mc_table(items)
            if len(t) >= 8:
                rows = t
                break
        if not rows:
            print("  %-5s 没找到可解析的 MC 答案表" % k)
            result[k] = {"matched": None, "score": 0, "total": 0}
            continue
        best = (None, 0)
        for y, m in mc_map.items():
            hit = 0
            for q, ans, pct in rows:
                e = m.get(str(q))
                if e and e[0] == ans and (e[1] is None or int(e[1]) == pct):
                    hit += 1
            if hit > best[1]:
                best = (y, hit)
        result[k] = {"matched": best[0], "score": best[1], "total": len(rows)}
        print("  %-5s 解析 %2d 题 → 最匹配年份 %-5s 命中 %2d/%2d"
              % (k, len(rows), best[0], best[1], len(rows)), flush=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
