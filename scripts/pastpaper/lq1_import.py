# -*- coding: utf-8 -*-
"""卷一乙部：把「已识别完的年份」一键导入正式资料档。

为什么要有它
------------
卷一乙部的识别是逐份卷跑（3 workers，每份 15–30 分钟），跑完一份就想导入一份，
但手动要三步（parse → build → figures）且 figures 还要带三个环境变量，容易漏。

用法
----
    python scripts/pastpaper/lq1_import.py              # 导入所有已完成的年份
    python scripts/pastpaper/lq1_import.py 2013 2014    # 只导入指定的
    python scripts/pastpaper/lq1_import.py --min 8      # 至少识别到 8 页才算完成（默认 10）

判定「已完成」：`scratch/_p1_vl/<year>/pNNN.json` 的页数 >= --min。
之所以不要求「等于总页数」：最后几页常是答题格/水印，识别完也几乎没内容，
卡在最后两页会白白拖住导入。
"""
import os
import subprocess
import sys
import glob

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VL = os.path.join(_ROOT, "scratch", "_p1_vl")
PP = os.path.join(_ROOT, "scratch", "_pp_pages")
PY = sys.executable

# 各年乙部起始页（跳过甲部 MC）：2020 是 p12，其余 p11；2019 是 p14
FIRST = {"2019": 14, "2020": 12}
DEFAULT_FIRST = 11


def run(cmd, env=None):
    e = os.environ.copy()
    if env:
        e.update(env)
    r = subprocess.run(cmd, cwd=_ROOT, env=e, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mn = 10
    if "--min" in sys.argv:
        mn = int(sys.argv[sys.argv.index("--min") + 1])
        args = [a for a in args if a != str(mn)]

    years = args or sorted(d for d in os.listdir(VL)
                           if os.path.isdir(os.path.join(VL, d)))
    done_any = False
    for y in years:
        n = len(glob.glob(os.path.join(VL, y, "p*.json")))
        tot = len(glob.glob(os.path.join(PP, y, "p*.jpg")))
        if n == 0:
            continue
        if n < mn:
            print("  跳过 %-5s 只识别了 %d/%d 页（< %d）" % (y, n, tot, mn))
            continue
        first = FIRST.get(y, DEFAULT_FIRST)
        print("=== %s（%d/%d 页）===" % (y, n, tot))

        code, out = run([PY, "scripts/pastpaper/lq1_parse.py", y,
                         "--first", str(first), "--last", "99"])
        line = [l for l in out.splitlines() if "道大題" in l]
        print("  parse  :", line[0].split("→")[0].strip() if line else out[-160:])
        if code != 0:
            print("  ⚠️ parse 失败：", out[-300:])
            continue

        code, out = run([PY, "scripts/pastpaper/lq1_build.py", y])
        line = [l for l in out.splitlines() if "併入" in l]
        print("  build  :", line[0].strip() if line else out[-160:])

        code, out = run([PY, "scripts/pastpaper/lq_figures.py", y],
                        env={"LQ_JSON": "data/bio/_lq_p1.json",
                             "LQ_PAGES_DIR": "scratch/_pp_pages",
                             "LQ_IMG_REL": "img/lq1"})
        line = [l for l in out.splitlines() if "張圖" in l or "张图" in l]
        print("  figures:", line[-1].strip() if line else out[-160:])
        done_any = True

    if not done_any:
        print("没有可导入的年份。")
    else:
        print("\n下一步：python site/build.py && python scripts/verify_build.py")


if __name__ == "__main__":
    main()
