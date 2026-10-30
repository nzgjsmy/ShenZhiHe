# -*- coding: utf-8 -*-
"""在**原卷页图**里按关键词定位某道题所在页，并抽出该页印着的分值。

为什么要有这个
--------------
《評卷參考》给的是「評卷員視角」的得分點，右列分值與小題的歸屬要靠 OCR 猜；
**原卷上每道小題右邊直接印著分值**，是最權威、最直接的來源 —— 但原卷是掃描件，
PDF 文本層只有 2013／2015／2017／SP 的部分頁可用，所以只能對頁圖做 OCR。

用法
----
    python scripts/pastpaper/lq_orig_marks.py find 2018 益生菌
    python scripts/pastpaper/lq_orig_marks.py dump 2018 p007
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.path.join(ROOT, "scratch", "_lq_pages")

_ENG = None


def eng():
    global _ENG
    if _ENG is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENG = RapidOCR()
    return _ENG


def boxes_of(path):
    """→ [{x0,y0,x1,y1,t}]"""
    res, _ = eng()(path)
    out = []
    for box, txt, sc in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append({"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
                    "t": (txt or "").strip()})
    out.sort(key=lambda b: (b["y0"], b["x0"]))
    return out


def rows_of(bs, gap=12):
    """把框按 y 聚成視覺行。"""
    rows = []
    for b in bs:
        cy = (b["y0"] + b["y1"]) / 2
        hit = None
        for r in rows:
            if abs((r["y0"] + r["y1"]) / 2 - cy) <= gap:
                hit = r
                break
        if hit is None:
            rows.append({"y0": b["y0"], "y1": b["y1"], "items": [b]})
        else:
            hit["y0"] = min(hit["y0"], b["y0"])
            hit["y1"] = max(hit["y1"], b["y1"])
            hit["items"].append(b)
    rows.sort(key=lambda r: r["y0"])
    for r in rows:
        r["items"].sort(key=lambda b: b["x0"])
    return rows


# 原卷上印著的分值：(3 分) / (3分) / （3 分） / 3分
MARK = re.compile(r"^[\(（]?\s*(\d{1,2})\s*分\s*[\)）]?$")
# 小題標記：(i) (ii) (1) (2)
SUB = re.compile(r"^[\(（]\s*([ivx]{1,4}|\d{1,2})\s*[\)）]?$", re.I)


def cmd_find(year, *kws):
    d = os.path.join(PAGES, year)
    if not os.path.isdir(d):
        print("沒有 %s 的頁圖" % year)
        return
    pages = sorted(f for f in os.listdir(d) if f.lower().endswith(".jpg"))
    keys = list(kws)
    for pg in pages:
        txt = "".join(b["t"] for b in boxes_of(os.path.join(d, pg)))
        hit = [k for k in keys if k in txt]
        if hit:
            print("  %-5s %s  命中 %s" % (year, pg, "、".join(hit)))


def cmd_dump(year, page):
    """打印一页的所有行（含分值与小題標記）。"""
    if not page.lower().endswith((".jpg", ".png", ".jpeg")):
        page += ".jpg"
    path = os.path.join(PAGES, year, page)
    bs = boxes_of(path)
    for r in rows_of(bs):
        parts = []
        for b in r["items"]:
            tag = ""
            if MARK.match(b["t"]):
                tag = "★分值"
            elif SUB.match(b["t"]):
                tag = "·標記"
            parts.append("%s%s" % (b["t"][:44], ("  <" + tag + ">") if tag else ""))
        print("  y=%5d | %s" % (r["y0"], "  ||  ".join(parts)))


def cmd_sheet(year, *pages):
    """一次 dump 多頁，只看含分值／小題標記的行 —— 用來逐頁人工核對分值。"""
    for pg in pages:
        if not pg.lower().endswith((".jpg", ".png", ".jpeg")):
            pg += ".jpg"
        path = os.path.join(PAGES, year, pg)
        if not os.path.exists(path):
            print("== %s %s 缺" % (year, pg))
            continue
        print("===== %s %s =====" % (year, pg))
        for r in rows_of(boxes_of(path)):
            line = []
            has = False
            for b in r["items"]:
                t = b["t"]
                if MARK.match(t):
                    t = "【%s 分】" % MARK.match(t).group(1)
                    has = True
                elif SUB.match(t):
                    t = "〈%s〉" % SUB.match(t).group(1)
                    has = True
                line.append(t[:52])
            if has:
                print("   " + "  ".join(line))


def cmd_check(year):
    """一卷一屏：先列我們的題目與子題分值，再列原卷各頁印著的分值。"""
    import json
    lq = json.load(open(os.path.join(ROOT, "data", "bio", "_lq.json"),
                        encoding="utf-8"))
    qs = lq["years"].get(year, [])
    print("========== 我們的資料（%s）==========" % year)
    for q in qs:
        subs = " ".join("%s%s=%s" % (s.get("no"),
                                     "" if (s.get("level") or 1) <= 1 else "",
                                     s.get("marks"))
                        for s in (q.get("subqs") or []))
        print("  %-6s p%-4s 總=%-4s | %s" % (q["qnum"], q.get("page"),
                                             q.get("marksTotal"), subs))
    d = os.path.join(PAGES, year)
    pages = sorted(f for f in os.listdir(d) if f.lower().endswith(".jpg"))
    print("========== 原卷印刷分值 ==========")
    for pg in pages:
        lines = []
        for r in rows_of(boxes_of(os.path.join(d, pg))):
            line = []
            has = False
            for b in r["items"]:
                t = b["t"]
                if MARK.match(t):
                    t = "【%s分】" % MARK.match(t).group(1)
                    has = True
                elif SUB.match(t):
                    t = "〈%s〉" % SUB.match(t).group(1)
                    has = True
                line.append(t[:44])
            if has:
                lines.append("  " + "  ".join(line))
        if lines:
            print("--- %s ---" % pg)
            for l in lines:
                print(l)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "find":
        cmd_find(sys.argv[2], *sys.argv[3:])
    elif cmd == "dump":
        cmd_dump(sys.argv[2], sys.argv[3])
    elif cmd == "sheet":
        cmd_sheet(sys.argv[2], *sys.argv[3:])
    elif cmd == "check":
        cmd_check(sys.argv[2])


if __name__ == "__main__":
    main()
