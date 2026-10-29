# -*- coding: utf-8 -*-
"""LQ 数据集构建：VL 解析中间物 → 正式数据文件 data/bio/_lq.json

为什么 MC 与 LQ 分开存放
------------------------
用户明确要求：「MC 和 LQ 要分开存放，不然用户会很乱」。理由不只是排版：

  · 答题方式不同 —— MC 点选 A/B/C/D（一个 answer 字段即可）；
    LQ 要写长答，一道大题下挂多级子题，每子题各有分值。
  · 题号体系不同 —— MC 是整数 qnum（1..40）；LQ 是 1(a)(i)(1) 三级编号。
  · 统计口径不同 —— 「446 道选择题」与「N 道长答题」混算会失真。

所以本脚本产出**独立的** `data/bio/_lq.json`，
`data/bio/_pastpaper.json`（MC）一个字节都不动。

输入
----
  scratch/_lq_vl_raw/<key>.json    （由 lq_vl_parse.py 从 PaddleOCR-VL 产物解析）

输出
----
  data/bio/_lq.json
  {
    "id": "lq_bio",
    "title": "DSE 生物 卷二（長題目）",
    "description": "...",
    "years": { "2019": [ {题...}, ... ], ... }
  }

单题结构
--------
  {
    "id": "lq_2019_q1a",
    "year": "2019",
    "qnum": "1(a)",            ← LQ 用字符串题号，不是整数
    "part": "A", "partName": "甲部",
    "chapter": "人體生理學：調節與控制",
    "stem": "為探究雌激素…",     ← 大题题干（已剥离题号）
    "imgs": [],                ← 配图相对路径（外置，与 MC 同规则）
    "subqs": [
      {"no":"i","level":1,"q":"就卵巢…","marks":null},
      {"no":"1","level":2,"q":"由週期 I 的…","marks":2}
    ],
    "marksTotal": 10,
    "page": 1,
    "ocr": true                ← OCR 还原，文字可能有错字（前端需提示）
  }

用法
----
  python scripts/pastpaper/lq_dataset.py            # 所有已有 VL 数据的年份
  python scripts/pastpaper/lq_dataset.py 2019 2020
"""
import io
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(_ROOT, "scratch", "_lq_vl_raw")
OUT = os.path.join(_ROOT, "data", "bio", "_lq.json")

PART_NAME = {"A": "甲部", "B": "乙部", "C": "丙部", "D": "丁部", "E": "戊部", "F": "己部"}

# 题号前缀（VL 的 stem 里常残留 "I(a)" "1(b)" 等）
RE_LEAD_QID = re.compile(
    r"^\s*[（(]?\s*([lI1]|\d{1,2})\s*[）)]?\s*[.．]?\s*[（(]\s*([a-zA-Z])\s*[)）]\s*")
# 子题文本里的题号前缀
RE_LEAD_SUB = re.compile(
    r"^\s*[（(]\s*([0-9]{1,2}|[ivxIVX]{1,4})\s*[)）]\s*")
# 分值（在文本任意位置）
RE_MARKS = re.compile(r"[（(]\s*(\d{1,2})\s*分\s*[)）]")
# 图注："圖 1" "图2" "圖X"
RE_FIGREF = re.compile(r"[圖图]\s*([0-9A-Za-z]{1,3})")


def norm_qid(qid, stem):
    """规范化题号：OCR 常把 1 读成 I/l。"""
    m = re.match(r"^\s*([lI1]|\d{1,2})\s*\(([a-zA-Z])\)\s*$", qid or "")
    if not m:
        return qid
    num = m.group(1)
    if num in ("l", "I"):
        num = "1"
    return "%s(%s)" % (num, m.group(2))


def strip_lead(text, pattern):
    """剥离行首的题号，返回 (剩余文本, 提取到的题号或 None)。"""
    if not text:
        return "", None
    m = pattern.match(text)
    if not m:
        return text.strip(), None
    return text[m.end():].strip(), m.group(0).strip()


def sub_level(no):
    """判断子题层级：罗马数字 = 1 级，阿拉伯数字 = 2 级。"""
    if no is None:
        return 1
    s = str(no).strip()
    if s.isdigit():
        return 2
    return 1


