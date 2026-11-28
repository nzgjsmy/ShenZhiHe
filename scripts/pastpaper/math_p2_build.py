"""數學 DSE 卷二（MC）逐題裁圖。

數學 P2 是掃描件（無文字層），且大量分式／根號／圖形，OCR 轉文字必然失真，
所以題庫走「原卷題圖」路線：用 OCR 找出每頁的題號位置，以相鄰題號之間為一題的範圍，
整幅寬度裁下來；跨頁的題目把下一頁頂部那段接在同一張圖下面。

幾種排版都要處理：
  * 一般單頁（2012–2013、2015–2023、2025）
  * **跨頁拼版**（2014：每張 PDF 頁 = 左右兩個印刷頁，1191×842），要按中縫切開、左先右後
  * 有些年份第一張 PDF 頁就是正文（2018 沒有封面頁），不能固定跳過第 1 頁

輸出：
  site/img/pp/math/<year>/qNN.webp
  scratch/mathpp/crops_<year>.json   （給 math_p2_dataset.py 合成 JSON）

用法：
    python scripts/pastpaper/math_p2_build.py 2014 --sheet
    python scripts/pastpaper/math_p2_build.py            # 全部年份
"""
import json
import os
import re
import sys

import numpy as np
import pymupdf
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = r"G:\.shortcut-targets-by-id\1j-j-2gxdrFRBPz-Pnuv31FRi8n_Fx_MA\DSE Past Paper（持續更新中）\3. 數學"
OUTDIR = os.path.join(ROOT, "site", "img", "pp", "math")
WORK = os.path.join(ROOT, "scratch", "mathpp")

FILES = {
    "2012": "2012 P2.pdf", "2013": "2013 P2.pdf", "2014": "2014 P2.pdf",
    "2015": "2015 P2.pdf", "2016": "2016 P2.pdf", "2017": "2017 P2.pdf",
    "2018": "2018 P2.pdf", "2019": "2019 P2.pdf", "2020": "2020 P2.pdf",
    "2021": "2021 P2.pdf", "2022": "2022 P2.pdf", "2023": "2023 P2.pdf",
    "2024": "2024 P2.pdf", "2025": "2025 P2.pdf",
}

DPI = 150           # 裁图分辨率（与站内其他真题页图一致）
# 题号检测分辨率：200 对多数年份最准；150 在 2012／2015 这类淡扫描上反而更稳，
# 可用环境变量 MATHPP_DET_DPI 覆盖后单独重跑某一年。
DET_DPI = int(os.environ.get("MATHPP_DET_DPI", "200"))
RE_LEAD_NUM = re.compile(r"^(\d{1,2})\s*[.．](?!\d)")


def page_gray(page, dpi=DPI, clip=None):
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, clip=clip)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    # 有些卷子（2018）四周有黑色扫描边框，行/列投影会把整页当成一大块墨，
    # 题号检测与裁图全乱；MATHPP_TRIM=0.015 先把边框裁掉再分析。
    trim = float(os.environ.get("MATHPP_TRIM", "0") or 0)
    if trim > 0:
        dy, dx = int(a.shape[0] * trim), int(a.shape[1] * trim)
        a = a[dy:a.shape[0] - dy, dx:a.shape[1] - dx]
    return a, a.shape[1], a.shape[0]


def clean_mask(a, thr=170):
    """墨迹遮罩：抹掉扫描边线（整列/整行几乎全黑），否则左边距会被拉歪。"""
    m = a < thr
    if m.size == 0:
        return m
    cf = m.mean(axis=0)
    rf = m.mean(axis=1)
    m[:, cf > 0.5] = False
    m[rf > 0.5, :] = False
    return m


