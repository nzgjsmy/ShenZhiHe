"""扫描深色主题下仍未转深的浅色背景元素。

思路：在真实浏览器里切到深色主题，遍历所有可见元素，
计算「实际绘制出的背景色」的亮度。亮度高于阈值 = 浅底漏转。

⚠️ 关键细节：background-color 为 transparent 的元素不算问题
（它透出父级，父级深就是深）。所以要沿父链找到第一个不透明的背景，
再判断那个颜色。但那样会重复报「同一个浅色祖先下的所有子元素」，
所以只报「自己有不透明浅色背景」的元素。

两类检查：
  A. 浅底漏转 —— 深色主题下背景亮度仍 > 0.42 的元素
  B. 文字糊掉 —— 文字与其真实背景的对比度 < 3.0（WCAG AA 大字线）

用法：
  python scripts/audit_dark_theme.py            # 人读
  python scripts/audit_dark_theme.py --json     # 机器可读

⚠️ 依赖 Playwright + 本机 Chrome，约 1 分钟。
   因此**不接入** verify_build.py（CI 的 ubuntu runner 没有浏览器，
   接上去会让每次提交都挂）。改动配色/主题后手动跑一次即可。

⚠️ 排除逻辑：主色系（--accent 亮青、--amber 强调、--hn-accent）本身
   就是«有意为之»的亮色，必须排除，否则报告会被几百个按钮刷屏。
   排除时要注意变量表存的是 #2dd4bf 这种 hex，parse() 必须同时认 hex 和 rgb()。
"""
# 本脚本是为了回答「深色主题有些区域还是浅色」而写。
# 根因是第一轮手账化时把 .pcard / .expl / .qtype / .opt 等容器的背景
# 硬编码成 #fffdf4，没走 --paper 变量 —— 深色主题自然转不到。

import json
import os
import sys

HTML = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "site", "神智核.html")).replace("\\", "/")

# 每条路由 = (名称, hash, 前置动作)
ROUTES = [
    ("科目首页", "#/home", "switchSubject"),
    ("全部科目", "#/subjects", None),
    ("DSE真題(按話題)", "#/pastpaper", "pp"),
    ("卷二LQ", "#/lq", None),
    ("測驗", "#/quiz", None),
    ("複習", "#/review", None),
    ("錯題本", "#/wrong", None),
    ("關聯地圖", "#/graph", None),
    ("設定", "#/settings", None),
]

JS_SCAN = r"""
() => {
  const out = [];
  // 必须同时支持 rgb() 和 #hex —— 变量表里存的是 #2dd4bf 这种十六进制，
  // 只认 rgb() 会导致「排除主色」永远拿不到值（实测踩过）。
  const parse = (s) => {
    if (!s) return null;
    s = s.trim();
    let m = s.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    if (m) return {r:+m[1], g:+m[2], b:+m[3], a: m[4] === undefined ? 1 : +m[4]};
    m = s.match(/^#([0-9a-f]{6})$/i);
    if (m) { const h = m[1]; return {r:parseInt(h.slice(0,2),16), g:parseInt(h.slice(2,4),16), b:parseInt(h.slice(4,6),16), a:1}; }
    m = s.match(/^#([0-9a-f]{3})$/i);
    if (m) { const h = m[1]; return {r:parseInt(h[0]+h[0],16), g:parseInt(h[1]+h[1],16), b:parseInt(h[2]+h[2],16), a:1}; }
    return null;
  };
  const lum = (c) => (0.2126*c.r + 0.7152*c.g + 0.0722*c.b) / 255;

  const all = document.querySelectorAll('body *');
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 20) continue;      // 太小的不算（图标、圆点）
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (cs.opacity === '0') continue;

    const bg = parse(cs.backgroundColor);
    if (!bg || bg.a < 0.5) continue;                  // 透明/半透明：透出父级，不算自己漏转

    // 排除主色系元素：深色主题的 --accent 是亮青 #2dd4bf，本身就是强调色，
    // 不算「漏转」。不排除的话每次扫描都会被几百个按钮刷屏。
    const accent = parse(getComputedStyle(document.documentElement).getPropertyValue('--accent').trim());
    if (accent && Math.abs(bg.r-accent.r)<26 && Math.abs(bg.g-accent.g)<26 && Math.abs(bg.b-accent.b)<26) continue;
    // 排除标签色系（amber 强调底同样是有意为之）
    const amber = parse(getComputedStyle(document.documentElement).getPropertyValue('--amber').trim());
    if (amber && Math.abs(bg.r-amber.r)<30 && Math.abs(bg.g-amber.g)<30 && Math.abs(bg.b-amber.b)<30) continue;
    // 排除手账主色（页头实心按钮 --hn-accent，深色下是 #4d8a7f，亮度 0.49 属正常）
    const hn = parse(getComputedStyle(document.documentElement).getPropertyValue('--hn-accent').trim());
    if (hn && Math.abs(bg.r-hn.r)<26 && Math.abs(bg.g-hn.g)<26 && Math.abs(bg.b-hn.b)<26) continue;

    const L = lum(bg);
    if (L < 0.42) continue;                           // 够暗，正常

    // 排除：图片、渐变本身
    const cls = (typeof el.className === 'string' ? el.className : '').trim();
    out.push({
      tag: el.tagName.toLowerCase(),
      cls: cls.slice(0, 70),
      id: el.id || '',
      bg: cs.backgroundColor,
      L: +L.toFixed(3),
      w: Math.round(r.width),
      h: Math.round(r.height),
      txt: (el.textContent || '').trim().slice(0, 26),
    });
  }
  // 按面积降序，大的先修
  out.sort((a, b) => (b.w*b.h) - (a.w*a.h));
  return out.slice(0, 40);
}
"""