def build_question(g, year):
    qid = norm_qid(g.get("qid"), g.get("stem"))
    if not qid:
        return None
    part = g.get("part") or ""
    stem = g.get("stem") or ""
    # 剥离 stem 行首残留的题号
    stem_body, _ = strip_lead(stem, RE_LEAD_QID)

    subqs = []
    marks_total = 0
    for s in g.get("subs", []):
        txt = s.get("txt") or ""
        no = s.get("no")
        body, _ = strip_lead(txt, RE_LEAD_SUB)
        # 从正文里抽分值并去掉 "(2分)"
        found = RE_MARKS.findall(body)
        marks = int(found[0]) if found else None
        if marks:
            marks_total += marks
        body = RE_MARKS.sub("", body).strip()
        if not body:
            continue
        subqs.append({
            "no": no,
            "level": sub_level(no),
            "q": body,
            "marks": marks,
        })

    # ---- 分值兜底 ----
    # VL 的 marks 是按出现顺序的扁平数组。个别子题的分值会被 VLM 吞掉
    # （实测 2020 2(a)：(i)(iii) 两个子题，marks=[2,4,3] 三个值 → 漏了 (ii)）。
    # 策略：把 marks 里没被用掉的值，按顺序补给「无分值」的子题。
    #       优先补 level 2（阿拉伯数字子项，分值通常标在它们上），
    #       若补完还有剩且存在 level 1 无分值的，再补 level 1。
    #       凡是被补过的都标 marksInferred，整题标 needsReview 供人工核对。
    flat_marks = [int(x) for x in (g.get("marks") or []) if str(x).isdigit()]
    spare = list(flat_marks)
    for s in subqs:
        if s["marks"] and s["marks"] in spare:
            spare.remove(s["marks"])
    needs_review = False
    if spare:
        for want_level in (2, 1):
            for s in subqs:
                if not spare:
                    break
                if s["marks"] is None and s["level"] == want_level:
                    s["marks"] = spare.pop(0)
                    s["marksInferred"] = True
                    marks_total += s["marks"]
                    needs_review = True
    # 论文式判定：缺失的 (ii) 这类整条子题被吞掉时，子题数会少于 marks 数
    n_leaf = len([s for s in subqs if s["level"] == 2]) or len(subqs)
    if len(flat_marks) > n_leaf:
        needs_review = True

    # 题干正文也可能带分值（整题给分）
    if not marks_total:
        for m in RE_MARKS.findall(stem_body):
            marks_total += int(m)

    if not subqs and not stem_body:
        return None

    # 配图引用（图 1 / 图2 …），供后续裁图对齐
    figs = sorted(set(RE_FIGREF.findall(stem_body)))
    for s in subqs:
        figs += [f for f in RE_FIGREF.findall(s["q"]) if f not in figs]
        figs = list(dict.fromkeys(figs))

    q = {
        "id": "lq_%s_q%s" % (year, qid.replace("(", "_").replace(")", "")),
        "year": year,
        "qnum": qid,
        "part": part,
        "partName": PART_NAME.get(part, part),
        "chapter": g.get("chapter") or "",
        "stem": stem_body,
        "imgs": [],
        "figRefs": figs,
        "subqs": subqs,
        "marksTotal": marks_total or None,
        "page": g.get("start_page"),
        "tables": len(g.get("tables") or []),
        "ocr": True,
    }
    if needs_review:
        q["needsReview"] = True
    return q


def build():
    if not os.path.isdir(RAW):
        print("[miss] 找不到", RAW)
        return
    keys = [n[:-5] for n in sorted(os.listdir(RAW)) if n.endswith(".json")]
    years = {}
    for k in keys:
        with io.open(os.path.join(RAW, k + ".json"), encoding="utf-8") as f:
            d = json.load(f)
        qs = []
        for g in d.get("groups", []):
            q = build_question(g, k)
            if q:
                qs.append(q)
        if qs:
            years[k] = qs
            print("  %-6s %d 道大题 · %d 个子题 · %d 分" % (
                k, len(qs),
                sum(len(q["subqs"]) for q in qs),
                sum(q["marksTotal"] or 0 for q in qs)))

    payload = {
        "id": "lq_bio",
        "title": "DSE 生物 卷二（長題目 LQ）",
        "description": (
            "香港中學文憑試生物科卷二（長題目）。與卷一選擇題分開收錄："
            "長題目需自行書寫，題號為 1(a)(i)(1) 三級結構。"
            "題幹由 PaddleOCR-VL 從原卷還原，文字可能仍有錯字，"
            "重要處請對照原卷。"
        ),
        "schema": "lq-v1",
        "years": years,
    }

    n = sum(len(v) for v in years.values())
    if n == 0:
        print("[abort] 没有解析出任何题目，不写文件")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print("\n[done] %s" % OUT)
    print("       共 %d 个年份 · %d 道大题" % (len(years), n))


if __name__ == "__main__":
    build()
