# -*- coding: utf-8 -*-
"""把官方「参考答案.pdf」的**全部页面 OCR 成纯文本**存档，并建立
「参考 PDF ↔ 我们收录的卷二」的**内容匹配矩阵**。

为什么要做这个
--------------
之前的核对只验了**卷一 MC 答案表**（2012 命中 15/18），确认参考 PDF 的年份
与我们数据对应。但卷二评分参考在 PDF 的哪几页、它讲的是不是我们收录的那
份卷二，都还没落实 —— 直接拿它去校正分值有可能张冠李戴。

做法：用中文 **字符 bigram 重合度**做匹配。题干里的专有词（「遷移農業」
「人工魚礁」「Dolly」「胰島素」…）会在同一份卷的评分参考里反复出现，
而不同年份之间几乎不重合。bigram 对扫描件的错字也相对宽容。

用法
----
  python scripts/pastpaper/ref_text_dump.py             # OCR 全部页并存档
  python scripts/pastpaper/ref_text_dump.py --match     # OCR 完顺便出匹配矩阵

产出
----
  scratch/_ref_text/<年份>/pNNN.txt    每行一个 OCR 框的文本
  scratch/_ref_match.json             匹配矩阵
"""
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.environ.get("LQ_PAGES_DIR") or os.path.join(ROOT, "scratch", "_ref_pages")
TXT = os.path.join(ROOT, "scratch", "_ref_text")
LQ = os.path.join(ROOT, "data", "bio", "_lq.json")

_eng = None

# 中文停用词：只保留有信息量的片段
STOP = set("的了吗是在和有與與我你他她它這那個些之於於對對於就都也很並而"
           "以下如果因所以但是而且一個一些進行表示其中可以需要用以及由從"
           "將把被讓使給各該其此則若當如根據關於比較指出試說明解釋".split())


def eng():
    global _eng
    if _eng is None:
        from rapidocr_onnxruntime import RapidOCR
        _eng = RapidOCR()
    return _eng


def dump_page(task):
    key, pg = task
    dst = os.path.join(TXT, key, pg.replace(".jpg", ".txt"))
    if os.path.exists(dst):
        return key, pg, "skip", 0
    path = os.path.join(PAGES, key, pg)
    res, _ = eng()(path)
    items = []
    for box, txt, sc in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append((round(min(ys)), round(min(xs)), (txt or "").strip()))
    items.sort()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        for y, x, t in items:
            if t:
                f.write("%s\n" % t)
    return key, pg, "ok", len(items)


def bigrams(s):
    """中文字符 bigram（先去掉空白与标点）。"""
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", s)
    out = set()
    for i in range(len(s) - 1):
        bg = s[i:i + 2]
        if bg[0] in STOP or bg[1] in STOP:
            continue
        out.add(bg)
    return out


def load_ref_grams():
    """→ {年份: {页码: set(bigram)}}"""
    ref = {}
    for key in sorted(os.listdir(TXT)):
        d = os.path.join(TXT, key)
        if not os.path.isdir(d):
            continue
        pages = {}
        for pg in sorted(os.listdir(d)):
            if not pg.endswith(".txt"):
                continue
            with open(os.path.join(d, pg), encoding="utf-8") as f:
                body = f.read()
            pages[pg[:-4]] = bigrams(body)
        ref[key] = pages
    return ref


def main():
    do_match = "--match" in sys.argv
    keys = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = PAGES
    if not keys:
        keys = sorted(d for d in os.listdir(base)
                      if os.path.isdir(os.path.join(base, d)))
    tasks = []
    for k in keys:
        d = os.path.join(PAGES, k)
        if not os.path.isdir(d):
            continue
        for pg in sorted(f for f in os.listdir(d)
                         if f.lower().endswith((".jpg", ".png", ".jpeg"))):
            tasks.append((k, pg))
    print("[plan] %d 页" % len(tasks), flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(dump_page, t) for t in tasks]
        for fu in as_completed(futs):
            fu.result()
            done += 1
            if done % 20 == 0:
                print("   %d/%d" % (done, len(tasks)), flush=True)
    print("[done] OCR %d 页 → %s" % (done, TXT), flush=True)

    if not do_match:
        return

    ref = load_ref_grams()
    lq = json.load(open(LQ, encoding="utf-8"))
    matrix = {}
    for year, qs in lq["years"].items():
        for q in qs:
            g = bigrams(q.get("stem") or "")
            if not g:
                continue
            scores = {}
            for rk, pages in ref.items():
                for pg, pg_g in pages.items():
                    if not pg_g:
                        continue
                    inter = len(g & pg_g)
                    if inter:
                        scores[(rk, pg)] = inter / len(g)
            best = sorted(scores.items(), key=lambda z: -z[1])[:3]
            if best and best[0][1] > 0.12:
                matrix[q["id"]] = {
                    "qnum": q.get("qnum"),
                    "year": year,
                    "top": [{"ref": rk, "page": pg, "score": round(sc, 3)}
                            for (rk, pg), sc in best],
                }
                print("  %-16s %-6s → %s" % (
                    q["id"], q.get("qnum"),
                    ", ".join("%s/%s %.2f" % (rk, pg, sc)
                              for (rk, pg), sc in best)), flush=True)
    with open(os.path.join(ROOT, "scratch", "_ref_match.json"), "w",
              encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
