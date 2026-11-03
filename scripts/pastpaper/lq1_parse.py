# -*- coding: utf-8 -*-
"""卷一乙部（長題目）解析器。

與卷二（`lq_parse.py`）的差別
------------------------------
卷二的大題題號是 `1(a)` `1(b)`（題號自帶小問），一年只有 4 道；
卷一乙部是 `1.` `2.` … `11.`（純阿拉伯數字＋句點），一年 10–11 道，
小題另外用 `(a)` `(b)`，再下一層 `(i)` `(ii)` / `(1)` `(2)`。

因為 PaddleOCR-VL 的塊是「完整語義單元」，題號基本都保留在行首
（實測 2019 p016：`3. 以下顯微照片顯示在某花朵內進行減數分裂的某些階段：`），
所以不需要卷二那套「多信號融合」的補救邏輯，按題號順序切就行。
但**跨頁**很常見（2019 的 Q3 題幹在 p16、小題全在 p17），所以要跨頁累積。

用法
----
    python scripts/pastpaper/lq1_parse.py 2019
    python scripts/pastpaper/lq1_parse.py 2019 --first 14 --last 30

輸入：`scratch/_p1_vl/<year>/pNNN.json`（PaddleOCR-VL 產物）
輸出：`scratch/_p1_raw/<year>.json`（中間產物，供人工核對後再入正式資料檔）

⚠️ 這一步**只做結構**（題號／小題／分值／頁碼），不做人工核對。
   分值若 OCR 讀不到就留 null，前端會顯示「—」而不是瞎填。
"""
import io
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VL_DIR = os.environ.get("LQ_OUT_DIR") or os.path.join(_ROOT, "scratch", "_p1_vl")
RAW_DIR = os.path.join(_ROOT, "scratch", "_p1_raw")

# 大題：`3.` `3．` `3、`（VLM 偶爾把句點讀成全角）
RE_BIG = re.compile(r"^\s*(\d{1,2})\s*[\.．、]\s*(.*)$", re.S)
# 小題第一層：(a) (b) …；第二層：(i) (ii) (1) (2)
RE_SUB_A = re.compile(r"^\s*[（(]\s*([a-z])\s*[)）]\s*(.*)$", re.S)
RE_SUB_N = re.compile(r"^\s*[（(]\s*(\d{1,2}|[ivxIVX]{1,4})\s*[)）]\s*(.*)$", re.S)
# 分值：(2 分) / （2分） / ( 2 分 )
RE_MARK = re.compile(r"[（(]\s*(\d{1,2})\s*分\s*[)）]")
# 頁腳/水印，直接丟掉
DROP_LABELS = {"footer", "header", "footnote", "number", "aside_text",
               # 圖內標註（「顯微照片X」「着絲點」）不進題幹 —— 它們是圖的一部分，
               # 原卷頁圖裡看得到；混進題幹只會讓文字讀起來支離破碎。
               "figure_title", "vision_footnote"}
# 答題簿的印刷提示，不是題目內容（VLM 會把它當正文塊讀出來）
NOISE = re.compile(r"(?:請\s*)?在此貼上電腦條碼|將不予評閱|寫於邊界以外|寫於遙界以外|"
                   r"[寫写]?[於于]\s*[邊边]界以外|答案寫在預留的空位內|全部試題均須作答")
# 原卷的答題橫線被讀成 `—` / `____`，不是題目內容
RULE_LINE = re.compile(r"^\s*[—–\-_＿]{2,}\s*$")
# 幻覺碎片：VLM 把答題格附近的空白／手寫痕跡讀成短句，常以「，。」這種語法上不成立的組合收尾
JUNK_TAIL = re.compile(r"^.{0,24}[，,]\s*[。.]?\s*$")


