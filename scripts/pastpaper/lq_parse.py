# -*- coding: utf-8 -*-
"""LQ（卷二）解析器 v2：多信号融合，解決題號 OCR 丟失。

背景：14 份卷二 OCR 後發現「大題題號」識別率極不均勻：
    2022/2023/PP/SP = 0% 丟失      2012/2015/2016 = 12%
    2013/2017 = 25%   2014 = 38%   2018 = 50%
    2020 = 62%       2021 = 88%   2019 = 100%（全丟）
  原因：題號用**加粗**字體印，RapidOCR 在部分掃描件上整個漏讀。

解法（多信號融合，不靠單一正則）
--------------------------------
  信號 1：題號塊本身（OCR 讀到 `1(a)` / `1.(a)` / `l(b)`）——最準，但可能缺失
  信號 2：Part 邊界（「甲部/乙部…」）+「回答本部分內的所有試題」→ 大題起點
  信號 3：**(i)(ii)(1)(2) 小題號序列** —— 每個大題都以小題號開頭；
           小題號 OCR 率達 88%（24-58 個/年），比大題號可靠得多
  信號 4：左邊界 x —— 大題題幹塊的 x 值在同一年內高度一致（該年題號欄位置）

融合邏輯
--------
  以「小題號塊」為骨架切分大題；再用「大題號塊」校正標號；
  缺失時按 DSE 固定編號規則（甲部=1,乙部=2,丙部=3,丁部=4，
  每部固定 2 個大題：(a)(b)）推斷，並標記 inferred=True 供人工核對。

⚠️ 所有 inferred 標記都必須人工核對後才能進正式資料檔。
"""
import io
import json
import os
import re
import sys
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.path.join(_ROOT, "scratch", "_lq_pages")
OUT = os.path.join(_ROOT, "scratch", "_lq_raw")

# ---- 正則 ---------------------------------------------------------------

RE_MARK = re.compile(r"^[（(]\s*(\d{1,2})\s*分\s*[)）]?$")
RE_SUB_ONLY = re.compile(r"^[（(]\s*([0-9]{1,2}|[a-zA-Z]|[ivxIVX]{1,4})\s*[)）]$")
# 大題前綴：1(a) 1.(a) l(b) I(b) 1(a)(i)
RE_BIG_PREFIX = re.compile(
    r"^\s*([lI1]|\d{1,2})\s*[\.．]?\s*[（(]\s*([a-zA-Z])\s*[)）]"
    r"(?:\s*[（(]\s*([0-9]{1,2}|[ivxIVX]{1,4})\s*[)）])?"
)
RE_SUB_PREFIX = re.compile(r"^[（(]\s*([0-9]{1,2}|[ivxIVX]{1,4})\s*[)）]\s*(.*)$")
RE_PARTEND = re.compile(r"回[答覆].{0,12}試?題")

PART_VARIANTS = [
    (re.compile(r"^[甲脸朤]\s*部$"), "A"),
    (re.compile(r"^[乙亿亿]\s*部$"), "B"),
    (re.compile(r"^[丙]\s*部$"), "C"),
    (re.compile(r"^[丁]\s*部$"), "D"),
    (re.compile(r"^[戊]\s*部$"), "E"),
    (re.compile(r"^[己]\s*部$"), "F"),
    # 「部」被讀成形近的「2」
    (re.compile(r"^[最品始贴]\s*[2２]$"), "B"),
    (re.compile(r"^[甲邮]\s*[部邮]$"), "A"),
    (re.compile(r"^[丙]\s*[2２]$"), "C"),
    (re.compile(r"^[丁]\s*[2２]$"), "D"),
    (re.compile(r"^[戊]\s*[2２]$"), "E"),
]

RE_CHAPTER = re.compile(
    r"(人體生理|調節與控制|應用生態|生態學|微生物與人類|生物工程|生物技術|"
    r"應用生熊|生熊|探索|基因|生物多樣|污染|疾病|免疫|細胞|人體)"
)

# DSE 固定編號：甲=1 乙=2 丙=3 丁=4，每部兩個大題 (a)(b)
PART_TO_NUM = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}


def load_pages(key):
    f = os.path.join(PAGES, key, "ocr.json")
    if not os.path.exists(f):
        return []
    with open(f, encoding="utf-8") as fp:
        return json.load(fp)


def detect_part(blocks):
    """找頁面頂部的 Part 標題。回傳 (字母, 原文, 章節名) 或 None。"""
    for i, b in enumerate(blocks):
        t = b["txt"].strip()
        if b["x"] > 470 or b["y"] > 480:
            continue
        for pat, letter in PART_VARIANTS:
            if pat.match(t):
                chap = ""
                for nb in blocks[i + 1:i + 4]:
                    if RE_CHAPTER.search(nb["txt"]):
                        chap = nb["txt"].strip()
                        break
                return letter, t, chap
    return None


def norm_num(num):
    """OCR 把 1 讀成 l/I/l → 統一成數字。"""
    if num in ("l", "I", "l", "|"):
        return "1"
    return num


