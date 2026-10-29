# -*- coding: utf-8 -*-
"""全站题目数据体检：扫出所有可能触发前端异常的入口点。

检查项分四类：
  A. 渲染类（内容会出现字面 \n、markdown 不生效、表格被截断）
  B. 结构类（答案越界、选项数不对、id 重复、topic 失效）
  C. 引用类（配图文件不存在、题图/选项图错配）
  D. 数值类（得分率越界、题量异常）

用法：python scripts/audit_questions.py [--json]
"""
import json, os, sys, glob, re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PP = os.path.join(ROOT, 'data', 'bio', '_pastpaper.json')
MC = os.path.join(ROOT, 'data', 'bio', '_mc_answers.json')
QUIZ = os.path.join(ROOT, 'quiz')

issues = defaultdict(list)   # 类别 -> [描述]


def add(cat, msg):
    issues[cat].append(msg)


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# 1) 生物真题库
# ============================================================
pp = load(PP)
years = pp.get('years', {})
allq = []
for y, qs in years.items():
    for q in qs:
        allq.append((y, q))

# --- 1.1 字面 \n（渲染类，P0）---
lit = [(y, q['id']) for y, q in allq if '\\n' in (q.get('explanation') or '')]
if lit:
    add('A1-题解含字面\\n', '%d 题的 explanation 存的是字面 "\\n" 两字符而非真换行，'
        'mdLite 逐行解析失效，表格/列表/代码块全部退化成一行。年份分布：%s'
        % (len(lit), dict(Counter(y for y, _ in lit))))
    add('A1-题解含字面\\n', '  受影响题号：' + ', '.join(
        '%s:%s' % (y, i.split('_')[-1]) for y, i in lit[:40]) + (' …' if len(lit) > 40 else ''))

# --- 1.2 题干/选项里的字面 \n ---
litq = [(y, q['id']) for y, q in allq if '\\n' in (q.get('q') or '')]
if litq:
    add('A2-题干含字面\\n', '%d 题的题干含字面 "\\n"' % len(litq))

# --- 1.3 题干里的字面转义（\t \" \' 等）---
esc_pat = re.compile(r'\\[nrt"\'`]')
esc_hits = []
for y, q in allq:
    for fld in ('q', 'explanation'):
        t = q.get(fld) or ''
        if esc_pat.search(t):
            esc_hits.append((q['id'], fld))
if esc_hits:
    add('A3-其它转义残留', '%d 处字段含 \\n/\\t/\\" 等转义残留' % len(esc_hits))

# --- 1.4 答案合法性 ---
bad_ans = [(q['id'], q.get('answer')) for _, q in allq
           if q.get('answer') not in list('ABCD')]
if bad_ans:
    add('B1-答案非法', '%d 题的 answer 不在 A-D：%s' % (len(bad_ans), bad_ans[:10]))

# --- 1.5 选项结构 ---
no_opt = []
for _, q in allq:
    opts = q.get('options') or []
    keys = [o.get('k') for o in opts]
    if len(opts) != 4 and not (q.get('optImg') or q.get('qImg')):
        no_opt.append((q['id'], len(opts)))
    if keys and keys != ['A', 'B', 'C', 'D']:
        no_opt.append((q['id'], 'keys=%s' % keys))
if no_opt:
    add('B2-选项结构异常', '%d 题选项数≠4（且无选项图）或 key 非 ABCD：%s'
        % (len(no_opt), no_opt[:10]))

empty_opt = [q['id'] for _, q in allq
             if any(not (o.get('v') or '').strip() for o in (q.get('options') or []))
             and not (q.get('optImg') or q.get('qImg'))]
if empty_opt:
    add('B3-空选项且无选项图', '%d 题：%s' % (len(empty_opt), empty_opt[:12]))

# --- 1.6 id / qnum 重复 ---
idc = Counter(q['id'] for _, q in allq)
dup_id = [k for k, v in idc.items() if v > 1]
if dup_id:
    add('B4-id重复', '%s' % dup_id[:10])
qn = Counter((y, q['qnum']) for y, q in allq)
dup_qn = [k for k, v in qn.items() if v > 1]
if dup_qn:
    add('B5-同年份题号重复', '%s' % dup_qn[:10])

# --- 1.7 空题干 / 空题解 ---
empty_q = [q['id'] for _, q in allq if not (q.get('q') or '').strip()]
if empty_q:
    add('B6-空题干', '%s' % empty_q)
empty_e = [q['id'] for _, q in allq if not (q.get('explanation') or '').strip()]
if empty_e:
    add('B7-空题解', '%s' % empty_e)

# --- 1.8 数值 ---
bad_pct = [(q['id'], q.get('pct')) for _, q in allq
           if not isinstance(q.get('pct'), int) or not (0 <= q.get('pct', 0) <= 100)]
if bad_pct:
    add('D1-得分率越界', '%s' % bad_pct[:10])

# --- 1.9 配图文件 ---
miss_img = []
for _, q in allq:
    for fld in ('img', 'optImg', 'qImg'):
        p = q.get(fld)
        if p and not os.path.exists(os.path.join(ROOT, 'site', p)):
            miss_img.append((q['id'], fld, p))
if miss_img:
    add('C1-配图文件缺失', '%s' % miss_img[:10])

# --- 1.10 optImg 复用（同一张图被多题引用，常见于「错题」）---
optmap = defaultdict(list)
for _, q in allq:
    if q.get('optImg'):
        optmap[q['optImg']].append(q['id'])
shared = {k: v for k, v in optmap.items() if len(v) > 1}
if shared:
    add('C2-选项图被多题共用', '%d 张选项图被多题引用：%s'
        % (len(shared), {k: v for k, v in list(shared.items())[:5]}))

