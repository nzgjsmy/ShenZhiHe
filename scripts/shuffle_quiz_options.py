# -*- coding: utf-8 -*-
"""把 quiz 題庫「正確選項固定排第一」的偏差打散成 A/B/C/D 平均。

背景：生成器長期把正確選項寫在 options[0]，導致生物 90%、物理 53% 的 MC 答案都是 A，
使用者光猜 A 就能拿高分。本腳本只做「交換兩個選項的文字 + 改 answer 索引」，
**題幹、題解、id、point 一個字都不動**，格式也保持原檔的手工排版（不重新序列化）。

必須鎖住不碰的題：
  1. 題解／題幹裡出現單個大寫 A–D —— 很多是「故 A 錯」「選項 B 描述…」，
     也可能是維生素 A、¹²C、A 區等學科符號；分不清就一律不冒險。
  2. options 自帶 `A `／`B. ` 這類字母前綴 —— 前綴本身就是位置標籤，重排會對不上。
  3. 選項數不是 4、answer 不是合法索引 —— 交給 check_quiz.py 管，這裡別碰。

鎖住的題答案仍偏 A，所以用「補償分配」把可重排題的答案補到總體計數最少的位置，
讓**全科** A/B/C/D 盡量平均（不是只有被改的那批平均）。

用法：python scripts/shuffle_quiz_options.py            # 乾跑，只看計畫
      python scripts/shuffle_quiz_options.py --apply   # 真的寫回
"""
import argparse
import collections
import glob
import io
import json
import os
import random
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 20261106
ANY_LETTER = re.compile(r'(?<![A-Za-z0-9⁰-⁹])[ABCD](?![A-Za-z0-9⁰-⁹])')
PREFIX = re.compile(r'^[ABCD][ .、．:：]\s*')
DEC = json.JSONDecoder()
TEXT_CACHE = {}


def array_spans(s, bracket):
    """回傳 JSON 陣列裡每個元素的 (start, end) 文字範圍，不重新序列化。"""
    spans, i = [], bracket + 1
    while True:
        while i < len(s) and s[i] in ' \t\r\n,':
            i += 1
        if i >= len(s) or s[i] == ']':
            return spans
        _, end = DEC.raw_decode(s, i)
        spans.append((i, end))
        i = end


def question_spans(text, n):
    m = re.search(r'"questions"\s*:\s*\[', text)
    if not m:
        raise RuntimeError('找不到 questions 陣列')
    spans = array_spans(text, m.end() - 1)
    if len(spans) != n:
        raise RuntimeError('題數對不上：文字 %d / JSON %d' % (len(spans), n))
    return spans


def is_locked(q):
    opts = q.get('options') or []
    if len(opts) != 4 or not isinstance(q.get('answer'), int):
        return True
    if not (0 <= q['answer'] < 4):
        return True
    text = (q.get('explanation') or '') + ' ' + (q.get('q') or '')
    if ANY_LETTER.search(text):
        return True
    if any(isinstance(o, str) and PREFIX.match(o) for o in opts):
        return True
    return False


def plan_targets(items):
    """items: [(file, qi, q, span)]；回傳 {(file,qi): target} 與最終分布。"""
    counts = collections.Counter({k: 0 for k in range(4)})
    free = []
    for f, qi, q, span in items:
        if is_locked(q):
            counts[q['answer']] += 1
        else:
            free.append((f, qi, q))
    rng = random.Random(SEED)
    rng.shuffle(free)
    targets = {}
    for f, qi, q in free:
        lo = min(counts[k] for k in range(4))
        cand = [k for k in range(4) if counts[k] == lo]
        t = rng.choice(cand)
        counts[t] += 1
        targets[(f, qi)] = t
    return targets, counts