def _sub_rank(no):
    """把小問號轉成可比較的序號：(i)(ii)(iii) 與 (1)(2)(3) 各成一條序列。"""
    if no is None:
        return (0, 0)
    s = str(no).strip()
    if s.isdigit():
        return (0, int(s))
    low = s.lower()
    if low and all(ch in "ivx" for ch in low):
        val = 0
        for ch in low:
            val = val * 5 + "ivx".index(ch) + 1
        return (1, val)
    return (2, ord(low[0]) - ord("a") + 1 if low else 0)


def _sub_seq_reset(subs, new_no, new_x, x_tol=26):
    """判斷新的小問號是否代表「開了新的大題」。

    實測可靠的信號是 **x 座標**（左邊界），不是小問號序列：
      · 同一大題內，小問號的 x 幾乎完全一致（實測 2012 p2: 245/245/247）
      · 換大題時左邊界會變（2012 p8: 232,232 → 310,311 是嵌套的另一層）

    ⚠️ 序號「回退」**不能單獨當判據**：OCR 常把 (ii) 讀成 (i)
      （實測 2012 p2 出現 i, i, iii 三個，x 全同 —— 實為 i, ii, iii）。
      所以：x 相同 + 序號重複 → 視為同一大題內的**遞增**，不切分。

    判斷順序：
      1. x 明顯變化（超過 x_tol）→ 新大題
      2. x 相同但序號「類型」變了（(i)→(1)）→ 新大題（弱訊號）
      3. x 相同、序號相同或遞增 → 同一大題
    """
    if not subs:
        return False
    prev = subs[-1]
    prev_no, prev_x = prev["no"], prev.get("x")
    if prev_x is not None and new_x is not None and abs(new_x - prev_x) > x_tol:
        return True
    if prev_no is None or new_no is None:
        return False
    pr, nr = _sub_rank(prev_no), _sub_rank(new_no)
    if pr[0] != nr[0]:
        # 序列類型變了（(i) → (1)）：視為新大題
        return True
    # 同 x 且序號重複 → OCR 把 (ii) 讀成 (i)，視為同一大題內遞增
    return False


