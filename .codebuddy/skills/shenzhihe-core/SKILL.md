---
name: shenzhihe-core
description: 神智核 DSE 笔记整合站的构建/部署/数据守门流程。改动 site/、data/、scripts/ 后必须使用。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# 神智核 · 核心铁律

> 完整背景见仓库根目录 `AGENTS.md` 与 `SHARED-MEMORY.md`（唯一事实来源）。
> 本文件是**自动加载**的精简版，只保留最容易被违反、后果最严重的条目。

## 0. 分支语义（错分支 = 白干）

| 分支 | 内容 | 你该做什么 |
|---|---|---|
| `source` | 源码 | **所有开发在这里** |
| `main` | 已构建产物（GitHub Pages 发布源） | **不要往 main 提交源码** |

`master` 分支已废弃删除。开工先 `git checkout source && git pull`。

## 1. 构建：唯一入口是 `python site/build.py`

- `site/build.mjs` **已废弃**，现在只是转发桩。**不要恢复它的实现**——它缺 `_pastpaper`（真题数据）和 `__SEARCH_WORKER_URL__`（搜索 worker）。
- **绝不手改 `site/神智核.html`**，它是产物。改内容 → 改 `data/` 或 `site/template.html` → 重新构建。
- **绝不设 `EMBED_IMG=1`**，会把 HTML 从 3.7 MB 涨到 63 MB，线上加载崩溃。

## 2. 部署：必须「先清后拷」，不能 `cp -rn`

```bash
rm -rf "神智核-GitHub部署包/img"     # ⚠️ 先清
cp -r  f6chem/gh-pages/img "神智核-GitHub部署包/img"
```

`cp -rn` 的 `-n` 是 no-clobber，**目标已存在的同名文件不会被覆盖**。改过内容的 webp 会静默保留旧版 → 线上显示旧图但本地构建是对的，极难排查。

漏拷 `img/` → 新增图片全部 404（已发生两次）。

## 3. 版本号：批次粒度，不要碎 bump

`site/version.json` 的 version 是 service worker 缓存键（`shenzhine-<version>`），**不 bump 客户端就永远吃旧缓存**。但 bump 太频繁会反复作废用户缓存。

规矩：
- **同一批改动只 bump 一次**，全部做完再统一 bump + 部署。
- 只在「内容或功能有实质变化」时 bump；纯排版微调、临时排查、中间态构建**不 bump、不部署**。
- 一批大批量改动用一个版本号（如 V0.25.0），不要拆成 V0.24.1 / V0.24.2 / V0.24.3。
- 提交前看 `git log` 最近 3 个版本号，连续三个小版本号 = 拆太碎了。

## 4. 数据守门：`_pastpaper.json` 只准改两个字段

`data/bio/_pastpaper.json` 里**只有 `explanation` 和 `explSource` 可以自由改**。
其余（`q` / `options` / `answer` / `topic` / `pct` / `img` / `optImg` / `qImg` / `ocr*`）已人工校对过，
任何"顺手优化"都会破坏已校对内容。

改完必须跑 `python scripts/guard_data.py`（需要改受保护字段时用 `--allow <题号>:<字段>`，白名单仅本次生效，commit 信息必须写明原因）。

## 5. 收工清单（顺序固定）

```bash
python site/build.py && python scripts/verify_build.py   # 全绿才算完成
python scripts/guard_data.py                              # 动了题库就要跑
python scripts/check_quiz.py                              # 动了 quiz/ 就要跑
```

然后：
1. 部署走 `SHARED-MEMORY.md` §6 六步（**别忘先清后拷 img/**）
2. `SHARED-MEMORY.md` **§5 变更日志追加一条**（作者、时间、验证结果）
3. 更新 **§2 现状**（版本号、题数、题解数）
4. 详细过程写进 `docs/journal/<日期>-<你的名字>.md`（**不要把详细日志堆进 §5**，两人同时追加必冲突）

## 6. 协作防撞

- 动工前在 `SHARED-MEMORY.md` **§3 占用**登记，做完删掉。
- 分工：`data/bio/_pastpaper.json` 与 `site/template.html` 的真题区归 WorkBuddy；
  `site/extras.js`、`extras/*`、`_mk_pkg.py` 归 DSH；
  `site/build.py`、`site/prep_ghpages.py` 共同，改动需登记。

## 7. 已知陷阱速查（详细版见 `SHARED-MEMORY.md` §4）

| 陷阱 | 后果 |
|---|---|
| 用 build.mjs 构建 | 真题页整页空白 |
| 内嵌图片 | HTML 涨到 63 MB |
| 部署漏 `img/` | 新增图 404 |
| 没 bump 版本号 | 用户吃旧缓存看不到更新 |
| 渲染函数抛异常 | 页面**静默停在上一帧**，表现为「按钮没反应」 |
| 用 `go()` 跳到当前相同 hash | 不触发 hashchange，不重绘 |
| 照抄外部 AI 给的「补丁方案」 | 未核对真实代码就改，5/9 条是错的 |

## 8. 颜色与样式

- 只用**语义变量**（如 `--on-accent`），主色底上的文字用 `--on-accent`。
- 写死颜色会在深色主题里坏掉（历史踩过 18 处对比度坑）。
- 深色主题改完要用浏览器实测，别只看浅色。
