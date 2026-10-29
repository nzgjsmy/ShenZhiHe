# -*- coding: utf-8 -*-
"""检测真题配图是否「张冠李戴」：对每张图跑 OCR，提取图中文字，
再与该题题干/选项做关键词匹配。若图上出现的是别一题的题干文字，即为错位。

原理：真题原卷的图通常不含题干文字（选项为图时例外），所以
  · 图中文字 与 本题题干 高度重合  → 可疑（图其实是别题的题干截图）
  · 图中文字 与 本题完全无关      → 正常（示意图/曲线图）或需人工看

用法：python scripts/audit_images.py [年份...]
"""
import json, os, re, sys, glob
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PP = os.path.join(ROOT, 'data', 'bio', '_pastpaper.json')
ocr = RapidOCR()

# 高频词（题目里必然出现的），用于匹配
STOP = set('下列以下哪個哪項哪些正確不正確錯誤的是有會將被把於與和或及在對中上個這那其之並且為以不'.split())


def keywords(text):
    """取 2 字以上的连续中文/字母数字片段做指纹"""
    t = re.sub(r'[^\w一-鿿]+', ' ', text or '')
    out = set()
    for seg in t.split():
        if len(seg) >= 3 and seg not in STOP:
            out.add(seg)
    return out


def main():
    d = json.load(open(PP, encoding='utf-8'))
    years = sys.argv[1:] or list(d['years'].keys())
    hits = []
    for y in years:
        for q in d['years'].get(y, []):
            for fld in ('img', 'optImg'):
                p = q.get(fld)
                if not p:
                    continue
                fp = os.path.join(ROOT, 'site', p)
                if not os.path.exists(fp):
                    continue
                try:
                    res, _ = ocr(fp)
                except Exception as e:
                    print('  OCR 失败', p, e)
                    continue
                if not res:
                    continue
                txt = ''.join(t for _, t, _ in res)
                gk = keywords(txt)
                if len(gk) < 3:
                    continue
                qk = keywords((q.get('q') or '') + ' ' +
                              ' '.join(o.get('v') or '' for o in (q.get('options') or [])))
                if not qk:
                    continue
                # 判据一：图中出现连续长中文（>=10 字）→ 图上很可能整段题干文字
                longs = [m.group(0) for m in re.finditer(r'[一-鿿]{10,}', txt)]
                # 判据二：图中文字与本题文字重合度高
                hit = gk & qk
                ratio = len(hit) / len(gk) if gk else 0
                if longs or ratio >= 0.55:
                    hits.append((y, q['qnum'], fld, os.path.basename(p),
                                 round(ratio, 2), ' | '.join(longs)[:70] or txt[:70]))
    print('=== 配图文字与本题高度重合（疑似错位）===')
    for h in hits:
        print('  %s Q%-2d %-7s %-26s 重合%.2f  %s' % h)
    print('共 %d 处' % len(hits))


if __name__ == '__main__':
    main()