def parse_year(key):
    pages = load_pages(key)
    if not pages:
        return None

    # ---- 1) 逐頁攤平成 block 序列，標注 part 上下文 ----
    seq = []           # 每個元素：{kind, ...}
    cur_part = None
    cur_chapter = ""
    for pg in pages:
        part = detect_part(pg["blocks"])
        if part:
            cur_part, _, cur_chapter = part
            seq.append({
                "kind": "part", "letter": cur_part, "chapter": cur_chapter,
                "page": pg["page"], "y": -1, "x": 0, "txt": "",
            })
        for b in pg["blocks"]:
            t = b["txt"].strip()
            rec = {
                "page": pg["page"], "x": b["x"], "y": b["y"],
                "x2": b["x2"], "y2": b["y2"], "txt": b["txt"],
                "part": cur_part, "chapter": cur_chapter,
            }
            if RE_MARK.match(t):
                rec["kind"] = "mark"
                rec["value"] = int(RE_MARK.match(t).group(1))
            elif RE_SUB_ONLY.match(t):
                rec["kind"] = "sub"
                rec["value"] = RE_SUB_ONLY.match(t).group(1)
            else:
                m = RE_BIG_PREFIX.match(t)
                if m:
                    rec["kind"] = "big"
                    rec["value"] = "%s(%s)" % (norm_num(m.group(1)), m.group(2))
                    rec["sub"] = m.group(3)
                    rest = t[m.end():].strip()
                    if rest:
                        rec["leftover"] = rest
                else:
                    m = RE_SUB_PREFIX.match(t)
                    if m:
                        rec["kind"] = "sub"
                        rec["value"] = m.group(1)
                        if m.group(2).strip():
                            rec["leftover"] = m.group(2).strip()
                    elif RE_PARTEND.match(t):
                        rec["kind"] = "partend"
                        rec["value"] = t
                    else:
                        rec["kind"] = "text"
                        rec["value"] = t
            seq.append(rec)

    seq.sort(key=lambda r: (r["page"], r["y"], r["x"]))

    # ---- 2) 找出所有「大題起點」候選 ----
    # 候選來源：kind=='big' 的塊（OCR 讀到題號）
    #           或 kind=='sub' 且該頁是第一個小題（Part 內第一個大題的開始）
    bigs = [r for r in seq if r["kind"] == "big"]

    # ---- 3) 大題分組 ----
    #
    # LQ 版式是**三層縮進**（實測 2022 p4 實拍確認）：
    #     2(a)   ← 大題（x 最小，約 200）
    #       (i)    ← 小問（x 約 260）
    #         (1)  ← 子項（x 約 325）
    # 所以 **x 座標 = 層級**，不是「大題邊界」。
    # 真正的「大題邊界」只有兩個可靠信號：
    #   1. OCR 讀到的題號塊（kind=='big'）—— 最準
    #   2. Part 邊界後的第一個題塊
    # 小問/子項一律歸屬當前大題，用 x 記錄其層級。
    groups = []
    cur = None
    for r in seq:
        if r["kind"] == "part":
            cur = None
            continue
        if r["kind"] == "big":
            cur = {
                "qid": r["value"], "inferred": False,
                "part": r["part"], "chapter": r["chapter"],
                "start_page": r["page"], "start_y": r["y"], "start_x": r["x"],
                "stem": r.get("leftover", ""), "subs": [], "texts": [], "marks": [],
            }
            groups.append(cur)
            continue
        if r["kind"] == "sub":
            if cur is None:
                # 沒有 big 骨架（題號 OCR 丟失）：用 Part 內第一個題塊開新大題
                cur = {
                    "qid": None, "inferred": True,
                    "part": r["part"], "chapter": r["chapter"],
                    "start_page": r["page"], "start_y": r["y"], "start_x": r["x"],
                    "stem": r.get("leftover", ""), "subs": [], "texts": [], "marks": [],
                }
                groups.append(cur)
            else:
                # 題號丟失的年份（2019/2020/2021）：靠 x 回退判斷新大題。
                # 大題號欄是最左邊界，小問/子項都比它右移；
                # 當某個小問的 x 回到本大題起始 x 附近（±20px）→ 新的大題。
                # ⚠️ 只對 inferred（無題號錨點）的大題生效 ——
                #    有題號的大題，其 start_x 是「題號欄」，小問 x 本來就更大，
                #    用同一條規則會把小問誤判成新大題。
                if cur.get("inferred"):
                    base_x = cur.get("base_x", cur["start_x"])
                    if r["x"] <= base_x + 20:
                        cur = {
                            "qid": None, "inferred": True,
                            "part": r["part"], "chapter": r["chapter"],
                            "start_page": r["page"], "start_y": r["y"], "start_x": r["x"],
                            "stem": r.get("leftover", ""), "subs": [], "texts": [], "marks": [],
                        }
                        groups.append(cur)
            cur.setdefault("base_x", cur["start_x"])
            cur["subs"].append({
                "no": r["value"], "page": r["page"], "y": r["y"], "x": r["x"],
                "stem": r.get("leftover", ""),
            })
            continue
        if r["kind"] == "mark" and cur is not None:
            cur["marks"].append({"mark": r["value"], "page": r["page"], "y": r["y"]})
            continue
        if r["kind"] == "text" and cur is not None:
            cur["texts"].append({
                "page": r["page"], "y": r["y"], "x": r["x"],
                "txt": r.get("leftover") or r["value"],
            })

    # ---- 4) 給沒有題號的大題推斷編號 ----
    #    規則：同一 Part 內，(a)(b) 依序；(a) 的編號 = Part 序號
    by_part = defaultdict(list)
    for g in groups:
        by_part[g["part"]].append(g)
    for pletter, gs in by_part.items():
        pnum = PART_TO_NUM.get(pletter)
        if pnum is None:
            continue
        # 依開始位置排序
        gs.sort(key=lambda g: (g["start_page"], g["start_y"]))
        # 已有的題號提供錨點
        anchors = [g for g in gs if g["qid"]]
        sub_letter = 0
        for g in gs:
            if g["qid"]:
                m = re.match(r"^(\d+)\(([a-z])\)$", g["qid"])
                if m:
                    pnum = int(m.group(1))
                    sub_letter = ord(m.group(2)) - ord("a") + 1
                    continue
            sub_letter += 1
            g["qid"] = "%d(%s)" % (pnum, chr(ord("a") + sub_letter - 1))

    return {"key": key, "groups": groups, "seq": seq}


def summarize(res):
    gs = res["groups"]
    by_part = defaultdict(list)
    for g in gs:
        by_part[g["part"]].append(g)
    return {
        "n_groups": len(gs),
        "parts": {k: [g["qid"] for g in v] for k, v in by_part.items()},
        "n_sub": sum(len(g["subs"]) for g in gs),
        "n_mark": sum(len(g["marks"]) for g in gs),
        "n_inferred": sum(1 for g in gs if g.get("inferred")),
        "n_noqid": sum(1 for g in gs if not g["qid"]),
    }


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    keys = sys.argv[1:] or ["2019"]
    for k in keys:
        res = parse_year(k)
        if not res:
            print("[miss]", k)
            continue
        with open(os.path.join(OUT, k + ".json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        s = summarize(res)
        print("=" * 66)
        print("%s  大題=%d 小問=%d 分值=%d 無題號=%d 推斷=%d" % (
            k, s["n_groups"], s["n_sub"], s["n_mark"], s["n_noqid"], s["n_inferred"]))
        print("  parts:", s["parts"])
        for g in res["groups"][:10]:
            stem = (g["stem"] or "")[:34]
            print("    %-7s p%-2d subs=%-2d marks=%-2d %s%s" % (
                g["qid"], g["start_page"], len(g["subs"]), len(g["marks"]),
                stem, "  [推斷]" if g.get("inferred") else ""))
