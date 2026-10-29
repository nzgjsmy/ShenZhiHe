# -*- coding: utf-8 -*-
"""构建产物自检：一条命令确认这次构建没把东西弄坏。

用法：python scripts/verify_build.py
退出码 0 = 全部通过；1 = 有失败项（CI 里可直接当门禁）。

检查项：
  1. site/神智核.html 存在，体积合理（< 6 MB，防内嵌图片）
  2. payload 含 bio._pastpaper，题数 > 300
  3. site.copyright 存在、disclaimer 非空（防页脚黄条无字）
  4. 搜索 worker 已注入（__SEARCH_WORKER_URL__ 已替换）
  5. 每个 <script> 块语法可解析（需 node；无 node 则跳过）
  6. 图片引用全部存在（抽样 60 个，全量太慢）
  7. service-worker.js 的 SW_VERSION 与 version.json 一致
  8. build.mjs 仍是「转发桩」（防有人恢复旧实现）
"""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # f6chem/
SITE = os.path.join(BASE, "site")
HTML = os.path.join(SITE, "神智核.html")
VER = os.path.join(SITE, "version.json")
SW = os.path.join(SITE, "service-worker.js")

ok = []
bad = []


def check(name, cond, detail=""):
    (ok if cond else bad).append((name, detail))


