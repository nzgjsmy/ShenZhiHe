# 手账全套落地（2026-10-30）

> 参与者：WorkBuddy ｜ 设计源：`scratch/_proto/handbook_pc.html`

## 起点

用户先给了 `handbook_pc.html` 原型，说「想做成这个效果」，随后要求「直接全改吧，就以那个原型为基础改就行了」。

改造前先犯了个理解错误：用户说「那个倾斜每次刷新之后的度数都不一样」，我读成抱怨（以为要固定），于是把 `Math.random()` 换成 `nth-child` 固定角度。用户立刻纠正：「不是啦，我的意思就是想能够随机倾斜啦」。**教训：用户描述现象时，先确认它是抱怨还是需求，别自作聪明。**

## 原型拆解

原型是一张「摊在深色桌上的方格纸」，要素：

| 要素 | 原型实现 |
|---|---|
| 桌面 | 深色 + 两圈径向光晕（台灯感）+ 噪点层 |
| 纸张 | 暖白 + 双向 24px 方格线 + 投影 + 右下角卷边 |
| 胶带 | 三处：左上斜贴 −38°、右上斜贴 +41°、顶部中间 −1.5°，边缘用 mask 做毛边 |
| 页头 | 10px 大写日期 → 46px 衬线标题 → 手写小字，底部虚线 |
| 便利贴 | 黄/粉两色，各带图钉，旋转 ±1° |
| 卡片 | 白纸 + 顶部胶带 + 两层柔和投影 + 轻微倾斜，hover 回正 |
| 书签 | 纸缘右侧伸出 26px 竖排，选中变深青 |
| 底部 | 左「手记」正文（荧光笔标记）+ 右「今日待办」（勾选框） |

## 落地做法

### 结构：不复刻 DOM，改造成既有元素

原型是静态 HTML，神智核有真实路由和数据绑定。原则是**保留 DOM 结构与 `data-r` 属性**，只换外观——这样 `navOn()` 高亮、点击跳转、localStorage 全部零风险。

导航就是上一轮把 `nav#nav` 从横条改成纸缘书签，这次没再动。

### 配色：一套 `--hn-*` 语义变量

```css
:root{
  --hn-paper:#fffdf4;   --hn-note-y:#f8f0dd;  --hn-note-p:#e8f2ef;
  --hn-edge:#d8cfb9;    --hn-tape:rgba(226,206,150,.62);
  --hn-red:#c25b3f;     --hn-hand:#b08a5a;    --hn-muted:#8a9aa8;
  --hn-accent:#3d6b62;  --hn-title:#2f2a22;   --hn-track:#e6dfcb;
}
html[data-theme="dark"]{ /* 整套反向覆盖 */ }
```

必须走变量而不是硬编码，否则深色模式一定会漏——这个坑项目里踩过 18 次。

### 改造范围

| 页面 | 改动 |
|---|---|
| 站点首页（三科选择） | 深绿大卡 → 纸面页头；`.subcard` → 手账卡（胶带 + 倾斜） |
| 科目首页 | 页头纸面化；`.dash` → 黄便利贴；`.dse-duo` → 青/黄便利贴；`.tcard` → 手账卡；新增底部两栏 |
| 单元页 | 复用 `.tcard`，自动继承 |
| 答题页 / 真题页 / LQ 页 | **不动** —— 阅读与作答优先 |

## 倾斜：随机，但分三层幅度

```js
var R=function(a){return ((Math.random()*2-1)*a).toFixed(2)+'deg';};
// 手机端先否掉（见下文坑③）
document.querySelectorAll('#app .tcard').forEach(c => c.style.setProperty('--tilt', R(2.2)));
document.querySelectorAll('#app .subcard').forEach(c => c.style.setProperty('--tilt', R(2.0)));
document.querySelectorAll('#app .dash').forEach(c => c.style.setProperty('--tilt', R(1.1)));
document.querySelectorAll('#app .dse-duo .dse-hero').forEach(c => c.style.setProperty('--tilt', R(1.4)));
```

