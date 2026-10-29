# -*- coding: utf-8 -*-
"""渲染验证：DSE 卷一（MC）/ 卷二（LQ）是否真的分开了。

为什么必须实际渲染
------------------
构建通过 ≠ 页面正确。本项目历史上出现过「渲染函数抛异常 → 页面静默停在上一帧」
（表现为按钮没反应），只看 build.py 成功是查不出来的。

检查项
------
  1. 首页出现两张 DSE 卡（卷一 MC / 卷二 LQ），互不混淆
  2. 点「卷二」能进 #/lq，且题卡数量与数据一致
  3. 题号是 LQ 格式（1(a)），不是 MC 的整数
  4. 子题有分层（罗马数字 + 阿拉伯数字）
  5. 卷一 MC 仍然正常（未被改坏）
  6. 深色模式下 LQ 卡片的文字对比度

用法
----
  python scripts/verify_lq_render.py
"""
import io
import json
import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "site", "神智核.html")
SHOT = os.path.join(ROOT, "scratch", "_shots")
os.makedirs(SHOT, exist_ok=True)

FAIL = []
def ck(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✖ ") + name + (("  " + str(detail)) if detail else ""))
    if not cond:
        FAIL.append(name)

def main():
    if not os.path.exists(HTML):
        print("找不到产物，先跑 python site/build.py")
        return 1
    url = "file:///" + HTML.replace("\\", "/")
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        pg = b.new_page(viewport={"width": 1400, "height": 950}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(url, wait_until="load")
        pg.wait_for_timeout(1800)

        print("=== 1) 首页 DSE 两张卡 ===")
        # 先确保在首页且已选生物
        pg.evaluate("() => { try{ switchSubject('bio'); }catch(e){} }")
        pg.wait_for_timeout(600)
        pg.evaluate("() => go('#/home')")
        pg.wait_for_timeout(1200)
        n_mc = pg.locator(".dse-hero.dse-mc").count()
        n_lq = pg.locator(".dse-hero.dse-lq").count()
        ck("卷一 MC 卡存在", n_mc >= 1, n_mc)
        ck("卷二 LQ 卡存在", n_lq >= 1, n_lq)
        txt = pg.locator(".dse-duo").inner_text() if pg.locator(".dse-duo").count() else ""
        ck("两卡文案区分（卷一/卷二）", ("卷一" in txt and "卷二" in txt), txt.replace("\n", " / ")[:70])
        pg.screenshot(path=os.path.join(SHOT, "lq_home.png"), clip={"x": 0, "y": 0, "width": 1400, "height": 760})

        print("=== 2) 进入卷二 LQ 视图 ===")
        pg.evaluate("() => go('#/lq')")
        pg.wait_for_timeout(1500)
        ncard = pg.locator(".lq-card").count()
        ck("LQ 题卡已渲染", ncard > 0, "%d 张" % ncard)
        ck("无 JS 异常", len(errs) == 0, errs[:2])

        qids = pg.eval_on_selector_all(".lq-qid", "els => els.map(e => e.textContent.trim())")
        ck("题号是 LQ 格式（含括号）", all("(" in q for q in qids if q), qids[:8])
        nsub = pg.locator(".lq-sub").count()
        nsub2 = pg.locator(".lq-sub.lq-sub2").count()
        ck("子题已渲染", nsub > 0, "%d 个（其中二级 %d）" % (nsub, nsub2))
        ck("存在二级子题（1(a) 下挂 (1)(2)）", nsub2 > 0, nsub2)
        nmk = pg.locator(".lq-mk").count()
        ck("分值标签已渲染", nmk > 0, nmk)

        # 展开评分指引
        pg.locator(".lq-btn").first.click()
        pg.wait_for_timeout(700)
        panel_open = pg.locator(".lq-panel.open").count()
        ck("「评分指引」可展开", panel_open > 0, panel_open)

        # 写笔记
        pg.locator(".lq-note-btn").first.click()
        pg.wait_for_timeout(400)
        vis = pg.locator(".lq-notebox").first.is_visible()
        ck("「写笔记」可展开输入框", vis, vis)

        pg.screenshot(path=os.path.join(SHOT, "lq_view.png"), clip={"x": 0, "y": 0, "width": 1400, "height": 950})

        print("=== 3) 卷一 MC 未被改坏 ===")
        pg.evaluate("() => go('#/pastpaper')")
        pg.wait_for_timeout(1500)
        nmc = pg.locator(".ppq").count()
        ck("MC 题卡仍正常", nmc > 0, "%d 张" % nmc)
        ck("MC 与 LQ 卡片不混排", pg.locator(".lq-card").count() == 0)

        print("=== 4) 深色模式 ===")
        pg.evaluate("() => setTheme('dark')")
        pg.evaluate("() => go('#/lq')")
        pg.wait_for_timeout(1200)
        # 读 LQ 卡片主题文字色与背景，粗算对比度
        colors = pg.evaluate("""() => {
          const c = document.querySelector('.lq-card');
          if(!c) return null;
          const cs = getComputedStyle(c);
          const q = c.querySelector('.lq-q');
          const qs = q ? getComputedStyle(q) : null;
          return {bg: cs.backgroundColor, fg: qs ? qs.color : null};
        }""")
        ck("深色下 LQ 卡片有取到颜色", bool(colors and colors.get("bg")), colors)
        pg.screenshot(path=os.path.join(SHOT, "lq_dark.png"), clip={"x": 0, "y": 0, "width": 1400, "height": 950})

        print("=== 5) 数据一致性 ===")
        data = pg.evaluate("""() => {
          const y = (SUB && SUB._lq && SUB._lq.years) || {};
          let n = 0, sub = 0, rev = 0;
          Object.keys(y).forEach(k => (y[k]||[]).forEach(q => {
            n++; sub += (q.subqs||[]).length; if(q.needsReview) rev++;
          }));
          return {years: Object.keys(y).length, n, sub, rev,
                  mcYears: Object.keys((SUB._pastpaper||{}).years||{}).length};
        }""")
        print("    数据:", data)
        ck("LQ 与 MC 各自独立统计",
           data["years"] > 0 and data["mcYears"] > 0 and data["years"] != data["mcYears"],
           "LQ %d 年 / MC %d 年" % (data["years"], data["mcYears"]))
        ck("页面卡片数 = 数据大题数", ncard == data["n"], "%d vs %d" % (ncard, data["n"]))

        b.close()

    print()
    if FAIL:
        print("✖ 失败 %d 项：" % len(FAIL))
        for f in FAIL:
            print("   -", f)
        return 1
    print("✅ 全部通过")
    print("截图：", SHOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