def main():
    # 1) 产物存在 + 体积
    if not os.path.exists(HTML):
        print("✖ 找不到 site/神智核.html，请先跑 python site/build.py")
        return 1
    size = os.path.getsize(HTML)
    check("产物体积 < 6 MB", size < 6 * 1024 * 1024,
          "%.2f MB%s" % (size / 1048576.0, "（疑似内嵌了图片？EMBED_IMG=1）" if size > 6 * 1024 * 1024 else ""))

    html = io.open(HTML, encoding="utf-8").read()

    # 2) 真题数据
    m = re.search(r'<script[^>]*id="payload"[^>]*>([\s\S]*?)</script>', html)
    if not m:
        check("payload 存在", False, "找不到 <script id=\"payload\">")
        payload = None
    else:
        try:
            payload = json.loads(m.group(1))
            check("payload 可解析", True)
        except Exception as e:
            check("payload 可解析", False, str(e)[:80])
            payload = None

    if payload:
        bio = None
        for s in payload.get("subjects", []):
            if s.get("id") == "bio":
                bio = s
                break
        pp = (bio or {}).get("_pastpaper") or {}
        years = pp.get("years") or {}
        n_q = sum(len(v) for v in years.values())
        check("bio._pastpaper 存在且题数 > 300", n_q > 300,
              "%d 题（%d 个年份）%s" % (n_q, len(years),
                                      "  ← 是否用了 build.mjs？" if n_q == 0 else ""))

        site = payload.get("site") or {}
        check("site.copyright 存在", bool(site.get("copyright")),
              "" if site.get("copyright") else "页脚「版權與免責聲明」会空")
        check("site.disclaimer 非空", bool(site.get("disclaimer")),
              "%d 条" % len(site.get("disclaimer") or []))

        ver = site.get("version", "?")
        check("版本号非空", ver not in ("", "?"), ver)

    # 4) 搜索 worker（注意：这个字符串作为「变量名」出现是正常的，
    #    真正要检查的是有没有被赋值成 Blob URL）
    injected = re.search(r"var\s+__SEARCH_WORKER_URL__\s*=\s*URL\.createObjectURL", html) is not None
    check("搜索 worker 已注入", injected,
          "" if injected else "未找到 `var __SEARCH_WORKER_URL__ = URL.createObjectURL(...)`（搜索会失效）")

    # 5) 脚本语法（需要 node）
    node = None
    for cand in ("node", "node.exe"):
        try:
            subprocess.run([cand, "--version"], capture_output=True, timeout=5)
            node = cand
            break
        except Exception:
            continue
    blocks = re.findall(r"<script(?![^>]*application/json)[^>]*>([\s\S]*?)</script>", html)
    if node and blocks:
        js_bad = 0
        for i, b in enumerate(blocks):
            p = os.path.join(SITE, "_verify_block_%d.js" % i)
            io.open(p, "w", encoding="utf-8").write(b)
            r = subprocess.run([node, "--check", p], capture_output=True)
            if r.returncode != 0:
                js_bad += 1
            os.remove(p)
        check("所有 <script> 块语法正确", js_bad == 0,
              "%d/%d 块通过%s" % (len(blocks) - js_bad, len(blocks), "" if js_bad == 0 else " ← 整站会白屏"))
    else:
        print("  （跳过 JS 语法检查：找不到 node）")

    # 6) 图片引用抽样
    refs = sorted(set(re.findall(r"img/([A-Za-z0-9_./-]+\.(?:webp|png|svg|jpg))", html)))
    missing = []
    step = max(1, len(refs) // 60)
    for r in refs[::step][:60]:
        if not os.path.exists(os.path.join(SITE, "img", r.replace("/", os.sep))):
            missing.append(r)
    check("图片引用存在（抽样 %d/%d）" % (len(refs[::step][:60]), len(refs)), not missing,
          "" if not missing else "缺 %d 个，如 %s" % (len(missing), missing[:3]))

    # 7) SW 版本一致（检查部署目录里的那份；源文件本来就是占位符）
    SW_DEPLOY = os.path.join(BASE, "gh-pages", "service-worker.js")
    if os.path.exists(SW_DEPLOY) and os.path.exists(VER):
        sw = io.open(SW_DEPLOY, encoding="utf-8").read()
        m2 = re.search(r"var SW_VERSION = '([^']*)'", sw)
        want = json.load(io.open(VER, encoding="utf-8")).get("version", "")
        got = m2.group(1) if m2 else "?"
        check("SW_VERSION 与 version.json 一致（gh-pages）", got == want,
              "SW=%s / version.json=%s%s" % (got, want, "" if got == want else " ← 客户端会吃旧缓存"))

    # 8) build.mjs 仍是转发桩
    bm = os.path.join(SITE, "build.mjs")
    if os.path.exists(bm):
        s = io.open(bm, encoding="utf-8").read()
        check("build.mjs 仍是转发桩（已废弃）", "已废弃" in s and "build.py" in s,
              "" if "已废弃" in s else "有人恢复了旧实现 → 会丢真题与搜索 worker")

    # 9) 题库体检：字面 \n、答案越界、空选项、指引串题、配图缺失……
    #    这些问题不会让构建失败，但会让线上「题目看起来是坏的」，所以当门禁。
    try:
        import subprocess
        r = subprocess.run([sys.executable,
                            os.path.join(BASE, "scripts", "audit_questions.py"), "--quiet"],
                           capture_output=True, text=True, cwd=BASE)
        out = (r.stdout or "") + (r.stderr or "")
        bad_lines = [l.strip() for l in out.splitlines()
                     if l.strip().startswith(("A1-", "A2-", "B1-", "B2-", "B3-",
                                              "B6-", "B7-", "B9-", "B10-",
                                              "B12-", "C1-"))]
        n_bad = len(bad_lines)
        check("题库体检（字面\\n / 答案越界 / 空选项 / 串题 / 缺图）", n_bad == 0,
              "" if n_bad == 0 else ("%d 项：%s" % (n_bad, " ｜ ".join(bad_lines[:3]))))
    except Exception as e:
        check("题库体检（audit_questions.py 可运行）", False, str(e)[:80])

    # 输出
    print()
    for name, detail in ok:
        print("  ✓ %s%s" % (name, ("  " + detail) if detail else ""))
    for name, detail in bad:
        print("  ✖ %s%s" % (name, ("  " + detail) if detail else ""))
    print()
    if bad:
        print("✖ %d 项失败 / %d 项通过 —— 不要部署，先修。" % (len(bad), len(ok)))
        return 1
    print("✅ 全部 %d 项通过，可以部署。" % len(ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
