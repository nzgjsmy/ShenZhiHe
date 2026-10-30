#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 LQ 题解文本稿导入 data/bio/_lq.json。

为什么要单独一个脚本
--------------------
题解是几百字的 Markdown，直接塞进 JSON 字符串要转义引号和换行，
在 shell 里写 python -c 或 heredoc 时中文与 \\n 极易被吃掉——这个项目
在 V0.19.0 就踩过「题解里全是字面 \\n」的坑（152 条数据全部退化）。

所以约定：正文写在纯文本稿里，用 `@@@ <题号>` 分节，本脚本只做搬运。

文本稿格式
----------
    @@@ 1(a)
    （Markdown 正文，支持多段、列表、引用块、表格）

    @@@ 1(b)
    ...

用法
----
    python scripts/pastpaper/lq_apply_guide.py 2019
    python scripts/pastpaper/lq_apply_guide.py 2019 --dry-run
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data", "bio", "_lq.json")

SRC_NOTE = "本站依據題目與 DSE 生物科評分慣例整理，**非官方評分指引**，僅供自評參考。"


def parse_guide_file(path):
    """按 `@@@ 題號` 切節。回傳 {qnum: markdown}。"""
    if not os.path.exists(path):
        raise SystemExit("找不到題解稿：%s" % path)
    txt = io.open(path, encoding="utf-8").read()
    out = {}
    cur = None
    buf = []
    for line in txt.splitlines():
        if line.startswith("@@@ "):
            if cur:
                out[cur] = "\n".join(buf).strip()
            cur = line[4:].strip()
            buf = []
        else:
            buf.append(line)
    if cur:
        out[cur] = "\n".join(buf).strip()
    return out


def main():
    year = sys.argv[1] if len(sys.argv) > 1 else "2019"
    dry = "--dry-run" in sys.argv

    path = os.path.join(ROOT, "scratch", "_lq_guide_%s.txt" % year)
    guides = parse_guide_file(path)
    print("題解稿：%s  共 %d 節" % (os.path.basename(path), len(guides)))

    d = json.load(io.open(DATA, encoding="utf-8"))
    qs = d.get("years", {}).get(year)
    if not qs:
        raise SystemExit("%s 年沒有題目資料" % year)

    hit = miss = 0
    for q in qs:
        g = guides.get(q["qnum"])
        if g:
            q["guide"] = g
            q["guideSrc"] = SRC_NOTE
            hit += 1
            print("  ✓ %-7s %d 字" % (q["qnum"], len(g)))
        else:
            miss += 1
            print("  · %-7s 無題解稿" % q["qnum"])

    print("\n寫入 %d 題，缺 %d 題" % (hit, miss))
    if dry:
        print("（--dry-run，未寫檔）")
        return

    io.open(DATA, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    print("已寫入 %s" % DATA)


if __name__ == "__main__":
    main()
