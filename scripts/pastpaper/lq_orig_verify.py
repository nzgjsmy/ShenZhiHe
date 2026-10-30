# -*- coding: utf-8 -*-
"""用**原卷印刷分值**核對我們的分值 —— 全量校驗。

為什麼要有這條路
--------------
《評卷參考》只給「評卷員視角」的得分點，小題分值要靠 OCR 反推，會漏讀；
原卷上**每道小題右邊直接印著分值**，是最權威、最直接的來源。

實測教訓
--------
「子題分值和 == marksTotal 所以沒問題」這個檢查是**自欺** —— 兩者都來自同一批
漏讀的資料。2014 甲部就是例子：1(a) 的 (i) 與 1(b) 的 (iv) 原卷各印 4 分、5 分，
我們記成 None，整個甲部少了 9 分，而內部一致性檢查完全看不出來。

為什麼先做「全卷總量」
--------------------
原卷的題號行經常被 OCR 漏讀（2014 p004 的「2(b)」整個沒認出來），
小題級自動對齊不可靠。但「(N 分)」這種括號格式在正文裡不會出現，
只可能是印刷分值 —— 所以**先把全卷的印刷分值加總**，再與我們的 marksTotal 總和比，
信噪比最高、誤判最少。有差異的卷再人工逐題細分。

用法
----
    python scripts/pastpaper/lq_orig_verify.py                # 全量
    python scripts/pastpaper/lq_orig_verify.py 2014 2018      # 指定年份
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "pastpaper"))

from lq_orig_marks import boxes_of, rows_of, PAGES  # noqa: E402

LQ = os.path.join(ROOT, "data", "bio", "_lq.json")
OUT = os.path.join(ROOT, "scratch", "_orig_verify.json")

# 原卷上印著的分值：(3 分) / (3分) / （3 分） / 3分
MARK = re.compile(r"^[\(（]?\s*(\d{1,2})\s*分\s*[\)）]?$")
# 小題標記：(i) (ii) (1) (2)
SUB = re.compile(r"^[\(（]?\s*([ivx]{1,4}|\d{1,2})\s*[\)）]?$", re.I)


def scan_year(year):
    """→ {'sum': 全卷印刷分值總和, 'items': [(分值, 頁, y)], 'pages': {...}}

    關鍵：原卷上**分值常常單獨成行**（題幹太長時被擠到下一行行末），
    所以標記行沒有分值時，要往下一行找那個孤立的分值框。
    但每個分值框**只能歸屬一次** —— 否則「標記行借下一行的分值」與
    「分值行自己也有分值」會重複計數（實測會讓 2012 多算 50 分）。
    """
    d = os.path.join(PAGES, year)
    if not os.path.isdir(d):
        return None
    pages = sorted(f for f in os.listdir(d) if f.lower().endswith(".jpg"))
    items = []
    for pg in pages:
        bs = boxes_of(os.path.join(d, pg))
        ph = max((b["y1"] for b in bs), default=0)
        rows = rows_of(bs)
        used = set()
        for i, r in enumerate(rows):
            if ph and r["y0"] > ph * 0.90:
                continue
            hit = None
            # A) 本行末尾的分值
            for b in reversed(r["items"]):
                if id(b) in used:
                    continue
                mm = MARK.match(b["t"])
                if mm:
                    hit = (b, int(mm.group(1)))
                    break
            # B) 本行是小題標記行、下一行只有孤立的分值框
            if hit is None and i + 1 < len(rows):
                has_mark = any(SUB.match(b["t"]) for b in r["items"][:2])
                nxt = rows[i + 1]
                if has_mark and len(nxt["items"]) <= 2 \
                        and not (ph and nxt["y0"] > ph * 0.90) \
                        and (nxt["y0"] - r["y1"]) < 110:
                    for b in reversed(nxt["items"]):
                        if id(b) in used:
                            continue
                        mm = MARK.match(b["t"])
                        if mm:
                            hit = (b, int(mm.group(1)))
                            break
            if hit:
                used.add(id(hit[0]))
                items.append((hit[1], pg, r["y0"]))
    items.sort(key=lambda x: (x[1], x[2]))
    return {"sum": sum(v for v, _, _ in items), "items": items}


def main():
    years = sys.argv[1:] or None
    lq = json.load(open(LQ, encoding="utf-8"))
    if not years:
        years = sorted(lq["years"].keys())

    report = {}
    bad = []
    for y in years:
        got = scan_year(y)
        if not got:
            print("  %-5s 沒有頁圖" % y)
            continue
        qs = lq["years"].get(y, [])
        ours = sum(q.get("marksTotal") or 0 for q in qs)
        nsub = sum(1 for q in qs for s in (q.get("subqs") or [])
                   if s.get("marks") not in (None, ""))
        report[y] = {"orig": got["sum"], "ours": ours, "nOrig": len(got["items"]),
                     "nOurs": nsub, "items": got["items"]}
        flag = ""
        if got["sum"] != ours:
            flag = "  ← 差 %+d" % (ours - got["sum"])
            bad.append(y)
        print("  %-5s 原卷印刷分值 %3d 分（%3d 個標記） vs 我們 %3d 分（%3d 個子題有分值）%s"
              % (y, got["sum"], len(got["items"]), ours, nsub, flag))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("\n總分不一致的年份：%s" % ("、".join(bad) if bad else "無"))
    print("報告：%s" % OUT)


if __name__ == "__main__":
    main()
