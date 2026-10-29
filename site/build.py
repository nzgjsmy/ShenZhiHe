# -*- coding: utf-8 -*-
"""把 data/<科目>/*.json、links.json、quiz/<科目>/*.json 注入 template.html，
產出單檔離線網站。

科目結構（每個科目完全獨立，資料不互相混雜）：
    data/<sid>/subject.json      科目設定（名稱、顏色、課題清單）
    data/<sid>/<tid>.json        課題內容（sections → points）
    data/<sid>/links.json        本科目內的知識串連
    quiz/<sid>/<tid>.json        課題測驗題

新增科目：在 data/ 下開一個資料夾放 subject.json 即可，build 會自動掃描。
"""
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
DATA = os.path.join(ROOT, "data")
QUIZ = os.path.join(ROOT, "quiz")
EXTRAS = os.path.join(ROOT, "extras")
VER_PATH = os.path.join(BASE, "version.json")
# 舊檔名：留轉址頁，讓既有書籤／桌面捷徑還能用
# 註：這是歷史檔名（早期叫「F6筆記整合網」），刻意保留原字串，
#     因為舊書籤／桌面捷徑指向的就是這幾個檔名，改名會讓轉址失效。
LEGACY_NAMES = ("F6筆記整合網.html", "F6化學筆記整合網.html")

# 版權與免責聲明的預設內容（version.json 的 copyright 欄位可覆寫）
DEFAULT_COPYRIGHT = (
    "本網站一切資源僅供學習用途，請勿商用。"
    "筆記內容整理自公開教材，版權歸原作者及出版方所有。"
)


def site_meta():
    """站名與版號。只改 version.json 一處，檔名、頁面標題、頁尾全部跟著動。"""
    v = load(VER_PATH, {}) or {}
    name = (v.get("name") or "神智核").strip()
    ver = (v.get("version") or "V0.1.0").strip()
    return {
        "name": name,
        "version": ver,
        "subtitle": v.get("subtitle") or "",
        "tagline": v.get("tagline") or "",
        "out_name": "%s-%s.html" % (name, ver),
        "stable_name": "%s.html" % name,
        "note": v.get("note") or "",
        # 版權與免責聲明：由 version.json 提供，注入模板頁尾與「關於」區
        "copyright": v.get("copyright") or DEFAULT_COPYRIGHT,
        "disclaimer": v.get("disclaimer") or [],
    }

# 這些檔名不是課題內容，掃描時要跳過
RESERVED = {"subject", "links", "index"}


