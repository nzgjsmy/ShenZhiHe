# -*- coding: utf-8 -*-
"""把題解稿裡的「（分值待核對）」換成核對後的實際分值。

為什麼需要
----------
題解稿是當初分值還沒確認時寫的，所以標了「分值待核對」。
現在分值已用**原卷印刷分值**逐題核對完畢（見 lq_ref_manual.py），
這些標記就可以換成真實分值，讓學生看到的題解不再有「待核對」字樣。

匹配方式
--------
題解稿標題的標記（如「（ii）(1)」）→ [(level, no), ...]
庫裡該題的子題序列            → [(level, no), ...]
按順序逐項貪心匹配（同類型、同序號），把標題的分值換成庫裡的值。

用法
----
    python scripts/pastpaper/lq_sync_guide_marks.py            # 只看報告
    python scripts/pastpaper/lq_sync_guide_marks.py --write
"""
import argparse
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LQ = os.path.join(ROOT, "data", "bio", "_lq.json")
GU = os.path.join(ROOT, "scripts", "pastpaper", "lq_guides")

ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
# 標題行：**（i）xxx（3 分）** / **（ii）(1) xxx（2 分）**
TITLE = re.compile(r"^\*\*（(.+?)）(.*?)（(?:(\d+) 分|分值待核對)）\*\*", re.M)
MARK = re.compile(r"[（(]\s*([a-z]{1,3}|\d{1,2})\s*[)）]", re.I)


def parse_mark(text):
    """'（ii）(1) xxx' → [(1,'ii'), (2,'1')]

    註：一定要用**帶括號**的正則去掃整行 —— 因為標題裡的括號是被
    TITLE 正則吃掉的，剩下來的純文字（如 'ii'）反而認不出。
    「（3 分）」「（分值待核對）」不會被誤判成標記（括號內不是純標記）。
    """
    out = []
    for tok in MARK.findall(text):
        t = tok.lower()
        if t in ROMAN:
            out.append((1, t))
        elif t.isdigit():
            out.append((2, t))
    return out


def subq_seq(q):
    """庫裡一道題的子題 → [(level, no), ...]"""
    out = []
    for s in (q.get("subqs") or []):
        no = (s.get("no") or "").lower()
        lv = s.get("level") or 1
        if no in ROMAN:
            out.append((1, no))
        elif no.isdigit():
            out.append((2, no))
        else:
            out.append((lv, no))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    lq = json.load(open(LQ, encoding="utf-8"))
    changed = 0
    pend_total = 0

    for year in sorted(lq["years"]):
        path = os.path.join(GU, year + ".txt")
        if not os.path.exists(path):
            continue
        txt = io.open(path, encoding="utf-8").read()
        pend_total += txt.count("分值待核對")
        if "分值待核對" not in txt:
            continue

        # 依 @@@ 分節，逐節處理
        parts = re.split(r"(^@@@ .*$)", txt, flags=re.M)
        out = [parts[0]]
        i = 1
        while i < len(parts):
            head, body = parts[i], parts[i + 1]
            i += 2
            qnum = head[4:].strip()
            q = next((qq for qq in lq["years"][year] if qq["qnum"] == qnum), None)
            if q and "分值待核對" in body:
                seq = subq_seq(q)
                marks_of = {}
                for s in (q.get("subqs") or []):
                    no = (s.get("no") or "").lower()
                    lv = s.get("level") or 1
                    key = (1, no) if no in ROMAN else ((2, no) if no.isdigit()
                                                       else (lv, no))
                    marks_of.setdefault(key, s.get("marks"))
                pos = 0

                def fix(m):
                    mk = parse_mark(m.group(0))
                    if not mk:
                        return m.group(0)
                    # 用最後一層標記去查（(ii)(1) → (2,'1')）；
                    # 不靠順序對齊 —— 題解稿常常略過引導句，順序會錯位。
                    v = marks_of.get(mk[-1])
                    if v is not None:
                        return m.group(0).replace("（分值待核對）",
                                                 "（%d 分）" % v)
                    return m.group(0)

                body = TITLE.sub(fix, body)
            out.append(head)
            out.append(body)

        new = "".join(out)
        if new != txt:
            changed += 1
            if args.write:
                io.open(path, "w", encoding="utf-8", newline="\n").write(new)
            print("  %-5s 已處理（剩餘待核對 %d 處）"
                  % (year, new.count("分值待核對")))

    print()
    print("共 %d 份題解稿有更動；原本共 %d 處「分值待核對」" % (changed, pend_total))
    if args.write:
        print("已寫入")


if __name__ == "__main__":
    main()
