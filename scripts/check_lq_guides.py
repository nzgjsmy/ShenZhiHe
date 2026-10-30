#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查卷二题解稿的用字与排版问题。

为什么需要它
------------
题解稿是纯文本，要写几万字的中文繁體內容。手寫時很難完全避免幾類低級錯誤：

  ① **簡體字混入**（适/农/显/种…）—— 港台讀者一看就覺得刺眼，
     而 Markdown 渲染正常，CI 與 build 完全不會報錯。
  ② **半角括號混用**（（iii)）—— 渲染成半角，與全角並排會很刺眼。
  ③ **中英文之間缺空格或多空格** —— 影響閱讀節奏。
  ④ **未替換的佔位符**（TODO / 待填 / xxx）—— 半成品混進正式資料。

用法
----
  python scripts/check_lq_guides.py            # 掃描全部年份
  python scripts/check_lq_guides.py 2016       # 只掃某年
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDES = os.path.join(ROOT, "scripts", "pastpaper", "lq_guides")

# 「繁體一定不同」的簡體字。刻意不收兩字同形的（增/慢/約/級/絕/統/綠/則/僅/於/雲/亞/經…），
# 它們在繁體裏寫法相同，收進來只會製造噪音。
SIMP = set(
    "适农显发产变温药检验压阴阳虫杂养园圆脑听图团网卫稳务险边际继价见讲奖阶决军开课"
    "类离历丽联练疗临邻灵领刘楼陆虑乱买卖满门们梦灭拟鸟宁齐启气迁签浅枪抢桥亲穷区权劝让"
    "荣伞丧扫伤声胜湿师诗势兽书术树苏虽随岁孙缩谈汤涛讨腾题条铁厅头袜湾雾戏吓咸响协写兴须"
    "悬选盐严样爷业叶医仪遗议异银隐婴拥忧邮犹诱鱼语狱誉预员缘远愿约跃运灾载脏责择泽赠战"
    "张涨账胀赵证织职执纸质钟种肿众昼烛专砖转装妆壮状准浊资总纵组钻强岛济挤"
)

HALF_PAREN = re.compile(r"（([ivxIVX0-9]+)\)")
CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z0-9]")
PLACEHOLDER = re.compile(r"TODO|FIXME|待填|待補|xxx|XXX|\?\?\?", re.I)


def check(path):
    issues = []
    for i, line in enumerate(io.open(path, encoding="utf-8").read().split("\n"), 1):
        if not line.strip():
            continue
        simp = [c for c in line if c in SIMP]
        if simp:
            issues.append((i, "簡體字", "".join(simp), line.strip()[:56]))
        for m in HALF_PAREN.finditer(line):
            issues.append((i, "半角括號", m.group(0), line.strip()[:56]))
        for m in PLACEHOLDER.finditer(line):
            issues.append((i, "佔位符", m.group(0), line.strip()[:56]))
        # 中英文之間缺空格（只抓明顯的：中文緊接英文字母或數字）
        m = re.search(CJK.pattern + r"[A-Za-z]", line)
        if m:
            issues.append((i, "中英無空格", line[m.start():m.start() + 6], line.strip()[:56]))
    return issues


def main():
    years = sys.argv[1:]
    files = sorted(glob.glob(os.path.join(GUIDES, "*.txt")))
    if years:
        files = [f for f in files if os.path.basename(f)[:-4] in years]
    if not files:
        print("找不到題解稿：%s" % GUIDES)
        return 1

    total = 0
    for f in files:
        issues = check(f)
        total += len(issues)
        print("%-14s %s" % (os.path.basename(f), "✓ 無問題" if not issues else "%d 處" % len(issues)))
        for i, kind, frag, line in issues[:12]:
            print("   %4d  [%s]  %-10s  %s" % (i, kind, frag, line))
        if len(issues) > 12:
            print("   …… 還有 %d 處" % (len(issues) - 12))

    print("\n合計 %d 處問題" % total)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
