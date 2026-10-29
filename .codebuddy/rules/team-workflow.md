---
alwaysApply: true
---

# 神智核 · 团队通用规则

> 这是**每次都会自动加载**的规则。完整铁律见 `AGENTS.md`，项目级记忆见 `.codebuddy/CODEBUDDY.md`。

## 分支

- 源码在 `source` 分支；`main` 只放已构建的部署产物。
- `master` 已废弃。开工先 `git checkout source && git pull`。

## 动手前

1. 读 `SHARED-MEMORY.md` §2 现状、§3 占用、§4 陷阱。
2. 看 `git log --oneline -5`，确认别人最近在改什么。
3. 若 `SHARED-MEMORY.md` §3 占用里已有别人登记的区域，**不要碰**；要碰就先沟通。

## 改完

1. `python site/build.py && python scripts/verify_build.py` —— 必须全绿。
2. 动了 `data/bio/_pastpaper.json` → 再跑 `python scripts/guard_data.py`。
3. 动了 `quiz/` → 再跑 `python scripts/check_quiz.py`。
4. 详细过程写 `docs/journal/<日期>-<你的名字>.md`；`SHARED-MEMORY.md` §5 **只加一行**摘要。
5. 更新 `SHARED-MEMORY.md` §2 现状。

## 不要做的事

- ❌ 手改 `site/神智核.html`（产物，由 `site/build.py` 生成）。
- ❌ 用 `site/build.mjs` 构建（已废弃转发桩，缺 `_pastpaper` 与搜索 worker）。
- ❌ 设 `EMBED_IMG=1`（HTML 会从 3.7 MB 涨到 63 MB）。
- ❌ 用 `cp -rn` 部署图片（no-clobber 会漏掉改过的图，必须先 `rm -rf` 再 `cp -r`）。
- ❌ 改 `_pastpaper.json` 里 `explanation` / `explSource` 以外的字段。
- ❌ 写死颜色（必须用语义变量，深色主题会坏）。
- ❌ 照抄外部 AI 给的「补丁方案」而不核对真实代码。
- ❌ 每个小改动都 bump 版本号（同一批改动只 bump 一次）。

## 沟通

- 遇到疑问先查 `SHARED-MEMORY.md` §4 陷阱表，90% 的坑都记在那里。
- 需要别人区域的文件时，先在 §3 登记占用。
