# -*- coding: utf-8 -*-
"""从 OCR 结果里定位每道题的题号 -> (page, y_top)

用法:
  python scratch/_pp_locate.py 2012
"""
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(_ROOT, "scratch", "_pp_pages")

# 题号：1-2 位数字 + . 或 、，后面可能直接接题干
RE_NUM = re.compile(r"^\s*(\d{1,2})\s*[\.．、]\s*")


def locate(key):
    path = os.path.join(BASE, key, "ocr.json")
    pages = json.load(open(path, encoding="utf-8"))
    marks = []
    for pg in pages:
        for b in pg["blocks"]:
            m = RE_NUM.match(b["txt"])
            if not m:
                continue
            n = int(m.group(1))
            if not (1 <= n <= 40):
                continue
            # 题号必须在左侧栏（题干都从左边距起）
            if b["x"] > 420:
                continue
            # 纯题号（"7."）或 "7. 题干…" 都算
            rest = b["txt"][m.end():].strip()
            marks.append(
                {
                    "n": n,
                    "page": pg["page"],
                    "y": b["y"],
                    "y2": b["y2"],
                    "x": b["x"],
                    "rest": rest,
                    "txt": b["txt"],
                }
            )
    # 同一题号可能被重复识别（图内数字、题号被误读）-> 收集所有候选
    cands = {}
    for m in marks:
        cands.setdefault(m["n"], []).append(m)
    for k in cands:
        cands[k].sort(key=lambda m: (m["page"], m["y"]))

    # 贪心 + 单调约束：题号位置必须随题号递增，否则会挑到别页的误识别
    seq = []
    prev = None
    for n in range(1, 41):
        if n not in cands:
            continue
        pick = None
        for c in cands[n]:
            if prev is None or (c["page"], c["y"]) > (prev["page"], prev["y"]):
                pick = c
                break
        if pick is None:
            pick = cands[n][-1]  # 实在没有递增的，取最后一个并标记
        pick["_odd"] = bool(cands[n]) and len(cands[n]) > 1
        seq.append(pick)
        prev = pick
    return pages, seq


def main():
    key = sys.argv[1]
    pages, seq = locate(key)
    H = pages[0]["H"]
    print("== %s  共 %d 页, 页高 %d ==" % (key, len(pages), H))
    prev = None
    for m in seq:
        flag = ""
        if prev is not None:
            if m["page"] < prev["page"] or (m["page"] == prev["page"] and m["y"] < prev["y"]):
                flag = "  << 顺序异常"
        print(
            "q%-3d p%02d y=%4d  x=%3d  %s%s"
            % (m["n"], m["page"], m["y"], m["x"], (m["rest"] or m["txt"])[:46], flag)
        )
        prev = m
    got = [m["n"] for m in seq]
    missing = [i for i in range(1, max(got) + 1) if i not in got]
    print("识别到题号 %d 个, 缺: %s" % (len(got), missing))


if __name__ == "__main__":
    main()
