# 原卷處理工具箱（scripts/pastpaper/）

處理 DSE 歷屆試卷（掃描版 PDF）的一套小工具。原本是為了解決生物卷一 MC 題庫的
「題幹殘缺 / 配圖錯位 / 明明能辨認卻貼了原圖」這幾類問題而寫的。

> 試卷 PDF 本身**不入庫**（版權）。腳本裡的 `SRC` 指向本機目錄 `D:/生物DSE Past Paper/`，
> 換機器時改這個常數即可。

## 前置

```bash
python -m pip install pymupdf rapidocr-onnxruntime opencv-python pillow
```

RapidOCR 首次執行會下載約 15 MB 模型。CPU 上約 2.5 秒／頁（200 dpi A4）。

## 五個步驟

### 1. `pp_build.py` — 把 PDF 拆成頁圖 + OCR

```bash
python scripts/pastpaper/pp_build.py            # 全部年份
python scripts/pastpaper/pp_build.py 2016       # 只做某一年
```

- 輸出 `scratch/_pp_pages/<年份>/p001.jpg …`（200 dpi，約 1.2 MB/頁）
- 輸出 `scratch/_pp_pages/<年份>/ocr.json`：每頁每個文字塊的 `x/y/x2/y2/txt`

已存在的年份會自動跳過（可中斷後續跑）。

### 2. `pp_locate.py` — 定位每道題的題號

```bash
python scripts/pastpaper/pp_locate.py 2016
```

輸出 `q1 p02 y=280 …` 這樣的清單，末尾會報告「缺哪幾個題號」。
**注意**：2018 與 2020 兩年的題號 OCR 漏讀較多（題號被識別成別的符號），
這兩年若缺號，直接用 `pp_find.py` 按關鍵詞找。

### 3. `pp_find.py` — 按關鍵詞找位置

```bash
python scripts/pastpaper/pp_find.py 2018 混凝土 牙齒
```

輸出頁碼與 y 座標。**遇到題號定位失敗時，這是最快的定位方式。**

### 4. `pp_crop.py` / `pp_recut.py` — 裁圖

```bash
# 按座標裁一段（讀圖用）
python scripts/pastpaper/pp_crop.py 2016 4 1270-2324 out.png --scale=0.95

# 按題號自動定界（題號 → 下一題號）
python scripts/pastpaper/pp_crop.py 2016 4 q11 out.png

# 裁「配圖」並自動收緊到墨跡邊界，輸出 webp（正式入庫用）
python scripts/pastpaper/pp_recut.py --one 2016 4 1300,1850 site/img/pp/2016/f11.webp
```

`pp_recut.py` 的關鍵是**自動墨跡包絡**：給一個「大致包含目標」的 y 範圍，
它會自己找到真正的圖形邊界並留 14 px 白邊，所以不必目測得很準。
`--one` 之後的參數順序是 `<年份> <頁> <y1> <y2> <輸出檔>`，
必要時可加 `x1=... x2=...` 限制橫向（腳本內用 `one(..., x1=, x2=)` 呼叫）。

### 5. `pp_sheet.py` — 拼圖目檢

```bash
python scripts/pastpaper/pp_sheet.py out.png 620 site/img/pp/2016/*.webp
```

把多張圖拼成一張帶檔名標注的網格，一次看十幾張，用來快速找出「被切壞」的配圖。

## 血的教訓（別重踩）

| 坑 | 說明 |
|---|---|
| 目測 y 座標一定不準 | 先把整頁縮成 0.7 倍看一眼版面，再用 `ocr.json` 的實際 y 值裁，不要靠眼睛換算比例 |
| 圖內文字會騙過「找空隙」演算法 | 曲線圖的 **y 軸標題是豎排文字**，OCR 會把整條當成一個高 500px 的文字塊；判斷「正文行」時要把 `高>140 且 寬<110` 的塊排除 |
| 圖常在題號**之前** | DSE 的「指引 → 圖 → 題號」順序很常見，按題號定界會漏掉圖；要從上一題的正文塊之後開始算 |
| 選項是圖時，前端會丟掉選項文字 | 本站 `ppCard()` 在 `qImg`/`optImg` 存在時只渲染 A/B/C/D 四個字母按鈕，所以配了圖就不要指望文字選項 |
| 原卷可能是英文版 | 2022 的卷一 PDF 是中文版，但舊資料裡有英文截圖；凡是从舊圖讀到的文字，一律回原卷核對 |
| 有些圖救不回來 | 掃描時就已糊掉的（如 2018 Q5 的錐體圖）在 420 dpi 下仍是一團黑，這種只能標注「對照紙本原卷」，不要憑想像寫題解 |

## 一次完整的返工流程（2026-10-29 實際用過）

```bash
python scripts/pastpaper/pp_build.py          # 1. 全部年份渲染 + OCR（約 15 分鐘）
python scripts/pastpaper/pp_locate.py 2012    # 2. 確認題號齊全
python scripts/pastpaper/pp_find.py 2012 蒸騰  # 3. 定位要處理的題
python scripts/pastpaper/pp_crop.py 2012 4 q11 check.png   # 4. 讀圖核對
python scripts/pastpaper/pp_recut.py --one 2012 4 1100,1830 site/img/pp/2012/f11.webp
python scripts/pastpaper/pp_sheet.py sheet.png 620 site/img/pp/2012/*.webp  # 5. 目檢
```

改完資料後照 `AGENTS.md` 的流程建構與校驗。
