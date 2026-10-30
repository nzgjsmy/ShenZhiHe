# -*- coding: utf-8 -*-
"""人工核對官方《評卷參考》後的**分值修正表** —— 一次性套用。

為什麼要人工
------------
自動抽取（`lq_ref_extract.py`）只能在「官方小题序列」與「我們的子題序列」
能一一對上時自動判定；遇到三級結構（(i) 下面還有 (1)(2)）、或官方把
「(ii)(1) 最高 2 分」這種上限標法混在得分點裡，就只能人眼看圖。

這一檔記錄的是**逐頁看圖核對後**的結論，每條都附核對依據。

用法
----
  python scripts/pastpaper/lq_ref_manual.py           # 只看報告
  python scripts/pastpaper/lq_ref_manual.py --write   # 套用
"""
import argparse
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LQ = os.path.join(ROOT, "data", "bio", "_lq.json")

# 題號 → {子題 no: 分值}（None = 不動）、marksTotal、依據
FIX = {
    # 官方 p009 丁部：4(a) = (i)1+1=2、(ii)(1)「最高 2」=2、(ii)(2) 三個得分點=3、
    # (iii) 四個得分點=4 → 合計 11 分。我們原本只記了 (iii)=4（總分 4）。
    "lq_2012_q4_a": {
        "subs": {"i": 2, "1": 2, "2": 3, "iii": 4},
        "total": 11,
        "why": "官方 p009 丁部：4(a)=(i)2+(ii)(1)2+(ii)(2)3+(iii)4=11 分",
    },
    # 官方 p009 丙部：3(a)(i)=5、(ii)=2、(iii) 底下 (1)=1、(2)=3 → (iii)=4，合計 11。
    # RapidOCR 把 '(iii)' 讀成 '(ii）'，自動抽取因此只認到 1 分。
    "lq_2013_q3_a": {
        "subs": {"i": 5, "ii": 2, "iii": 4},
        "total": 11,
        "why": "官方 p009 丙部：3(a)=(i)5+(ii)2+(iii)4=11 分（(iii) 含 (1)1+(2)3）",
    },
    # 官方 p011 丁部：4(a)=(i)2+(ii)(1)1+(ii)(2)1+(iii)2+(iv)(1)2+(iv)(2)2=10。
    "lq_2017_q4_a": {
        "subs": {"i": 2, "ii": None, "1": 1, "2": 1, "iii": 2,
                 "iv": None, "1#2": 2, "2#2": 2},
        "total": 10,
        "why": "官方 p011 丁部：4(a)=(i)2+(ii)(1)1+(ii)(2)1+(iii)2+(iv)(1)2+(iv)(2)2=10 分",
    },
}

# 只記錄、不改數據的缺口（源文件本身不全，要重掃完整原卷才能補）
GAPS = {
    "lq_2014_q3_a": "官方 p009 丙部：3(a)=(i)3+(ii)3+(iii)2+(iv)(1)1+(iv)(2)3=12 分，"
                    "但我們只收錄了 (i)=3 —— **(ii)(iii)(iv) 整段漏錄**，"
                    "要補須重掃 2014 完整原卷（該年原卷只有 6 頁，缺丁部）。",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    lq = json.load(open(LQ, encoding="utf-8"))
    idx = {}
    for qs in lq["years"].values():
        for q in qs:
            idx[q["id"]] = q

    print("=== 人工核對修正（%d 題）===" % len(FIX))
    for qid, f in FIX.items():
        q = idx.get(qid)
        if not q:
            print("  %-16s 找不到，略過" % qid)
            continue
        subs = q.get("subqs") or []
        before = [(s.get("no"), s.get("marks")) for s in subs]
        # 依 no 順序套用；同名的第二个用 #2 区分
        seen = {}
        for s in subs:
            no = s.get("no")
            seen[no] = seen.get(no, 0) + 1
            key = no if seen[no] == 1 else "%s#%d" % (no, seen[no])
            if key in f["subs"] and f["subs"][key] is not None:
                s["marks"] = f["subs"][key]
        after = [(s.get("no"), s.get("marks")) for s in subs]
        print("  %-16s %s" % (qid, f["why"]))
        print("      前 %s" % (before,))
        print("      后 %s  总分 %s → %s" %
              (after, q.get("marksTotal"), f["total"]))
        q["marksTotal"] = f["total"]

    print()
    print("=== 源文件缺口（改不了，要重掃原卷）===")
    for qid, why in GAPS.items():
        print("  %-16s %s" % (qid, why))

    if args.write:
        with io.open(LQ, "w", encoding="utf-8", newline="\n") as f:
            json.dump(lq, f, ensure_ascii=False, indent=1)
        print("\n已套用 %d 題修正" % len(FIX))


if __name__ == "__main__":
    main()