def strip_prefixes():
    """清掉選項文字自帶的 `A `／`B. ` 位置標籤。

    ⚠️ 只能動「四個選項前綴剛好是 A/B/C/D 各一次」的題：
    bio25-q31 的「A 與 T 配對，C 與 G 配對」四個選項都以 A 開頭，
    那裡的 A 是腺嘌呤，剝掉就把題目毀了。
    只刪除前綴那幾個字元，引號與其餘文字一個字都不動。
    """
    edits = collections.defaultdict(list)
    n_q = 0
    for f in sorted(glob.glob(os.path.join(ROOT, 'quiz', '*', '*.json'))):
        if os.path.basename(os.path.dirname(f)) not in ('bio', 'chem', 'phys'):
            continue
        text = io.open(f, encoding='utf-8').read()
        data = json.loads(text)
        spans = question_spans(text, len(data['questions']))
        for q, (s, e) in zip(data['questions'], spans):
            if q.get('type') != 'mc':
                continue
            obj = text[s:e]
            mo = re.search(r'"options"\s*:\s*\[', obj)
            if not mo:
                continue
            opt_spans = array_spans(obj, mo.end() - 1)
            vals, letters = [], []
            for a, b in opt_spans:
                try:
                    v = json.loads(obj[a:b])
                except Exception:
                    v = None
                vals.append(v)
                m = PREFIX.match(v) if isinstance(v, str) else None
                letters.append(v[0] if m else None)
            if sorted(x for x in letters if x) != ['A', 'B', 'C', 'D']:
                continue
            for (a, b), v in zip(opt_spans, vals):
                plen = len(PREFIX.match(v).group(0))
                # s+a 是開頭引號的位置；+1 之後才是字串內容
                edits[f].append((s + a + 1, s + a + 1 + plen, ''))
            n_q += 1
    for f, ops in edits.items():
        text = io.open(f, encoding='utf-8').read()
        for s, e, new in sorted(ops, key=lambda x: x[0], reverse=True):
            text = text[:s] + new + text[e:]
        io.open(f, 'w', encoding='utf-8', newline='').write(text)
    print('清掉 %d 題的選項字母前綴（共 %d 處）' % (n_q, sum(len(v) for v in edits.values())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='真的寫回檔案')
    ap.add_argument('--force', action='store_true', help='即使已均勻也強制重排（換一批順序）')
    ap.add_argument('--strip-prefix', action='store_true',
                    help='清掉選項自帶的 A /B. 前綴（與重排分開執行）')
    args = ap.parse_args()

    if args.strip_prefix:
        strip_prefixes()
        return

    files = sorted(glob.glob(os.path.join(ROOT, 'quiz', '*', '*.json')))
    by_sub = collections.defaultdict(list)
    for f in files:
        sub = os.path.basename(os.path.dirname(f))
        if sub not in ('bio', 'chem', 'phys'):
            continue
        text = io.open(f, encoding='utf-8').read()
        data = json.loads(text)
        spans = question_spans(text, len(data['questions']))
        for qi, q in enumerate(data['questions']):
            if q.get('type') == 'mc':
                by_sub[sub].append((f, qi, q, spans[qi]))
        # 快取文字，避免重複讀
        TEXT_CACHE[f] = text

    # 冪等保護：三科都已經平均時就別再洗一次（否則每次跑都會換一批順序）
    befores = {s: collections.Counter(q['answer'] for f, qi, q, sp in by_sub[s])
               for s in ('bio', 'chem', 'phys')}
    spread = [max(befores[s][k] for k in range(4)) - min(befores[s][k] for k in range(4))
              for s in ('bio', 'chem', 'phys')]
    if max(spread) <= 1 and not args.force:
        print('三科答案分布都已平均（最大落差 %d），無須重跑。' % max(spread))
        for s in ('bio', 'chem', 'phys'):
            print('  %-5s %s' % (s, [befores[s][k] for k in range(4)]))
        print('若想換一批順序，加 --force --apply。')
        return

    total_changed = 0
    for sub in ('bio', 'chem', 'phys'):
        items = by_sub[sub]
        before = befores[sub]
        targets, after = plan_targets(items)
        ansmap = {(f, qi): q['answer'] for f, qi, q, sp in items}
        locked = sum(1 for f, qi, q, sp in items if is_locked(q))
        changed = sum(1 for key, t in targets.items() if t != ansmap[key])
        print('%-5s MC %4d | 鎖住 %3d | 將改 %3d 題' % (sub, len(items), locked, changed))
        print('      改前 %s → 改後 %s' % (
            [before[k] for k in range(4)], [after[k] for k in range(4)]))
        total_changed += changed

    if not args.apply:
        print('\n（乾跑，未寫入。加 --apply 才會真的改檔）')
        return

    # 逐檔收集「文字替換」，全部做完再從後往前套用，避免偏移量錯亂
    edits = collections.defaultdict(list)
    for sub in ('bio', 'chem', 'phys'):
        items = by_sub[sub]
        targets, _ = plan_targets(items)
        for f, qi, q, span in items:
            key = (f, qi)
            if key not in targets:
                continue
            t = targets[key]
            a = q['answer']
            if t == a:
                continue
            text = TEXT_CACHE[f]
            s, e = span
            obj = text[s:e]
            mo = re.search(r'"options"\s*:\s*\[', obj)
            ma = re.search(r'"answer"\s*:\s*(\d+)', obj)
            if not mo or not ma:
                raise RuntimeError('%s q#%d 找不到 options/answer' % (f, qi))
            opt_spans = array_spans(obj, mo.end() - 1)
            if len(opt_spans) != 4:
                raise RuntimeError('%s q#%d 選項數 %d' % (f, qi, len(opt_spans)))
            oi, oj = opt_spans[a], opt_spans[t]
            if oi[0] > oj[0]:
                oi, oj = oj, oi
            # 交換兩段選項文字（連引號一起），格式 100% 保留
            edits[f].append((s + oi[0], s + oi[1], obj[oj[0]:oj[1]]))
            edits[f].append((s + oj[0], s + oj[1], obj[oi[0]:oi[1]]))
            edits[f].append((s + ma.start(1), s + ma.end(1), str(t)))

    for f, ops in edits.items():
        text = TEXT_CACHE[f]
        for s, e, new in sorted(ops, key=lambda x: x[0], reverse=True):
            text = text[:s] + new + text[e:]
        io.open(f, 'w', encoding='utf-8', newline='').write(text)
        print('寫回 %-34s %3d 處替換' % (os.path.relpath(f, ROOT), len(ops)))
    print('\n共改 %d 題；請接著跑 scripts/check_quiz.py 與 site/build.py' % total_changed)


if __name__ == '__main__':
    main()
