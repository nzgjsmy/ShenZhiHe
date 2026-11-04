# -*- coding: utf-8 -*-
"""把卷一乙部的解析結果（scratch/_p1_raw/<year>.json）併進正式資料檔。

用法
----
    python scripts/pastpaper/lq1_build.py 2019          # 併入某一年（覆蓋該年）
    python scripts/pastpaper/lq1_build.py 2019 --dry    # 只看不寫

設計
----
· **按年份覆蓋**：同一年重跑就整年替換，不會留下半新半舊的題目。
· 新併入的題目一律 `needsReview: true` —— 這是 OCR 結構化結果，還沒人工核對過，
  前端會顯示「待核對」標記，提醒使用者重要處要對照原卷。
· `imgs` 由 `lq_figures.py` 事後補（它要讀 page 字段算頁範圍），這一步先留空。
"""
import io
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_DIR = os.path.join(_ROOT, "scratch", "_p1_raw")
DST = os.path.join(_ROOT, "data", "bio", "_lq_p1.json")

# ── 人工修正表 ──────────────────────────────────────────────────────────
# VLM 對「兩欄對照表」這種版式會整張讀成線性文字：欄標題黏在題幹末尾，
# 右欄的 A/B/C/D 選項混進左欄的填空項裡（實測 2019 Q1）。
# 按題目 id 打補丁，**重跑 parse 不會丟** —— 比直接手改 _lq_p1.json 安全，
# 後者下次 parse→build 就被覆蓋了。
#   patch: {小題號: {要覆蓋的欄位}}
#   drop : 要刪掉的小題號（內容已併進別的小題）
FIXES = {
    "lq1_2019_q1": {
        "patch": {
            "a": {"q": "物理屏障和化學屏障是人體的第一道防線。由欄Ⅱ選擇屬於欄Ⅰ內兩種屏障的"
                        "所有正確例子，然後將英文字母寫在所提供的空位內。\n"
                        "<table><tr><td>欄 I</td><td>欄 II</td></tr>"
                        "<tr><td>(i) 物理屏障 ____</td><td>A. 皮膚<br>B. 眼淚</td></tr>"
                        "<tr><td>(ii) 化學屏障 ____</td><td>C. 抗體<br>D. 血凝塊<br>E. 胃液</td></tr>"
                        "</table>"},
        },
        "drop": ["i", "ii"],   # 兩者本來就沒有獨立分值，已併進 (a) 的表格
    },
    # 2012 Q1：VLM 把「欄 1／欄 2」整片配對表判成空白（y 348–956 那塊），
    # 題幹只剩一句引導語，卡片上看不到任何選項。按原卷補回。
    "lq1_2012_q1": {
        "qpatch": {
            "stem": "因應欄 1 所列的每一種血細胞，從欄 2 選出一項有關其功能的正確描述，"
                    "並把字母填寫在預留的空位內。\n"
                    "<table><tr><td>欄 1</td><td>欄 2</td></tr>"
                    "<tr><td>淋巴細胞 &nbsp;____</td><td>A. 涉及血液凝固</td></tr>"
                    "<tr><td>血小板 &nbsp;____</td><td>B. 涉及運輸氧氣</td></tr>"
                    "<tr><td>紅血細胞 &nbsp;____</td><td>C. 涉及產生抗體</td></tr>"
                    "<tr><td></td><td>D. 涉及吞噬作用</td></tr>"
                    "<tr><td></td><td>E. 涉及運輸激素</td></tr></table>",
        },
    },
}


def apply_fixes(qs):
    for q in qs:
        fx = FIXES.get(q["id"])
        if not fx:
            continue
        # 大題層級的覆蓋（例如整段題幹被 OCR 漏掉）
        if fx.get("qpatch"):
            q.update(fx["qpatch"])
        for s in q.get("subqs") or []:
            p = (fx.get("patch") or {}).get(s.get("no"))
            if p:
                s.update(p)
        if fx.get("drop"):
            q["subqs"] = [s for s in q["subqs"] if s.get("no") not in fx["drop"]]
    return qs


def convert(year, qs):
    out = []
    for q in qs:
        subs = []
        for s in q.get("subs") or []:
            subs.append({
                "no": s.get("no"),
                "level": s.get("level") or 1,
                "q": s.get("q") or "",
                "marks": s.get("marks"),
            })
        out.append({
            "id": "lq1_%s_q%s" % (year, q["qnum"]),
            "year": year,
            "paper": 1,
            "qnum": q["qnum"],
            "part": "B",
            "partName": "乙部",
            "chapter": "",
            "stem": q.get("stem") or "",
            "imgs": [],
            "figRefs": [],
            "subqs": subs,
            "marksTotal": q.get("marksTotal"),
            "page": q.get("page"),
            "needsReview": True,      # OCR 結構化，尚未人工核對
            "hasFig": bool(q.get("hasFig")),
        })
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    if not args:
        print("用法: python scripts/pastpaper/lq1_build.py 2019 [2018 ...]")
        return
    data = json.load(io.open(DST, encoding="utf-8"))
    years = data.setdefault("years", {})
    for y in args:
        raw = os.path.join(RAW_DIR, "%s.json" % y)
        if not os.path.exists(raw):
            print("  跳过 %s：找不到 %s（先跑 lq1_parse.py）" % (y, raw))
            continue
        src = json.load(io.open(raw, encoding="utf-8"))
        qs = apply_fixes(convert(y, src.get("questions") or []))
        if not qs:
            print("  跳过 %s：解析结果为空" % y)
            continue
        years[y] = qs
        tot = sum((q.get("marksTotal") or 0) for q in qs)
        print("  %-5s 併入 %2d 道大題 · %3d 小題 · %s 分"
              % (y, len(qs), sum(len(q["subqs"]) for q in qs), tot or "?"))
    if dry:
        print("  （--dry：未寫入）")
        return
    # 年份按字串排序，PP/SP 放最後
    order = sorted(years.keys(), key=lambda k: (k in ("PP", "SP"), k))
    data["years"] = {k: years[k] for k in order}
    io.open(DST, "w", encoding="utf-8", newline="\n").write(
        json.dumps(data, ensure_ascii=False, indent=1))
    n = sum(len(v) for v in data["years"].values())
    print("  → %s  共 %d 年 · %d 道大題" % (DST, len(data["years"]), n))


if __name__ == "__main__":
    main()
