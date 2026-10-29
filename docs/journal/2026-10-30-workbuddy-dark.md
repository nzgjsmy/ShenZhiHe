# 深色主题浅底漏转根治（2026-10-30）

> 参与者：WorkBuddy ｜ 触发：用户截图反馈「有些区域在深色主题仍然会呈现浅色」

## 症状

用户给的截图是 **DSE 真题页（按話題视图）**：一大块米白色容器裹着深色题卡，容器标题「生命的基本單位」是**白字写在白底上**，几乎看不见。

## 根因

**不是深色覆盖写少了，而是容器颜色被写死了。**

第一轮手账化（同一天早些时候）加过一段：

```css
.qtext{color:#2f2a22}                                  /* 死文字色 */
.qtype{background:#fffdf4;border:1px solid #e6dfcd}    /* 死背景 */
.opt  {background:#fffdf4;border:1px solid #e6dfcd}
.expl {background:#fffdf4}
.pcard{background:#fffdf4;border:1px solid #ece6d6}
```

而深色主题覆盖的是**变量**：

```css
html[data-theme="dark"]{ --paper:#1c1e25; --ink:#e8e5de; }
```

硬编码 `#fffdf4` 不读变量，所以永远是浅色。同类硬编码共 **23 行 / 35 处**，分布在真题卡、答题卡、错题本、进度条槽、表格头、hover 态。

## 改法：硬编码 → 语义变量

| 硬编码 | 变量 | 出现 |
|---|---|---|
| `#fffdf4` / `#fff` / `#ffffff` | `--paper` | 8 |
| `#efe9dd` | `--panel` | 4 |
| `#f3efe6` | `--hover` | 2 |
| `#f5f1e8` | `--paper-alt` | 2 |
| `#fff7ed` / `#fff8e6` | `--amber-soft` | 3 |
| `#eef6f0` | `--green-tint` | 1 |
| `#fdf0ee` | `--red-soft` | 1 |
| `#e6dfcd` / `#ece6d6` / `#e5e7eb` | `--line` | 8 |
| `#2f2a22` | `--ink` | 1 |
| `#8a9aa8` | `--muted` | 1 |

**浅色视觉不变**（`--paper` 在浅色下就是 `#fffdf4`），深色自动跟随。

### 一个必须开的例外

`mark` 搜索高亮原本是亮黄 `#fff3bf`。直接套 `--amber-soft` 会退化成 `#fdf1e3`（淡橙），**高亮等于失效**。

所以新增独立变量：

```css
:root{--mark-bg:#fff3bf}                      /* 浅色：原来的亮黄 */
html[data-theme="dark"]{--mark-bg:#6b5312}    /* 深色：暗黄，配浅字可读 */
mark{background:var(--mark-bg);color:var(--ink)}
```

**教训：批量替换时要盯住「这个颜色的作用是语义，还是特定的视觉效果」。** 高亮、警示、状态色往往不能简单归入通用底色调色板。

## 新工具：`scripts/audit_dark_theme.py`

肉眼找浅底不可靠（用户这次就发现了我漏看的一整块）。写成脚本：

### A 类：浅底漏转

遍历所有可见元素，取 `backgroundColor`，算相对亮度，`> 0.42` 就报。

关键细节：
- **`background-color: transparent` 不算问题** —— 它透出父级，父级深就是深。只看"自己有不透明背景"的元素，否则同一个浅色祖先下的每个子元素都会被报一次。
- **必须排除主色系** —— 深色主题的 `--accent` 是亮青 `#2dd4bf`（亮度 0.69），`--amber`、`--hn-accent` 同理。不排除的话，一页几百个按钮刷屏，真正的漏转被淹没。

### B 类：文字糊掉

背景修好后，可能出现「深底深字」。所以还要查对比度：
- 沿父链找第一个不透明背景（`a >= 0.9`）作为真实背景
- 算 WCAG 对比度，`< 3.0` 就报
- 只查「自己直接含文本节点」的元素，避免父子重复计

### 踩的坑

**排除逻辑静默失效**：第一版写成

```js
const accent = parse(getComputedStyle(html).getPropertyValue('--accent').trim());
```

但变量表里存的是 `#2dd4bf`（hex），而 `parse()` 只认 `rgb(...)` → 返回 `null` → 排除分支永不进入 → 报告里全是按钮。

修复：`parse()` 同时支持 `rgb()/rgba()/#rrggbb/#rgb`。

**假阴性自检**：脚本跑出「0 处」时不能直接信。我往页面注入了一个深底深字元素（`bg #2b2e38` / `color #33363f`），实测对比度 1.12，确认能被抓到 —— 这样「0 处」才有意义。

## 为什么不接入 `verify_build.py`

它依赖 Playwright + 本机 Chrome。CI 的 ubuntu runner 没装浏览器，接进去会让每次提交都挂。定位是**本地工具**：改配色 / 主题后手动跑一次（约 1 分钟）。

## 验证

| 项目 | 结果 |
|---|---|
| A 类浅底漏转（9 条路由） | **0 处** |
| B 类文字对比度（9 条路由） | **0 处** |
| 注入自检 | 深底深字被抓到（1.12） |
| `build.py` | 通过 |
| `verify_build.py` | 13/13 |
| `guard_data.py` | 0 道题改动 |
| 浅色真题页 | 目视无退化（暖白纸、题目卡、选项按钮均正常） |
| 深色真题页 | 分组容器已转深，标题清晰 |
| 深色 LQ 页 | 全深，题号/分值标签清晰 |
| 深色答题页 | 全深，选项按钮清晰 |

## 状态

**未 bump 版本号、未部署**（延续用户「先本地看效果」的要求）。

## 遗留

- `.ppimg{background:var(--paper)}`：图片容器在深色下是深底，扫描图本身白底，会显出边框。目前观感可接受，若觉得突兀可单独给图片容器保留浅底。
- 图表页（答案与得分率）用 canvas 绘制，不在 DOM 背景扫描范围内，需要单独看。
