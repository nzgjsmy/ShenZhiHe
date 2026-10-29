# -*- coding: utf-8 -*-
"""把纯文本文件里的题解写入 _pastpaper.json。

文本文件格式：每题一段，以单独一行 `@@@Q<题号> <年份>` 开始，下一段以 `@@@` 开头的新段或文件结束为界。
用法：python scratch/_ex_apply.py 2020 scratch/_ex_2020b.txt
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'data', 'bio', '_pastpaper.json')


def parse(path):
    """返回 {qnum: text}"""
    raw = open(path, encoding='utf-8').read()
    # 以行首 @@@Q 作为分段标记
    parts = re.split(r'(?m)^@@@Q\s*(\d+)\s+(\w+)\s*$', raw)
    out = {}
    # parts[0] 是头部（忽略），之后每两个元素一组
    for i in range(1, len(parts) - 2, 3):
        qnum = int(parts[i])
        year = parts[i + 1]
        body = parts[i + 2]
        # 去掉开头换行与结尾多余换行
        body = body.strip('\n')
        out.setdefault(year, {})[qnum] = body
    return out


def main():
    year = sys.argv[1]
    path = sys.argv[2]
    data = parse(path)
    d = json.load(open(P, encoding='utf-8'))
    by = {q['qnum']: q for q in d['years'][year]}
    applied = []
    for qnum, text in sorted(data[year].items()):
        if qnum not in by:
            print('!! 跳过：%s 年無第 %d 題' % (year, qnum))
            continue
        by[qnum]['explanation'] = text
        by[qnum]['explSource'] = 'notes'
        applied.append((qnum, len(text)))
    d['years'][year] = [by[n] for n in sorted(by)]
    json.dump(d, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('已寫入 %s 年 %d 題：%s' % (year, len(applied), applied))


if __name__ == '__main__':
    main()