# --- 1.11 题图被多题共用（共用指引题是合理的，但要能区分）---
imgmap = defaultdict(list)
for _, q in allq:
    if q.get('img'):
        imgmap[q['img']].append(q['id'])
shared_img = {k: v for k, v in imgmap.items() if len(v) > 1}
add('C3-题图共用统计', '%d 张题图被多题共用（共用指引题属正常）' % len(shared_img))

# --- 1.12 topic 有效性 ---
topics = set()
for f in glob.glob(os.path.join(ROOT, 'data', 'bio', 'bio*.json')):
    try:
        topics.add(os.path.basename(f)[:-5])
    except Exception:
        pass
bad_topic = sorted(set(q.get('topic') for _, q in allq if q.get('topic') not in topics))
if bad_topic:
    add('B8-topic不存在', '%s' % bad_topic)

# --- 1.13 指引题号与自身是否一致 ---
guide_bad = []
for y, q in allq:
    m = re.search(r'第\s*(\d+)\s*(?:及|和|至|到)\s*(\d+)\s*題', q.get('q') or '')
    if m and not (int(m.group(1)) <= q['qnum'] <= int(m.group(2))):
        guide_bad.append(q['id'])
if guide_bad:
    add('B9-指引题号串题', '%s' % guide_bad)

# ============================================================
# 2) 答案与得分率表
# ============================================================
mc = load(MC)
mismatch = []
for y, lst in mc.get('years', {}).items():
    if y not in years:
        continue
    by = {q['qnum']: q for q in years[y]}
    for it in lst:
        q = by.get(it['qnum'])
        if not q:
            continue
        if q.get('answer') != it.get('answer'):
            mismatch.append((y, it['qnum'], it.get('answer'), q.get('answer')))
        if (q.get('pct') or 0) != it.get('pct'):
            mismatch.append((y, it['qnum'], 'pct', it.get('pct'), q.get('pct')))
if mismatch:
    add('B10-图表与题库答案/得分率不一致', '%d 处：%s' % (len(mismatch), mismatch[:10]))

# ============================================================
# 3) quiz 题库（判分类）
# ============================================================
qfiles = sorted(glob.glob(os.path.join(QUIZ, '**', '*.json'), recursive=True))
bad_types = Counter()
ans_oob = []
md_in_quiz = []
opt_count = []
dup_qid = []
qid_all = Counter()
for f in qfiles:
    rel = os.path.relpath(f, ROOT)
    try:
        d = load(f)
    except Exception as e:
        add('E1-quiz文件解析失败', '%s: %s' % (rel, e))
        continue
    qs = d.get('questions') or []
    for q in qs:
        qid = q.get('id')
        qid_all[qid] += 1
        t = q.get('type')
        bad_types[t] += 1
        opts = q.get('options')
        ans = q.get('answer')
        if t == 'mc':
            if not isinstance(opts, list) or not opts:
                opt_count.append((rel, qid, 'options 缺失'))
                continue
            if not isinstance(ans, int) or not (0 <= ans < len(opts)):
                ans_oob.append((rel, qid, 'answer=%r options=%d' % (ans, len(opts))))
            if len(opts) != 4:
                opt_count.append((rel, qid, 'options=%d' % len(opts)))
        elif t == 'tf':
            if not isinstance(ans, bool):
                ans_oob.append((rel, qid, 'tf answer 非 bool: %r' % ans))
        elif t == 'fill':
            if ans is None or (isinstance(ans, list) and not ans):
                ans_oob.append((rel, qid, 'fill answer 空'))
        else:
            ans_oob.append((rel, qid, '未知 type=%r' % t))
        if q.get('explanation') and '\\n' in q['explanation']:
            add('A4-quiz题解含字面\\n', '%s %s' % (rel, qid))
        if q.get('explanation') and re.search(r'\*\*|^\s*[-*]\s|\|.*\|', q['explanation'], re.M):
            md_in_quiz.append((rel, qid))

dup_qid = [k for k, v in qid_all.items() if v > 1]
if dup_qid:
    add('B11-quiz id重复', '%d 个：%s' % (len(dup_qid), dup_qid[:10]))
if ans_oob:
    add('B12-quiz答案越界/类型错', '%d 处：%s' % (len(ans_oob), ans_oob[:12]))
if opt_count:
    add('B13-quiz选项数异常', '%d 处：%s' % (len(opt_count), opt_count[:12]))
if md_in_quiz:
    add('D4-quiz题解含markdown', '%d 条题解写了 markdown（渲染已改用 mdLite，现已生效）' % len(md_in_quiz))
add('D2-quiz题型分布', str(dict(bad_types)))
add('D3-quiz文件/题量', '%d 个文件，%d 道题' % (len(qfiles), sum(qid_all.values())))

# ============================================================
# 输出
# ============================================================
order = sorted(issues.items(), key=lambda kv: kv[0])
if '--json' in sys.argv:
    print(json.dumps({k: v for k, v in issues.items()}, ensure_ascii=False, indent=1))
elif '--quiet' in sys.argv:
    # 只輸出「需要處理」的條目，每行一條，供 verify_build 當門禁
    QUIET_SKIP = ('C2-', 'C3-', 'D1-', 'D2-', 'D3-', 'D4-', 'B4-', 'B5-', 'B8-', 'B11-', 'B13-')
    for cat, msgs in order:
        if cat.startswith(QUIET_SKIP):
            continue
        for m in msgs:
            print('[%s] %s' % (cat, m))
else:
    for cat, msgs in order:
        print('\n【%s】' % cat)
        for m in msgs:
            print('  · ' + m)
    print('\n' + '=' * 60)
    print('共 %d 类问题' % len(issues))
