"""抓取科研時事 → data/_news.json

設計原則（重要）：
1. **只抓有摘要的源**。Google News 只有標題和連結，卡片會空掉一半。
   中文用泛科學（pansci.asia，繁體、有摘要、科普向）；
   英文用 ScienceDaily 分科 RSS（物理/化學/生物各有 60 條，品質穩定）。

   **英文條目自動翻譯**（Google 免費接口，非官方）：
   - 只翻「入選」的少數幾條，不是把 60 條全翻 —— 每天最多 6 次請求，避開限流
   - 翻譯失敗就保留英文原文，**不丟數據、不阻塞流程**
   - 原文另存 `orig` 欄位，src 標成「ScienceDaily（譯）」提醒是機翻
2. **寧缺勿濫**。抓不到就保持原樣，不硬湊、不生成假內容。
   時事寫錯的代價遠高於少一條。
3. **一律保留原文連結**。使用者能自己核對，不把我當唯一資訊源。
4. **去重按連結**。同一篇重複抓到不會產生重複卡片。

用法：
  python scripts/fetch_news.py            # 抓取並寫入
  python scripts/fetch_news.py --dry-run  # 只看抓到什麼，不寫檔
"""

import io
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "_news.json")
KEEP = 9          # 保留最近 N 條（每科最多 3 條，前端 3×3 排得整齊）
TIMEOUT = 20

FEEDS = [
    # lang=zh：分類靠關鍵詞判斷；take：每個源最多取幾條（英文源要翻譯，取少一點）
    {"name": "泛科學", "url": "https://pansci.asia/feed", "lang": "zh", "cat": None, "take": 6},
    {"name": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/matter_energy/physics.xml",
     "lang": "en", "cat": "phys", "take": 2},
    {"name": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/matter_energy/chemistry.xml",
     "lang": "en", "cat": "chem", "take": 2},
    {"name": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/plants_animals.xml",
     "lang": "en", "cat": "bio", "take": 2},
]

# 分類關鍵詞：命中越多越優先。泛科學偏醫療，所以 bio 的詞要收緊一點，
# 免得所有健康文章都被歸到生物。
CATS = {
    "chem": ["化學", "分子", "原子", "催化", "合成", "化合物", "結晶", "元素",
             "反應", "電池", "奈米", "材料", "同位素", "酸鹼"],
    "phys": ["物理", "量子", "粒子", "光子", "重力", "雷射", "微中子", "磁場",
             "天文", "宇宙", "衛星", "聲波", "光速", "熱力", "電磁"],
    "bio": ["細胞", "基因", "DNA", "蛋白", "神經", "微生物", "細菌", "病毒",
            "植物", "演化", "免疫", "生態", "癌", "疫苗", "生物", "腦"],
}

# 明顯不是「科研」的內容，直接丟掉（產業、投資、活動公告）
DROP = ["募資", "營收", "股價", "投資", "財報", "合作備忘錄", "簽署", "發表會",
        "優惠", "報名", "抽獎", "課程", "論壇報名", "徵才"]


def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
         .replace("&gt;", ">").replace("&quot;", '"').replace("&#8217;", "’")
         .replace("&#8230;", "…").replace("&#8220;", "「").replace("&#8221;", "」")
         .replace("&#8212;", "—").replace("&#039;", "'"))
    return re.sub(r"\s+", " ", s).strip()


def classify(text):
    """回傳 (cat, score)。分不出來就回 ('', 0)。"""
    best, best_n = "", 0
    for cat, words in CATS.items():
        n = sum(1 for w in words if w in text)
        if n > best_n:
            best, best_n = cat, n
    return best, best_n


def parse_date(s):
    """RSS 的 pubDate → YYYY-MM-DD。失敗回今天。"""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z"):
        try:
            d = datetime.strptime((s or "").strip(), fmt)
            return d.astimezone(timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            continue
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def _g_translate(text, client):
    """Google 免費端點（非官方）。client 不同，走的後端也不同 —— 一個被限流
    另一個往往還能用，這是這條路最關鍵的一點。"""
    q = urllib.parse.quote(text[:900])
    url = ("https://translate.googleapis.com/translate_a/single"
           "?client=%s&sl=en&tl=zh-TW&dt=t&q=%s" % (client, q))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15,
                                context=ssl.create_default_context()) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
    return out if out and out != text else ""


def _mymemory(text):
    """MyMemory 備援（免費翻譯記憶庫，無需 key，匿名每日有額度）。"""
    url = ("https://api.mymemory.translated.net/get?q=%s&langpair=en|zh-TW"
           % urllib.parse.quote(text[:500]))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20,
                                context=ssl.create_default_context()) as r:
        d = json.loads(r.read().decode("utf-8"))
    out = (d.get("responseData") or {}).get("translatedText") or ""
    # 額度用完時它會把警告字串塞進 translatedText
    if "MYMEMORY WARNING" in out.upper() or len(out) < 2:
        return ""
    return out.strip()