def rows_of(a, thr=170, join=3):
    """按行切开，返回 [(y0, y1, minx, maxx)]。"""
    m = clean_mask(a, thr)
    rr = np.where(m.any(axis=1))[0]
    groups = []
    for y in rr:
        if groups and y - groups[-1][1] <= join:
            groups[-1][1] = y
        else:
            groups.append([y, y])
    out = []
    for y0, y1 in groups:
        seg = m[y0:y1 + 1]
        cc = np.where(seg.any(axis=0))[0]
        if len(cc):
            out.append((int(y0), int(y1), int(cc.min()), int(cc.max())))
    return out


def content_bbox(a):
    m = clean_mask(a)
    cols = np.where(m.any(axis=0))[0]
    rws = np.where(m.any(axis=1))[0]
    if len(cols) == 0:
        return None
    return int(cols.min()), int(cols.max()), int(rws.min()), int(rws.max())


def margin_x(a, w):
    """左边距（题号列）：取各行行首 x 的众数。

    不能直接用整页 content_bbox 的 x0 —— 卷面左缘若有扫描边线，bbox 会给出 0，
    条带就切到空白区，题号整列认不出来（2018／2022 的第 1 题就是这样漏的）。
    """
    rows = rows_of(a)
    cand = [r[2] for r in rows if r[2] < w * 0.35]
    if not cand:
        return content_bbox(a)[0]
    mx = int(np.bincount(np.array(cand)).argmax())
    if mx < w * 0.04:              # 众数贴着纸边 → 是扫描边线，不是题号列
        return content_bbox(a)[0]
    return mx


def content_bottom(a, footer_ratio=0.9):
    m = clean_mask(a)
    h = a.shape[0]
    rws = np.where(m.any(axis=1))[0]
    rws = rws[rws < h * footer_ratio]
    return int(rws.max()) if len(rws) else int(h * footer_ratio)


def logical_pages(doc):
    """把 PDF 页拆成「印刷页」：宽 > 1.4×高 视为左右拼版，按中缝切，左先右后。"""
    out = []
    for i in range(doc.page_count):
        r = doc[i].rect
        if r.width > r.height * 1.4:
            mid = r.x0 + r.width / 2
            out.append((i, "L", pymupdf.Rect(r.x0, r.y0, mid, r.y1)))
            out.append((i, "R", pymupdf.Rect(mid, r.y0, r.x1, r.y1)))
        else:
            out.append((i, "", pymupdf.Rect(r.x0, r.y0, r.x1, r.y1)))
    return out


def page_tokens(ocr, a):
    img = np.stack([a] * 3, axis=-1)
    res, _ = ocr(img)
    out = []
    for box, txt, score in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append({"t": txt.strip(), "x0": min(xs), "x1": max(xs),
                    "y0": min(ys), "y1": max(ys)})
    return out


def strip_qnums(ocr, a, x0, band=None):
    """左边界窄条 OCR：题号是孤立数字，不会被题干糊住（2012 就是靠这个补全的）。

    条带宽度要按页宽比例给：2024 原卷解像度是其他年份的 1.8 倍，
    固定 90px 的窄条切不到题号（整页识别也会把「1.」当噪声丢掉）。
    """
    env = os.environ.get("MATHPP_STRIP", "")
    if env:                      # 需要時可指定絕對條帶範圍，例如 MATHPP_STRIP="230,420"
        x0, x1 = [int(v) for v in env.split(",")]
    elif band:
        x0, x1 = band
    else:
        x0, x1 = max(0, x0 - 10), x0 + max(90, int(a.shape[1] * 0.06))
    strip = a[:, x0:x1]
    if strip.size == 0:
        return []
    img = np.stack([strip] * 3, axis=-1)
    res, _ = ocr(img)
    got = []
    for box, txt, score in (res or []):
        m = re.match(r"^(\d{1,2})\s*[.．,，]?$", txt.replace(" ", ""))
        if m:
            got.append((int(m.group(1)), int(min(p[1] for p in box))))
    return got


