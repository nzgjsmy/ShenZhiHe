# 2026-10-28 · WorkBuddy AI

## V0.18.18：外部补丁方案核实后择优（采用 4 / 驳回 5）

### 起因

用户转来一份 txt（微信里另一个 AI 生成的），标题是「針對 9 大需求設計的精準修改與新增模組」，
里面直接给了可以复制替换的函数代码。用户说「根据文件里面的内容，优化神智核」。

**第一反应不该是照着改。** 先逐条核对真实代码，结果有一半是错的。

### 逐条核对结果

| 文档主张 | 核实结论 |
|---|---|
| 加 CSP `default-src 'self' 'unsafe-inline' 'unsafe-eval'` | ❌ 允许 inline+eval 的 CSP 等于没有防护；且 `worker-src` 回退到 default-src，虽然含 blob: 但仍可能干扰离线缓存。收益≈0，风险>0 |
| 删除 nav 里的「知識圖譜」按钮 | ❌ `viewGraph()` 是完整可用功能（`#/graph`、首页快捷入口、图例都在）。用户从未要求删 |
| 停用虚拟滚动 | ✅ **前提成立**（确实有 `virt*` 模式，`VIRT_THRESHOLD=50`），但实现方式应该是一行阈值，不是整段替换 `viewTopic` |
| 改写 `topicCardHTML` 去掉描述 | ⚠️ 方向对，但「整段替换」会丢掉 tag/徽章样式；改成 CSS 2 行 clamp 更安全 |
| `viewPastPaper` 换成 MC/LQ 双分页 | ❌ 提议的 `renderMCCards` 用 `allMC.slice(0,25)`，**374 题变 25 题**，且丢掉话题筛选、错题本联动、懒加载 |
| 内置 2 道示范 LQ 题目 | ❌ 「2024 Q7」「2023 Q4」的题干、答案、得分率全是编的。学习站放虚构考题会误导学生 |
| 「總結重點」按钮跳第一章 | ❌ 名不副实（第一章不是总结） |
| iOS 弹性曲线 + 加载屏 | ✅ 有价值，但要重写：品牌名应是「神智核」而非「HKDSE 生物科」（本站是四科） |

### 一个关键发现：文档里用了不存在的 CSS 变量

提议代码里写 `background:var(--paper-mute)`，但当时的 `:root` 里**没有** `--paper-mute`。
说明写文档的 AI 没读过源码，是靠猜的。

（巧合的是 DSH 当天晚些时候加深色模式时**正好**引入了 `--paper-mute`。）

### 实际改了什么

1. **启动加载屏**（`#boot`）
   - 品牌名用 `/*__SITE_NAME__*/` 占位符，四科通用
   - `--ease-ios` 弹性淡出，尊重 `prefers-reduced-motion`
   - 首屏渲染完成后**双 rAF** 再淡出，避免「闪一下空白」
   - **4 秒保险丝**：在主脚本之前注册，主程序抛错也不会卡在「正在載入」
2. **停用虚拟滚动**：`VIRT_THRESHOLD` 50 → 100000
   - 全站 86 个课题只有 6 个超过 50，最多 `chem/2a` 88 个知识点，直出毫无压力
   - 换来 Ctrl+F 能搜到、能跨卡片选文字
   - `virt*` 代码全部保留，改回 50 就恢复
3. **卡片描述**：`min-height:44px` → `-webkit-line-clamp:2`，颜色改用 `var(--text-soft)` 与深色模式统一
4. **`--ease-ios`** 变量，套用到 `.tcard` 过场

### 并发事故（这次真踩了）

改 `template.html` 期间，DSH 往 `source` 推了 419 行深色模式代码（`cf5b5ec`，作者 DavisYung）。

我**先部署了不含它改动的版本**（`push -f` 到 main），然后才发现 `git push origin source` 被拒。
也就是说线上有几分钟是「有我的改动、没 DSH 的深色模式」。

补救：`git rebase origin/source` → `:root` 冲突（DSH 加语义色变量、我加 `--ease-ios`，两边都保留）
→ 重建 → 复测 → 重新部署。线上现在两者都有。

**教训写进 §4.10**：部署前必须 `git fetch` + `git log origin/source`。

### 验证方式：真的开了浏览器

仓库里有 CDP 测试脚本（连 9333 端口）。这次自己搭了一套：

```
python -m http.server 8791  (在 site/)
chrome --headless=new --remote-debugging-port=9333
node t_merge.cjs  → 8/8 通过
```

测的是：深色/浅色两套主题下加载屏的底色与淡出、`chem/2a` 是否真的直出 88 点、
描述实测高度（h=47 < sh=71，clamp=2）、真题页 28 个话题、设置页外观开关、零未捕获异常。

**关键点**：只 `grep` 到 `id="boot"` 存在是不够的，必须确认它会**消失**——
否则用户就永远卡在加载屏上了。所以专门测了 `classList.contains('done')` 和 `opacity=0`。

### 线上终态

```
HTTP 200 · 3,895,792 bytes（本地 3,900,743，差值是 git 换行符归一化）
id="boot" ×1 · data-theme ×209 · VIRT_THRESHOLD = 100000 · SW_VERSION = V0.18.18
```

---

## V0.18.19：主题开关挡住导航 + 补齐「跟随系统」

### 用户反馈

截图显示 header 右上角的深浅色开关压在 nav 最后一项「額外資訊」上。用户建议放进设置页。

### 根因（是布局算错，不是运气不好）

```css
.hwrap{ padding:10px 60px 10px 20px; }   /* 右侧只留 60px */
.gearbtn{ position:absolute; right:12px; width:38px; }   /* 占 50px */
.themetoggle{ position:absolute; right:58px; width:52px; } /* 从 58px 往左吃掉 52px */
```

齿轮占 12+38=50px，剩 10px；开关从 58px 开始往左延伸，直接盖在 nav 上。
**两个 absolute 元素在同一角落，却只有一个被 padding 预留了空间。**

### 改法

直接删掉顶部那颗。理由：设置页本来就有「白天／黑夜／跟随系统」三颗按钮，
顶部那颗是重复入口，删掉不损失功能。

CSS 没删，改成一段注释说明为什么移除、以及怎么恢复（`.hwrap padding-right ≥ 118px`）。
删掉 50 行别人的代码风险大于收益，留注释更负责任。

### 「跟随系统」其实早就写了，但看不出来

DSH 实现了 `followSystemTheme()` 和 `matchMedia` 监听，可是：
- 三颗按钮没有任何选中态，用户不知道当前是哪个模式
- 系统切换时页面确实变了，但界面没有任何说明

补了：
- `curThemeMode()`：localStorage 有 light/dark → 手动模式；没有 → auto
- `syncThemeBtns()`：同步按钮高亮 + 一行说明
- `matchMedia` 的 handler 里也调用它，系统一变说明文字就跟着变

### 验证手段：CDP 模拟系统配色

`Emulation.setEmulatedMedia({features:[{name:'prefers-color-scheme',value:'dark'}]})`
可以真的模拟「系统切到深色」，然后检查 `data-theme` 有没有跟着变。

测了完整闭环：跟随（dark↔light 双向）→ 手动固定 → 系统再变不跟随 → 点跟随系统清空选择并立刻套用。
16 项全过。

### 遗留观察

系统**没有**偏好（`prefers-color-scheme` 两者都不匹配）时，默认取 dark。
这是 DSH 的原始选择，本次未改。如果觉得默认该是浅色，改 `followSystemTheme()` 里的兜底即可。
