---
description: 构建 + 全量自检（build → verify → guard → quiz）。改完代码/数据后用这个。
argument-hint: "[可选说明]"
allowed-tools: Bash
---

对神智核仓库执行构建与完整自检。当前仓库根目录：$ARGUMENTS

按顺序执行，每步失败**立即停下并报告**，不要继续往下跑：

```bash
cd "$(git rev-parse --show-toplevel)" || exit 1
git branch --show-current    # 必须显示 source，否则停下提醒
```

若当前分支不是 `source`，**停止**并提示：「当前在 `<分支>`，源码分支是 source，请先切换。」

然后依次执行：

1. `python site/build.py` —— 唯一构建入口。失败则停。
2. `python scripts/verify_build.py` —— 必须全绿。失败则停，把失败项原样列出。
3. `python scripts/guard_data.py` —— 题库守门员。若本次改动了 `data/bio/_pastpaper.json`，此项必须为绿。
4. `python scripts/check_quiz.py` —— 仅当本次改动了 `quiz/` 才需要跑；若未改动就跳过并说明。

全部通过后，输出：
- 构建产物大小（应 < 6 MB）
- `verify_build.py` 的检查项通过情况
- 本次是否需要 bump `site/version.json`：**只有在内容或功能有实质变化时才需要**；纯排版微调、临时排查、中间态构建不要 bump。
- 提醒：**本命令不部署**。部署是独立步骤（见 `/deploy`）。