# Google 的 zh-TW 輸出常把「系」誤轉成「係」（係 在繁體是「是」的意思）。
# 這幾組是實測抓到、一定錯的，逐條修正；「係數」本身正確，不動。
T2_FIX = [("根係", "根系"), ("係統", "系統"), ("一係列", "一系列"),
          ("體係", "體系"), ("聯係", "聯繫"), ("派係", "派系"),
          ("關係統", "關係系統"), ("學係", "學系"), ("係譜", "系譜")]


def _fix_trad(s):
    for a, b in T2_FIX:
        s = s.replace(a, b)
    return s


def translate(text):
    """英→繁中。失敗回空字串（呼叫端保留英文，不阻斷流程）。

    ⚠️ 用 Google 的免費端點，非官方 API，**會限流**。
    2026-10 實測：`client=gtx` 被 429 擋死（每日時事因此整批沒翻成），
    但 `client=at` 與 `client=dict-chrome-ex` 走的是不同後端，仍然可用。

    所以依序試多個端點，任一成功即止；全失敗才回空、保留英文原文。
    另外：① 只翻入選的少數條目 ② 原文另存 orig 供核對 ③ 條目前後加小延遲。
    """
    if not text:
        return ""
    for client in ("at", "dict-chrome-ex", "gtx"):
        try:
            out = _g_translate(text, client)
            if out:
                return _fix_trad(out)
        except Exception as e:
            print("    翻譯端點 %s 失敗：%s" % (client, str(e)[:40]))
        time.sleep(0.4)
    try:
        out = _mymemory(text)
        if out:
            print("    （改用 MyMemory 備援）")
            return _fix_trad(out)
    except Exception as e:
        print("    MyMemory 也失敗：%s" % str(e)[:40])
    print("    翻譯失敗（保留英文）：%s" % (text or "")[:40])
    return ""


def fetch(url):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ShenZhiHe/1.0)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        return r.read()


def refetch_title(url):
    """回原文頁面取回**完整標題**（補翻舊資料用）。

    ⚠️ 為什麼需要：早先翻譯失敗時只存了截斷到 60 字的 `orig`，
    直接拿它去翻會鬧笑話 —— 實測過：
        "Chinese scientists discover ... a giant fungus with roo" → 「巨型袋鼠菌」
        "Scientists discover a hidden factor that can make or break c" → 「成就或破壞c」
        "...could turn CO2 i" → 「將二氧化碳轉化為二氧化碳」
    所以補翻前先回原頁把標題補全。
    """
    if not url:
        return ""
    try:
        html = fetch(url).decode("utf-8", "ignore")
    except Exception:
        return ""
    pats = (r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title',
            r"<title[^>]*>(.*?)</title>")
    for pat in pats:
        m = re.search(pat, html, re.S | re.I)
        if not m:
            continue
        t = strip_html(m.group(1)).strip()
        t = re.sub(r"\s*[|\-–]\s*ScienceDaily\s*$", "", t, flags=re.I).strip()
        if len(t) >= 20:
            return t
    return ""


