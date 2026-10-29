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


def translate(text):
    """英→繁中。失敗回空字串（呼叫端保留英文，不阻斷流程）。

    ⚠️ 用的是 Google 的免費端點（client=gtx），非官方 API，隨時可能失效或限流。
    所以：① 只翻入選的少數條目 ② 失敗一律回空、保留原文 ③ 原文另存 orig 供核對。
    """
    if not text:
        return ""
    try:
        q = urllib.parse.quote(text[:900])
        url = ("https://translate.googleapis.com/translate_a/single"
               "?client=gtx&sl=en&tl=zh-TW&dt=t&q=" + q)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            data = json.loads(r.read().decode("utf-8"))
        return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
    except Exception as e:
        print("    翻譯失敗（保留英文）：%s" % str(e)[:50])
        return ""


def fetch(url):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ShenZhiHe/1.0)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        return r.read()


def main():
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
                # 翻譯標題與摘要；失敗就保留英文，不丟條目
                zh_t = translate(title)
                zh_x = translate(desc[:300])
                if zh_t:
                    entry["orig"] = entry["t"]
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
