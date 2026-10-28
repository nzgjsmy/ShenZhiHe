# -*- coding: utf-8 -*-
"""從 _pastpaper.json 重新生成「DSE 生物 卷一 MC 答案與得分率」的網頁版與 Excel 版

背景：這兩份檔案原本是 2025-10 手工做的產物，倉庫裡沒有生成腳本。
2026-10-29 加入 PP/SP 時只能直接改產物，屬於技術債。本腳本把它補上。

用法：
    python scripts/gen_mc_answers.py            # 重新生成 HTML + XLSX
    python scripts/gen_mc_answers.py --html     # 只出 HTML
    python scripts/gen_mc_answers.py --xlsx     # 只出 XLSX

資料來源：data/bio/_mc_answers.json（每題的 answer 與 pct；由手工版表格一次性抽出，
          含題庫缺少的 21 道題，所以不要改讀 _pastpaper.json）
模板：data/bio/_mc_answers_template.html（骨架 + CSS，含 {{SUB}} {{KPI}} <!--T1..T4--> 佔位）

樣本卷（PP/SP）官方沒有公布每題答對率，pct 記為 0：
  - 矩陣裡照樣顯示答案，得分率以「—」表示
  - 匯總表、最難／最易兩表不納入統計
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "bio", "_mc_answers.json")
TPL = os.path.join(ROOT, "data", "bio", "_mc_answers_template.html")
OUT_HTML = os.path.join(ROOT, "extras", "bio", "生物DSE_卷一MC_答案與得分率.html")
OUT_XLSX = os.path.join(ROOT, "extras", "bio", "生物DSE_卷一MC_答案與得分率_2012-2022.xlsx")

SAMPLE = ("PP", "SP")          # 無官方得分率的年份

BANDS = [                       # (上限, 底色, 字色)
    (30, "#efa896", "#7d1f14"),
    (45, "#f6c8b4", "#8f3a1c"),
    (55, "#fbdfc6", "#8a4a15"),
    (65, "#fdf1d3", "#7a5a12"),
    (75, "#f4f7dc", "#5a6320"),
    (85, "#e3f3dd", "#2b6b34"),
    (101, "#cdeccf", "#1f5c2e"),
]


def band(p):
    for hi, bg, fg in BANDS:
        if p < hi:
            return bg, fg
    return BANDS[-1][1], BANDS[-1][2]


def load():
    d = json.load(open(DATA, encoding="utf-8"))
    years = {y: sorted(qs, key=lambda q: q["qnum"]) for y, qs in d["years"].items()}
    keys = sorted([k for k in years if k not in SAMPLE], key=lambda k: int(k))
    keys += [k for k in SAMPLE if k in years]
    return [(k, years[k]) for k in keys]


def stats(qs):
    ps = [q["pct"] for q in qs if (q.get("pct") or 0) > 0]
    if not ps:
        return None
    ps.sort()
    n = len(ps)
    med = ps[n // 2] if n % 2 else (ps[n // 2 - 1] + ps[n // 2]) / 2
    return {"n": len(qs), "avg": sum(ps) / n, "med": med, "max": max(ps), "min": min(ps), "npct": n}


def table_summary(data):
    rows = ['      <tr><th>年份</th><th>題數</th><th>平均答對率</th><th>平均</th>'
            '<th>中位數</th><th>最高</th><th>最低</th></tr>']
    for y, qs in data:
        st = stats(qs)
        if st:
            w = int(round(st["avg"] * 2.6))
            rows.append(
                '      <tr>\n        <td class="yr">%s</td>\n        <td class="num">%d</td>\n'
                '        <td class="barCell"><div class="barWrap"><div class="bar" style="width:%dpx"></div></div></td>\n'
                '        <td class="num strong">%.1f%%</td>\n        <td class="num">%.1f%%</td>\n'
                '        <td class="num">%d%%</td>\n        <td class="num">%d%%</td>\n      </tr>'
                % (y, st["n"], w, st["avg"], st["med"], st["max"], st["min"]))
        else:
            rows.append(
                '      <tr>\n        <td class="yr">%s</td>\n        <td class="num">%d</td>\n'
                '        <td class="barCell"><span style="color:#999999;font-size:12px">無官方得分率</span></td>\n'
                '        <td class="num strong">—</td>\n        <td class="num">—</td>\n'
                '        <td class="num">—</td>\n        <td class="num">—</td>\n      </tr>' % (y, len(qs)))
    return '    <table>\n' + "\n".join(rows) + '\n    </table>'


def table_matrix(data):
    keys = [y for y, _ in data]
    head = '<th>題號</th>' + "".join('<th class="yrHead">%s</th>' % y for y in keys) + '<th>多年平均</th>'
    maxq = max(max(q["qnum"] for q in qs) for _, qs in data)
    idx = {y: {q["qnum"]: q for q in qs} for y, qs in data}
    rows = ['      <tr>%s</tr>' % head]
    for n in range(1, maxq + 1):
        cells = ['<td class="qno">%d</td>' % n]
        ps = []
        for y in keys:
            q = idx[y].get(n)
            if not q:
                cells.append('<td class="cell" style="background:#f7f7f7;color:#bbbbbb">—</td>')
                continue
            p = q.get("pct") or 0
            if p > 0:
                bg, fg = band(p)
                cells.append('<td class="cell" style="background:%s;color:%s"><b>%s</b><span>%d</span></td>'
                             % (bg, fg, q["answer"], p))
                ps.append(p)
            else:
                cells.append('<td class="cell" style="background:#eeeeee;color:#777777"><b>%s</b><span>—</span></td>'
                             % q["answer"])
        cells.append('<td class="cell qavg">%s</td>' % ('%d%%' % round(sum(ps) / len(ps)) if ps else '—'))
        rows.append('      <tr>%s</tr>' % "".join(cells))
    return '    <table class="matrix">\n' + "\n".join(rows) + '\n    </table>'


def table_rank(data, n, hardest=True):
    flat = []
    for y, qs in data:
        if y in SAMPLE:
            continue
        for q in qs:
            p = q.get("pct") or 0
            if p > 0:
                flat.append((p, y, q["qnum"], q["answer"]))
    flat.sort(key=lambda t: (t[0] if hardest else -t[0], t[1], t[2]))
    rows = ['          <tr><th>#</th><th>年份</th><th>題號</th><th>答案</th><th>答對率</th></tr>']
    for i, (p, y, qn, a) in enumerate(flat[:n], 1):
        bg, fg = band(p)
        rows.append('          <tr><td class="qno">%d</td><td class="yr">%s</td><td class="num">Q%d</td>'
                    '<td class="num"><b>%s</b></td><td class="cell" style="background:%s;color:%s">%d%%</td></tr>'
                    % (i, y, qn, a, bg, fg, p))
    return '        <table>\n' + "\n".join(rows) + '\n        </table>'


def build_html(data):
    tpl = open(TPL, encoding="utf-8").read()
    allp = [q["pct"] for _, qs in data for q in qs if (q.get("pct") or 0) > 0]
    nq = sum(len(qs) for _, qs in data)
    st = stats([q for _, qs in data if _ not in SAMPLE for q in qs])
    sub = ("資料來源：2012–2022 各年《評卷參考》卷一甲部答案表（括號內為答對百分率）；"
           "PP（樣本試卷）、SP（練習卷）另據其建議答案補入，<b>這兩份卷官方沒有公布答對率</b>。<br>\n"
           "    共 <b>%d</b> 個年份、<b>%d</b> 條題目（2013 年第 9 題被刪除，不計入統計）。" % (len(data), nq))
    kpi = ('\n    <div class="kpi"><div class="lab">全期平均答對率</div><div class="val">%.1f<small>%%</small></div></div>\n'
           '    <div class="kpi"><div class="lab">最易一題</div><div class="val">%d<small>%%</small></div></div>\n'
           '    <div class="kpi"><div class="lab">最難一題</div><div class="val">%d<small>%%</small></div></div>\n'
           '    <div class="kpi"><div class="lab">統計題目數</div><div class="val">%d<small>題</small></div></div>'
           % (st["avg"], max(allp), min(allp), len(allp)))
    html = (tpl.replace("{{SUB}}", sub).replace("{{KPI}}", kpi)
            .replace("<!--T1-->", table_summary(data))
            .replace("<!--T2-->", table_matrix(data))
            .replace("<!--T3-->", table_rank(data, 15, True))
            .replace("<!--T4-->", table_rank(data, 8, False)))
    open(OUT_HTML, "w", encoding="utf-8").write(html)
    return len(html)


def build_xlsx(data):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Side, PatternFill, Font

    thin = Side(style="thin", color="D9D9D9")
    BORD = Border(left=thin, right=thin, top=thin, bottom=thin)
    HEAD = PatternFill("solid", fgColor="F2F5F8")
    GRAY = PatternFill("solid", fgColor="F2F2F2")
    CEN = Alignment(horizontal="center", vertical="center")

    wb = Workbook()

    def head(ws, cols):
        for i, c in enumerate(cols, 1):
            cell = ws.cell(row=1, column=i, value=c)
            cell.fill = HEAD
            cell.font = Font(bold=True)
            cell.alignment = CEN
            cell.border = BORD

    # 概览
    ws = wb.active
    ws.title = "概览"
    head(ws, ["年份", "题数", "平均答對率", "最高", "最低", "中位数"])
    r = 2
    for y, qs in data:
        st = stats(qs)
        ws.cell(row=r, column=1, value=y)
        ws.cell(row=r, column=2, value=len(qs))
        if st:
            for i, v in enumerate((round(st["avg"], 1), st["max"], st["min"], round(st["med"], 1)), 3):
                ws.cell(row=r, column=i, value=v)
        else:
            for i in range(3, 7):
                ws.cell(row=r, column=i, value="—")
                ws.cell(row=r, column=i).fill = GRAY
        for c in range(1, 7):
            ws.cell(row=r, column=c).alignment = CEN
            ws.cell(row=r, column=c).border = BORD
        r += 1

    # 逐年明细
    ws = wb.create_sheet("逐年明细")
    head(ws, ["年份", "题号", "答案", "答對率(%)"])
    r = 2
    for y, qs in data:
        for q in qs:
            p = q.get("pct") or 0
            ws.cell(row=r, column=1, value=y)
            ws.cell(row=r, column=2, value=q["qnum"])
            ws.cell(row=r, column=3, value=q["answer"])
            ws.cell(row=r, column=4, value=p if p > 0 else "—")
            for c in range(1, 5):
                ws.cell(row=r, column=c).alignment = CEN
                ws.cell(row=r, column=c).border = BORD
                if p == 0:
                    ws.cell(row=r, column=c).fill = GRAY
            r += 1

    # 答案矩阵
    ws = wb.create_sheet("答案矩阵")
    keys = [y for y, _ in data]
    head(ws, ["题号"] + keys)
    idx = {y: {q["qnum"]: q for q in qs} for y, qs in data}
    maxq = max(max(q["qnum"] for q in qs) for _, qs in data)
    for n in range(1, maxq + 1):
        ws.cell(row=n + 1, column=1, value=n)
        for j, y in enumerate(keys, 2):
            q = idx[y].get(n)
            if not q:
                ws.cell(row=n + 1, column=j, value="—")
                continue
            p = q.get("pct") or 0
            ws.cell(row=n + 1, column=j, value="%s %s" % (q["answer"], "%d%%" % p if p else "—"))
        for c in range(1, len(keys) + 2):
            ws.cell(row=n + 1, column=c).alignment = CEN
            ws.cell(row=n + 1, column=c).border = BORD

    # 最难题目
    flat = []
    for y, qs in data:
        if y in SAMPLE:
            continue
        for q in qs:
            p = q.get("pct") or 0
            if p > 0:
                flat.append((p, y, q["qnum"], q["answer"]))
    hardest = sorted(flat, key=lambda t: (t[0], t[1], t[2]))
    ws = wb.create_sheet("最难题目")
    head(ws, ["排名", "年份", "题号", "答案", "答對率(%)"])
    for i, (p, y, qn, a) in enumerate(hardest[:30], 1):
        for c, v in enumerate((i, y, qn, a, p), 1):
            ws.cell(row=i + 1, column=c, value=v).alignment = CEN
            ws.cell(row=i + 1, column=c).border = BORD

    # 答案分布
    ws = wb.create_sheet("答案分布")
    head(ws, ["年份", "A", "B", "C", "D"])
    for i, (y, qs) in enumerate(data, 2):
        ws.cell(row=i, column=1, value=y)
        for j, k in enumerate("ABCD", 2):
            ws.cell(row=i, column=j, value=sum(1 for q in qs if q["answer"] == k))
        for c in range(1, 6):
            ws.cell(row=i, column=c).alignment = CEN
            ws.cell(row=i, column=c).border = BORD

    wb.save(OUT_XLSX)


if __name__ == "__main__":
    data = load()
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    if only != "--xlsx":
        n = build_html(data)
        print("HTML  ->", OUT_HTML, "(%d 字符)" % n)
    if only != "--html":
        build_xlsx(data)
        print("XLSX  ->", OUT_XLSX)
    print("年份:", [y for y, _ in data], " 题数:", sum(len(q) for _, q in data))
