# 2026-10-29 · WorkBuddy AI

## 13:40 团队工作空间接入：`.codebuddy/` 项目级配置 + 指南

### 起因

用户问：「我要怎么把现在这个工作空间接入团队工作空间」。

先查了官方文档（`/docs/workbuddy/Overview`、`/docs/workbuddy/Pricing`、
`/docs/cli/codebuddy-dir`、资料库与协作章节），结论是**用户问题里藏着一个误解**：

> **本地工作空间（电脑上的文件夹）不能"接入"云端团队空间。**
> WorkBuddy 没有这个开关。本地目录永远是本地的。

真正能共享的是**三层东西**，得分别处理：

| 承载物 | 路径 | 对神智核意味着 |
|---|---|---|
| 代码、规则、数据 | **git**（`.codebuddy/` 随仓库走） | 已有 CI，零额外成本 |
| 资料、产物 | **资料库 → 团队空间** | 云端文档树，四档权限 |
| 协作容器 | **项目（Project）** | 项目指令 + 资产库 + 任务分享/流转 |

### 查证过的事实（避免凭印象说）

- **版本门槛**：官方定价页写明体验版就有「创建项目数 5 个/人、单项目成员数 3 人/项目（限免 5 人）、资料库 5GB」。
  → 结论是**不必等付费**，体验版就能建项目、邀请 3–5 人。
  （搜索结果里那篇讲「个人版不支持项目协作」的第三方文章与官方定价页冲突，以官方页为准。）
- **权限四档**：查看 / 编辑 / 管理 / 无权限；链接可设为「需申请权限」。
- **Agent 权限**：与当前用户完全一致，人看不到的 Agent 也读不到。
- **协作任务限制**：个人授权连接器在协作任务中全部禁用，只有公共授权可用。
- **`LibraryUpload` 的边界**：只能上传到**自己**的资料库，不能指定团队空间 id，也不生成分享链接。
  → 团队空间那步必须在客户端 UI 做，工具做不到。
- **项目级配置优先级**：项目级 > 用户级 > 插件级；`.codebuddy/settings.local.json` 自动进 `.gitignore` 不提交。

### 本地现状盘点

```
$ ls .codebuddy                          → 不存在
$ git status --short                      → 干净
$ git branch --show-current               → source
$ git ls-files | wc -l                    → 2051
$ du -sh data site gh-pages               → 19M / 513M / 52M
```

`site/` 513 MB、`gh-pages/` 52 MB，**远超资料库 5 GB 配额的实际可用性**（且这些是产物，本就不该上传）。
→ 所以明确写下：代码类一律走 git，资料库只放精选产物。

### 做了什么

**1. `.codebuddy/`（6 个文件，随 git 走，队友 clone 即生效）**

```
.codebuddy/
├─ CODEBUDDY.md                    项目级记忆（只放指针+速查，不复制 SHARED-MEMORY 的事实）
├─ rules/team-workflow.md          alwaysApply:true，团队通用规则，每次自动加载
├─ skills/shenzhihe-core/SKILL.md  构建/部署/数据守门技能
└─ commands/
   ├─ verify.md                    /verify            一键构建+11项自检
   ├─ deploy.md                    /deploy            一键六步部署+验收+回写
   └─ write-explanation.md         /write-explanation 写题解（含守门检查）
```

设计取舍：
- `CODEBUDDY.md` **不复制** `SHARED-MEMORY.md` 的内容，只做指针。
  理由：`SHARED-MEMORY.md` 是唯一事实来源，两份内容一旦分叉就是第二个真相源——这正是记忆体系铁律要避免的。
- `rules/` 放「每次都要看到」的（分支语义、构建入口、禁改字段、收工清单）；
  `skills/` 放「需要时才展开」的完整铁律。避免每次会话都塞满几千字。
- `commands/` 把散在文档里的流程**固化成可执行命令**，这是队友最容易出错的地方。

**2. `.gitattributes`**

统一 LF 入库、Windows 检出转 CRLF。
起因：加 `.codebuddy/` 时 git 报了 6 条 `LF will be replaced by CRLF` 警告。
多平台团队混合作业时，若不统一，「只差换行符」会被当成真实改动，污染 diff、引发误冲突。
用 `* text=auto eol=lf` + 对 `*.bat/*.cmd/*.ps1` 单独保 CRLF（cmd.exe 需要）。

**3. `docs/团队工作空间接入指南.md`**

给**人**看的接入文档（`docs/贡献指南.md` 讲"怎么一起建"，这份讲"怎么接进团队空间"）：
三条路径对比表、权限四档表、项目创建配置表（神智核该填什么）、队友加入标准流程、6 个常见疑问。

### 验证

```bash
python site/build.py        → 4,434,100 bytes / V0.24.1 / 2528 题
python scripts/verify_build.py → ✅ 全部 11 项通过
git check-ignore -v .codebuddy/CODEBUDDY.md → 未被忽略，会正常入库
git rev-list --left-right --count origin/source...source → 0 1（远端无新提交）
```

**没有改动任何既有源码或数据**，也没有 bump 版本号——
这批是纯协作基建，不影响站点产物，按 §5 铁律 5「只在内容或功能有实质变化时才 bump」不 bump。
`build.py` + `verify_build.py` 仍然 11/11 全绿，确认没破坏任何环节。

### 提交

```
7d6a858 chore: 加入 .codebuddy 项目级配置 + .gitattributes，团队成员 clone 即生效
1fb13d0 docs: 团队工作空间接入指南（三条路径 + 神智核组合方案 + 队友加入流程）
```

两次都先 `git fetch` 确认远端无新提交（铁律 8），再推 `source`。
**未推 `main`**——本次没有部署，部署包独立仓库不应被无谓改动。

### 留给用户手动做的（工具做不到）

1. 客户端左侧导航栏 →**项目** → `+ 新建项目`，把 `AGENTS.md` 铁律压缩成项目指令
2. 资料库 →**团队空间** → `+` 建空间 → 上传精选产物 → 邀请成员配权限
3. 体验版够用（5 项目 / 单项目 3 人限免 5 人 / 资料库 5GB），不必等付费

### 踩坑

- `LibraryUpload` 文档写得很明确：**不能**指定团队空间 id、**不**生成分享链接、**不**改权限。
  一开始想用它把文档直接"塞进团队空间"，读完 schema 才发现做不到——不要凭工具名猜能力。
- 搜索到的第三方文章称「个人版不支持项目协作」，与官方定价页直接冲突。
  遇到这种矛盾**以官方文档为准**，不要采信二手文章。