def retranslate():
    """把既有 _news.json 裡「沒翻成」的英文條目補翻。

    為什麼需要：翻譯端點會限流（2026-10-30 那批就整批落成英文），
    條目本身已經寫進檔了、不會再被抓一次，所以要有個專門補翻的入口。
    """
    if not os.path.exists(OUT):
        print("  %s 不存在" % OUT)
        return
    d = json.load(io.open(OUT, encoding="utf-8"))
    items = d.get("items") or []

    def is_ascii_title(t):
        # 標題裡沒有中日韓字元 = 還沒翻
        return not re.search(r"[\u4e00-\u9fff]", t or "")

    todo = [it for it in items if is_ascii_title(it.get("t"))]
    print("  待補翻 %d / %d 條" % (len(todo), len(items)))

    fixed = 0
    for it in todo:
        # 一律用**完整原文**去翻。舊資料的 orig 可能是被截到 60 字的版本
        # （那時翻譯失敗、只存了截斷的 t），這種要重新抓原文，不能直接拿來翻。
        t0 = it.get("orig") or it.get("t") or ""
        x0 = it.get("origX") or it.get("x") or ""
        if len(t0) >= 58 and not re.search(r"[。！？.!?]$", t0):
            t0 = refetch_title(it.get("url") or "") or t0
        zh_t = translate(t0)
        if not zh_t:
            print("    ✗ 仍失敗：%s" % t0[:44])
            continue
        it["orig"] = t0
        it["t"] = zh_t[:60]
        # 摘要原本也是英文才重翻，否則保留
        if is_ascii_title(it.get("x")):
            zh_x = translate(x0)
            if zh_x:
                it["x"] = zh_x[:130].rstrip() + ("…" if len(zh_x) > 130 else "")
        src = (it.get("src") or "").replace("（譯）", "")
        it["src"] = src + "（譯）"
        fixed += 1
        print("    ✓ [%s] %s" % (it.get("cat"), it["t"][:44]))
        time.sleep(0.5)

    # 繁中用字修正也對「既有條目」做一次（Google 的 zh-TW 常把「系」誤轉「係」）
    tuned = 0
    for it in items:
        for k in ("t", "x"):
            v = it.get(k)
            if v:
                nv = _fix_trad(v)
                if nv != v:
                    it[k] = nv
                    tuned += 1

    if fixed or tuned:
        io.open(OUT, "w", encoding="utf-8", newline="\n").write(
            json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    print("  補翻 %d 條，用字修正 %d 處" % (fixed, tuned))


def main():
    if "--retranslate" in sys.argv:
        retranslate()
        return

    dry = "--dry-run" in sys.argv

    old = []
    if os.path.exists(OUT):
        try:
            d = json.load(io.open(OUT, encoding="utf-8"))
            old = d.get("items") or []
        except Exception as e:
            print("  警告：讀取既有 _news.json 失敗（%s），視為空" % e)

    seen = {(it.get("url") or "").strip() for it in old}
    got = []

    for feed in FEEDS:
        name, url, lang = feed["name"], feed["url"], feed["lang"]
        fixed_cat, take = feed["cat"], feed["take"]

        try:
            root = ET.fromstring(fetch(url))
        except Exception as e:
            print("  ✗ %s 抓取失敗：%s" % (name, e))
            continue

        items = root.findall(".//item")
        print("  %s：抓到 %d 條（取前 %d）" % (name, len(items), take))

        n = 0
        for it in items:
            if n >= take:
                break

            title = strip_html(it.findtext("title") or "")
            desc = strip_html(it.findtext("description") or "")
            link = (it.findtext("link") or "").strip()
            if not title or not link:
                continue

            # 中文源要擋掉產業/投資類；英文源本身就是科研 RSS，不必擋
            if lang == "zh" and any(w in title for w in DROP):
                continue

            if link in seen:
                continue

            if fixed_cat:
                cat = fixed_cat           # 分科 RSS 直接知道科目，不必猜
            else:
                cat, score = classify(title + " " + desc)
                if score == 0:
                    continue              # 分不出科目 → 不是學科內容

            seen.add(link)

            entry = {
                "date": parse_date(it.findtext("pubDate")),
                "cat": cat,
                "t": title[:60],
                "x": desc[:130].rstrip() + ("…" if len(desc) > 130 else ""),
                "src": name,
                "url": link,
            }

            if lang == "en":
                # ⚠️ 完整原文一定要留下 —— 翻譯失敗後要補翻時，
                # 只有截斷到 60 字的 t 是不夠的：
                # "giant fungus with roo" 會被翻成「巨型袋鼠菌」，
                # "make or break c" 會被翻成「成就或破壞c」。
                entry["orig"] = title
                entry["origX"] = desc
                # 翻譯標題與摘要；失敗就保留英文，不丟條目
                zh_t = translate(title)
                zh_x = translate(desc[:400])
                if zh_t:
                    entry["t"] = zh_t[:60]
                    entry["src"] = name + "（譯）"
                if zh_x:
                    entry["x"] = zh_x[:130].rstrip() + ("…" if len(zh_x) > 130 else "")
                print("     · [%s] %s" % (cat, entry["t"][:40]))

            got.append(entry)
            n += 1

    print("  新增 %d 條（既有 %d 條）" % (len(got), len(old)))

    if dry:
        for g in got:
            print("   · [%s] %s" % (g["cat"], g["t"]))
        return

    if not got:
        print("  沒有新內容 → 保持原檔不變（不硬湊）")
        return

    merged = got + old
    # 按日期新到舊，同日期保持原順序
    merged.sort(key=lambda x: x.get("date") or "", reverse=True)

    # 科目平衡：每科最多 3 條。
    # 不做這個的話中文源偏醫療，bio 會把物理化學全擠出去（實測過）。
    picked, cnt = [], {}
    for it in merged:
        c = it.get("cat") or "bio"
        if cnt.get(c, 0) >= 3:
            continue
        cnt[c] = cnt.get(c, 0) + 1
        picked.append(it)
        if len(picked) >= KEEP:
            break
    merged = picked

    payload = {
        "_note": ("科研時事（站點級，跨科目）。顯示在三科總覽頁。cat 用 bio/chem/phys/math，"
                  "只影響標籤顏色。越新的排越前。內容必須來自可靠來源並附連結"
                  "——時事不是常識，寧可少寫也不要編。"
                  "本檔由 scripts/fetch_news.py 自動抓取泛科學 RSS 產生，可手動補充。"),
        "items": merged,
    }
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print("  已寫入 %s（保留 %d 條）" % (OUT, len(merged)))


if __name__ == "__main__":
    main()
