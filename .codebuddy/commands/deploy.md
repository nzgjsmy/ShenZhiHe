---
description: 按六步流程部署到 GitHub Pages（先清后拷 img/，推 main 分支，线上验收）。
argument-hint: "<版本号及说明，例如 V0.25.0：补充化学真题>"
allowed-tools: Bash
---

把神智核部署到 GitHub Pages。版本号与说明：$ARGUMENTS

## 前置检查（不满足就停）

1. 当前分支必须是 `source`（源码）。`main` 只放部署产物。
2. `python scripts/verify_build.py` 必须全绿（没有就先跑 `/verify`）。
3. `site/version.json` 的 version 已经改成 $ARGUMENTS 里指定的版本号。**如果没改，先停下来问**，不要自己猜版本号。
4. `git fetch` —— 部署前必须 fetch，否则会覆盖别人的成果（历史上发生过线上丢失深色模式的事故）。

## 六步

```bash
cd "$(git rev-parse --show-toplevel)" || exit 1

# 0) 备份题库
cp data/bio/_pastpaper.json "data/bio/_pastpaper.json.bak-$(date +%H%M)"

# 1) 构建 + 自检
python site/build.py && python scripts/verify_build.py || exit 1

# 2) 准备部署目录
NO_WIPE=1 python site/prep_ghpages.py || exit 1

# 3) 同步到 git 部署包（★ 先清后拷，不能用 cp -rn）
DEPLOY="<工作区父目录>/神智核-GitHub部署包"
cp gh-pages/index.html        "$DEPLOY/index.html" || exit 1
cp gh-pages/service-worker.js "$DEPLOY/service-worker.js" || exit 1
rm -rf "$DEPLOY/img"          # ⚠️ 先清：cp -rn 的 no-clobber 会漏掉改过的图
cp -r  gh-pages/img           "$DEPLOY/img" || exit 1

# 4) 推送（部署包是独立 git 仓库，推 main）
cd "$DEPLOY" && git add -A && git commit -m "$ARGUMENTS" && git push origin main || exit 1
```

## 部署后回写（不要漏）

回到仓库根目录，更新 `SHARED-MEMORY.md`：
1. **§5 变更日志追加一条**：作者、时间、版本号、验证结果。**只加一行摘要**，详细过程写进 `docs/journal/<日期>-<名字>.md`。
2. **§2 现状**：更新版本号、题数、题解数。

## 验收

推送后等 60–90 秒：

```bash
curl -s https://nzgjsmy.github.io/ShenZhiHe/service-worker.js | grep SW_VERSION
```

SW_VERSION 应等于新版本号。不一致就报告，不要重试部署。

最后向用户汇报：版本号、构建大小、自检结果、线上 SW_VERSION、回写了哪些章节。
