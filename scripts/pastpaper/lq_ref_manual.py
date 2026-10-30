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
# 可選欄位：
#   "newSubs"  —— 完整替換 subqs（用於 OCR 把多個小題併成一條時的**結構修正**）
#   "stem"     —— 覆蓋 stem
#   "reviewed" —— 設 True 表示此題已人工核實，不再標「待核對」
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
    # ── 2014 丙部第 3 題：原卷截圖逐字核對 ─────────────────────────────
    # OCR 把 (i)(ii)(iii)(iv)(1)(2) 六個小題併成一條，分值全部遺失（總分記成 3）。
    # 依原卷印刷分值：3(a) = (i)3+(ii)3+(iii)2+(iv)(1)1+(iv)(2)3 = 12 分。
    # （原卷 (iv) 只是引導句，本身不印分值 → 記 None；這與 1(a)、2021 3(a) 等題
    #   的建模慣例一致。）
    "lq_2014_q3_a": {
        "newSubs": [
            {"no": "i", "level": 1,
             "q": "為什麼大腸桿菌讀數可以用來反映水質？", "marks": 3},
            {"no": "ii", "level": 1,
             "q": "根據以上資料，你會選擇到哪個海灘游泳？為什麼？", "marks": 3},
            {"no": "iii", "level": 1,
             "q": "寫出利用大腸桿菌讀數來估測水質的兩項限制。", "marks": 2},
            {"no": "iv", "level": 1,
             "q": "量度水樣本中的大腸桿菌數量時，要經過培養步驟，並需要無菌操作。",
             "marks": None},
            {"no": "1", "level": 2,
             "q": "在這個過程中，無菌操作有什麼重要性？", "marks": 1},
            {"no": "2", "level": 2,
             "q": "描述一項常用於預備培養基的無菌技術，並概述它的原理。", "marks": 3},
        ],
        "total": 12,
        "reviewed": True,
        "why": "原卷截圖：3(a)=(i)3+(ii)3+(iii)2+(iv)(1)1+(iv)(2)3=12 分",
    },
    # 3(b) 的 (i) 被 OCR 併進 stem；(ii) 是引導句卻被誤記 3 分（原卷 (ii) 不印分值，
    # 分值在下面的 (1)2 分與 (2)3 分）。流程圖內容也從截圖抄回題幹。
    "lq_2014_q3_b": {
        "newSubs": [
            {"no": "i", "level": 1,
             "q": "從前，芝士是牛奶經周遭微生物活動轉變而成。芝士的味道主要來自微生物的"
                  "代謝物。同一年內，不同季節生產出來的芝士批次，其味道也不盡相同。"
                  "試解釋這現象。",
             "marks": 3},
            {"no": "ii", "level": 1,
             "q": "現今，芝士是在受控情況下進行大量生產，以確保其品質及穩定性。以下流程圖"
                  "顯示芝士的生產過程中，一些涉及微生物的步驟：\n\n"
                  "收集新鮮牛奶 → (I) 巴斯德消毒法 → (II) 發酵／凝固：加入某種細菌，"
                  "並可加入黴菌孢子 → (III) 成熟",
             "marks": None},
            {"no": "1", "level": 2,
             "q": "就品質及穩定性而言，解釋步驟 (I) 及 (II) 的重要性。", "marks": 2},
            {"no": "2", "level": 2,
             "q": "生產藍芝士時，會在步驟 (II) 把少量某種需氧黴菌的孢子混入凝固的芝士內，"
                  "並在步驟 (III) 用針在芝士上鑽孔。當大量孢子在芝士內出現時，孢子的顏色"
                  "（藍色）便會變得明顯。以下照片顯示芝士成熟前後的外觀："
                  "試描述在芝士上鑽孔這個步驟如何令藍芝士出現成熟後的外觀。",
             "marks": 3},
        ],
        "stem": "",
        "total": 8,
        "reviewed": True,
        "why": "原卷截圖：3(b)=(i)3+(ii)(1)2+(ii)(2)3=8 分；(ii) 為引導句不計分",
    },
}

# 只記錄、不改數據的缺口（源文件本身不全，要重掃完整原卷才能補）
GAPS = {
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
        # ---- 結構修正：OCR 把多個小題併成一條時，整份替換 subqs
        if "newSubs" in f:
            new = []
            for s in f["newSubs"]:
                item = {"no": s.get("no"), "level": s.get("level", 1),
                        "q": s.get("q", ""), "marks": s.get("marks")}
                new.append(item)
            q["subqs"] = new
        else:
            # 依 no 順序套用；同名的第二个用 #2 区分
            seen = {}
            for s in subs:
                no = s.get("no")
                seen[no] = seen.get(no, 0) + 1
                key = no if seen[no] == 1 else "%s#%d" % (no, seen[no])
                if key in f["subs"] and f["subs"][key] is not None:
                    s["marks"] = f["subs"][key]
        if "stem" in f:
            q["stem"] = f["stem"]
        if f.get("reviewed"):
            q["needsReview"] = False
        after = [(s.get("no"), s.get("marks")) for s in (q.get("subqs") or [])]
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
