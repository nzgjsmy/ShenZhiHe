# -*- coding: utf-8 -*-
"""LQ（卷二）解析 —— PaddleOCR-VL 版。

与 lq_parse.py 的根本区别
-------------------------
`lq_parse.py` 面对的是 PP-OCR 的**碎片化块**（一行一块），必须靠 x 坐标
推断层级，结果把小题当大题（2019 p4 切出 3 道，实际 1 道）。

PaddleOCR-VL 的每块是**完整语义单元、题号在行首**：
    text  2(a) 在非洲的一些細小村落…    ← 大題
    text  (i) 扼要描述…                 ← 小問
    table <table>…                      ← 表格
    text  (1) 根據兩個系統…             ← 子項

→ 所以本版**完全不用 x 坐标**，直接对块内容做正则分类。
   层级由编号形态决定（2(a) / (i) / (1)），天然无歧义。

用法
----
  python scripts/pastpaper/lq_vl_parse.py 2019
  python scripts/pastpaper/lq_vl_parse.py            # 全部有数据的年份

产出
----
  scratch/_lq_vl_raw/<key>.json
"""
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VL = os.path.join(_ROOT, "scratch", "_lq_vl")
OUT = os.path.join(_ROOT, "scratch", "_lq_vl_raw")

RE_BIG = re.compile(
    r"^\s*([lI1]|\d{1,2})\s*[.．]?\s*[（(]\s*([a-zA-Z])\s*[)）]"
)
RE_SUB_ROMAN = re.compile(r"^\s*[（(]\s*([ivxIVX]{1,4})\s*[)）]")
RE_SUB_NUM = re.compile(r"^\s*[（(]\s*(\d{1,2})\s*[)）]")
RE_MARK = re.compile(r"[（(]\s*(\d{1,2})\s*分\s*[)）]")

PART_MAP = [
    (re.compile(r"^甲\s*部"), "A"),
    (re.compile(r"^乙\s*部"), "B"),
    (re.compile(r"^丙\s*部"), "C"),
    (re.compile(r"^丁\s*部"), "D"),
    (re.compile(r"^戊\s*部"), "E"),
]

# 页脚噪声，不进正文。
# ⚠️ header 不能丢：VLM 常把「甲部／章節名」標成 header（實測 2019 p1 的
#    「人體生理學：調節與控制」就是 header），丟了會讓 part 資訊整段消失。
DROP_LABELS = {"footer", "footer_image", "header_image",
               "number", "aside_text", "footnote"}


def norm_num(s):
    """OCR 把 1 讀成 l / I / | → 統一成數字。"""
    return "1" if s in ("l", "I", "|") else s


# 塊內任意位置的「題號」，用於拆開 VLM 的合併塊
RE_ANY_BIG = re.compile(
    r"(?<!\d)(\d{1,2})\s*[.．]?\s*[（(]\s*([a-zA-Z])\s*[)）]"
)


def split_merged(txt):
    """拆開「說明句 + 題號題幹」這種被 VLM 合併成一塊的內容。

    實測 2021 p01 第一塊是：
        「回答本部分内的所有試題。 1(a) 兩名年青學生小美和小光進行…」
    題號不在行首，若直接分類會整道 `1(a)` 丟失。
    → 在題號處切開，前半當普通正文，後半才是大題。
    """
    m = RE_ANY_BIG.search(txt)
    if m and m.start() > 3:
        head = txt[:m.start()].strip()
        tail = txt[m.start():].strip()
        if head and tail:
            return [head, tail]
    return [txt]


def kind_of(t):
    """回傳 (kind, value)。kind ∈ big / sub_roman / sub_num / text"""
    t = t.strip()
    m = RE_BIG.match(t)
    if m:
        return "big", "%s(%s)" % (norm_num(m.group(1)), m.group(2).lower())
    m = RE_SUB_ROMAN.match(t)
    if m:
        return "sub_roman", m.group(1).lower()
    m = RE_SUB_NUM.match(t)
    if m:
        return "sub_num", m.group(1)
    return "text", None


def part_of(t):
    for pat, letter in PART_MAP:
        if pat.match(t.strip()):
            return letter
    return None


def sort_blocks(blocks):
    """按阅读顺序排块。

    ⚠️ `block_order` 為 null 的塊（表格、圖、頁腳）不能簡單排到最後——
       實測 2021 p1 的表格 y=724 在 `(ii)` 之後，若排到最後會誤報
       「表格出現在任何大題之前」。改用 y 座標插回正確位置。
    """
    ordered = [b for b in blocks if b.get("block_order") is not None]
    loose = [b for b in blocks if b.get("block_order") is None]
    ordered.sort(key=lambda b: b["block_order"])
    out = list(ordered)
    for b in loose:
        y = b["block_bbox"][1]
        pos = 0
        for i, r in enumerate(out):
            if r["block_bbox"][1] < y:
                pos = i + 1
        out.insert(pos, b)
    return out


