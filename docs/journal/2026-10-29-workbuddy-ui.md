# 2026-10-29 · WorkBuddy AI · 移动端顶栏收敛

## 起因

用户拿来朋友给的 idea（一份 UI/UX prompt 文档），问能不能实现。

## 先核对，不照抄

按项目铁律「不照抄外部 AI 给的补丁方案而不核对真实代码」，先逐条 grep 核对。

### 第一段（11 项技术规范）：**全部已实现**

| 规范 | 证据 |
|---|---|
| 语义化变量 | `--bg:#faf7f2` `--paper:#fff` `--accent:#0f766e` |
| `--on-accent` | 12 处 |
| `--ease-ios` | 24 处 |
| `--anim-k` 三档 | 37 处 + `data-anim="simple"/"off"` |
| `.ppans` grid-template-rows | 13 处 |
| `color-mix()` | 13 处 |
| `safe-area-inset` | 已用 |
| `-webkit-tap-highlight` / `touch-action` | 3–4 处 |
| `.tcard` 整卡可点 | `cursor:pointer` + `:active scale(.985)` |

→ 这段其实是**本项目现有设计系统的总结**，不是新需求。

### 第二段（5 个维度）：4/5 已实现

1. 卡片分层 —— 已做（标题→简介→数据）
2. **顶栏收敛 —— 真问题** ← 唯一值得做的
3. 低对比护眼背景 —— 已实现（`--bg:#faf7f2` 暖白 + 卡片纯白）
4. 数据模块化 —— 已做（进度条 + 图标文字）
5. 整卡可点击 —— 已实现

## 实测问题

390×844 下顶栏占 **约 400px（5 行）**，内容要滑半屏才看到：

```
logo 神智核 V0.24.1        ⚙
[搜索框]
科目 首頁 關聯地圖 測驗
複習 錯題本 額外資訊
科目 [化學][物理][生物]
     [數學][全部科目]
```

## 改法

只改 `site/template.html` 的 `@media (max-width:860px)` 块，桌面端零改动：

1. `.hwrap` 改 `flex-wrap:nowrap` → 品牌 + 搜索框 + 齿轮一行
2. `.brand .verbadge` 隐藏（窄屏省宽度给搜索框）
3. `.subbar` 改单行横向滚动
4. `nav#nav` → `position:fixed` 底部 Tab Bar，`grid-template-columns:repeat(7,1fr)`
5. `main`/`footer` 加 padding-bottom 让出 Tab Bar 高度
6. 既有浮层（`.pickbar` / `#pwaupd` / `#pwahint` / `.memwarn`）上移避让

## 踩坑：`backdrop-filter` 会破坏子元素 `position:fixed`

第一版写完，`nav` 的 `position:fixed` **没生效**，卡在 `y=42`（header 底部）而不是视窗底部。

根因：`header{backdrop-filter:blur(8px)}`。`backdrop-filter`（以及 `filter`/`transform`/`perspective`/`will-change`）会**创建包含块**，
让后代的 `position:fixed` 相对该祖先定位而非视口。

解法：移动端 `header{-webkit-backdrop-filter:none;backdrop-filter:none;background:var(--bg)}`
（顺带省掉 iOS 上 backdrop-filter 的合成开销）。

## 另一个假警报：Playwright 全页截图的重影

改完后全页截图出现淡淡重影（「神智核 V0.24.1」「連續學習天數」重复出现）。
排查过：`.stat` 背景不透明、无 text-shadow、无重复 DOM、boot 已 `visibility:hidden`。

结论：**Playwright 全页截图的合成残留**。证据：
- 带 `clip` 参数的截图三张 md5 完全相同且干净
- Chrome CLI `--headless=new` 截图完全无重影
- 滚动后截图无重影

→ 不是真实 CSS 问题，不处理。

## 验证

```
build.py            → 4,436,654 bytes / V0.24.1
verify_build.py     → 11 项全绿
移动端 scrollW=clientW=390   → 无横向溢出
移动端 header=96px / nav y=791 / 7 项 / 1 高亮
桌面端 header=103px / nav y=14  → 完全未变
```

## 未做

