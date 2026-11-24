# 2026-11-24 「Pages 看不到更新」排查：化学长题图从未部署

## 现象

用户反馈线上 <https://nzgjsmy.github.io/ShenZhiHe/> 看不到更新。

## 三层原因

### 1. 没部署（表层）

改动全在 source 分支（`253c439` / `aecf97e` / `929c73d`），部署包 `神智核-GitHub部署包`
还停在 `9cf26fa`（V0.25.25.20），从没执行部署六步。版本号自然没变。

### 2. 有别人推过 main（并发）

部署前 `git fetch` 发现远端 main 已经到 `a8e9cfe deploy: 科研時事自動更新 2026-11-23`。
**这个自动更新提交顺手删掉了 54 张图片**（`img/pp/2020/*.webp`、`img/lq1/2012/*.webp` 等），
但版本号仍是 V0.25.25.20，只改了 index.html 的新闻 payload。

处理：部署包先 `git merge --ff-only origin/main` 快进，再覆盖产物，避免把新闻更新冲掉。

### 3. 化学长题图从未进过 gh-pages/（真正的 bug）

`site/prep_ghpages.py` 只複製「index.html 引用到的图片」，匹配长题图的 regex 是：

```python
r"img/(lq1?/(?:[0-9]{4}|PP|SP)/p[0-9]{3}[A-Za-z0-9_\-]*\.webp)"
```

它认得生物的 `img/lq1/2012/p014.webp`，**认不得化学的 `img/lq1/chem/2012/p014.webp`**
（中间多一层 `chem/`）。

后果：`gh-pages/img/` 里从来没有 `lq1/chem` 目录，
**化学卷一乙部 210 题、256 张原卷页图，从 2012–2014 那批上线起就一直 404。**

为什么一直没被发现：Playwright 验收测的是本地 `site/` 目录（图片都在），不是 `gh-pages/`。
`verify_build.py` 也不比对部署目录。所以「本地全绿 + 线上图挂」能长期共存。

修法（与 pp 的写法对齐）：

```python
r"img/(lq1?/(?:chem/)?(?:[0-9]{4}|PP|SP)/p[0-9]{3}[A-Za-z0-9_\-]*\.webp)"
```

修后 prep 图片数 **1568 → 1824（+256）**。

## 部署结果

- 部署包 commit `6162c32`，推 `main`：`a8e9cfe..6162c32`
- 同步内容：index.html、service-worker.js、img（先 `rm -rf` 后整份 `cp -r`）、files
- 恢复 a8e9cfe 误删的 54 张图（本地 `gh-pages/img` 是完整的）
- `SW_VERSION = V0.25.25.23-14e50228`
- source 分支 commit `4aed5d5`（prep_ghpages 修复）

## 教训

1. **验收必须查线上**。本地 `site/` 正常 ≠ 线上正常；`prep_ghpages.py` 是白名单复制，
   漏一条 regex 就静默少一整批图。
2. **部署前必 fetch**。这次远端 main 已被自动更新任务推进，硬推会丢掉新闻数据。
3. **自动更新任务不带 img/**。`a8e9cfe` 只推了 index.html + service-worker.js，
   54 张图被删。任何改 index.html 的部署都必须连 img 一起同步。
4. 新增一类图片目录时，**要同时改 prep_ghpages 的 regex**——这是第二处「路径多一层」的坑
   （第一处是 pp 的 `pp/chem/`）。
