# -*- coding: utf-8 -*-
"""把官方评分参考提取出的分值，与 `data/bio/_lq.json` 逐题逐小题比对，
产出**差异报告**（不直接改数据 —— 改不改由人决定）。

比对口径
--------
官方结果按「卷内大题号 + 部分」组织：评分参考里的第 1 题 (a) 对应我们数据里的
`1(a)`。小题按**出现顺序**对齐 —— 因为官方扫描件里 '(ii)' 常被 OCR 读成 '(i)'，
按标记字面匹配会把边界弄乱，顺序对齐才可靠。

差异分类
--------
  · FILL     我们的分值是空的，官方有值 → 可以直接补
  · SAME     两边一致
  · CONFLICT 两边都有值但不同 → 需要人工判断（官方权威，但要排除提取误差）
  · COUNT    小题数量对不上 → 多半是漏题或提取有误，先查

用法
----
  python scripts/pastpaper/lq_ref_apply.py            # 出报告
  python scripts/pastpaper/lq_ref_apply.py --write    # 只写入 FILL
"""
import argparse
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LQ = os.path.join(ROOT, "data", "bio", "_lq.json")
EXTRACT = os.path.join(ROOT, "scratch", "_ref_extract")
REPORT = os.path.join(ROOT, "scratch", "_ref_diff.json")


def qnum_parts(qnum):
    m = re.match(r"^\s*(\d+)\s*[（(]\s*([a-z])\s*[）)]", qnum or "")
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^\s*(\d+)", qnum or "")
    return (m.group(1), None) if m else (None, None)


def scorable(q):
    """我们数据里的子题条目（**全部**）。

    早先这里会滤掉「level=1 且没有分值」的条目，以为那是题干引导句 —— 但
    官方评分参考里往往**正是一个真实小题**（例如 2012 2(a) 的 (i) 就是
    「階段 II → 階段 III 自然植被重現的過程」，我们把它记成了引导句，
    分值也就丢了 3 分）。所以这里一条都不能滤。
    """
    return list(q.get("subqs") or [])


def align_subs(official, ours):
    """把官方小题序列与我们的子题序列对齐。

    官方按「罗马小题」划分，我们的库里常把 (i) 下面的 (1)(2) 也列成独立
    条目（level=2），所以两边条目数经常对不上，只能靠**已知分值做锚点**
    找偏移量。

    返回 (pairs, confidence)：
      pairs = [(官方下标, 我们的下标, 官方值, 我们的值), ...]
      confidence = 命中的已知值个数
    """
    best = ([], -1)
    for off in range(-3, 4):
        pairs = []
        score = 0
        known = 0
        for i, o in enumerate(official):
            j = i + off
            if not (0 <= j < len(ours)):
                continue
            v = ours[j]
            pairs.append((i, j, o, v))
            if v is not None:
                known += 1
                if v == o:
                    score += 1
        if len(pairs) < min(len(official), len(ours)):
            continue
        # 命中数优先；命中相同时取覆盖更多的
        if (score, len(pairs)) > (best[1], len(best[0])):
            best = (pairs, score)
    return best