- **未 bump 版本号**（用户要求「等我说要部署的时候再部署」，bump 与部署应同批）
- 未改桌面端
- 卡片底部标签数不一致（第 1、4 条的微调）未做——优先级低于顶栏，留待确认

---

## 23:15 追加：全局统一 `--ease-ios`

用户要求「所有互动过渡必须预设套用 `--ease-ios`」。

### 先查现状

| 项 | 数量 |
|---|---|
| `transition` 总数 | 39 |
| 已用 `--ease-ios` | 26 |
| 显式写 `ease` | 14（集中在 4 行：3 个进度条 + 1 个开关） |
| **隐性默认 `ease`**（简写里没写缓动） | **23** |

隐性那批是关键：`transition:opacity var(--dur-base)` 这种简写会把
`transition-timing-function` 重置成浏览器默认 `ease`，**不写就等于用了 ease**。

### 做法

1. 4 行显式 `ease` → `var(--ease-ios)`（3 个进度条 + 主题开关）
2. 加一条全局兜底：

```css
*,*::before,*::after{transition-timing-function:var(--ease-ios)!important}
```

**为什么必须 `!important`**：`*` 的优先级是 (0,0,0)，压不过任何类选择器里的
`transition` 简写；不加强制就只能管到没写 transition 的元素，等于没用。

**为什么不破坏降级**：`html[data-anim="off"] *` 是靠
`transition-duration:0s!important` 归零的，与 timing-function 无关；
时长为 0 时缓动曲线无意义。实测三档：

```
默认    → 0.18s  cubic-bezier(0.32,0.72,0,1)
simple  → 0.18s  cubic-bezier(0.32,0.72,0,1)
off     → 0s     cubic-bezier(0.32,0.72,0,1)   ← 时长归零，正常
```

### 验证

Playwright 实测 5 个代表元素（`.tcard` / `nav button` / `.gearbtn` /
`.subbar button` / `.pbar i`）的 `transitionTimingFunction` 全部为
`cubic-bezier(0.32, 0.72, 0, 1)`，5/5 一致；verify 11 项全绿。

---

## 23:30 追加：卡片数据模块化（第 4、5 条）

### 第 4 条前半：发现真问题——数据重复两遍

用 Playwright 提取真实卡片结构，发现每张卡片的同一份数据出现两次：

```
pmeta:  掌握度 0%  |  38 知識點 · 49 題
foot:   [10 章] [38 知識點]  |  📝 49 題     ← 知識點、題数重复
```

**12 张卡片全部如此**，而且 `foot` 左边是 pill、右边是裸文字，格式不统一。

改法（`site/template.html` 两处生成代码 + 1 条 CSS）：

```js
// 课题卡
<div class="pmeta"><span>掌握度 ${mp}%</span></div>
<div class="foot"><span class="pill">📖 ${章} 章</span>
  <span class="pill">🎯 ${pts} 知識點</span>
  <span class="pill">📝 ${nq} 題</span></div>

// 单元卡（多一项课题数）
<div class="foot"><span class="pill">📚 ${ts.length} 課題</span>
  <span class="pill">📖 ${nSec} 章</span>
  <span class="pill">🎯 ${nPts} 知識點</span>
  <span class="pill">📝 ${nQ} 題</span></div>
```

```css
.foot{display:flex;justify-content:flex-start;align-items:center;
      gap:6px;flex-wrap:wrap;...}
.foot .pill{margin-right:0}
```

去掉了单元卡右下角的「進入 →」——整卡本来就可点（`onclick` 在 `.tcard` 上），
那个按钮只是冗余暗示，反而让用户以为只有它能点。

### 第 4 条后半：WCAG 对比度实测

浅色（卡片底 `#fff`）：

| 元素 | 颜色 | 对比度 |
|---|---|---|
| 标题 h3 | `rgb(43,42,38)` | **14.36** |
| 简介 .desc | `rgb(87,83,74)` | 7.66 |
| 文件名 .meta | `rgb(122,117,106)` | 4.59 |
| 掌握度 .pmeta | 同上 | 4.59 |
| pill | `rgb(15,118,110)` | 5.47 |

深色（卡片底 `rgb(28,30,37)`）全部 6.09–13.23。