def detect_qnums(ocr, a, w, h, x0=None, band=None):
    """找题号：允许与题干糊在同一 token（"34.若 x…"），要求贴左边、不在页脚。"""
    toks = page_tokens(ocr, a)
    cand = []
    for t in toks:
        m = RE_LEAD_NUM.match(t["t"])
        if not m:
            continue
        if t["y0"] > h * 0.92 or t["x0"] > w * 0.42:
            continue
        cand.append((int(m.group(1)), t["y0"]))
    if x0 is not None:
        cand += [(n, y) for n, y in strip_qnums(ocr, a, x0, band) if y <= h * 0.92]
    cand.sort(key=lambda z: z[1])
    clean, last, lasty = {}, 0, -999
    for n, y in cand:
        if y - lasty < 24:            # 同一行的重复识别
            continue
        if n > last:                  # 题号必须递增
            clean[n] = y
            last, lasty = n, y
    return clean


def fill_gaps(pages):
    """在相邻两个已识别题号之间补漏（跨页也要能补）。"""
    def seq_of():
        out = [(n, pi, y) for pi, p in enumerate(pages) for n, y in p["qn"].items()]
        out.sort()
        return out

    for k in range(1, 46):
        seq = seq_of()
        if any(n == k for n, _, _ in seq):
            continue
        prev = [x for x in seq if x[0] < k]
        nxt = [x for x in seq if x[0] > k]
        if not prev or not nxt:
            continue
        _, ppi, py = prev[-1]
        _, npi, ny = nxt[0]
        cands = []
        for pi in range(ppi, min(npi, len(pages) - 1) + 1):
            p = pages[pi]
            for y0, y1, mnx, mxx in p["rows"]:
                if pi == ppi and y0 < py + 40:
                    continue
                if pi == npi and y0 > ny - 20:
                    continue
                if mxx - mnx < 20:      # 太窄的一小截（页码、标点）不算
                    continue
                cands.append((pi, y0, mnx))
        if not cands:
            continue
        # 一道题在 150dpi 下至少 150px 高；候选行若紧贴上一题开头，多半是选项行，
        # 直接拿它当边界会裁出「只有一行选项」的废图（2015 Q8–Q11 踩过）。
        far = [c for c in cands if c[0] != ppi or c[1] > py + 150]
        if far:
            cands = far
        mn = min(c[2] for c in cands)
        pick = None
        for pi, y0, mnx in cands:
            if mnx <= max(pages[pi]["x0"] + 12, mn + 10):
                pick = (pi, y0)
                break
        if pick is None:
            pick = (cands[0][0], cands[0][1])
        pages[pick[0]]["qn"][k] = pick[1]
        print("    补漏：第 %d 题 → p%d%s y=%d" %
              (k, pages[pick[0]]["pdfpage"] + 1, pages[pick[0]]["half"], pick[1]))