def inline_body_images(payload):
    """（回退模式，EMBED_IMG=1 時使用）把 ](img/<file>) 轉成 data URI 內嵌。

    內嵌讓單檔自足，但會把 HTML 撐到 16 MB+——外置模式（預設）見 check_body_images。
    找不到圖檔時保留原引用並計數回報，不中斷建置。
    """
    import base64
    IMG_DIR = os.path.join(BASE, "img")
    pat = re.compile(r"\]\(img/([^)\s]+)\)")
    n, miss = 0, []
    for s in payload.get("subjects", []):
        for t in s.get("topics", []):
            for sec in t.get("sections", []):
                for p in sec.get("points", []):
                    body = p.get("body") or ""
                    if "](img/" not in body:
                        continue

                    def repl(m):
                        nonlocal n
                        fp = os.path.join(IMG_DIR, m.group(1))
                        if not os.path.exists(fp):
                            miss.append(m.group(1))
                            return m.group(0)
                        with open(fp, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode("ascii")
                        n += 1
                        return "](data:image/webp;base64,%s)" % b64
                    p["body"] = pat.sub(repl, body)
    if miss:
        print("  warning: %d 個圖片缺失（引用保留）: %s" % (len(miss), ", ".join(sorted(set(miss))[:5])))
    return n, miss


def check_body_images(payload):
    """外置模式（預設）：保留 ](img/<file>) 相對引用，只校驗檔案存在。

    圖片隨部署包放在 img/ 目錄，HTML 單檔因此保持 ~3 MB；
    Service Worker 的同源緩存天然覆蓋 img/，離線體驗與內嵌一致。
    圖檔缺失照樣回報但不中斷構建（殘缺部署不該讓整站失敗）。
    """
    pat = re.compile(r"\]\(img/([^)\s]+)\)")
    IMG_DIR = os.path.join(BASE, "img")
    files, miss = set(), []
    for s in payload.get("subjects", []):
        for t in s.get("topics", []):
            for sec in t.get("sections", []):
                for p in sec.get("points", []):
                    body = p.get("body") or ""
                    if "](img/" not in body:
                        continue
                    for m in pat.finditer(body):
                        name = m.group(1)
                        if os.path.exists(os.path.join(IMG_DIR, name)):
                            files.add(name)
                        else:
                            miss.append(name)
    if miss:
        print("  warning: %d 個圖片缺失（引用保留）: %s" % (len(miss), ", ".join(sorted(set(miss))[:5])))
    return len(files), miss, files


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def is_topic_name(name):
    if not name.endswith(".json"):
        return False
    stem = name[:-5]
    if stem in RESERVED:
        return False
    # 過程檔／批次檔不是正式課題
    if stem.startswith(("payload", "batch", "tmp", "_")) or stem.endswith("-batch"):
        return False
    return True


def scan_topics(sdir):
    """自動掃描科目資料夾裡的課題檔（依檔名排序）。"""
    return sorted(n[:-5] for n in os.listdir(sdir) if is_topic_name(n))


def load_subject(sid):
    sdir = os.path.join(DATA, sid)
    qdir = os.path.join(QUIZ, sid)
    meta = load(os.path.join(sdir, "subject.json"), {})
    listed = [t for t in (meta.get("topics") or []) if t]
    found = scan_topics(sdir)

    if listed:
        topics_ids = listed
        extra = [t for t in found if t not in listed]
        if extra:
            print("  note: %s 有未列在 subject.json 的課題檔，已忽略：%s"
                  % (sid, ", ".join(extra)))
    else:
        topics_ids = found

    topics = []
    for tid in topics_ids:
        path = os.path.join(sdir, tid + ".json")
        if not os.path.exists(path):
            print("  warning: %s 缺少課題檔 %s.json" % (sid, tid))
            continue
        t = load(path)
        if isinstance(t, dict):
            t.setdefault("id", tid)
            topics.append(t)
        else:
            print("  warning: %s/%s.json 格式不是物件，已跳過" % (sid, tid))

    topics.sort(key=lambda t: str(t.get("id", "")))

    # 知識串連：過濾掉指向不存在的知識點，避免前端出現死連結
    point_ids = set()
    for t in topics:
        for s in t.get("sections", []):
            for p in s.get("points", []):
                point_ids.add(p.get("id"))
    links = []
    dropped = 0
    for l in load(os.path.join(sdir, "links.json"), []) or []:
        if not isinstance(l, dict):
            continue
        if l.get("from") in point_ids and l.get("to") in point_ids:
            links.append(l)
        else:
            dropped += 1
    if dropped:
        print("  note: %s links.json 有 %d 條指向不存在的知識點，已忽略" % (sid, dropped))

    # 測驗題：只收本科目課題的題目
    quiz = {}
    for tid in topics_ids:
        path = os.path.join(qdir, tid + ".json")
        if not os.path.exists(path):
            continue
        q = load(path, {"questions": []})
        if isinstance(q, dict) and isinstance(q.get("questions"), list):
            qs = [x for x in q["questions"] if isinstance(x, dict)]
            if qs:
                quiz[tid] = qs
        else:
            print("  warning: %s/%s.json 測驗題格式不對，已跳過" % (sid, tid))

    # 歷屆真題（_pastpaper.json）：以 _ 開頭不會被 build 當作課題載入，
    # 這裡額外讀進來，掛在 subject 的 _pastpaper 欄位，供前端「DSE 真題」頁面使用。
    pastpaper = None
    pp_path = os.path.join(sdir, "_pastpaper.json")
    if os.path.exists(pp_path):
        pp = load(pp_path, None)
        if isinstance(pp, dict):
            pastpaper = pp
            print("  note: %s 載入歷屆真題 %d 個年份" % (sid, len(pp.get("years", {}))))
        else:
            print("  warning: %s/_pastpaper.json 格式不是物件，已跳過" % sid)

    # DSE 卷二長題目（_lq.json）：與卷一選擇題**完全分開**存放。
    # 用戶明確要求「MC 和 LQ 要分開存放，不然用戶會很亂」：
    # 兩者題型、題號體系、答題方式、統計口徑都不同，混在一份檔案會讓
    # 「446 道選擇題」這類數字失真，也讓人誤以為答對選擇題就學會了。
    lq = None
    lq_path = os.path.join(sdir, "_lq.json")
    if os.path.exists(lq_path):
        d = load(lq_path, None)
        if isinstance(d, dict):
            lq = d
            n_lq = sum(len(v) for v in (d.get("years") or {}).values())
            print("  note: %s 載入卷二長題 %d 個年份 · %d 道大題" % (
                sid, len(d.get("years") or {}), n_lq))
        else:
            print("  warning: %s/_lq.json 格式不是物件，已跳過" % sid)

    # 額外資訊：extras/<科目>/*.json（元素週期表、速查表…），依 order 排序
    extras = []
    edir = os.path.join(EXTRAS, sid)
    if os.path.isdir(edir):
        for n in sorted(os.listdir(edir)):
            if not n.endswith(".json"):
                continue
            x = load(os.path.join(edir, n), None)
            if isinstance(x, dict):
                x.setdefault("id", n[:-5])
                extras.append(x)
        extras.sort(key=lambda x: (x.get("order", 99), str(x.get("id", ""))))

    n_pts = sum(len(s.get("points", [])) for t in topics for s in t.get("sections", []))
    n_q = sum(len(v) for v in quiz.values())
    ready = n_pts > 0

    # 子分區（單元）：把課題分成「熱學／力學／波動學」等大塊，
    # 避免科目底下課題一多就平鋪成一長串。
    # subject.json 用 units 宣告；沒宣告就維持平鋪（化學、生物目前如此）。
    # 重要：unit 只做分組，不影響課題 id 與知識點 id——既有學習進度不受影響。
    units = []
    raw_units = meta.get("units") or []
    tid_set = {t.get("id") for t in topics}
    for u in raw_units:
        if not isinstance(u, dict):
            continue
        u_tids = [x for x in (u.get("topics") or []) if x in tid_set]
        if not u_tids:
            print("  warning: %s 的單元 %s 沒有對應課題，已略過"
                  % (sid, u.get("id")))
            continue
        u_topics = [t for t in topics if t.get("id") in u_tids]
        u_pts = sum(len(s.get("points", [])) for t in u_topics
                    for s in t.get("sections", []))
        u_q = sum(len(quiz.get(t.get("id"), [])) for t in u_topics)
        units.append({
            "id": u.get("id"),
            "title": u.get("title") or u.get("id"),
            "emoji": u.get("emoji") or "",
            "description": u.get("description") or "",
            "topics": u_tids,
            "stats": {
                "topics": len(u_tids),
                "sections": sum(len(t.get("sections", [])) for t in u_topics),
                "points": u_pts,
                "questions": u_q,
            },
        })
    # 沒被任何單元收錄的課題：歸進一個「其他」，避免內容憑空消失
    covered = {x for u in units for x in u["topics"]}
    orphan = [t.get("id") for t in topics if t.get("id") not in covered]
    if orphan:
        if units:
            print("  note: %s 有 %d 個課題不在任何單元內，已歸入「其他」：%s"
                  % (sid, len(orphan), ", ".join(orphan)))
            o_topics = [t for t in topics if t.get("id") in orphan]
            units.append({
                "id": "other", "title": "其他", "emoji": "📎", "description": "",
                "topics": orphan,
                "stats": {
                    "topics": len(orphan),
                    "sections": sum(len(t.get("sections", [])) for t in o_topics),
                    "points": sum(len(s.get("points", [])) for t in o_topics
                                  for s in t.get("sections", [])),
                    "questions": sum(len(quiz.get(t.get("id"), [])) for t in o_topics),
                },
            })
        else:
            print("  note: %s 未宣告單元，首頁維持平鋪顯示 %d 個課題"
                  % (sid, len(topics)))

    subject = {
        "id": sid,
        "title": meta.get("title") or sid,
        "full": meta.get("full") or meta.get("title") or sid,
        "emoji": meta.get("emoji") or "📘",
        "color": meta.get("color") or "#0f766e",
        "order": meta.get("order", 99),
        "description": meta.get("description") or "",
        "source": meta.get("source") or "",
        "ready": ready,
        "topics": topics,
        "units": units,
        "links": links,
        "quiz": quiz,
        "extras": extras,
        "_pastpaper": pastpaper,
        "_lq": lq,
        "stats": {
            "topics": len(topics),
            "sections": sum(len(t.get("sections", [])) for t in topics),
            "points": n_pts,
            "links": len(links),
            "questions": n_q,
            "units": len(units),
        },
    }
    return subject


def discover_subjects():
    if not os.path.isdir(DATA):
        sys.exit("找不到 data 目錄：%s" % DATA)
    ids = []
    for name in sorted(os.listdir(DATA)):
        d = os.path.join(DATA, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "subject.json")):
            ids.append(name)
    if not ids:
        sys.exit("data/ 底下沒有任何科目資料夾（需要 <科目>/subject.json）")
    return ids


