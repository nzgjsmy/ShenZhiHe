# 2026-10-29 · WorkBuddy AI（下午）

## 18:50 云端自主工作：GitHub Actions 定时巡检

### 用户问题

「你能不能直接修改 github 仓库上面的源码，这样就算我电脑没有开机也继续工作了」

### 核实到的机制（不能凭印象答）

先查了官方文档再动手：

| 方案 | 电脑关机能跑吗 | 依据 |
|---|---|---|
| GitHub Actions | ✅ | runner 跑在 GitHub 服务器 |
| WorkBuddy **云端**定时任务 | ✅ | 文档原文「在云端沙箱中执行，电脑关机或离线时也能按时运行」 |
| WorkBuddy **本地**定时任务 | ❌ | 文档原文「本地定时任务在本机客户端中执行，执行期间请勿关闭电脑或退出客户端」 |

另外查到 CodeBuddy CLI 有官方无头模式文档（`codebuddy.cn/docs/cli/headless`）：
`-p` + `-y`（**非交互模式的必需参数**，否则文件读写/命令执行全被拦）+ `--allowedTools` 精确限权。

### 实测（本机装 CLI 验证，不是看文档）

```
npm install -g @tencent-ai/codebuddy-code   → 23 包，16s
codebuddy --version                          → 2.178.1
codebuddy -p "回复 OK" --output-format json → Error: Authentication required.
```

**关键结论**：CI 里必须用 `CODEBUDDY_API_KEY` 环境变量，不能用 `/login` 登录态
（CI 无交互式登录）。认证变量：
- `CODEBUDDY_API_KEY` — 仅调模型接口
- `CODEBUDDY_AUTH_TOKEN` — 完整平台功能（Token 刷新、计费查询）
- `CODEBUDDY_INTERNET_ENVIRONMENT=internal` — 中国版必须

装完已卸载，本机环境保持干净。

### 踩坑 1：schedule 事件要求 workflow 在默认分支

GitHub 官方规则：**`schedule`（定时）事件要求 workflow 文件存在于默认分支，否则 Cron 永不触发**；
而 `push` 事件不受此限制（读推送 ref 里的 workflow）。

本仓库默认分支是 `main`（部署产物分支），原本 `main` 上**一个 workflow 都没有**，
只改 source 分支的话定时任务永远不会跑。

解法：
1. `daily-audit.yml` 在 `main` 与 `source` **两分支各一份**，内容必须一致
   （用 `git rev-parse` 核对 git 对象哈希相同，不靠肉眼看）
2. `main` 是产物分支、没有 `data/`，所以 job 里显式检出源码：
   ```bash
   git fetch origin source --depth=1
   git checkout FETCH_HEAD -- data scripts
   ```

### 踩坑 2：.gitattributes 的 eol=lf 会制造伪 diff

上一轮我加的 `.gitattributes` 用了 `* text=auto eol=lf`，
结果这次改指南文档时**整个文件被标为已修改**（整片 diff，实际只改了一行）。

原因：`eol=lf` 强制**工作区**也是 LF，与仓库里已入库的 CRLF 文件冲突。
真正解决伪 diff 的是 `text=auto`（**入库时**统一 LF）。

修正为：
```gitattributes
* text=auto          # 入库统一 LF → 解决伪 diff
*.bat text eol=crlf  # 检出必须 CRLF（cmd.exe 不认 LF 批处理）
```
检出保持平台原生，不打扰本地工具链。
验证方式：`git add --renormalize .` 后 `git status` ——
**既有文件零误改**才算修对（这次跑出既有文件全部干净的正确结果）。

### 踩坑 3：audit_questions.py 的 --json 输出含统计类条目

`--json` 会输出 5 类，其中「题型分布」「文件/题量」「题图共用统计」是**正常信息**不是问题。
若照单全收，CI 每天都会误报开 Issue。

脚本本身已有 `QUIET_SKIP` 机制（`--quiet` 参数），与 `verify_build.py` 的门禁口径一致。
**用 `--quiet` 而不是自己实现过滤** —— 复用既有口径，不造第二套标准。
实测当前输出 0 行（题库干净）→ 不会误报。

### 交付

新增 `.github/workflows/daily-audit.yml`（**零 token 消耗**，纯标准库脚本）：
- 每天 UTC 03:17（港时 11:17）定时跑 `audit_questions.py --quiet`
- 与 `verify.yml` 分工：verify = 提交时守门，daily-audit = 定时体检存量
- 发现问题开 Issue（带「巡检」标签），**不自动改题库**（内容是人工校对的）
- 同日去重；`workflow_dispatch` 可手动重跑（带 force 开关）
- 权限最小化：`contents: read` + `issues: write`
- 标签不存在会自动创建，创建失败则降级无标签重试

验证：YAML 用 js-yaml 解析通过；6 个 bash 块用 `bash -n` 逐个校验通过；
`audit_questions.py` 纯净环境零依赖可跑；GitHub API 确认 workflow `state: active`。

### 关于 API Key 方案的判断（未实施，留给用户决定）

- 体验版每月 500 积分，API Key 消耗的就是账号积分
- **仓库是 public**（`"private": false`）→ 公开仓库的 Actions 有被薅额度的风险，
  启用前必须限制触发条件与权限
- 三档强度：①只巡检开 Issue（安全）②巡检+自动提 PR（CI 11 项守门员兜底）③全自动改主线（不建议）

### 未做

- 没有安装 API Key 相关的 workflow（需用户先申请 Key 并存进 GitHub Secrets）
- 没有触发手动运行（无 gh CLI；定时任务不依赖手动触发）
- 没有部署（本次只动 CI 配置与 .gitattributes，不影响站点产物）
- **未 bump 版本号**（纯 CI 基建，不影响站点）

### 提交

```
636ec11 ci: 新增 daily-audit 云端定时巡检 + 修正 .gitattributes 换行规则
1672126 ci: daily-audit 补 main 分支检出（main 是产物分支，题库在 source 上）
7293094 ci: 在 main 分支同步 daily-audit（激活定时巡检）
```
推 `source` 与 `main` 前均先 `git fetch` 确认远端无新提交（铁律 8）。