def build_year(ocr, year):
    doc = pymupdf.open(os.path.join(BASE, year, FILES[year]))
    pages = []
    for pdfidx, half, clip in logical_pages(doc):
        a, w, h = page_gray(doc[pdfidx], DPI, clip)
        bb = content_bbox(a)
        if bb is None:
            continue
        # 题号检测：默认 200dpi＋6% 宽条带。若一页只认出 0–1 个题号（扫描淡、
        # 版面特殊），依次换「更宽条带／150dpi／300dpi」重试，取认出来最多的那组。
        qn_raw, sc = {}, 1.0
        # 条带宽度要试几档：太窄切不到题号（2024），太宽会把题干吃进来、
        # 题号与公式糊成一个 token（2022 的「1.α2-α-β2+β=」）。
        anchor = os.environ.get("MATHPP_ANCHOR", "mode")
        if anchor == "scan":
            # 各页左边距不一致的卷子（2018 重新排版：第 1 页 181px、第 2 页 347px），
            # 固定锚点必串页；改成在左半页扫几段窄条，把所有题号并起来。
            hi, hw, hh = page_gray(doc[pdfidx], DET_DPI, clip)
            merged = {}
            for f in (0.06, 0.10, 0.14, 0.18, 0.22):
                got = detect_qnums(ocr, hi, hw, hh, int(hw * f),
                                   (int(hw * f), int(hw * (f + 0.07))))
                for n, y in got.items():
                    merged.setdefault(n, y)
            qn_raw, sc = merged, w / hw
        else:
            for det_dpi, ratio in ((DET_DPI, 0.06), (DET_DPI, 0.12), (DET_DPI, 0.03),
                                   (150, 0.05), (300, 0.05)):
                hi, hw, hh = page_gray(doc[pdfidx], det_dpi, clip)
                hx0 = content_bbox(hi)[0] if anchor == "bbox" else margin_x(hi, hw)
                band = (max(0, hx0 - 10), hx0 + int(hw * ratio))
                got = detect_qnums(ocr, hi, hw, hh, hx0, band)
                if len(got) > len(qn_raw):
                    qn_raw, sc = got, w / hw
                if len(qn_raw) >= 3:   # 甲部每页最多 4 题、乙部 3 题，认到 3 个就够
                    break
        qn = {n: int(y * sc) for n, y in qn_raw.items()}
        x0, x1, ytop, ybot = bb
        pages.append({"pdfpage": pdfidx, "half": half, "a": a, "w": w, "h": h,
                      "qn": qn, "x0": x0, "x1": x1, "ytop": ytop,
                      "rows": rows_of(a), "cb": content_bottom(a)})
        print("  p%02d%s 题号 %s" % (pdfidx + 1, ("-" + half) if half else "", sorted(qn)))

    # 全局单调校验：题号必须按页序递增。同一题号在两页都「认出来」时，
    # 后面那个多半是把公式/星号读成题号（2018 Q34、2022 Q41 都踩过）。
    # 允许的跳跃：一页最多 4–5 题，所以「比上一个题号大很多」的候选多半是把
    # 公式里的数字读成了题号（如 2016 把 "34." 误认在很前面，结果把真 34–45 全挡掉）。
    # 相邻两个题号在卷面上永远是连号（最多跳 1–2，因为可能漏认），所以比上一个
    # 题号大 3 以上的候选就是公式/页脚被读成题号（2021 p10 的「38.／40.」把 31–39 全挡过）。
    last = 0
    for p in pages:
        keep = {}
        for n, y in sorted(p["qn"].items(), key=lambda kv: kv[1]):
            if last < n <= last + 3:
                keep[n] = y
                last = n
        p["qn"] = keep

    # 第 1 题常在「甲部」标题下面、题干紧接题号，OCR 容易把「1.」与公式糊在一起漏掉；
    # 它的位置可以确定地推出来：本页 2 题上方、行首贴边的那一行。
    for p in pages:
        if 1 in p["qn"] or 2 not in p["qn"]:
            continue
        y2 = p["qn"][2]
        # 参考左边距用「本页最靠左的行首」（x0 遇到扫描边线会是 0，不能直接用）
        mref = min((r[2] for r in p["rows"]), default=p["x0"])
        cand = [r for r in p["rows"]
                if r[2] <= mref + 20 and p["ytop"] < r[0] < y2 - 40]
        if cand:
            p["qn"][1] = cand[-1][0]
            print("    補第 1 题 → p%d%s y=%d" % (p["pdfpage"] + 1, p["half"], cand[-1][0]))

    fill_gaps(pages)
    allnums = [n for p in pages for n in p["qn"]]
    missing = [n for n in range(1, 46) if n not in allnums]
    dup = sorted({n for n in allnums if allnums.count(n) > 1})
    if missing or dup:
        print("  ⚠️ 题号异常：缺 %s，重复 %s" % (missing, dup))

    outdir = os.path.join(OUTDIR, year)
    os.makedirs(outdir, exist_ok=True)
    crops = []
    for pi, p in enumerate(pages):
        order = sorted(p["qn"].items(), key=lambda kv: kv[1])
        for k, (n, y0) in enumerate(order):
            top = max(0, int(y0) - 8)
            cont = None
            if k + 1 < len(order):
                bot = int(order[k + 1][1]) - 14
            else:
                bot = int(p["cb"]) + 4
                nxt = pages[pi + 1] if pi + 1 < len(pages) else None
                if nxt and nxt["qn"]:
                    first_y = min(nxt["qn"].values())
                    # 只有「本题把本页排到最底」时才可能跨页
                    if bot >= p["cb"] - 2 and first_y - nxt["ytop"] > 20:
                        cont = (nxt, max(0, int(nxt["ytop"]) - 6), int(first_y) - 16)
            x0 = max(0, p["x0"] - 6)
            x1 = min(p["w"], p["x1"] + 6)
            img = Image.fromarray(p["a"][top:bot, x0:x1])
            if cont:
                nxt, cy0, cy1 = cont
                if cy1 > cy0:
                    nx0 = max(0, nxt["x0"] - 6)
                    nx1 = min(nxt["w"], nxt["x1"] + 6)
                    img2 = Image.fromarray(nxt["a"][cy0:cy1, nx0:nx1])
                    W = max(img.width, img2.width)
                    canvas = Image.new("L", (W, img.height + 14 + img2.height), 255)
                    canvas.paste(img, (0, 0))
                    canvas.paste(img2, (0, img.height + 14))
                    img = canvas
            fp = os.path.join(outdir, "q%02d.webp" % n)
            # 2024 的原卷掃描解像度是其他年份的 1.8 倍，裁出來會特別大，
            # 統一壓到 1300px 寬（和站內其他真題圖同級），檔案才不會爆。
            if img.width > 1300:
                img = img.resize((1300, max(1, int(img.height * 1300 / img.width))))
            img.convert("RGB").save(fp, "WEBP", quality=82, method=5)
            crops.append({"qnum": n, "page": p["pdfpage"] + 1, "half": p["half"],
                          "file": fp, "size": list(img.size), "cont": bool(cont)})
    crops.sort(key=lambda c: c["qnum"])
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, "crops_%s.json" % year), "w", encoding="utf-8") as f:
        json.dump(crops, f, ensure_ascii=False, indent=1)
    tot = sum(os.path.getsize(c["file"]) for c in crops) / 1024
    print("  → %s：%d 张，共 %.1f KB，跨页 %d 题" %
          (year, len(crops), tot, sum(1 for c in crops if c["cont"])))
    return crops


