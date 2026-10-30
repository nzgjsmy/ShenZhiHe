# -*- coding: utf-8 -*-
"""诊断：题解稿里的分值 与 _lq.json 里的 subqs 能不能顺序对齐。

为什么需要这个
--------------
`data/bio/_lq.json` 里 90 个子题的 `marks` 是空的，但分值其实一直写在
`scripts/pastpaper/lq_guides/<年份>.txt` 的题解稿里 —— 每小题标题形如
`**（ii）(1) 雌激素對 FSH 的效應（4 分）**`，每个得分点还带「（1 分）」。

题解稿的小题标记带**完整层级路径**（`(i)(1)`），而 `_lq.json` 的 `subqs.no`
只存了末级（`1`）、`level` 也标错过（2019 1(a) 里 `(ii)(1)` 被记成 level=1，
与前面的 `(i)` 撞号）。所以**不能按 no 匹配，只能按顺序对齐**，再用两边
已知的分值互相校验。

本脚本只做诊断，不改数据：
  · 逐题比较「题解稿标题行数」与「subqs 中可计分条目数」
  · 列出对不齐的题，以及两边已知分值的冲突

用法：python scripts/pastpaper/lq_marks_diag.py [年份]
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIDES = os.path.join(ROOT, "scripts", "pastpaper", "lq_guides")
LQ = os.path.join(ROOT, "data", "bio", "_lq.json")

# 标题行：**（i）(1) 文字（4 分）**
HEAD = re.compile(r"^\*\*[（(]([^）)]*)[）)](.*?)[（(]\s*(\d+)\s*分\s*[）)]\*\*")
# 章节标题：@@@ 1(a)
SEC = re.compile(r"^@@@\s*(\S+)\s*$")


def parse_guide(path):
    """→ {题号: [(marker, marks, title)]}，marker 形如 'i(1)' / 'iii'。"""
    out = {}
    cur = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = SEC.match(line.strip())
            if m:
                cur = m.group(1).strip()
                out.setdefault(cur, [])
                continue
            if cur is None:
                continue
            m = HEAD.match(line.strip())
            if m:
                marker = re.sub(r"\s+", "", m.group(1))
                out[cur].append((marker, int(m.group(3)), m.group(2).strip()))
    return out


def qkey(qnum):
    """'1(a)' → '1a'。"""
    return re.sub(r"[^\w]", "", qnum or "")


def scorable(q):
    """subqs 里「可计分」的条目：有分值，或层级 >=2（具体小题）。"""
    got = []
    for s in (q.get("subqs") or []):
        if s.get("marks") in (None, "") and (s.get("level") or 1) < 2:
            continue
        got.append(s)
    return got


def main():
    keys = sys.argv[1:] or None
    d = json.load(open(LQ, encoding="utf-8"))
    total_missing = 0
    align_ok = 0
    align_bad = []
    conflicts = []
    for year, qs in d["years"].items():
        if keys and year not in keys:
            continue
        gp = os.path.join(GUIDES, year + ".txt")
        if not os.path.exists(gp):
            print("[miss] 无题解稿:", year)
            continue
        guides = parse_guide(gp)
        for q in qs:
            qk = qkey(q.get("qnum"))
            heads = guides.get(q.get("qnum")) or guides.get(qk) or []
            subs = scorable(q)
            miss = [s for s in subs if s.get("marks") in (None, "")]
            total_missing += len(miss)
            if not heads:
                continue
            if len(heads) != len(subs):
                align_bad.append((year, q.get("qnum"), len(heads), len(subs)))
                continue
            align_ok += 1
            # 分值互校
            for (marker, gmarks, _), s in zip(heads, subs):
                if s.get("marks") not in (None, "") and s["marks"] != gmarks:
                    conflicts.append((year, q.get("qnum"), marker,
                                      gmarks, s["marks"]))
    print("可计分条目缺分值合计：", total_missing)
    print("顺序对齐成功的大题数：", align_ok)
    print("对不齐的大题数：", len(align_bad))
    for y, qn, a, b in align_bad[:30]:
        print("   %s %s  题解稿 %d 项 / subqs %d 项" % (y, qn, a, b))
    print("分值冲突数：", len(conflicts))
    for y, qn, mk, g, s in conflicts[:40]:
        print("   %s %s  标记(%s) 题解稿 %s / 库中 %s" % (y, qn, mk, g, s))


if __name__ == "__main__":
    main()