def partition_match(official, ours):
    """把我们的条目序列分段，匹配到官方的子题序列。

    我们的库里常把 (i) 下面的 (1)(2) 也列成独立条目（level=2），所以一条
    官方子题可能对应我们连续好几条；反过来，一条也可能对应好几条官方子题。
    官方每道子题的分值是权威的，于是可以用**分段和**来反推对应关系。

    ours 里值为 None 的位置是「待补」，先当通配。

    返回 [(官方下标, [我们的下标…])]，匹配不上返回 None。
    """
    n, m = len(official), len(ours)
    if n == 0:
        return []
    # 已知值，用来约束分段
    known = [v for v in ours if v not in (None, "")]

    def seg_sum(a, b):
        """ours[a:b] 的已知值之和（None 当 0）。"""
        return sum(v for v in ours[a:b] if v not in (None, ""))

    def seg_known_count(a, b):
        return sum(1 for v in ours[a:b] if v not in (None, ""))

    # dp[i][j] = 前 i 个官方项用 ours 前 j 条是否可行
    dp = [[False] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = True
    for i in range(n):
        for j in range(m):
            if not dp[i][j]:
                continue
            # 官方第 i 项消耗 ours[j:k]
            for k in range(j + 1, m + 1):
                s = seg_sum(j, k)
                c = seg_known_count(j, k)
                # 允许通配，但至少要有一个已知值参与判断
                if c == 0:
                    continue
                if s == official[i] or s == 0:
                    dp[i + 1][k] = True
    if not dp[n][m]:
        return None
    # 回溯一条可行路径
    res = []
    i, j = n, m
    while i > 0:
        for k in range(j - 1, -1, -1):
            if dp[i - 1][k]:
                s = seg_sum(k, j)
                c = seg_known_count(k, j)
                if c and (s == official[i - 1] or s == 0):
                    res.append((i - 1, list(range(k, j))))
                    i, j = i - 1, k
                    break
        else:
            return None
    res.reverse()
    return res


def solve_blanks(official, ours, limit=4000):
    """枚举所有可行的「官方子题 ↔ 我们的条目」分段解，找出**能被唯一确定**
    的空缺值。

    我们的库里常把 (i) 下面的 (1)(2) 也列成独立条目，所以官方一个子题可能
    对应我们连续好几条；反过来一条也可能对应好几个官方子题。约束只有两条：
      · 每一段的**已知值之和**不能超过对应的官方分值；
      · 段里**只有一个空缺**时，那个空缺的值就被唯一确定；
      · 段里有多个空缺 → 无法单独确定（只保留总和约束），放弃这条分支。

    返回 {我们的下标: 唯一确定的值} —— 只有在**所有可行解里取值都相同**
    的空缺才会被返回。
    """
    m = len(ours)
    known = [v for v in ours if v not in (None, "")]
    del known
    sols = []

    def dfs(i, j, assign, depth):
        if len(sols) >= limit:
            return
        if i == len(official):
            if j == m:
                sols.append(dict(assign))
            return
        if j >= m:
            return
        for k in range(j + 1, m + 1):
            seg = list(range(j, k))
            seg_known = sum(ours[t] for t in seg
                            if ours[t] not in (None, ""))
            seg_blank = [t for t in seg if ours[t] in (None, "")]
            need = official[i] - seg_known
            if need < 0:
                continue
            if not seg_blank:
                if need != 0:
                    continue
                dfs(i + 1, k, assign, depth + 1)
            elif len(seg_blank) == 1:
                a = dict(assign)
                a[seg_blank[0]] = need
                dfs(i + 1, k, a, depth + 1)
            else:
                # 段里多个空缺：值分不出来，但总分得对得上才继续。
                # 只在官方剩余项刚好够分配时保留，否则剪掉。
                rest = sum(official[i + 1:])
                rest_known = sum(ours[t] for t in range(k, m)
                                 if ours[t] not in (None, ""))
                rest_blank = sum(1 for t in range(k, m)
                                 if ours[t] in (None, ""))
                if rest >= need + rest_known and rest_blank > 0:
                    a = dict(assign)
                    for t in seg_blank:
                        a[t] = None      # 未知，记为待定
                    dfs(i + 1, k, a, depth + 1)

    dfs(0, 0, {}, 0)
    if not sols:
        return {}
    # 取所有解的交集（只有处处相同的空缺才算被确定）
    keys = set()
    for s in sols:
        keys |= set(s)
    out = {}
    for t in keys:
        vals = {s.get(t) for s in sols}
        if len(vals) == 1:
            v = vals.pop()
            if v is not None and v > 0:
                out[t] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    lq = json.load(open(LQ, encoding="utf-8"))
    diff = {}
    stats = Counter()
    fills = []
    total_fixes = []

    for year, qs in lq["years"].items():
        path = os.path.join(EXTRACT, year + ".json")
        if not os.path.exists(path):
            continue
        off = json.load(open(path, encoding="utf-8"))
        for q in qs:
            qn, part = qnum_parts(q.get("qnum"))
            oq = off.get(qn)
            if not oq:
                continue
            op = None
            for p in oq["parts"]:
                if p["part"] == part:
                    op = p
                    break
            if op is None:
                continue
            o_subs = [s["marks"] for s in op["subs"]]
            our = scorable(q)
            our_vals = [s.get("marks") for s in our]
            S_o = op["sum"]
            S_u = sum(v for v in our_vals if v not in (None, ""))
            blanks = [i for i, v in enumerate(our_vals) if v in (None, "")]

            rec = {"qnum": q.get("qnum"), "id": q.get("id"),
                   "officialSubs": o_subs, "officialPartSum": S_o,
                   "ourPartSum": S_u, "ourTotal": q.get("marksTotal"),
                   "ourSubs": our_vals, "blanks": blanks, "items": []}

            # 合理性闸门：官方 part 和超过 15 分基本是提取错乱（DSE 一個
            # part 一般 ≤ 12 分），这种直接放弃，不拿它去改数据。
            plausible = S_o <= 15 and S_o >= S_u

            # 规则 1：只有一个空缺 → 直接用 part 总差补
            if plausible and len(blanks) == 1 and S_o > S_u:
                j = blanks[0]
                val = S_o - S_u
                rec["kind"] = "FILL"
                rec["items"].append({"ourIdx": j, "no": our[j].get("no"),
                                     "official": val, "ours": None})
                fills.append((q.get("id"), j, val))
                stats["FILL"] += 1
            # 规则 2：分段求解，能唯一确定的空缺直接补
            elif plausible:
                solved = solve_blanks(o_subs, our_vals)
                if solved and all(v <= 10 for v in solved.values()):
                    trial = [solved.get(i, v) if v in (None, "")
                             else v for i, v in enumerate(our_vals)]
                    trial = [v for v in trial if v not in (None, "")]
                    if sum(trial) == S_o:
                        rec["kind"] = "FILL"
                        for k, v in sorted(solved.items()):
                            rec["items"].append(
                                {"ourIdx": k, "no": our[k].get("no"),
                                 "official": v, "ours": None})
                            fills.append((q.get("id"), k, v))
                        stats["FILL"] += 1
                    else:
                        rec["kind"] = "COUNT"
                        stats["COUNT"] += 1
                else:
                    rec["kind"] = "COUNT"
                    stats["COUNT"] += 1
            else:
                rec["kind"] = "COUNT"
                stats["COUNT"] += 1

            # 规则 3：大题总分 —— 官方只会漏读不会多读，所以「官方和 > 我们和」
            # 说明我们漏了分，可以放心补；反之不动（可能是官方漏读）。
            if S_o > (q.get("marksTotal") or 0):
                rec["totalFix"] = S_o
                total_fixes.append((q.get("id"), q.get("marksTotal"), S_o))
                stats["TOTAL_UP"] += 1
            rec["totalNote"] = ("官方小题和=%d，我们小题和=%d，我们记总分=%s"
                                % (S_o, S_u, q.get("marksTotal")))
            diff[q.get("id")] = rec

    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=1)

    print("统计：", dict(stats))
    print()
    for kind in ("FILL", "PARTIAL", "COUNT"):
        ids = [k for k, v in diff.items() if v["kind"] == kind]
        if not ids:
            continue
        print("=== %s（%d 题）===" % (kind, len(ids)))
        for k in ids[:40]:
            v = diff[k]
            extra = ""
            if kind == "FILL":
                extra = "  → 补:" + "; ".join(
                    "%s=%s" % (it.get("no"), it["official"])
                    for it in v["items"])
            print("  %-16s %-6s 官方=%-18s 我们=%-18s %s%s" %
                  (k, v["qnum"], v["officialSubs"], v["ourSubs"],
                   v["totalNote"], extra))
        if len(ids) > 40:
            print("  …还有 %d 题" % (len(ids) - 40))
        print()

    print("=== 大题总分偏低（官方和 > 我们记） %d 题 ===" % len(total_fixes))
    for qid, ours, offv in total_fixes[:40]:
        print("  %-16s 我们记=%-4s 官方=%d" % (qid, ours, offv))

    if args.write and fills:
        # 写回前再核一遍：每条补值写进去后，该题的小题和必须等于官方 part 和
        by_q = {}
        for qid, j, val in fills:
            by_q.setdefault(qid, []).append((j, val))
        done = 0
        for year_qs in lq["years"].values():
            for q2 in year_qs:
                items = by_q.get(q2.get("id"))
                if not items:
                    continue
                subs = q2.get("subqs") or []
                for j, val in items:
                    if 0 <= j < len(subs) and subs[j].get("marks") in (None, ""):
                        subs[j]["marks"] = val
                        done += 1
                # 小题和 == 官方 part 和 → 同步修正 marksTotal
                vals = [s.get("marks") for s in subs
                        if s.get("marks") not in (None, "")]
                rec = diff.get(q2.get("id"))
                if rec and vals and sum(vals) == rec["officialPartSum"]:
                    if q2.get("marksTotal") != rec["officialPartSum"]:
                        q2["marksTotal"] = rec["officialPartSum"]
        with open(LQ, "w", encoding="utf-8") as f:
            json.dump(lq, f, ensure_ascii=False, indent=1)
        print("已回填 %d 个空分值（并同步修正了对应题的 marksTotal）" % done)


if __name__ == "__main__":
    main()