def html_table_to_md(html):
    """保留 VLM 的 <table> HTML，只做清理。

    為什麼不轉 markdown 表格：原卷的表格大量用 colspan/rowspan（例如
    「植物物種數目」橫跨兩欄），markdown 表格不支援合併單元格，轉過去會變成
    表頭 3 欄、資料 4 欄的錯位表格（實測 2019 Q7 就是這樣）。
    保留 HTML 由瀏覽器按原結構排版，前端 `mdLite` 認得 `<table>` 就原樣輸出。
    """
    html = re.sub(r"<img[^>]*/?>", "", html)      # 圖引用指向不存在的本機路徑
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def clean_text(t):
    """清洗一段 VLM 文本：清理表格 HTML、去重複行、刪答題線與幻覺碎片。"""
    if "<table" in t:
        t = re.sub(r"<table[\s\S]*?</table>",
                   lambda m: "\n" + html_table_to_md(m.group(0)) + "\n", t)
    # VLM 把 LaTeX 的花括號多轉義了一層：`$ ^{{-1}} $` → 站內的 tex2html 只認單層
    t = t.replace("{{", "{").replace("}}", "}")
    lines, out = [l.rstrip() for l in t.split("\n")], []
    for l in lines:
        s = l.strip()
        if not s:
            out.append("")
            continue
        if RULE_LINE.match(s):          # 答題橫線
            continue
        # 只剩「的答案」「答案」的殘行：原本是「寫於邊界以外的答案，將不予評閱。」
        # 被 NOISE 切掉前後半段後留下的尾巴
        if re.fullmatch(r"[的之]?\s*答案[，,。.]?", s):
            continue
        if JUNK_TAIL.match(s) and len(s) <= 26:   # 「進田內外的笈安，。」這類幻覺碎片
            continue
        # 純漢字、無任何標點、8–24 字的獨立塊 —— VLM 把答題格附近的手寫痕跡／污漬
        # 讀成「句子」（實測「福建一任官堂竹府下的另苑」）。正常的題目短句一定帶標點。
        if re.fullmatch(r"[\u4e00-\u9fff]{8,24}", s):
            continue
        if NOISE.search(s):
            s = NOISE.sub("", s).strip(" ，,。")
            if not s or re.fullmatch(r"[的之]?\s*答案", s):
                continue
        # 去重：VLM 偶爾把同一句連輸出兩遍（2019 Q8 (b)(i) 整句重複），
        # 比對時先剝掉 `(i) ` 這種小題前綴，否則看起來不相等而漏掉。
        core = re.sub(r"^[（(]\s*[a-z0-9ivxIVX]+\s*[)）]\s*", "", s).strip()
        dup = False
        for o in out:
            oc = re.sub(r"^[（(]\s*[a-z0-9ivxIVX]+\s*[)）]\s*", "", o).strip()
            if core and core == oc:
                dup = True
                break
        if dup:
            continue
        out.append(s)
    # 壓掉多餘空行
    txt = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def page_json(year, n):
    p = os.path.join(VL_DIR, year, "p%03d.json" % n)
    if not os.path.exists(p):
        return None
    return json.load(io.open(p, encoding="utf-8"))


def collect_blocks(year, first, last):
    """按 (頁, y) 順序收集文字塊。image 塊保留佔位（用於判斷題幹裡有沒有圖）。"""
    out = []
    for n in range(first, last + 1):
        d = page_json(year, n)
        if not d:
            continue
        for b in d.get("res", {}).get("parsing_res_list", []):
            lab = b.get("block_label") or ""
            if lab in DROP_LABELS:
                continue
            bb = b.get("block_bbox") or [0, 0, 0, 0]
            txt = (b.get("block_content") or "").strip()
            if lab == "image":
                out.append({"page": n, "y": bb[1], "x": bb[0], "label": "image", "txt": ""})
                continue
            if not txt:
                continue
            out.append({"page": n, "y": bb[1], "x": bb[0], "label": lab, "txt": txt})
    out.sort(key=lambda b: (b["page"], b["y"], b["x"]))
    return out


def split_marks(txt):
    """把 `... 解釋你的答案。(2 分)` 拆成 (正文, 分值)。"""
    ms = RE_MARK.findall(txt)
    if not ms:
        return txt, None
    clean = RE_MARK.sub("", txt).strip()
    return clean, int(ms[-1])