def sheet(year, crops, per_row=3, target_w=520):
    """联络表：把裁好的题图缩小拼成一张，方便目检有没有裁错。"""
    if not crops:
        return None
    ims = []
    for c in crops:
        im = Image.open(c["file"])
        r = target_w / im.width
        ims.append((c["qnum"], im.resize((target_w, max(1, int(im.height * r))))))
    rows = (len(ims) + per_row - 1) // per_row
    pad = 10
    rowh = [max(im.height for _, im in ims[r * per_row:(r + 1) * per_row]) for r in range(rows)]
    W = per_row * target_w + (per_row + 1) * pad
    H = sum(rowh) + (rows + 1) * pad
    canvas = Image.new("RGB", (W, H), "white")
    y = pad
    for r in range(rows):
        x = pad
        for qnum, im in ims[r * per_row:(r + 1) * per_row]:
            canvas.paste(im, (x, y))
            x += target_w + pad
        y += rowh[r] + pad
    fp = os.path.join(WORK, "sheet_%s.png" % year)
    canvas.save(fp)
    return fp


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    years = args or sorted(FILES)
    ocr = RapidOCR()
    for y in years:
        print("== %s" % y, flush=True)
        crops = build_year(ocr, y)
        if "--sheet" in sys.argv:
            print("  联络表", sheet(y, crops))


if __name__ == "__main__":
    main()