→ 全部 ≥ 4.5（WCAG AA），且**层级清晰**：标题 14.36 > 简介 7.66 > 次要 4.59。
「次要資訊明顯弱於主標題、但對比度仍達標」這條本來就滿足。

### 第 5 条：本来就已经实现，实测确认

| 检查 | 结果 |
|---|---|
| `cursor` | `pointer` |
| hover | `transform: matrix(1,0,0,1,0,-3)` = `translateY(-3px)` |
| **点描述区（非按钮）** | 跳到 `#/chem/t/1a` ✅ |

所以文档说的「僅依賴右下角的文字按鈕」并不成立——整卡早就是单一可点击区域。
只顺手删掉了冗余的「進入 →」。

### 验证

`build + verify` 11 项全绿；卡片截图确认三个 pill 同一行、对齐一致、无重复。

---

## 23:50 追加：分页切换转场（iOS 手感）

用户要「各分页切换过程像 iOS 一样流畅」。

### 方案：View Transitions API

现状是 `.view{animation:none}`——切换**完全没有动画**，直接瞬切。

用浏览器原生 View Transitions：`document.startViewTransition(() => route())`。
浏览器自动快照新旧页并做交叉动画，**`route()` 完全不用改**，也不需要自己保留旧 DOM。

```js
window.addEventListener('hashchange', function(){
  var off = document.documentElement.getAttribute('data-anim')==='off'
         || matchMedia('(prefers-reduced-motion:reduce)').matches;
  if (document.startViewTransition && !off) {
    try { document.startViewTransition(function(){route();}); return; } catch(e){}
  }
  route();
});
```

```css
::view-transition-old(root){animation:vt-out .32s var(--ease-ios) both}
::view-transition-new(root){animation:vt-in  .32s var(--ease-ios) both}
@keyframes vt-out{to{opacity:0;transform:translateY(-26px) scale(.955)}}
@keyframes vt-in{from{opacity:0;transform:translateY(26px) scale(.955)}}
```

### 踩了三个坑

**坑 1：`::view-transition-group(root)` 是浏览器内置动画，默认 250ms。**
不把它拉齐到 320ms，320ms 的进出场会被提前截断（实测组动画 0.25s）。
→ `::view-transition-group(root){animation-duration:.32s;animation-timing-function:var(--ease-ios)}`

**坑 2：导航栏跟着内容一起淡入淡出，中间帧文字叠成两层重影。**
iOS 的做法是导航常驻、只有内容区转场。
→ 给顶栏和底部 Tab Bar 独立命名，从 root 快照里「挖掉」：

```css
header{view-transition-name:appheader}
nav#nav{view-transition-name:apptabbar}
::view-transition-old(appheader),::view-transition-new(appheader),
::view-transition-old(apptabbar),::view-transition-new(apptabbar){animation:none}
```

**坑 3：位移只有 12px，新旧页几乎完全重叠，内容区仍有重影。**
交叉淡入时，位置相同、内容相似的块（如统计卡片）会叠在一起。
→ 位移加大到 26px + `scale(.955)`，让新旧页有明确的空间层次（旧页缩小后退、新页升起）。
这也更接近 iOS 的层级切换手感。

### 一个容易误判的点

`document.getAnimations()` 里 `vt-in`/`vt-out` 的 `effect.getTiming().easing` 显示 `linear`，
一度以为 `var(--ease-ios)` 没生效。实际上这是**规范行为**：CSS animation 的
timing-function 作用在 keyframe 层，effect 级默认就是 `linear`。
用 `getComputedStyle(document.documentElement,'::view-transition-old(root)')`
读到的 `animationTimingFunction` 才是真实值 —— 实测确为 `cubic-bezier(0.32,0.72,0,1)`。

### 验证

| 检查 | 结果 |
|---|---|
| `startViewTransition` 可用 | function |
| 切页触发次数 | 每次 1 次（连切两次 = 2） |
| 三个伪元素 duration/ease | 全部 `0.32s / cubic-bezier(.32,.72,0,1)` |
| `data-anim=off` | **VT 触发 0 次**（直接跳转） |
| `data-anim=simple` | VT 触发 1 次，位移归零只淡入淡出 |
| 移动端 tabbar | `view-transition-name=apptabbar` 生效 |
| 切页后内容 | 正常渲染，hash 正确 |



