# 神智核 · 项目级记忆

> 本文件随 git 走，团队成员 clone 后自动加载。
> **完整事实来源是仓库根目录的 `SHARED-MEMORY.md`**；本文件只放「指针 + 速查」，
> 避免与它冲突。两者不一致时，以 `SHARED-MEMORY.md` 为准。

## 这是什么项目

DSE 生物/化学/物理/数学笔记整合站「神智核」。单文件离线网站，
由 `site/build.py` 把 `data/**/*.json` + `site/template.html` + `site/extras.js` 注入成一个 HTML。

```
f6chem/
├─ data/<sid>/*.json         ← 内容数据（bio/chem/phys/math）
├─ data/bio/_pastpaper.json  ← DSE 真题题库（下划线开头，不被当作课题加载）
├─ site/template.html        ← 前端模板（真题视图、错题本）
├─ site/extras.js            ← 额外资讯页逻辑
├─ site/build.py             ← ★ 唯一构建入口
├─ site/prep_ghpages.py      ← 生成部署目录 gh-pages/
├─ site/img/                 ← 所有图片（外置，不内嵌）
├─ quiz/                     ← 测验题
├─ docs/journal/             ← 每人自己的详细工作日志
├─ AGENTS.md                 ← 硬约束（给 AI 协作者）
└─ SHARED-MEMORY.md          ← ★ 唯一事实来源
```

## 每次开工必读

```bash
git checkout source && git pull
cat SHARED-MEMORY.md      # 至少读 §2 现状、§3 占用、§4 陷阱
cat AGENTS.md             # 硬约束
```

## 常用命令

```bash
python site/build.py                      # 构建
python scripts/verify_build.py            # ★ 构建后自检（必须全绿）
python scripts/guard_data.py              # ★ 题库守门员
python scripts/check_quiz.py              # 测验题自检
NO_WIPE=1 python site/prep_ghpages.py     # 生成部署目录
python site/_expl_coverage.py             # 题解覆盖率
python scripts/audit_questions.py         # 题库体检
python scripts/audit_images.py            # 配图体检（OCR 检测裁图错位）
```

## 硬约束（完整版见 AGENTS.md）

1. 构建只用 `python site/build.py`，`build.mjs` 已废弃。
2. 绝不手改 `site/神智核.html`（产物）。
3. 绝不设 `EMBED_IMG=1`（HTML 会涨到 63 MB）。
4. 部署必须**先清后拷** `img/`，不能用 `cp -rn`。
5. 改版才 bump `site/version.json`，同一批改动只 bump 一次。
6. `_pastpaper.json` 只准改 `explanation` / `explSource`。
7. 颜色只用语义变量，主色底文字用 `--on-accent`。

## 记忆怎么同步

| 文件 | 写什么 | 冲突风险 |
|---|---|---|
| `SHARED-MEMORY.md` | 现状/占用/陷阱/变更日志 | 高 → 只留一行摘要 |
| `docs/journal/<日期>-<名字>.md` | 详细过程、踩坑、命令 | 无 → 一人一文件 |
| `AGENTS.md` | 硬性约定 | 低 |
| `.codebuddy/`（本目录） | 自动加载的规则/技能/命令 | 低 → 改前先沟通 |

## 在线地址

- 线上：<https://nzgjsmy.github.io/ShenZhiHe/>
- `source` 分支 = 源码；`main` 分支 = 部署产物（GitHub Pages 从这里发布）。