JS_CONTRAST = r"""
() => {
  const parse = (s) => {
    if (!s) return null; s = s.trim();
    let m = s.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    if (m) return {r:+m[1], g:+m[2], b:+m[3], a: m[4] === undefined ? 1 : +m[4]};
    m = s.match(/^#([0-9a-f]{6})$/i);
    if (m) { const h=m[1]; return {r:parseInt(h.slice(0,2),16),g:parseInt(h.slice(2,4),16),b:parseInt(h.slice(4,6),16),a:1}; }
    m = s.match(/^#([0-9a-f]{3})$/i);
    if (m) { const h=m[1]; return {r:parseInt(h[0]+h[0],16),g:parseInt(h[1]+h[1],16),b:parseInt(h[2]+h[2],16),a:1}; }
    return null;
  };
  const rel = (c) => { const f=(v)=>{v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4);};
    return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b); };

  // 沿父链找第一个不透明背景
  const realBg = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a >= 0.9) return c;
      n = n.parentElement;
    }
    return parse(getComputedStyle(document.body).backgroundColor) || {r:28,g:26,b:23,a:1};
  };

  const bad = [];
  const walker = document.querySelectorAll('body *');
  for (const el of walker) {
    // 只看直接含文字的元素（不含子元素文字重复计算）
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!own) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;

    const fg = parse(cs.color);
    if (!fg || fg.a < 0.5) continue;
    const bg = realBg(el);
    const L1 = rel(fg), L2 = rel(bg);
    const ratio = (Math.max(L1,L2)+0.05) / (Math.min(L1,L2)+0.05);
    if (ratio < 3.0) {   // WCAG AA 大字 3.0；正文 4.5，但 3.0 以下一定是肉眼可见的糊
      const cls = (typeof el.className === 'string' ? el.className : '').trim();
      bad.push({
        tag: el.tagName.toLowerCase(), cls: cls.slice(0,60),
        fg: cs.color, bg: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
        ratio: +ratio.toFixed(2),
        txt: (el.textContent||'').trim().slice(0,24),
      });
    }
  }
  bad.sort((a,b)=>a.ratio-b.ratio);
  return bad.slice(0, 30);
}
"""

def main():
    as_json = "--json" in sys.argv
    from playwright.sync_api import sync_playwright

    report = {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        pg = b.new_page(viewport={"width": 1440, "height": 1000})

        for name, h, pre in ROUTES:
            try:
                pg.goto("file:///" + HTML, wait_until="load")
                pg.wait_for_timeout(1400)
                if pre == "switchSubject":
                    pg.evaluate("() => { try{ switchSubject('bio'); }catch(e){} }")
                elif pre == "pp":
                    pg.evaluate("() => { try{ switchSubject('bio'); }catch(e){} }")
                    pg.wait_for_timeout(400)
                pg.evaluate(f"() => go('{h}')")
                pg.wait_for_timeout(1100)
                pg.evaluate("() => setTheme('dark')")
                pg.wait_for_timeout(900)
                report[name] = pg.evaluate(JS_SCAN)
                report[name + " · 文字对比度"] = pg.evaluate(JS_CONTRAST)
            except Exception as e:
                report[name] = [{"error": str(e)}]

        b.close()

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return

    total = 0
    for name, items in report.items():
        real = [x for x in items if "error" not in x]
        if not real:
            continue
        total += len(real)
        print("\n=== %s：%d 处 ===" % (name, len(real)))
        for it in real[:10]:
            sel = it["tag"] + ("." + it["cls"].split()[0] if it["cls"] else "") + ("#" + it["id"] if it["id"] else "")
            print("  L=%.2f %-28s %dx%d  bg=%s  「%s」" % (
                it["L"], sel[:28], it["w"], it["h"], it["bg"], it["txt"]))
    print("\n合计 %d 处浅底元素需要转深。" % total)


if __name__ == "__main__":
    main()
