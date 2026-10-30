# -*- coding: utf-8 -*-
"""官方《評卷參考》的得分點，和我們題解稿列的得分點對照。

為什麼要對照
------------
分值對上了，不代表**得分點列全了**。舉個實例：2012 4(a)(ii)(2) 官方是 **3 分**
（三個得分點：以含抗生素的瓊脂培養基培養／只有取得具功能質粒的細胞才能生存／
因為它們的質粒有抗生素抗性基因），而我們題解稿只列了**後兩條** ——
分值表裡寫的 2 分也是照著自己漏的那條算的。這種漏點，靠比對分值發現不了，
只能拿官方的得分點**逐條**核。

做法
----
官方側：每個小题的得分點數 = 該小题右列分值之和（每個得分點 1 分時）；
        另存每個得分點的**文字**，供人工核對。
我們側：題解稿裡每個小题標題下「（1 分）」的出現次數。

輸出
----
  · 只報「我們比官方少列得分點」的題（漏點，最需要修）
  · 逐題列出官方該小题的得分點原文，方便照著補

用法
----
  python scripts/pastpaper/lq_ref_points.py            # 全年份
  python scripts/pastpaper/lq_ref_points.py 2012 2013  # 指定
"""
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIDES = os.path.join(ROOT, "scripts", "pastpaper", "lq_guides")
EXTRACT = os.path.join(ROOT, "scratch", "_ref_extract")
LQ = os.path.join(ROOT, "data", "bio", "_lq.json")

SEC = re.compile(r"^@@@\s*(\S+)\s*$")
# 小题標題：**（i）(1) 文字（4 分）**；分值待核對的寫成 **（i）文字（分值待核對）**
HEAD = re.compile(r"^\*\*[（(]([^）)]*)[）)](.*)$")
MARK1 = re.compile(r"[（(]\s*1\s*分\s*[）)]")
# 題解稿標題裡自己標的分值：'（4 分）' 或 '（分值待核對）'
OWNDECL = re.compile(r"[（(]\s*(\d+)\s*分\s*[）)]")
PENDING = re.compile(r"分值待核對|分值待核")


def parse_guide(path):
    """→ {题号: [[marker, 标题, 得分点数], ...]}（单遍掃描）

    得分點的計數靠「(1 分)」的出現次數 —— 題解稿裡每列一個得分點就標一次。
    """
    out = {}
    cur = None
    cur_idx = -1
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            m = SEC.match(s)
            if m:
                cur = m.group(1).strip()
                out.setdefault(cur, [])
                cur_idx = -1
                continue
            if cur is None:
                continue
            if s.startswith("**"):
                mm = HEAD.match(s)
                if mm:
                    out[cur].append([re.sub(r"\s+", "", mm.group(1)),
                                     mm.group(2), 0])
                    cur_idx = len(out[cur]) - 1
                    continue
            if cur_idx >= 0:
                out[cur][cur_idx][2] += len(MARK1.findall(line))
    return out


def qkey_parts(qnum):
    m = re.match(r"^\s*(\d+)\s*[（(]\s*([a-z])\s*[）)]", qnum or "")
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^\s*(\d+)", qnum or "")
    return (m.group(1), None) if m else (None, None)


def main():
    keys = sys.argv[1:] or None
    lq = json.load(open(LQ, encoding="utf-8"))
    total_issue = 0
    for year, qs in lq["years"].items():
        if keys and year not in keys:
            continue
        gp = os.path.join(GUIDES, year + ".txt")
        ep = os.path.join(EXTRACT, year + ".json")
        if not (os.path.exists(gp) and os.path.exists(ep)):
            continue
        guides = parse_guide(gp)
        ext = json.load(open(ep, encoding="utf-8"))
        for q in qs:
            qn, part = qkey_parts(q.get("qnum"))
            oq = ext.get(qn)
            if not oq:
                continue
            op = None
            for p in oq["parts"]:
                if p["part"] == part:
                    op = p
                    break
            if op is None:
                continue
            gh = guides.get(q.get("qnum")) or guides.get(qn) or []
            if not gh:
                continue
            o_subs = op["subs"]
            for i, (mk, body, cnt) in enumerate(gh):
                if i >= len(o_subs):
                    break
                os_ = o_subs[i]
                if os_["marks"] is None:
                    continue
                # 我們題解稿自己標的分值（'（4 分）'）；標「分值待核對」的算 None
                dm = OWNDECL.search(body)
                ours = int(dm.group(1)) if dm else (None if PENDING.search(body) else 0)
                tag = ""
                if ours is None:
                    tag = "待核對"
                elif ours != os_["marks"]:
                    tag = "不符"
                else:
                    continue
                print("  %s %-6s 小题#%d  官方 %d 分 / 我們標 %s  %s"
                      % (year, q.get("qnum"), i + 1, os_["marks"],
                         ("待核對" if ours is None else "%d 分" % ours), tag))
                print("      %s" % body[:74])
                total_issue += 1
    print()
    print("題解稿標註與官方不一致的小题：%d 處" % total_issue)


if __name__ == "__main__":
    main()
