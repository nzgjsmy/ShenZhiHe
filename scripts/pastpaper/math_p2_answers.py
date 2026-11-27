"""數學 DSE 卷二（MC）答案表抽取。

數學的《評卷參考》是掃描件、沒有文字層，答案表長這樣（每頁左右兩欄）：

    題號   答案        題號   答案
    1.     C (94)      26.    A (56)
    ...

括號內 = 該題答對百分率。本工具用 rapidocr 掃每一頁，找出「1–45 全齊」的那頁，
再把數字與答案配對，輸出 data/math/_mc_answers.json。

用法：
    python scripts/pastpaper/math_p2_answers.py            # 全部年份
    python scripts/pastpaper/math_p2_answers.py 2013 2014  # 指定年份
"""
import json
import os
import re
import sys

import numpy as np
import pymupdf
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = r"G:\.shortcut-targets-by-id\1j-j-2gxdrFRBPz-Pnuv31FRi8n_Fx_MA\DSE Past Paper（持續更新中）\3. 數學"
OUT = os.path.join(ROOT, "data", "math", "_mc_answers.json")
RAW = os.path.join(ROOT, "scratch", "mathpp", "ans_raw")

FILES = {
    "2012": ("2012", "2012 DSE 數學 (評卷參考).pdf"),
    "2013": ("2013", "2013 MS.pdf"),
    "2014": ("2014", "2014 MS.pdf"),
    "2015": ("2015", "2015 MS.pdf"),
    "2016": ("2016", "2016 MS+CP.pdf"),
    "2017": ("2017", "2017 MS.pdf"),
    "2018": ("2018", "2018 MS.pdf"),
    "2019": ("2019", "2019 MS.pdf"),
    "2020": ("2020", "2020 MS.pdf"),
    "2021": ("2021", "2021 MS.pdf"),
    "2022": ("2022", "2022 MS.pdf"),
    "2023": ("2023", "2023 MATH MS C.pdf"),
    "2024": ("2024", "2024 MS+CP.pdf"),
    "2025": ("2025", "2025 MS.pdf"),
}

RE_FULL = re.compile(r"^(\d{1,2})\s*[.．]?\s*([A-D])\s*[（(]\s*(\d{1,3})\s*[)）]$")
RE_NUM = re.compile(r"^(\d{1,2})\s*[.．]?$")
RE_ANS = re.compile(r"^([A-D])\s*[（(]\s*(\d{1,3})\s*[)）]$")
RE_ANSNUM = re.compile(r"^([A-D])\s*[（(]\s*(\d{1,3})\s*[)）]\s*(\d{1,2})\s*[.．]?$")


def ocr_page(ocr, page, dpi=150):
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    img = np.stack([img] * 3, axis=-1)
    res, _ = ocr(img)
    out = []
    for box, txt, score in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append({
            "t": txt.strip(),
            "x": sum(xs) / 4,
            "y": sum(ys) / 4,
            "w": max(xs) - min(xs),
            "h": max(ys) - min(ys),
            "w_page": pix.width,
        })
    return out, pix.width, pix.height


def _column_split(ans_list):
    """答案 token 的 x 明显分成两簇，取最大空隙的中点当栏分界（不同年份排版位置不同）。"""
    xs = sorted(t[3] for t in ans_list)
    if len(xs) < 6:
        return None
    gap, cut = 0, None
    for a, b in zip(xs, xs[1:]):
        if b - a > gap:
            gap, cut = b - a, (a + b) / 2
    return cut if gap > 60 else None


