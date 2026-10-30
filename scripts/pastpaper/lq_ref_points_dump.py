# -*- coding: utf-8 -*-
"""把官方《評卷參考》的**得分點原文**逐題導出成可對照的 Markdown。

為什麼要導出
------------
自動抽取只能可靠地拿到「每道大題、每個部分的總分」，**小题級的對齊**不可靠
（官方掃描件裡 '(ii)' 常被 OCR 讀成 '(i)'、'(b) (i)' 的括號會讀殘、三級結構
'(i) → (1)(2)' 會被打平），所以「官方第 2 個小题」與「我們題解稿第 2 個
標題」並不保證是同一個題。

但**得分點原文**是可以直接拿來用的：把官方右列有分值標記的那幾行正文
原文抓出來，按位置歸到各個小題，一份對照清單就出來了 —— 誰來讀都能直接
照著補題解。

用法
----
  python scripts/pastpaper/lq_ref_points_dump.py            # 全年份
  python scripts/pastpaper/lq_ref_points_dump.py 2012 PP    # 指定

產出
----
  scratch/_ref_points/<年份>.md
"""
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "pastpaper"))
PAGES = os.environ.get("LQ_PAGES_DIR") or os.path.join(ROOT, "scratch", "_ref_pages")
OUT = os.path.join(ROOT, "scratch", "_ref_points")
GUIDES = os.path.join(ROOT, "scripts", "pastpaper", "lq_guides")

from lq_ref_extract import _rows, QNUM, MARK, MARKX, MAXMK, TOTAL, parse_head_marks  # noqa


def dump_year(key):
    d = os.path.join(PAGES, key)
    if not os.path.isdir(d):
        return None
    pages = sorted(f for f in os.listdir(d)
                   if f.lower().endswith((".jpg", ".png")))
    # 只留卷二页：顶部有卷别标记，或页脚有 BIO 2-x
    from lq_ref_extract import is_paper2
    p2 = []
    for pg in pages:
        tp = os.path.join(ROOT, "scratch", "_ref_text", key,
                         pg.replace(".jpg", ".txt"))
        if not os.path.exists(tp):
            continue
        with open(tp, encoding="utf-8") as f:
            if is_paper2(f.read()):
                p2.append(pg)
    if not p2:
        return None

    cur_q = None
    cur_part = None
    cur_sub = None
    known_qs = set()
    blocks = []          # [(题号, part, sub, [得分点行])]

    def cur_block():
        if not blocks or blocks[-1][:3] != (cur_q, cur_part, cur_sub):
            blocks.append((cur_q, cur_part, cur_sub, []))
        return blocks[-1]

    for pg in p2:
        rows, page_w, ph = _rows(os.path.join(d, pg))
        xs = Counter()
        for r in rows:
            for b in r["items"][::-1]:
                if MARK.match(b["t"]) or MARKX.match(b["t"]) or MAXMK.match(b["t"]):
                    xs[b["x0"]] += 1
                    break
        col_x = xs.most_common(1)[0][0] if xs else None
        prev_text = ""      # 最近一段沒有分值標記的正文（得分點常跨行）
        for r in rows:
            if not r["items"]:
                continue
            head = r["items"][0]
            row_txt = "".join(b["t"] for b in r["items"]).strip()
            if len(r["items"]) <= 3 and head["x0"] > page_w * 0.40:
                if TOTAL.match(row_txt):
                    continue
            for b in r["items"][:3]:
                if b["x0"] > page_w * 0.30:
                    break
                txt = b["t"]
                mq = QNUM.match(txt)
                if mq:
                    q = mq.group(1)
                    if cur_q is None:
                        ok = True
                    elif q in known_qs:
                        ok = True
                    elif int(q) < int(cur_q):
                        ok = True
                    else:
                        ok = (q == str(int(cur_q) + 1))
                    if not ok:
                        txt = ""
                    else:
                        cur_q = q
                        known_qs.add(q)
                        cur_part = None
                        cur_sub = None
                        txt = txt[mq.end():]
                    if not txt.strip():
                        continue
                p, s = parse_head_marks(txt)
                if p is None and s is None:
                    continue
                if p:
                    cur_part = p
                    cur_sub = None
                if s:
                    cur_sub = s
                break
            if col_x is None or cur_q is None:
                continue
            for b in r["items"][::-1]:
                if abs(b["x0"] - col_x) > 90:
                    continue
                v = None
                mm = MARKX.match(b["t"])
                if mm:
                    v = int(mm.group(1)) * int(mm.group(2))
                else:
                    mm = MAXMK.match(b["t"])
                    if mm:
                        v = int(mm.group(1))
                    else:
                        mm = MARK.match(b["t"])
                        if mm:
                            v = int(mm.group(1))
                if v is None:
                    break
                # 得分點正文 = 同一行裡非右列的那段文字
                body = " ".join(x["t"] for x in r["items"]
                                if abs(x["x0"] - col_x) > 90)
                body = re.sub(r"\s+", " ", body).strip()
                bl = cur_block()
                # 得分點常跨兩行：正文的後半段（'體。'）單獨一行，
                # 分值標在上一行末尾。這時把上一行的正文接過來，
                # 並用 ↳ 標出「這行是接續推定，正文可能不完整」。
                if not body:
                    body = ("↳ " + prev_text) if prev_text else "（正文未讀出）"
                else:
                    prev_text = body
                bl[3].append((v, body))
                break
            else:
                # 這行沒有分值 → 它的正文可能是上一個得分點的續行
                t = " ".join(x["t"] for x in r["items"]
                             if abs(x["x0"] - col_x) > 90)
                t = re.sub(r"\s+", " ", t).strip()
                if t:
                    prev_text = t
    return blocks


def main():
    keys = sys.argv[1:] or None
    base = PAGES
    if not keys:
        keys = sorted(d for d in os.listdir(base)
                      if os.path.isdir(os.path.join(base, d)))
    os.makedirs(OUT, exist_ok=True)
    for k in keys:
        blocks = dump_year(k)
        if not blocks:
            print("  %-5s 无卷二页" % k)
            continue
        path = os.path.join(OUT, k + ".md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# %s 官方《評卷參考》得分點原文\n\n" % k)
            f.write("> 逐題列出右列有分值標記的原文行，可直接用來核對／補寫題解。\n")
            f.write("> 「（N）」是官方給該得分點的分數。\n\n")
            for q, part, sub, pts in blocks:
                if not pts:
                    continue
                total = sum(v for v, _ in pts)
                f.write("## %s(%s) %s  — 合計 %d 分\n\n" %
                        (q, part or "?", sub or "", total))
                for v, body in pts:
                    f.write("- （%d）%s\n" % (v, body))
                f.write("\n")
        print("  %-5s %d 個小題組 → %s" %
              (k, len([b for b in blocks if b[3]]), path))


if __name__ == "__main__":
    main()
