# 科研時事自動翻譯失效 —— 診斷與修復

> 2026-10-31 ｜ 不改版號（純資料修正 + 基礎設施）

## 使用者回報

「時事這邊沒有成功自動翻譯。」

截圖裡 10-30 那 6 條全是英文標題，10-29 那 3 條卻是中文（標著「ScienceDaily（譯）」）。
也就是說：**自動抓取時的翻譯整批失敗了**，而先前手動跑的那批是成功的。

## 診斷：兩個獨立的原因疊在一起

### 原因一：Google 免費端點被限流（HTTP 429）

翻譯用的是 `translate.googleapis.com/translate_a/single?client=gtx`。
實測直接回 **429 Too Many Requests** —— 這個 `client=gtx` 已經被擋死了。

但換個 `client` 參數居然還能用：

| client | 結果 |
|---|---|
| `gtx` | ✗ 429 |
| `at` | ✓ 可用 |
| `dict-chrome-ex` | ✓ 可用 |
| `t` | ✗ 403 |

這說明**同一個 translate_a 介面下，不同 client 走的是不同後端**，
限流是按 client + IP 分別算的。這是修復的關鍵。

連發 4 條測試（`at` → 失敗就換 `dict-chrome-ex`），**4/4 成功且全是繁體**、質量也不錯：

```
Smaller EV batteries, longer range? Scientists may have found the trick
→ 電動車電池更小，續航里程更長？科學家可能已經找到竅門
```

### 原因二：補翻時拿不到完整原文（更隱蔽，也更嚴重）

只換端點不夠。第一次用新端點補翻，出來的結果是：

| 譯文 | 原文（實際存的） |
|---|---|
| 將二氧化碳轉化為**二氧化碳** | `AI reveals a hidden chemical shortcut that could turn CO2 in` |
| 可以**成就或破壞c**的隱藏因素 | `Scientists discover a hidden factor that can make or break c` |
| 中國科學家發現**巨型袋鼠菌**「D-rex」 | `Chinese scientists discover "D-rex," a giant fungus with ro` |

問題不在翻譯器，在**存進去的原文已經被截斷**：

```python
entry = {"t": title[:60], ...}      # 先把標題截到 60 字
if lang == "en":
    zh_t = translate(title)          # 首次抓取時用的是完整 title，沒問題
    if zh_t:
        entry["orig"] = entry["t"]   # ← 但 orig 存的是**截斷後**的版本！
```

首次抓取翻譯成功時沒人會發現（因為翻譯用的是完整 `title`）；
但翻譯失敗後要補翻，就只能拿 `orig`（截斷版）去翻 —— 於是
`...with ro` 被猜成「袋鼠」、`...break c` 被猜成「成就或破壞c」。

**修法**：`orig` 一律存完整原文（`origX` 存完整摘要），與翻譯成敗無關。
補翻時若發現 `orig` 疑似被截斷（長度 ≥58 且不以句末標點結尾），回原頁面用
`og:title` 取回完整標題再翻。

實測取回成功：

```
旧 : 'AI reveals a hidden chemical shortcut that could turn CO2 in'
新 : 'AI reveals a hidden chemical shortcut that could turn CO2 into fuel'
→ 人工智慧揭示了一種隱藏的化學捷徑，可以將二氧化碳轉化為燃料 ✓
```

## 修法總結

`scripts/fetch_news.py`：

1. **多端點 fallback**：`at` → `dict-chrome-ex` → `gtx` → MyMemory → 放棄保留英文。
   任一成功即止，每個失敗後小延遲。實測補翻 6 條時 `at` 被限流 12 次，
   全部由 `dict-chrome-ex` 接住 —— fallback 真的救回來了。
2. **`orig` 永遠存完整原文**（`orig` / `origX`），不再存截斷版。
3. **`refetch_title(url)`**：從原頁面 `og:title` 補回完整標題（給已存在的壞資料用）。
4. **`--retranslate` 模式**：把 `_news.json` 裡仍是英文的條目補翻。
   為什麼需要：翻譯失敗的條目已經寫進檔、不會再被抓一次，得有專門入口。
5. **繁中用字修正**：Google 的 zh-TW 常把「系」誤轉「係」——
   「根系」被寫成「根係」。加了 9 組實測會錯的對照逐條修正（「係數」本身正確，不動）。

`.github/workflows/daily-news.yml`：

在抓取之後加一步 `python scripts/fetch_news.py --retranslate`。
這樣即使某天抓取時翻譯全滅，同一次或下一次跑都會補上 —— 不會再默默爛一週沒人發現。

## 順帶解決：不改版號也不會看到舊內容

使用者指示「不改版本」，但這裡有個坑：SW 的快取鍵是 `shenzhine-<版號>`，
導航請求又是**快取優先 + 背景更新**（`return hit || fetching`）。
版號不動 → 快取名不變 → **第一次打開看到的還是舊新聞**，要再刷一次才新。
每日新聞尤其明顯：早上打開還是昨天的。

改法：`prep_ghpages.py` 把 SW 版本從 `SITE_VER` 改成 `SITE_VER-<資料指紋>`，
指紋 = 所有 `data/**/*.json` 的 md5 前 8 位。

```
SW_VERSION = 'V0.25.11-e9658268'     ← 快取鍵跟著資料走
畫面顯示    = 神智核 V0.25.11         ← 版號照使用者決定，不動
```

這樣把「代碼版本」和「資料版本」分開了：以後純資料更新（新聞、題庫）不必 bump 版號，
使用者下次打開也會直接拿到新內容。

## 驗證

- 9 條新聞全部中文，未翻譯 0 條
- 頁面實測（Playwright）：卡片顯示中文標題，無 JS 錯誤
- `verify_build.py` 13 項通過、`guard_data.py` 通過
- 部署包 SW_VERSION = `V0.25.11-e9658268`，畫面版本仍 `V0.25.11`

## 教訓

1. **免費翻譯端點會限流，而且按 client 分別限**。不要只寫一個 URL 就當作「翻譯做好了」，
   要有 fallback，而且**要有補翻入口** —— 失敗的資料已經寫進檔了，沒有補救機制就會一直爛著。
2. **存原文不要截斷**。截斷的原文拿去二次處理（補翻、檢索、比對）一定出錯，
   而且錯得很隱蔽（「巨型袋鼠菌」看起來像正常句子，不會有人懷疑）。
3. **改資料不 bump 版號時要注意快取**。SW 快取優先的話，使用者第一次看到的是舊內容。
   把快取鍵與資料指紋綁定是個通用解法。
