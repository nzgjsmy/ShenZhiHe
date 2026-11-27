"""把「答案表（人工核對）」與「逐題裁圖」合成數學卷二真題庫 JSON。

輸入：
  scratch/mathpp/truth.txt          人工核對後的答案表（每年 45 題：1C94 這種寫法）
  scratch/mathpp/crops_<year>.json  裁圖清單（math_p2_build.py 產出）
輸出：
  data/math/_pastpaper.json         ← 前端「DSE 真題」頁讀這個
  data/math/_mc_answers.json        ← 答案表原檔（供額外資訊的答案表核對用，build 不載入）

題型說明：數學卷二是純選擇題（45 題），但原卷是掃描件、公式與圖形密集，
逐題轉文字必然失真，所以題目一律用原卷裁圖（qImg），選項只給 A/B/C/D 字母。
課題按卷別分兩組：ma1 甲部（Q1–30）、ma2 乙部（Q31–45）。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK = os.path.join(ROOT, "scratch", "mathpp")
OUT = os.path.join(ROOT, "data", "math", "_pastpaper.json")
ANS = os.path.join(ROOT, "data", "math", "_mc_answers.json")

RE_TOK = re.compile(r"^(\d{1,2})([A-D])(\d{1,3})$")


def load_truth():
    data = {}
    with open(os.path.join(WORK, "truth.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            year, rest = line.split(" ", 1)
            d = {}
            for tok in rest.split():
                m = RE_TOK.match(tok)
                if not m:
                    raise SystemExit("答案格式錯誤：%s %s" % (year, tok))
                d[int(m.group(1))] = {"ans": m.group(2), "pct": int(m.group(3))}
            if len(d) != 45:
                raise SystemExit("%s 只有 %d 題" % (year, len(d)))
            data[year] = d
    return data


def main():
    truth = load_truth()
    years = {}
    skipped = []
    for year in sorted(truth):
        cf = os.path.join(WORK, "crops_%s.json" % year)
        if not os.path.exists(cf):
            print("跳過 %s：還沒有裁圖清單" % year)
            continue
        crops = json.load(open(cf, encoding="utf-8"))
        by_q = {c["qnum"]: c for c in crops}
        qs = []
        for n in range(1, 46):
            c = by_q.get(n)
            a = truth[year].get(n)
            if not c or not a:
                print("  ⚠️ %s Q%d 缺裁圖或答案" % (year, n))
                continue
            rel = os.path.relpath(c["file"], os.path.join(ROOT, "site")).replace("\\", "/")
            qs.append({
                "id": "pp_math_%s_q%d" % (year, n),
                "year": year,
                "qnum": n,
                "pct": a["pct"],
                "answer": a["ans"],
                "topic": "ma1" if n <= 30 else "ma2",
                "q": "",
                "qImg": rel,
                "qImgNote": "數學題目含公式與圖形，這裡直接顯示原卷該題區域（含 ABCD 選項）；作答請點下方字母。",
                "options": [],
                "page": c.get("page"),
            })
        # 只收「45 題齊全」的年份：缺題的年份寧可不放，也不要讓學生點到半道題
        if len(qs) != 45:
            print("  ⏭ 跳過 %s（只湊到 %d/45 題，裁圖待補）" % (year, len(qs)))
            skipped.append(year)
            continue
        years[year] = qs
        print("%s：%d 題" % (year, len(qs)))

    doc = {
        "id": "_pastpaper",
        "title": "DSE 數學歷屆真題（卷二 MC）",
        "description": "DSE 數學必修部分卷二選擇題（甲部 Q1–30、乙部 Q31–45）。題目以原卷圖呈現，"
                       "公式與圖形零失真；答案與答對率取自各年《評卷參考》「試卷二」答案表。"
                       "目前收錄 %s 共 %d 個年份 %d 題，其餘年份裁圖整理中。",
        "years": years,
        "pendingYears": skipped,
        # 答案表用：所有已核對年份（含題庫還沒收錄的年份），前端「額外資訊 → 答案表」讀這個
        "answers": {y: {str(k): v for k, v in sorted(d.items())} for y, d in truth.items()},
    }
    n_q = sum(len(v) for v in years.values())
    doc["description"] = doc["description"] % ("、".join(sorted(years)), len(years), n_q)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print("寫入", OUT, "%.0f KB" % (os.path.getsize(OUT) / 1024))

    ansdoc = {
        "title": "DSE 數學卷二（MC）答案與答對率",
        "source": "各年《評卷參考》「試卷二」答案表；括號內為答對百分率",
        "note": "2024 年卷二評卷參考未包含答案表（該年檔案只有卷一評卷參考與考生表現），故暫缺。",
        "years": {y: {"%d" % k: v for k, v in sorted(d.items())} for y, d in truth.items()},
    }
    with open(ANS, "w", encoding="utf-8") as f:
        json.dump(ansdoc, f, ensure_ascii=False, indent=1)
    print("寫入", ANS)


if __name__ == "__main__":
    main()
