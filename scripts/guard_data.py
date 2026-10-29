# -*- coding: utf-8 -*-
"""题库守门员：确认你没有「顺手优化」到不该动的字段，并做结构校验。

为什么需要它：
  `data/bio/_pastpaper.json` 里的题目正文、选项、答案、分类都是**人工逐题校对过**的。
  这些字段一旦被脚本或手误改动，错误会静默进入线上，而且很难发现
  （界面上只是「答案好像不对」，没人知道是哪次改动弄坏的）。

  所以规则是：**只允许改 `explanation` 与 `explSource`**，其余字段一律锁死。
  本脚本用 git 里的上一个版本做基线，逐字段比对，越界就报错。

用法：
  python scripts/guard_data.py              # 结构校验 + 与 git HEAD 比对
  python scripts/guard_data.py --base HEAD~3   # 与更早的版本比对
  python scripts/guard_data.py --no-git     # 只做结构校验（首次 clone 或 CI 无 git 时）
  python scripts/guard_data.py --quiet      # 只输出问题

真的需要改受保护字段时（例如修「选项吞并了邻题」这类数据 bug），必须显式开白名单：

  python scripts/guard_data.py --allow pp_2019_q34:options,pp_2021_q24:q

  规则：
    * 格式 `<题号>:<字段>`，逗号分隔；
    * 白名单只在本次运行生效，**不会被记住**；
    * 提交信息里必须写明为什么改，方便以后追溯。

退出码：0 = 通过；1 = 有错误（可当 CI 门禁）。
"""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # f6chem/
PP_REL = "data/bio/_pastpaper.json"
PP = os.path.join(BASE, PP_REL.replace("/", os.sep))

# 允许被改动的字段（写题解时只会动这两个）
ALLOWED = {"explanation", "explSource"}

# 结构上必须存在的字段
REQUIRED = ["id", "year", "qnum", "answer", "q"]

errors = []
warns = []
oks = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warns.append(msg)


def ok(msg):
    oks.append(msg)


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def flat(doc):
    """把 {years:{2012:[q,...]}} 摊平成 {id: q}。"""
    out = {}
    for year, qs in (doc.get("years") or {}).items():
        for q in qs or []:
            out[q.get("id")] = q
    return out


def topic_ids():
    """data/bio/*.json 里出现过的课题 id（bio02…bio36）。"""
    ids = set()
    d = os.path.join(BASE, "data", "bio")
    for fn in os.listdir(d):
        if not fn.endswith(".json") or fn.startswith("_") or ".bak" in fn:
            continue
        if fn in ("subject.json", "links.json"):
            continue
        try:
            doc = load(os.path.join(d, fn))
        except Exception:
            continue
        if isinstance(doc, dict) and doc.get("id"):
            ids.add(doc["id"])
    return ids


def check_schema(doc, topics):
    """结构校验：不依赖 git，任何环境下都能跑。"""
    if not isinstance(doc, dict):
        err("顶层不是对象")
        return
    for k in ("id", "title", "years"):
        if k not in doc:
            err("顶层缺字段 `%s`" % k)
    years = doc.get("years")
    if not isinstance(years, dict) or not years:
        err("`years` 应为非空对象")
        return

    qs = flat(doc)
    ok("题数 %d（%d 个年份）" % (len(qs), len(years)))

    # id 唯一性
    seen = {}
    for year, lst in years.items():
        for q in lst or []:
            qid = q.get("id")
            if qid in seen:
                err("id 重复：%s（同时出现在 %s 与 %s）" % (qid, seen[qid], year))
            seen[qid] = year

    for year, lst in years.items():
        # 年份键应为四位数字；樣本卷／練習卷用 PP、SP 这类短代码（无官方得分率）
        if not (re.fullmatch(r"\d{4}", str(year)) or str(year) in ("PP", "SP")):
            err("年份键 `%s` 不是四位数字（也不是 PP/SP）" % year)
        for q in lst or []:
            qid = q.get("id", "<无 id>")
            # 必填
            for k in REQUIRED:
                if k not in q:
                    err("%s 缺字段 `%s`" % (qid, k))
            # id 与 year/qnum 一致性
            y, n = q.get("year"), q.get("qnum")
            if str(y) != str(year):
                err("%s 的 year=%r 与所在年份 %s 不一致" % (qid, y, year))
            if not isinstance(n, int) or n < 1:
                err("%s 的 qnum=%r 应为正整数" % (qid, n))
            elif qid != "pp_%s_q%d" % (year, n):
                err("%s 的 id 与 year/qnum 不匹配（应为 pp_%s_q%d）" % (qid, year, n))
            # 答案
            a = q.get("answer")
            if a not in ("A", "B", "C", "D"):
                err("%s 的 answer=%r 不是 A/B/C/D" % (qid, a))
            # 选项
            opts = q.get("options") or []
            if not isinstance(opts, list):
                err("%s 的 options 不是数组" % qid)
                opts = []
            ks = [o.get("k") for o in opts if isinstance(o, dict)]
            if len(ks) != len(opts):
                err("%s 的 options 里有非对象项" % qid)
            if len(set(ks)) != len(ks):
                dup = sorted({k for k in ks if ks.count(k) > 1})
                err("%s 的选项字母重复：%s" % (qid, dup))
            for k in ks:
                if k not in ("A", "B", "C", "D"):
                    err("%s 的选项字母非法：%r" % (qid, k))
            # 选项数与答案是否对得上
            fig = bool(q.get("figOptions") or q.get("optImg") or q.get("qImg"))
            if opts and a not in ks:
                err("%s 的答案 %s 不在选项里（选项为 %s）" % (qid, a, ks))
            if not opts and not fig:
                err("%s 没有任何选项，也没标记 figOptions/optImg（界面会显示空白）" % qid)
            if opts and len(opts) not in (4,) and not fig:
                warn("%s 有 %d 个选项（正常应为 4）——疑似吞并了邻题的选项，请人工确认" % (qid, len(opts)))
            # 答对率
            pct = q.get("pct")
            if pct is not None and not (isinstance(pct, int) and 0 <= pct <= 100):
                err("%s 的 pct=%r 应为 0–100 的整数" % (qid, pct))
            # 分类
            t = q.get("topic")
            if not t:
                warn("%s 没有 topic（by topic 视图里会归入未分类）" % qid)
            elif topics and t not in topics:
                err("%s 的 topic=%r 不是已知课题（已知：%s…）" % (qid, t, sorted(topics)[:3]))
            # 题解
            ex = q.get("explanation")
            if ex is not None and not isinstance(ex, str):
                err("%s 的 explanation 不是字符串" % qid)
            elif isinstance(ex, str) and ex.strip() and len(ex.strip()) < 10:
                warn("%s 的题解只有 %d 个字，疑似没写完" % (qid, len(ex.strip())))