def write_legacy_redirect(dst_new, dst_old, site, reason=None):
    """舊檔名留一個轉址頁，讓既有的書籤／桌面捷徑還能用。"""
    if os.path.abspath(dst_new) == os.path.abspath(dst_old):
        return
    name = os.path.basename(dst_new)
    from urllib.parse import quote
    msg = reason or ("已更名為《%s %s》" % (site["name"], site["version"]))
    html = (
        "<!doctype html>\n<html lang=\"zh-Hant\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<meta http-equiv=\"refresh\" content=\"0;url=%s\">\n"
        "<title>%s %s</title>\n"
        "<style>body{margin:0;min-height:100vh;display:flex;align-items:center;"
        "justify-content:center;background:#faf7f2;color:#2b2a26;text-align:center;"
        "font-family:\"Microsoft JhengHei\",\"PingFang TC\",system-ui,sans-serif;padding:20px}"
        "a{color:#0f766e;font-weight:700}</style></head>\n<body><div>\n"
        "<p>網站%s。</p>\n"
        "<p><a href=\"%s\">如果沒有自動跳轉，點這裡 →</a></p>\n"
        "</div><script>location.replace(%s);</script></body></html>\n"
    ) % (quote(name), site["name"], site["version"], msg, quote(name), json.dumps(name))
    with io.open(dst_old, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    site = site_meta()
    subjects = [load_subject(sid) for sid in discover_subjects()]
    subjects.sort(key=lambda s: (s.get("order", 99), s.get("id", "")))

    payload = {"site": site, "subjects": subjects}

    tpl_path = os.path.join(BASE, "template.html")
    with io.open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()

    # 站名與版號：template 裡用佔位符，改版只需動 version.json
    tpl = tpl.replace("/*__SITE_NAME__*/", site["name"])
    tpl = tpl.replace("/*__SITE_VERSION__*/", site["version"])
    tpl = tpl.replace("/*__SITE_SUBTITLE__*/", site["subtitle"])
    # 版權／免責聲明（version.json 的 copyright 欄位；缺省時給一份通用聲明）
    _copy = site.get("copyright") or DEFAULT_COPYRIGHT
    tpl = tpl.replace("/*__SITE_COPYRIGHT__*/", _copy)
    # 逐條免責聲明 → HTML 清單項目（注入頁尾的展開區）
    _disc = site.get("disclaimer") or []
    if isinstance(_disc, str):
        _disc = [_disc]
    _disc_html = "".join("<li>%s</li>" % d for d in _disc)
    tpl = tpl.replace("/*__SITE_DISCLAIMER__*/", _disc_html)

    # 額外資訊的前端程式碼放在 extras.js，build 時注入 template 的佔位符
    ex_path = os.path.join(BASE, "extras.js")
    if os.path.exists(ex_path):
        with io.open(ex_path, encoding="utf-8") as f:
            ex_js = f.read()
        if "/*__EXTRAS_JS__*/" in tpl:
            tpl = tpl.replace("/*__EXTRAS_JS__*/", ex_js)
    else:
        tpl = tpl.replace("/*__EXTRAS_JS__*/", "")

    # 搜索後台 worker（search-worker.js）注入為 base64 Blob URL，
    # 讓單檔離線站也能用 Web Worker，不阻塞主線程。
    sw_path = os.path.join(BASE, "search-worker.js")
    if os.path.exists(sw_path):
        import base64 as _b64
        with open(sw_path, "rb") as _f:
            sw_b64 = _b64.b64encode(_f.read()).decode("ascii")
        sw_src = ("var __SEARCH_WORKER_URL__ = URL.createObjectURL(new Blob([atob('"
                  + sw_b64 + "')], {type:'application/javascript'}));")
        if "/*__SEARCH_WORKER__*/" in tpl:
            tpl = tpl.replace("/*__SEARCH_WORKER__*/", sw_src)
    else:
        tpl = tpl.replace("/*__SEARCH_WORKER__*/", "var __SEARCH_WORKER_URL__ = null;")

    # 筆記原圖：預設外置（保留 ](img/…) 相對路徑，HTML 單檔保持 ~3 MB；
    # EMBED_IMG=1 回退成 data URI 內嵌（單檔自足但 16 MB+）
    if os.environ.get("EMBED_IMG") == "1":
        n_img, miss = inline_body_images(payload)
        img_mode = "內嵌 data URI"
    else:
        n_img, miss, _img_files = check_body_images(payload)
        img_mode = "外置 img/ 相對路徑"

    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # 防止 </script> 破壞注入
    blob = blob.replace("</", "<\\/")
    if "/*__DATA__*/" not in tpl:
        sys.exit("template.html 缺少 /*__DATA__*/ 佔位符")
    out = tpl.replace("/*__DATA__*/", blob)

    print("科目：")
    for s in subjects:
        st = s["stats"]
        flag = "" if s["ready"] else "  (內容準備中)"
        print("  %-5s %-4s 課題 %2d · 章節 %3d · 知識點 %3d · 串連 %2d · 題目 %3d%s"
              % (s["id"], s["title"], st["topics"], st["sections"],
                 st["points"], st["links"], st["questions"], flag))

    # 帶版號的主檔名（例：神智核-V0.1.6.html）
    dst = os.path.join(BASE, site["out_name"])
    with io.open(dst, "w", encoding="utf-8") as f:
        f.write(out)
    # 不帶版號的固定檔名也寫一份，分享連結不會隨改版失效
    dst_stable = os.path.join(BASE, site["stable_name"])
    if os.path.abspath(dst_stable) != os.path.abspath(dst):
        with io.open(dst_stable, "w", encoding="utf-8") as f:
            f.write(out)
    # 舊檔名一律留轉址頁
    for legacy in LEGACY_NAMES:
        p = os.path.join(BASE, legacy)
        if os.path.abspath(p) in (os.path.abspath(dst), os.path.abspath(dst_stable)):
            continue
        reason = ("已更名為《%s %s》" % (site["name"], site["version"])
                  if legacy.startswith(site["name"]) or "整合網" in legacy
                  else "已更名為《%s %s》" % (site["name"], site["version"]))
        write_legacy_redirect(dst_stable, p, site, reason)

    tot = {k: sum(s["stats"][k] for s in subjects) for k in
           ("topics", "sections", "points", "links", "questions")}
    print("\n合計 課題 %d · 章節 %d · 知識點 %d · 串連 %d · 題目 %d"
          % (tot["topics"], tot["sections"], tot["points"], tot["links"], tot["questions"]))
    print("筆記原圖：%s %d 張" % (img_mode, n_img))
    print("站名：%s %s" % (site["name"], site["version"]))
    print("written:", dst, os.path.getsize(dst), "bytes")
    print("stable :", dst_stable, os.path.getsize(dst_stable), "bytes")


if __name__ == "__main__":
    main()