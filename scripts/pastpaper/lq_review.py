# -*- coding: utf-8 -*-
"""LQ（卷二）人工核对工具：生成单文件 HTML，左页图右 OCR 块。

用途
----
`lq_parse.py` 无法可靠区分「大題号 / 小问 / 子项」——实测 2019 p4 上只有
一道大題 `2(a)`，parse 却切出 `2(a)(b)(c)` 三道（把 `(i)(ii)` 当成了大題）。
且 OCR 会成片漏检（同一页 `2(a)` 的题干首行两版引擎都没识别出来）。

→ 所以改為「机器给候选、人工点确认」：
   本工具把页图与 OCR 块叠在一起，按缩进层级（x）着色，
   最左层自动标为「大題候选」，人工逐页确认/修正后导出 JSON。

用法
----
  python scripts/pastpaper/lq_review.py 2019
  python scripts/pastpaper/lq_review.py 2019 2018 2013
  LQ_OCR_ENGINE=v6 python scripts/pastpaper/lq_review.py 2019   # 用 v6 的 OCR

产出
----
  scratch/_lq_review/<key>.html      单文件（图片 base64 内嵌，双击即可看）
  人工在页面里点完后，按「导出」下载 <key>-marks.json
"""
import base64
import io
import json
import os
import sys

from PIL import Image

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.path.join(_ROOT, "scratch", "_lq_pages")
V6DIR = os.path.join(_ROOT, "scratch", "_lq_ocr_v6")
OUT = os.path.join(_ROOT, "scratch", "_lq_review")

ENGINE = os.environ.get("LQ_OCR_ENGINE", "v4").strip().lower()
MAXW = 1150          # 页图缩放后的宽度（够看清题号，又不至于文件太大）
QUALITY = 72


def load_ocr(key):
    if ENGINE == "v6":
        f = os.path.join(V6DIR, key + ".json")
    else:
        f = os.path.join(PAGES, key, "ocr.json")
    if not os.path.exists(f):
        return None
    return json.load(open(f, encoding="utf-8"))


def page_img_b64(key, n):
    """回傳 (base64, 原圖寬, 原圖高)。

    ⚠️ 必須回傳原圖尺寸：舊版 lq_build 產出的 ocr.json 裡 W=0 / H=null，
    若拿它算百分比，所有框的座標都會錯（H=1 → y 全部溢出頁面）。
    """
    p = os.path.join(PAGES, key, "p%03d.jpg" % n)
    if not os.path.exists(p):
        return None, 0, 0
    im = Image.open(p).convert("RGB")
    W0, H0 = im.size
    h = int(im.height * MAXW / im.width)
    im = im.resize((MAXW, h), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=QUALITY, optimize=True)
    return base64.b64encode(buf.getvalue()).decode(), W0, H0


def build_payload(key):
    pages = load_ocr(key)
    if not pages:
        return None
    out = []
    for pg in pages:
        n = pg["page"]
        img, W0, H0 = page_img_b64(key, n)
        if img is None:
            continue
        blocks = []
        for b in pg["blocks"]:
            t = b["txt"].strip()
            if not t:
                continue
            blocks.append({
                "x": b["x"], "y": b["y"], "x2": b["x2"], "y2": b["y2"],
                "t": t,
            })
        blocks.sort(key=lambda z: (z["y"], z["x"]))
        out.append({
            "page": n,
            "W": pg.get("W") or W0,      # 舊資料 W=0 → 用原圖寬
            "H": pg.get("H") or H0,      # 舊資料 H=null → 用原圖高
            "img": img,
            "blocks": blocks,
        })
    return {"key": key, "engine": ENGINE, "pages": out}


HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>LQ 核对 · __KEY__</title>
<style>
  :root{
    --bg:#0f1216; --panel:#171c22; --line:#2a323b; --ink:#e6edf3;
    --dim:#8b98a5; --accent:#4aa8ff; --hot:#ff6b6b; --warm:#ffb347;
    --ok:#3fb950;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:14px/1.5 -apple-system,"Segoe UI","Noto Sans TC",sans-serif}
  header{position:sticky;top:0;z-index:50;background:var(--panel);
         border-bottom:1px solid var(--line);padding:10px 16px;
         display:flex;gap:14px;align-items:center;flex-wrap:wrap}
  h1{font-size:15px;margin:0;font-weight:600}
  .tag{font-size:12px;color:var(--dim);border:1px solid var(--line);
       border-radius:999px;padding:1px 9px}
  button{background:#222b34;color:var(--ink);border:1px solid var(--line);
         border-radius:7px;padding:6px 12px;font-size:13px;cursor:pointer}
  button:hover{border-color:var(--accent);color:var(--accent)}
  button.primary{background:var(--accent);color:#06121f;border-color:var(--accent);
                 font-weight:600}
  .wrap{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:0;
        align-items:start}
  .pages{padding:16px;overflow:auto}
  .side{position:sticky;top:57px;height:calc(100vh - 57px);overflow:auto;
        border-left:1px solid var(--line);background:var(--panel);padding:12px}
  .pg{position:relative;margin:0 auto 26px;max-width:100%;width:fit-content}
  .pg img{display:block;width:100%;border-radius:6px;background:#fff}
  .pglabel{font-size:12px;color:var(--dim);margin-bottom:5px}
  .box{position:absolute;border:1px dashed transparent;border-radius:2px;
       cursor:pointer}
  body.showall .box{border-color:rgba(255,255,255,.16)}
  .box:hover{background:rgba(74,168,255,.22);border-color:var(--accent)}
  .box.lv0{background:rgba(255,107,107,.14);border-color:rgba(255,107,107,.55)}
  .box.lv1{background:rgba(255,179,71,.10);border-color:rgba(255,179,71,.4)}
  .box.marked{background:rgba(63,185,80,.30);border-color:var(--ok);
              box-shadow:0 0 0 2px rgba(63,185,80,.5)}
  .box.active{background:rgba(74,168,255,.42);border-color:var(--accent);
              box-shadow:0 0 0 2px var(--accent)}
  .row{border:1px solid var(--line);border-radius:7px;padding:6px 8px;
       margin-bottom:6px;cursor:pointer;background:#1b2129}
  .row:hover{border-color:var(--accent)}
  .row.active{border-color:var(--accent);background:#1e2a38}
  .row.marked{border-color:var(--ok);background:#16241a}
  .row .meta{font-size:11px;color:var(--dim);display:flex;gap:8px;
             margin-bottom:2px;align-items:center}
  .row .txt{font-size:13px;word-break:break-all}
  .lvpill{font-size:10px;padding:0 6px;border-radius:999px;border:1px solid}
  .lv0 .lvpill{color:var(--hot);border-color:var(--hot)}
  .lv1 .lvpill{color:var(--warm);border-color:var(--warm)}
  .hint{font-size:12px;color:var(--dim);line-height:1.6;margin-bottom:12px}
  .kbd{background:#222b34;border:1px solid var(--line);border-radius:4px;
       padding:0 5px;font-size:11px}
  .pgsel{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
  .pgsel button{padding:3px 9px;font-size:12px}
  .pgsel button.on{background:var(--accent);color:#06121f;border-color:var(--accent)}
</style>
</head>
<body>
<header>
  <h1>LQ 核对 · __KEY__</h1>
  <span class="tag" id="engineTag">__ENGINE__</span>
  <span class="tag" id="cnt">已标记 0</span>
  <span style="flex:1"></span>
  <button onclick="toggleAllBoxes()" id="abtn">显示所有框：关</button>
  <button onclick="toggleManual()" id="mbtn">手动补：关</button>
  <button onclick="autoMark()">自动标最左层</button>
  <button onclick="clearAll()">清空</button>
  <button class="primary" onclick="exportJSON()">导出 JSON</button>
</header>

<div class="wrap">
  <div class="pages" id="pages"></div>
  <div class="side">
    <div class="hint">
      <b>点</b>右侧条目 → 左侧图上高亮定位。<b>双击</b>条目 → 标成「大題号」（再双击取消）。<br>
      <b>红框</b> = 本页题号块中最靠左的一层（大題候选）；<b>黄框</b> = 次左层。<br>
      <b>OCR 漏检时</b>：打开「显示所有框」→ 图上空白处就是 OCR 没读到的区域；
      再开「手动补」→ 点该处输入题号（如 <span class="kbd">2(a)</span>），
      即可补一个绿框标记。<br>
      所有标记存在浏览器本地，按右上角「导出 JSON」下载。
    </div>
    <div class="pgsel" id="pgsel"></div>
    <div id="rows"></div>
  </div>
</div>

<script>
const DATA = __DATA__;
const KEY = DATA.key;
const STORE = "lqmarks2:" + KEY + ":" + DATA.engine;

// 只把「看起来像题号」的块纳入分层，避免「乙部」「回答本部分內…」被误当候选
// 形态：2(a) / 1.(b) / (i) / (1)
const RE_NUM = /^\s*(?:\d{1,2}\s*[.．]?\s*[（(]\s*[a-zA-Z]\s*[)）]|[（(]\s*(?:\d{1,2}|[ivxIVX]{1,4})\s*[)）])/;

// marks: { "page:y": {page,y,x,x2,y2,txt,manual} }
let marks = {};
try { marks = JSON.parse(localStorage.getItem(STORE) || "{}"); } catch(e){}

// 每页按「题号块」的 x 分层：最小的一批 = L0
const LV = {};
DATA.pages.forEach(p => {
  const xs = p.blocks.filter(b => RE_NUM.test(b.t)).map(b => b.x);
  const minx = xs.length ? Math.min(...xs) : 0;
  LV[p.page] = p.blocks.map(b => {
    if (!RE_NUM.test(b.t)) return 2;
    if (b.x <= minx + 45) return 0;
    if (b.x <= minx + 105) return 1;
    return 2;
  });
});

let curPage = DATA.pages.length ? DATA.pages[0].page : 1;
let manualMode = false;

function toggleAllBoxes(){
  const on = document.body.classList.toggle("showall");
  const b = document.getElementById("abtn");
  b.textContent = "显示所有框：" + (on ? "开" : "关");
}

function toggleManual(){
  manualMode = !manualMode;
  const b = document.getElementById("mbtn");
  b.textContent = "手动补：" + (manualMode ? "开" : "关");
  b.style.background = manualMode ? "var(--warm)" : "";
  b.style.color = manualMode ? "#1a1200" : "";
  document.querySelectorAll(".pg").forEach(e =>
    e.style.cursor = manualMode ? "crosshair" : "");
}

function keyOf(pg, b){ return pg + ":" + b.y; }

function render(){
  const host = document.getElementById("pages");
  host.innerHTML = "";
  DATA.pages.forEach(p => {
    const d = document.createElement("div");
    d.className = "pg";
    d.id = "pg" + p.page;
    d.innerHTML = '<div class="pglabel">第 ' + p.page + ' 页 · ' + p.blocks.length + ' 块</div>';
    const img = document.createElement("img");
    img.src = "data:image/jpeg;base64," + p.img;
    d.appendChild(img);

    const layer = document.createElement("div");
    layer.className = "layer";
    layer.style.position = "absolute";
    layer.style.inset = "0";
    layer.onclick = e => { if (manualMode) addManual(p, e, layer); };
    d.appendChild(layer);

    p.blocks.forEach((b, i) => {
      const el = document.createElement("div");
      const lv = LV[p.page][i];
      el.className = "box" + (lv === 0 ? " lv0" : lv === 1 ? " lv1" : "");
      if (marks[keyOf(p.page, b)]) el.classList.add("marked");
      el.dataset.k = keyOf(p.page, b);
      el.style.left = (b.x / p.W * 100) + "%";
      el.style.top = (b.y / p.H * 100) + "%";
      el.style.width = ((b.x2 - b.x) / p.W * 100) + "%";
      el.style.height = ((b.y2 - b.y) / p.H * 100) + "%";
      el.title = b.t;
      el.onclick = e => { e.stopPropagation(); pick(p.page, b, true); };
      el.ondblclick = e => { e.stopPropagation(); toggle(p.page, b); };
      layer.appendChild(el);
    });

    // 已手动补的标记（OCR 漏检处）
    Object.values(marks).forEach(m => {
      if (m.page !== p.page || !m.manual) return;
      const el = document.createElement("div");
      el.className = "box marked";
      el.dataset.k = p.page + ":" + m.y;
      el.style.left = (m.x / p.W * 100) + "%";
      el.style.top = (m.y / p.H * 100) + "%";
      el.style.width = ((m.x2 - m.x) / p.W * 100) + "%";
      el.style.height = ((m.y2 - m.y) / p.H * 100) + "%";
      el.title = m.txt;
      el.onclick = e => { e.stopPropagation(); pick(p.page, m, true); };
      el.ondblclick = e => { e.stopPropagation(); delMark(m.page, m.y); };
      layer.appendChild(el);
    });

    host.appendChild(d);
  });
  renderPgSel();
  renderRows();
}

function renderPgSel(){
  const h = document.getElementById("pgsel");
  h.innerHTML = "";
  DATA.pages.forEach(p => {
    const b = document.createElement("button");
    b.textContent = "p" + p.page;
    if (p.page === curPage) b.className = "on";
    b.onclick = () => { curPage = p.page; renderRows(); renderPgSel();
                        document.getElementById("pg" + p.page)
                          .scrollIntoView({behavior:"smooth", block:"start"}); };
    h.appendChild(b);
  });
}

function renderRows(){
  const p = DATA.pages.find(z => z.page === curPage);
  const h = document.getElementById("rows");
  h.innerHTML = "";
  if (!p) return;

  // 先列本页已标（含手动补的），让人一眼看到成果
  const mine = Object.values(marks).filter(m => m.page === p.page)
                     .sort((a,b) => a.y - b.y);
  if (mine.length) {
    const t = document.createElement("div");
    t.className = "hint";
    t.style.color = "var(--ok)";
    t.textContent = "本页已标 " + mine.length + " 处：";
    h.appendChild(t);
    mine.forEach(m => {
      const row = document.createElement("div");
      row.className = "row marked";
      row.innerHTML = '<div class="meta"><span style="color:var(--ok)">●</span>' +
        '<span>y=' + m.y + ' x=' + m.x + '</span>' +
        (m.manual ? '<span style="color:var(--warm)">手动补</span>' : '') +
        '</div><div class="txt"></div>';
      row.querySelector(".txt").textContent = m.txt || "(手动标记)";
      row.onclick = () => pick(p.page, m, false);
      row.ondblclick = () => delMark(m.page, m.y);
      h.appendChild(row);
    });
    const sep = document.createElement("div");
    sep.style.cssText = "height:1px;background:var(--line);margin:12px 0";
    h.appendChild(sep);
  }

  p.blocks.forEach((b, i) => {
    const lv = LV[p.page][i];
    const row = document.createElement("div");
    row.className = "row" + (lv === 0 ? " lv0" : lv === 1 ? " lv1" : "")
                  + (marks[keyOf(p.page, b)] ? " marked" : "");
    row.dataset.k = keyOf(p.page, b);
    row.innerHTML =
      '<div class="meta"><span class="lvpill">L' + lv + '</span>' +
      '<span>y=' + b.y + '</span><span>x=' + b.x + '</span>' +
      '<span style="flex:1"></span>' +
      '<span style="color:' + (marks[keyOf(p.page,b)] ? 'var(--ok)' : 'var(--dim)') + '">' +
      (marks[keyOf(p.page,b)] ? '● 已标' : '○') + '</span></div>' +
      '<div class="txt"></div>';
    row.querySelector(".txt").textContent = b.t;
    row.onclick = () => pick(p.page, b, false);
    row.ondblclick = () => toggle(p.page, b);
    h.appendChild(row);
  });
  updateCnt();
}

function pick(pg, b, fromImg){
  document.querySelectorAll(".box.active,.row.active")
          .forEach(e => e.classList.remove("active"));
  const k = pg + ":" + b.y;
  const box = document.querySelector('.box[data-k="' + k + '"]');
  if (box) box.classList.add("active");
  const row = document.querySelector('.row[data-k="' + k + '"]');
  if (row) {
    row.classList.add("active");
    if (fromImg) row.scrollIntoView({block:"center"});
  }
}

function toggle(pg, b){
  const k = keyOf(pg, b);
  if (marks[k]) delete marks[k];
  else marks[k] = { page: pg, y: b.y, x: b.x, x2: b.x2, y2: b.y2, txt: b.t };
  localStorage.setItem(STORE, JSON.stringify(marks));
  updateCnt();
  // 增量更新，不重绘（重绘会让页面跳回顶部）
  document.querySelectorAll('.box[data-k="' + k + '"]')
          .forEach(e => e.classList.toggle("marked", !!marks[k]));
  const row = document.querySelector('.row[data-k="' + k + '"]');
  if (row) {
    row.classList.toggle("marked", !!marks[k]);
    const dot = row.querySelector(".meta span:last-child");
    if (dot) {
      dot.textContent = marks[k] ? "● 已标" : "○";
      dot.style.color = marks[k] ? "var(--ok)" : "var(--dim)";
    }
  }
}

function delMark(pg, y){
  delete marks[pg + ":" + y];
  save(true);
}

// 点页图空白处 = 手动补一个 OCR 漏检的题号
function addManual(p, e, layer){
  const rect = layer.getBoundingClientRect();
  const rx = (e.clientX - rect.left) / rect.width;
  const ry = (e.clientY - rect.top) / rect.height;
  const txt = prompt("此处补记一个题号（如 2(a)）；留空则取消：");
  if (!txt || !txt.trim()) return;
  const x = Math.round(rx * p.W), y = Math.round(ry * p.H);
  marks[p.page + ":" + y] = {
    page: p.page, y: y, x: x,
    x2: x + Math.round(0.06 * p.W), y2: y + Math.round(0.022 * p.H),
    txt: txt.trim(), manual: true,
  };
  save(true);
}

function save(repaint){
  localStorage.setItem(STORE, JSON.stringify(marks));
  updateCnt();
  if (repaint) {
    const y = window.scrollY;
    render();
    window.scrollTo(0, y);
  }
}

function updateCnt(){
  document.getElementById("cnt").textContent = "已标记 " + Object.keys(marks).length;
}

function autoMark(){
  if (!confirm("把所有 L0（题号最左层）标为大題号？会覆盖当前标记。")) return;
  marks = {};
  DATA.pages.forEach(p => {
    p.blocks.forEach((b, i) => {
      if (LV[p.page][i] === 0) {
        marks[keyOf(p.page, b)] =
          { page: p.page, y: b.y, x: b.x, x2: b.x2, y2: b.y2, txt: b.t };
      }
    });
  });
  save(true);
}

function clearAll(){
  if (!confirm("清空本年份的所有标记？")) return;
  marks = {};
  save(true);
}

function exportJSON(){
  const arr = Object.values(marks)
    .sort((a,b) => a.page - b.page || a.y - b.y);
  const out = { key: KEY, engine: DATA.engine, n: arr.length, marks: arr };
  const blob = new Blob([JSON.stringify(out, null, 1)],
                        {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = KEY + "-marks.json";
  a.click();
}

render();
</script>
</body>
</html>
"""


def build(key):
    payload = build_payload(key)
    if not payload:
        print("[miss] %s（没有 OCR 数据或页图）" % key)
        return None
    os.makedirs(OUT, exist_ok=True)
    html = (HTML
            .replace("__KEY__", key)
            .replace("__ENGINE__", payload["engine"])
            .replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
    dst = os.path.join(OUT, key + ".html")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)
    mb = os.path.getsize(dst) / 1024 / 1024
    print("[ok] %s  %d 页  %.1f MB  -> %s" % (
        key, len(payload["pages"]), mb, dst))
    return dst


if __name__ == "__main__":
    keys = sys.argv[1:] or ["2019"]
    for k in keys:
        build(k)