def git_baseline(ref):
    """取基线版本的题库；失败返回 None（例如首次 clone、浅克隆、无 git）。"""
    try:
        r = subprocess.run(
            ["git", "-C", BASE, "show", "%s:%s" % (ref, PP_REL)],
            capture_output=True,
        )
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.decode("utf-8"))
    except Exception:
        return None


def check_diff(old, new, allow=None):
    """逐字段比对：只允许 ALLOWED 里的字段变化，以及 allow 白名单里的 (题号, 字段)。"""
    allow = allow or set()
    a, b = flat(old), flat(new)
    removed = [i for i in a if i not in b]
    added = [i for i in b if i not in a]

    if removed:
        err("删除了 %d 道题：%s" % (len(removed), removed[:5]))
    if added:
        warn("新增了 %d 道题：%s（新增是允许的，但请确认答案与分类已校对）"
             % (len(added), added[:5]))

    touched = {}
    waived = {}
    for qid in a:
        if qid not in b:
            continue
        o, n = a[qid], b[qid]
        for k in set(o) | set(n):
            if k in ALLOWED:
                continue
            if o.get(k) != n.get(k):
                if (qid, k) in allow:
                    waived.setdefault(k, []).append(qid)
                else:
                    touched.setdefault(k, []).append(qid)

    if touched:
        for k, ids in sorted(touched.items()):
            err("字段 `%s` 被改了 %d 处：%s  ← 这个字段已人工校对，不允许改"
                % (k, len(ids), ids[:5]))
    for k, ids in sorted(waived.items()):
        warn("字段 `%s` 按白名单改了 %d 处：%s（确认是无误的修复）" % (k, len(ids), ids[:5]))

    if not touched:
        changed = sum(1 for qid in a if qid in b and a[qid].get("explanation") != b[qid].get("explanation"))
        ok("与基线比对：%d 道题有改动，全部落在允许范围内" % (changed + sum(len(v) for v in waived.values())))


def main():
    argv = sys.argv[1:]
    no_git = "--no-git" in argv
    quiet = "--quiet" in argv
    base = "HEAD"
    if "--base" in argv:
        i = argv.index("--base")
        if i + 1 < len(argv):
            base = argv[i + 1]

    allow = set()
    if "--allow" in argv:
        i = argv.index("--allow")
        if i + 1 < len(argv):
            for item in argv[i + 1].split(","):
                item = item.strip()
                if not item:
                    continue
                if ":" not in item:
                    print("✖ --allow 格式应为 `<题号>:<字段>`，收到 %r" % item)
                    return 1
                qid, field = item.split(":", 1)
                allow.add((qid.strip(), field.strip()))
            if allow:
                print("  ⚠ 白名单已启用（%d 项）：%s" % (len(allow), sorted(allow)))
                print("    改的是受保护字段，提交信息里请写明原因。")

    if not os.path.exists(PP):
        print("✖ 找不到 %s" % PP_REL)
        return 1

    try:
        doc = load(PP)
    except Exception as e:
        print("✖ 题库 JSON 解析失败：%s" % e)
        print("  （最常见原因：手改后多了/少了逗号或引号，用 python -m json.tool 定位）")
        return 1

    check_schema(doc, topic_ids())

    if no_git:
        if not quiet:
            print("  （跳过 git 比对：--no-git）")
    else:
        old = git_baseline(base)
        if old is None:
            if not quiet:
                print("  （跳过 git 比对：取不到 %s:%s，可能是浅克隆或首次提交）" % (base, PP_REL))
        else:
            check_diff(old, doc, allow)

    if not quiet:
        print()
        for m in oks:
            print("  ✓ %s" % m)
        for m in warns:
            print("  ⚠ %s" % m)
        for m in errors:
            print("  ✖ %s" % m)
        print()

    if errors:
        print("✖ %d 个错误 / %d 个警告 —— 修完再提交。" % (len(errors), len(warns)))
        return 1
    if warns:
        print("✅ 无错误，但有 %d 个警告值得看一眼。" % len(warns))
        return 0
    print("✅ 题库完好，可以提交。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