def parse_pairs(tokens, page_w=None):
    """把答案表还成 {题号: (答案, 百分比)}。

    答案表固定两栏（左 1–25、右 26–45），同一「行」上左右各有一对「题号 · 答案」。
    所以按 y 把 token 分行，行内用「答案在题号右侧最近」配对 —— 不依赖绝对 x 分栏
    （各年排版左右栏位置不同，用固定 mid 会把右栏题号判成左栏）。
    行内 OCR 漏认题号的，再用栏内 y 序兜底。
    """
    nums, anss, full = [], [], []
    for t in tokens:
        s = t["t"].replace(" ", "")
        m = RE_FULL.match(s) or RE_ANSNUM.match(s)
        if m and len(m.groups()) == 3:
            full.append((t["y"], int(m.group(1)), m.group(2), int(m.group(3))))
            continue
        m = RE_NUM.match(s)
        if m:
            nums.append((t["y"], int(m.group(1)), t["x"]))
            continue
        m = RE_ANS.match(s)
        if m:
            anss.append((t["y"], m.group(1), int(m.group(2)), t["x"]))

    direct = {n: (a, p) for y, n, a, p in full if 1 <= n <= 45}

    # 分行：同一行的 token y 差 < 16px（行距约 28–30px）
    items = [("N", y, n, x) for y, n, x in nums] + [("A", y, a, p, x) for y, a, p, x in anss]
    items.sort(key=lambda z: z[1])
    rows, cur = [], []
    for it in items:
        if cur and it[1] - cur[-1][1] > 16:
            rows.append(cur); cur = []
        cur.append(it)
    if cur:
        rows.append(cur)

    for row in rows:
        ns = [it for it in row if it[0] == "N"]
        as_ = [it for it in row if it[0] == "A"]
        used = set()          # ⚠️ 每行单独计：跨行共用会把后面所有行都判成「已占用」
        for _, ny, n, nx in ns:
            best, bkey = None, None
            for j, (_, ay, a, p, ax) in enumerate(as_):
                if j in used or ax < nx - 12:
                    continue
                key = (abs(ay - ny), ax - nx)
                if bkey is None or key < bkey:
                    best, bkey = j, key
            if best is not None:
                used.add(best)
                _, ay, a, p, ax = as_[best]
                direct.setdefault(n, (a, p))

    # 兜底：按答案 x 分左右两栏，用 y 序补上 OCR 漏认的题号
    by_order = {}
    if anss:
        mid = _column_split(anss) or (page_w or 1e9) * 0.55
        left = sorted([t for t in anss if t[3] < mid], key=lambda t: t[0])
        right = sorted([t for t in anss if t[3] >= mid], key=lambda t: t[0])
        for i, (y, a, p, x) in enumerate(left):
            by_order[i + 1] = (a, p)
        for i, (y, a, p, x) in enumerate(right):
            by_order[26 + i] = (a, p)

    out = {}
    for k in range(1, 46):
        if k in direct:
            out[k] = direct[k]
        elif k in by_order:
            out[k] = by_order[k]
    return out, direct, by_order


def _legacy_parse(tokens):  # noqa: 保留旧接口签名，避免外部脚本报错
    return parse_pairs(tokens)[0]


def scan_year(ocr, year):
    sub, fname = FILES[year]
    doc = pymupdf.open(os.path.join(BASE, sub, fname))
    best = (0, None, None, None, [])
    # 答案表通常就在文件最后几页：从后往前扫，找到就停
    for i in reversed(range(doc.page_count)):
        toks, w, h = ocr_page(ocr, doc[i])
        pairs, direct, byo = parse_pairs(toks, w)
        # 只有「行内配对失败、靠栏序兜底」的题号才需要人工看一眼
        bad = sorted(k for k in pairs if k not in direct)
        print("  %s p%02d 配對 %d 題%s" % (year, i + 1, len(pairs),
                                        "，⚠️ 待核 %s" % bad if bad else ""), flush=True)
        if len(pairs) > best[0]:
            best = (len(pairs), i + 1, pairs, toks, bad)
        if len(pairs) >= 45:
            break
    n, pno, pairs, toks, bad = best
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, "%s.json" % year), "w", encoding="utf-8") as f:
        json.dump({"year": year, "page": pno, "pairs": {str(k): v for k, v in pairs.items()},
                   "conflicts": bad, "tokens": toks or []}, f, ensure_ascii=False, indent=1)
    missing = [k for k in range(1, 46) if k not in pairs]
    print("%s → 第 %d 頁，%d/45 題%s%s" % (year, pno or 0, len(pairs),
                                       "，缺 %s" % missing if missing else "",
                                       "，衝突 %s" % bad if bad else ""))
    hard = bool(missing or bad)
    return pairs, pno, hard


def main():
    want = sys.argv[1:] or sorted(FILES)
    ocr = RapidOCR()
    data = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            data = json.load(f)
    meta = data.setdefault("_meta", {})
    years = data.setdefault("years", {})
    for y in want:
        print("== %s" % y)
        pairs, pno = scan_year(ocr, y)[:2]
        hard = len(pairs) < 45
        if hard:
            print("  ⚠️ %s 只抽到 %d 題，需人工核對" % (y, len(pairs)))
        years[y] = {str(k): {"ans": v[0], "pct": v[1]} for k, v in sorted(pairs.items())}
        meta[y] = {"page": pno, "n": len(pairs), "needReview": hard}
    data["title"] = "DSE 數學卷二（MC）答案與答對率"
    data["source"] = "各年《評卷參考》「試卷二」答案表（括號內為答對百分率）"
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("寫入", OUT)


if __name__ == "__main__":
    main()
