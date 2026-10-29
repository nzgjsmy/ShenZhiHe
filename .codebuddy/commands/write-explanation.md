---
description: 写/改 DSE 真题题解（data/bio/_pastpaper.json）。含守门检查与写作规范。
argument-hint: "<题号，例如 2018 q5 或 pp_2019_q34>"
allowed-tools: Read, Edit, Bash, Grep
---

为神智核的 DSE 真题库写或修改题解。目标题号：$ARGUMENTS

## 只准改两个字段

`data/bio/_pastpaper.json` 中**只有 `explanation` 和 `explSource` 可以改**。
其余字段（`q` / `options` / `answer` / `topic` / `pct` / `img` / `optImg` / `qImg` / `ocr*`）已人工校对过，
任何"顺手优化"都会破坏已校对内容。

确需改受保护字段时，用 `python scripts/guard_data.py --allow <题号>:<字段>` 显式放行，
白名单**只在本次运行生效**，且 commit 信息里必须写明原因。

## 写作规范（完整版见 `SHARED-MEMORY.md` §9）

三段式结构，缺一不可：

1. **判据** —— 凭什么能推出答案。先说清题干给了哪些条件、问的是什么。
2. **逐选项分析** —— A/B/C/D 逐个说为什么对/为什么错。错项要说明错在哪一步。
3. **易错点** —— 学生最容易踩的坑，以及怎么避开。

质量红线：
- 中位数不低于 **500 字**（当前全站中位约 569 字）。
- 不能只写结论不写理由；不能出现「显然」「不难看出」这类空话。
- 涉及图表的题，要说明看的是**哪个坐标/哪一段曲线/哪根柱**。
- 英文术语首次出现给中英对照（如 `酶（enzyme）`）。

## 改完必跑

```bash
python scripts/guard_data.py                                  # 守门员必须绿
python scripts/audit_questions.py                             # 题库体检
python site/build.py && python scripts/verify_build.py         # 构建 + 自检
python site/_expl_coverage.py                                 # 看覆盖率
```

## 报告

改完向用户汇报：题号、题解字数、结构是否齐全（判据/逐选项/易错点）、
守门员与体检结果。不要顺手 bump 版本号——版本号由 `/deploy` 统一处理。
