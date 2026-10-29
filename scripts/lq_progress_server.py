#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VLM 识别进度看板。

用途：lq_vl.py 跑卷二（LQ）识别时，它会连着跑几小时、每页 2–4 分钟，
      命令行看不到整体进度。这个小服务提供一个自动刷新的网页看板。

用法：
    python scripts/lq_progress_server.py [端口]
    然后浏览器打开 http://127.0.0.1:<端口>/

数据来源全部是「读文件系统」，不依赖任何进程内状态，所以：
  · 看板随时开关都不影响后台识别
  · 识别中途崩了，看板会如实显示停在哪个年份

只读，不写任何文件。
"""
import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = os.path.join(ROOT, "scratch", "_lq_pages")   # 原卷页图 pNNN.jpg
VLOUT = os.path.join(ROOT, "scratch", "_lq_vl")      # VL 产物 pNNN.json
LOGS = [os.path.join(ROOT, "scratch", f) for f in
        ("_vl_run3.log", "_vl_run2.log", "_vl_run.log")]

# 显示顺序：已完成的年份在前，正在跑的排最前（运行时会重排）
ORDER = ["2018", "2022", "2023", "2019", "2020", "2021", "2013",
         "2012", "2014", "2015", "2016", "2017", "SP", "PP"]

RE_PAGE = re.compile(r"^p(\d{3})\.(jpg|json)$")


def count_dir(path, ext):
    if not os.path.isdir(path):
        return 0
    n = 0
    for f in os.listdir(path):
        if f.endswith(ext):
            n += 1
    return n


def years():
    names = set()
    for base in (PAGES, VLOUT):
        if os.path.isdir(base):
            for d in os.listdir(base):
                if os.path.isdir(os.path.join(base, d)):
                    names.add(d)
    ordered = [y for y in ORDER if y in names]
    ordered += sorted(y for y in names if y not in ORDER)
    return ordered


def tail_log(lines=12):
    """取最新日志的尾部。日志可能有 GBK 乱码的 Paddle 启动信息，只保留有意义的行。"""
    for p in LOGS:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 20000))
                raw = f.read()
            txt = raw.decode("utf-8", "replace")
            keep = []
            for ln in txt.splitlines():
                s = ln.rstrip()
                if not s:
                    continue
                # 只要我们的进度行和 [done] 行
                if re.search(r"^\s+(20\d\d|PP|SP)\s+p\d+", s) or s.startswith("[done]") or s.startswith("[miss]"):
                    keep.append(s)
            return keep[-lines:]
        except Exception as e:  # noqa: BLE001
            return ["（读取日志失败：%s）" % e]
    return []


def current_state():
    """从日志最后一行推断「正在处理哪个年份的哪一页」。"""
    for p in LOGS:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 4000))
                txt = f.read().decode("utf-8", "replace")
            for ln in reversed(txt.splitlines()):
                m = re.match(r"^\s+(20\d\d|PP|SP)\s+p(\d+)\s+(\d+) blocks\s+(\d+)s", ln)
                if m:
                    return {"year": m.group(1), "page": int(m.group(2)),
                            "blocks": int(m.group(3)), "secs": int(m.group(4))}
                if ln.startswith("[done]"):
                    m2 = re.match(r"\[done\]\s+(\S+)\s+(\d+)/(\d+) 页\s+用时\s+(\d+)\s+分钟", ln)
                    if m2:
                        return {"done_year": m2.group(1), "done_pages": int(m2.group(2)),
                                "done_total": int(m2.group(3)), "done_min": int(m2.group(4))}
        except Exception:  # noqa: BLE001
            pass
    return {}


def status():
    rows = []
    total_pages = total_done = 0
    per_page = []          # 每页耗时，用于估 ETA

    now_ts = time.time()
    for y in years():
        tp = count_dir(os.path.join(PAGES, y), ".jpg")
        dn = count_dir(os.path.join(VLOUT, y), ".json")
        total_pages += tp
        total_done += min(dn, tp) if tp else dn

        # 「运行中」不能只看「目录有产物」——PP 有 1 页是早前单独跑的残留，
        # 会被误判成正在跑。改为看目录最近是否有写入（10 分钟内 = 活跃）。
        vdir = os.path.join(VLOUT, y)
        active = False
        try:
            active = (now_ts - os.path.getmtime(vdir)) < 600
        except OSError:
            pass

        if tp and dn >= tp:
            state = "done"
        elif active and dn < tp:
            state = "running"
        elif dn:
            state = "partial"
        else:
            state = "todo"

        rows.append({
            "year": y, "pages": tp, "done": dn,
            "pct": (min(dn, tp) / tp * 100) if tp else (100 if dn else 0),
            "state": state, "active": active,
        })

    # 每页耗时（从日志抓，取最近 30 条）
    for p in LOGS:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 60000))
                txt = f.read().decode("utf-8", "replace")
            per_page = [int(m) for m in re.findall(r"(\d+)s\s*$", txt, re.M)][-30:]
            if per_page:
                break
        except Exception:  # noqa: BLE001
            pass

    avg = (sum(per_page) / len(per_page)) if per_page else 0
    remain_pages = max(0, total_pages - total_done)
    eta_min = (remain_pages * avg / 60) if avg else None

    # 正在处理的年份
    cur = current_state()
    # 日志的最后一行往往是「上一份刚完成」，而实际已经在跑下一份了
    # （新一份的第一页还没写出，不会有日志行）。所以以「哪个目录最近在写」为准。
    active_row = next((r for r in rows if r["state"] == "running"), None)
    if active_row:
        cur = {
            "year": active_row["year"],
            "page": active_row["done"] + 1,
            "blocks": (cur.get("blocks") or 0),
            "secs": (cur.get("secs") or 0),
            "just_done": cur.get("done_year"),
        }

    return {
        "now": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_pages": total_pages,
        "total_done": total_done,
        "pct": (total_done / total_pages * 100) if total_pages else 0,
        "avg_secs": round(avg, 1),
        "eta_min": round(eta_min) if eta_min else None,
        "remain_pages": remain_pages,
        "current": cur,
        "years": rows,
        "tail": tail_log(),
    }


HTML = r"""<!doctype html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VLM 卷二识别 · 进度</title>
<style>
  :root{
    --bg:#15171c;--panel:#1d2028;--line:#2c3140;--ink:#e8ecf3;--dim:#8b95a8;
    --ok:#3ddc97;--run:#f0b429;--todo:#4a5163;--accent:#4ea8de;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.6 ui-sans-serif,system-ui,"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;
    padding:28px 26px 60px}
  h1{font-size:17px;font-weight:600;margin:0 0 4px;letter-spacing:.02em}
  .sub{color:var(--dim);font-size:12px;margin-bottom:22px}
  .hero{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px 22px;margin-bottom:18px}
  .hero .row{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
  .big{font-size:34px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
  .big small{font-size:15px;color:var(--dim);font-weight:400;margin-left:4px}
  .bar{height:10px;border-radius:99px;background:#252a35;overflow:hidden;margin:14px 0 10px}
  .bar i{display:block;height:100%;border-radius:99px;
    background:linear-gradient(90deg,#3ddc97,#4ea8de);transition:width .6s cubic-bezier(.3,.7,.2,1)}
  .meta{display:flex;gap:22px;flex-wrap:wrap;color:var(--dim);font-size:12.5px}
  .meta b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px;margin-bottom:18px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:13px 15px;position:relative;overflow:hidden}
  .card .y{font-size:16px;font-weight:600;font-variant-numeric:tabular-nums}
  .card .n{color:var(--dim);font-size:12px;margin-top:1px;font-variant-numeric:tabular-nums}
  .card .pb{height:4px;border-radius:99px;background:#252a35;margin-top:10px;overflow:hidden}
  .card .pb i{display:block;height:100%;border-radius:99px}
  .card.done{border-color:#274b3c}
  .card.done .pb i{background:var(--ok)}
  .card.running{border-color:#5a4a20;box-shadow:0 0 0 1px #3a3018 inset}
  .card.running .pb i{background:var(--run)}
  .card.partial .pb i{background:#7a8ba8}
  .card.todo .pb i{background:var(--todo)}
  .dot{position:absolute;right:13px;top:14px;width:7px;height:7px;border-radius:50%}
  .card.done .dot{background:var(--ok)}
  .card.running .dot{background:var(--run);animation:pulse 1.4s ease-in-out infinite}
  .card.partial .dot{background:#7a8ba8}
  .card.todo .dot{background:var(--todo)}
  @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.8)}}
  .now{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:14px 16px;margin-bottom:16px}
  .now .t{font-size:11px;letter-spacing:.18em;color:var(--dim);margin-bottom:7px}
  .now .v{font-size:14px}
  .log{background:#12141a;border:1px solid var(--line);border-radius:9px;padding:13px 15px;
    font:12px/1.85 ui-monospace,SFMono-Regular,Consolas,monospace;color:#9fb0c6;white-space:pre-wrap;overflow-x:auto}
  .log b{color:var(--ok);font-weight:500}
  .foot{color:#5c6577;font-size:11.5px;margin-top:16px}
  .err{color:#ff8a8a}
</style>
</head>
<body>
<h1>VLM 卷二识别 · 实时进度</h1>
<div class="sub">共 <span id="tp">–</span> 页 · 每 3 秒自动刷新 · 页面只读文件系统，随时开关不影响后台任务</div>

<div class="hero">
  <div class="row">
    <div class="big"><span id="done">–</span><small>/ <span id="tot">–</span> 页</small></div>
    <div class="meta" style="margin-left:auto">
      <span>完成度 <b id="pct">–</b></span>
      <span>每页均耗时 <b id="avg">–</b></span>
      <span>预计剩余 <b id="eta">–</b></span>
    </div>
  </div>
  <div class="bar"><i id="bar" style="width:0%"></i></div>
  <div class="meta"><span>更新于 <b id="now">–</b></span><span>剩余 <b id="remain">–</b> 页</span></div>
</div>

<div class="now"><div class="t">当 前 任 务</div><div class="v" id="cur">读取中…</div></div>

<div class="grid" id="grid"></div>

<div class="now" style="padding-bottom:12px"><div class="t">最 近 日 志</div>
<div class="log" id="log">–</div></div>

<div class="foot">数据源：scratch/_lq_pages（原卷页图）与 scratch/_lq_vl（识别产物）。<br>
「运行中」= 目录已建但页数未满；识别进度只在每页完成后落盘，所以单页之内不会跳动。</div>

<script>
const $ = id => document.getElementById(id);
const fmtEta = m => !m && m !== 0 ? '–' : (m < 60 ? m + ' 分钟' : (m/60).toFixed(1) + ' 小时');

async function tick(){
  try{
    const r = await fetch('/status', {cache:'no-store'});
    const d = await r.json();
    $('done').textContent = d.total_done;
    $('tot').textContent = d.total_pages;
    $('tp').textContent = d.total_pages;
    $('pct').textContent = d.pct.toFixed(1) + '%';
    $('bar').style.width = d.pct.toFixed(1) + '%';
    $('avg').textContent = d.avg_secs ? d.avg_secs + ' 秒' : '–';
    $('eta').textContent = fmtEta(d.eta_min);
    $('remain').textContent = d.remain_pages;
    $('now').textContent = d.now;

    const c = d.current || {};
    if (c.year) {
      const tail = c.secs ? '　·　上一页 ' + c.blocks + ' 个内容块、耗时 ' + c.secs + ' 秒' : '';
      const prev = c.just_done && c.just_done !== c.year ? '（' + c.just_done + ' 刚完成）' : '';
      $('cur').innerHTML = '正在识别 <b>' + c.year + '</b> 第 ' + c.page + ' 页' + tail + prev;
    } else if (c.done_year) {
      $('cur').textContent = '刚完成 ' + c.done_year + '（' + c.done_pages + '/' + c.done_total + ' 页，用时 ' + c.done_min + ' 分钟）';
    } else {
      $('cur').textContent = '未开始或已完成';
    }

    $('grid').innerHTML = d.years.map(y => {
      const cls = y.state;
      const lbl = cls==='done' ? '完成' : (cls==='running' ? '运行中' : (cls==='partial' ? '部分' : '待跑'));
      return '<div class="card ' + cls + '"><span class="dot"></span>' +
        '<div class="y">' + y.year + '</div>' +
        '<div class="n">' + y.done + ' / ' + y.pages + ' 页 · ' + lbl + '</div>' +
        '<div class="pb"><i style="width:' + y.pct.toFixed(0) + '%"></i></div></div>';
    }).join('');

    $('log').textContent = (d.tail && d.tail.length) ? d.tail.join('\n') : '（暂无）';
  }catch(e){
    $('cur').innerHTML = '<span class="err">连不上本地服务：' + e.message + '</span>';
  }
}
tick(); setInterval(tick, 3000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静默，别刷屏
        pass

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/status"):
            body = json.dumps(status(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("VLM 进度看板： http://127.0.0.1:%d/" % port)
    print("（Ctrl+C 停止；停止不影响后台识别）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