def load_pages(key):
    d = os.path.join(VL, key)
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if not re.match(r"p\d+\.json$", f):
            continue
        n = int(re.search(r"\d+", f).group())
        raw = json.load(open(os.path.join(d, f), encoding="utf-8"))
        r = raw.get("res") or raw
        out.append((n, r))
    out.sort(key=lambda x: x[0])
    return out


PART_TO_NUM = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}


def infer_qids(groups):
    """给缺题号的大題补号。

    比 lq_parse.py 可靠的底气：这里 **part 边界是准的**（VLM 能读出
    「乙部 應用生態學」这种 paragraph_title），而 DSE 卷二固定
    甲=1 乙=2 丙=3 丁=4、每部内 (a)(b) 依序。
    实测 2019：缺的正好是 p7（丙部首题=3(a)）和 p9（丁部首题=4(a)），
    按此规则补完全对。
    """
    # 甲部标题常被 VLM 并入 header 而丢失 → 第一个已知 part 之前视为 A
    first_known = next((i for i, g in enumerate(groups) if g.get("part")), None)
    if first_known is not None:
        for g in groups[:first_known]:
            if not g.get("part"):
                g["part"] = "A"

    by_part = {}
    for g in groups:
        by_part.setdefault(g.get("part"), []).append(g)

    for p, gs in by_part.items():
        num = PART_TO_NUM.get(p)
        if num is None:
            continue
        letter = 0
        for g in gs:
            if g["qid"]:
                m = re.match(r"^(\d+)\(([a-z])\)$", g["qid"])
                if m:
                    letter = ord(m.group(2)) - ord("a") + 1
                continue
            letter += 1
            g["qid"] = "%d(%s)" % (num, chr(ord("a") + letter - 1))
            g["inferred"] = True
    return groups


def parse_year(key):
    pages = load_pages(key)
    if not pages:
        return None

    groups = []
    cur = None
    cur_part = None
    warnings = []

    def new_group(qid, inferred, page, txt):
        g = {
            "qid": qid, "inferred": inferred, "part": cur_part,
            "start_page": page, "stem": txt,
            "subs": [], "texts": [], "marks": [], "tables": [],
        }
        groups.append(g)
        return g

    for pno, r in pages:
        blocks = sort_blocks(list(r.get("parsing_res_list") or []))
        for b in blocks:
            lab = b.get("block_label") or "text"
            txt = (b.get("block_content") or "").strip()
            if not txt or lab in DROP_LABELS:
                continue

            if lab in ("paragraph_title", "header"):
                p = part_of(txt)
                if p:
                    cur_part = p
                    cur = None      # 换部 = 新大题边界
                elif lab == "header":
                    # header 常是章節名（「人體生理學：調節與控制」），
                    # 不含「甲部」二字，但可作 chapter 記錄
                    if cur is not None:
                        cur.setdefault("chapter", txt)
                continue

            if lab == "table":
                if cur is not None:
                    cur["tables"].append({"page": pno, "html": txt})
                else:
                    warnings.append("p%d 表格出现在任何大題之前" % pno)
                continue

            for piece in split_merged(txt):
                kind, val = kind_of(piece)

                if kind == "big":
                    cur = new_group(val, False, pno, piece)
                    continue

                if kind in ("sub_roman", "sub_num"):
                    if cur is None:
                        # 部标题之后直接出现小问 = 大題号被漏检
                        cur = new_group(None, True, pno, piece)
                        warnings.append("p%d 大題号缺失，由第一个小問起头" % pno)
                    cur["subs"].append({
                        "no": val, "kind": kind, "page": pno, "txt": piece,
                    })
                    for m in RE_MARK.finditer(piece):
                        cur["marks"].append(int(m.group(1)))
                    continue

                # 普通正文
                if cur is not None:
                    cur["texts"].append({"page": pno, "txt": piece})
                    for m in RE_MARK.finditer(piece):
                        cur["marks"].append(int(m.group(1)))

    infer_qids(groups)
    return {"key": key, "groups": groups, "warnings": warnings}


def summarize(res):
    gs = res["groups"]
    return {
        "n_groups": len(gs),
        "qids": [g["qid"] or "?" for g in gs],
        "n_sub": sum(len(g["subs"]) for g in gs),
        "n_table": sum(len(g["tables"]) for g in gs),
        "n_inferred": sum(1 for g in gs if g["inferred"]),
        "n_mark": sum(len(g["marks"]) for g in gs),
        "warnings": res["warnings"],
    }


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    keys = sys.argv[1:]
    if not keys:
        keys = sorted(d for d in os.listdir(VL)
                      if os.path.isdir(os.path.join(VL, d))) if os.path.isdir(VL) else []
    for k in keys:
        res = parse_year(k)
        if not res:
            print("[miss]", k)
            continue
        with open(os.path.join(OUT, k + ".json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        s = summarize(res)
        print("=" * 70)
        print("%s  大題=%d  小問=%d  表格=%d  推斷=%d  分值=%d" % (
            k, s["n_groups"], s["n_sub"], s["n_table"],
            s["n_inferred"], s["n_mark"]))
        print("  題號:", s["qids"])
        if s["warnings"]:
            print("  警告:", s["warnings"][:5])