def parse(year, first, last):
    blocks = collect_blocks(year, first, last)
    bigs = []          # [{qnum, page, stem:[], subs:[]}]
    cur = None         # 當前大題
    cur_sub = None     # 當前小題
    pending_mark = None  # 上一塊只有 `(2 分)` 時暫存

    def add_text(t):
        nonlocal pending_mark
        t = clean_text(t)
        if not t:
            return
        body, mk = split_marks(t)
        if mk is not None:
            pending_mark = mk
        if body:
            if cur_sub is not None:
                cur_sub["q"] = (cur_sub["q"] + "\n" + body).strip() if cur_sub["q"] else body
            elif cur is not None:
                cur["stem"].append(body)
        # 分值落在「大題題幹」上（沒有小問的配對題／短文題，分值就印在題幹行末）：
        # 先記下來，收尾時若整題沒有任何小題分值就回填成總分。
        if mk is not None and cur_sub is None and cur is not None:
            cur["stemMark"] = mk
        if mk is not None and cur_sub is not None and cur_sub.get("marks") is None:
            cur_sub["marks"] = mk

    for b in blocks:
        if b["label"] == "image":
            if cur is not None and cur_sub is None:
                cur["hasFig"] = True
            elif cur_sub is not None:
                cur_sub["hasFig"] = True
            continue
        t = b["txt"]

        m = RE_BIG.match(t)
        # 題號必須在行首、且後面接著實質內容（避免把「2 分」「3 個」這種當題號）
        if m and len(m.group(2).strip()) >= 2 and not RE_MARK.match(t):
            cur = {"qnum": str(int(m.group(1))), "page": b["page"],
                   "stem": [], "subs": [], "hasFig": False}
            bigs.append(cur)
            cur_sub = None
            rest = m.group(2).strip()
            # ⚠️ 卷一的題號和小題常印在同一塊：`1. (a) 物理屏障和化學屏障…`
            # 只取 group(2) 當題幹的話，(a) 會被當成正文，整題就少一個小題。
            m2 = RE_SUB_A.match(rest)
            if m2:
                cur_sub = {"no": m2.group(1), "level": 1, "q": "", "marks": None}
                cur["subs"].append(cur_sub)
                add_text(m2.group(2))
            else:
                add_text(rest)
            continue

        m = RE_SUB_A.match(t)
        if m and cur is not None:
            # ⚠️ 大題題號會整塊丟失：2019 的 Q8 題號 `8.` 就沒被讀到，
            # 頁面直接從 `(a) 蝙蝠是夜間出沒的動物…` 開始。若只認題號，整題會被併進 Q7。
            # 判據：同一道大題不會出現兩個 (a) —— 再遇到 (a) 就是新大題，題號 = 上一題 +1。
            if m.group(1) == "a" and any(s["no"] == "a" for s in cur["subs"]):
                cur = {"qnum": str(int(cur["qnum"]) + 1), "page": b["page"],
                       "stem": [], "subs": [], "hasFig": False, "_inferred": True}
                bigs.append(cur)
            cur_sub = {"no": m.group(1), "level": 1, "q": "", "marks": None}
            cur["subs"].append(cur_sub)
            add_text(m.group(2))
            continue

        m = RE_SUB_N.match(t)
        if m and cur is not None:
            cur_sub = {"no": m.group(1), "level": 2, "q": "", "marks": None}
            cur["subs"].append(cur_sub)
            add_text(m.group(2))
            continue

        if cur is not None:
            add_text(t)

    # 切掉甲部（MC）尾巴：甲部最後一頁的 34–36 題會被一起收進來，
    # 之後乙部再從 1 重新編號。用「題號回落」當斷點，不必人工傳 --first
    # （每年甲部佔幾頁不同：2012 到 p11、2014 之後到 p11 但仍要跨頁判斷）。
    def _n(q):
        s = str(q.get("qnum") or "")
        return int(s) if s.isdigit() else None

    cut = 0
    for i in range(1, len(bigs)):
        prev, cur = _n(bigs[i - 1]), _n(bigs[i])
        if cur == 1 and prev and prev > 1:
            cut = i
            break
    if cut:
        print("    （自動切掉甲部殘留 %d 道，從乙部第 1 題起算）" % cut)
        bigs = bigs[cut:]

    # 同一題號出現兩次：頁圖重複造成的（2013 的 1B-3 被放了兩份），
    # 保留第一次出現的那個，後面重複的丟掉 —— 否則前端會顯示兩道一樣的題。
    seen, uniq = set(), []
    for q in bigs:
        if q["qnum"] in seen:
            print("    （題號 %s 重複出現，已丟棄後者 p%s）" % (q["qnum"], q.get("page")))
            continue
        seen.add(q["qnum"])
        uniq.append(q)
    bigs = uniq

    # 收尾：算總分、去重、標記
    for q in bigs:
        q["stem"] = "\n".join(x for x in q["stem"] if x).strip()
        q["subs"] = [s for s in q["subs"] if (s.get("q") or "").strip()]
        total = sum((s.get("marks") or 0) for s in q["subs"])
        if not total and q.get("stemMark"):
            total = q["stemMark"]
        q["marksTotal"] = total or None
        q.pop("stemMark", None)
        q["part"] = "B"
        q["partName"] = "乙部"
    return bigs


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("years", nargs="*", default=["2019"])
    ap.add_argument("--first", type=int, default=1, help="起始頁（跳過甲部 MC）")
    ap.add_argument("--last", type=int, default=99)
    a = ap.parse_args()
    os.makedirs(RAW_DIR, exist_ok=True)
    for y in a.years:
        qs = parse(y, a.first, a.last)
        dst = os.path.join(RAW_DIR, "%s.json" % y)
        json.dump({"year": y, "questions": qs},
                  io.open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        tot = sum((q.get("marksTotal") or 0) for q in qs)
        print("%-5s %2d 道大題 · %3d 小題 · 合計 %s 分 → %s"
              % (y, len(qs), sum(len(q["subs"]) for q in qs), tot or "?", dst))
        for q in qs:
            print("   %-3s p%-3d %-2d 小題 %-4s  %s"
                  % (q["qnum"], q["page"], len(q["subs"]),
                     (q.get("marksTotal") or "?"), q["stem"][:44].replace("\n", " ")))


if __name__ == "__main__":
    main()