**为什么幅度不一样**：大卡片歪一点有「手贴上去」的随机感；但便利贴和页头是阅读入口，歪过头会晕。递减幅度是折中。

调用点四处：`viewSubjects` / `viewHome` / `viewUnit`。每处渲染完立刻调一次——包括刷新和切页，所以「每次刷新度数都不一样」是稳的。

## 三个坑

### ① 白字写在了米黄纸上

`.hn-hand` / `.hn-date` 原本是给**深绿 hero** 写的：

```css
.hn-hand{color:rgba(255,255,255,.82)}
.hn-date{color:rgba(255,255,255,.72)}
```

页头改成纸面后，这两个类名被继续复用 → 白字写在 #fbf9f2 的纸上，肉眼几乎看不见。截图时才发现手写小字整行消失。

**教训**：改底色时必须把所有「白色文字」的旧规则翻一遍。这类 bug 不会报错、CI 也查不出来，只有肉眼能发现。

### ② 深色下幽灵按钮隐形

为了修「深色主题 --hn-accent 是亮青、白字对比不足」，我写了：

```css
html[data-theme="dark"] .hn-btn{color:#0d1a18}
```

结果 `.hn-btn.ghost` 是**透明底**，也被染成近黑色 → 深底黑字，等同隐形。

修复用 `:not(.ghost)` 限定实心按钮，幽灵按钮单独给 `--text-soft`：

```css
html[data-theme="dark"] .hn-btn:not(.ghost){color:#0d1a18}
html[data-theme="dark"] .hn-btn.ghost{color:var(--text-soft);border-color:var(--hn-edge)}
```

`html[data-theme="dark"] .hn-btn`（0,2,1）特异性高于 `.hn-btn.ghost`（0,2,0），所以后者被无声覆盖——**看起来「样式写了却不生效」时，先算特异性**。

### ③ CSS 压不住内联样式

手机端不想倾斜，CSS 里写了：

```css
@media (max-width:860px){ .tcard:nth-child(n){--tilt:0deg} }
```

实测无效，手机上卡片仍然歪（`-0.67deg / 0.64deg / 1.73deg / 2.06deg`）。

原因：`tiltCards()` 用的是 `element.style.setProperty()`，那是**内联样式**，优先级高于任何选择器。必须在 JS 里就否掉：

```js
if(window.matchMedia('(max-width:860px)').matches){
  document.querySelectorAll('#app .tcard,#app .dash,#app .dse-duo .dse-hero')
    .forEach(c => c.style.removeProperty('--tilt'));
  return;
}
```

## 另一处顺手修的：描述文本切不干净

手记区要显示「科目描述首句」，先写成 `split(/[。；]/)[0]`。但生物科的描述是：

> 細胞與生命基礎、人體營養與運輸、植物營養與運輸、生殖生長與發育、…

**整串用顿号连接，一个句号都没有**，切完之后还是把 10 个分区全列出来。改成按字数截断：

```js
const _desc=((SUB.description||'').split(/[。；]/)[0]||'').trim();
const shortDesc=_desc.length>46?_desc.slice(0,46)+'…':_desc;
```

## 验证

| 项目 | 结果 |
|---|---|
| `build.py` | 通过 |
| `verify_build.py` | 13/13 |
| `guard_data.py` | 0 道题改动 |
| 桌面浅色 1440 | 目视通过 |
| 桌面深色 1440 | 目视通过（修完 ghost 按钮） |
| 移动 390 | 目视通过，`overflowX=0`，`transform` 为单位矩阵 |
| JS 异常 | 0 |

## 状态

**未 bump 版本号、未部署**——用户要求先本地看效果。

若确认要上线：bump `site/version.json` → build → verify → 六步部署（清图目录再拷，别用 `cp -rn`）。

## 遗留

- 顶部栏（品牌 + 搜索框 + 科目 chips）仍是 SaaS 风胶囊。原型没有这两个元素（它是单科目笔记），但神智核需要跨科搜索，所以保留了。要更贴原型，可以把搜索折叠成图标按钮。
- 答题页、真题页、LQ 页保持原样。要不要也套手账外壳，等用户看完首页效果再定。
