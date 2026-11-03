# 2026-11-03 · AMD 显卡跑本地 OCR（方案 B 实测）

## 起因

用户问「VLM 在 CPU 的占用还是低了，能不能提上去」。查下来：

- `PaddleOCRVL()` **没有线程数参数**，单页是自回归解码，天然单线程
- worker 3 → 5 实测每页耗时 **300 秒 → 480 秒**，总吞吐不升反降
- 瓶颈在内存带宽，不在核心数。3 个 worker 是甜点

用户随后问「用 AMD 显卡做 OCR 有什么工具」，决定试 **方案 B：Ollama + Qwen-VL**。

## 环境

```
GPU    AMD Radeon RX 6600 XT · 8GB 显存（7.2GB 可用）
CPU    20 核
OS     Windows 11 (10.0.26200)
```

## 安装：踩了三个坑

### 坑 1：winget 安装卡死

`winget install Ollama.Ollama` 跑了 7 分半，下载缓存 0 字节，直接杀掉。

### 坑 2：Inno Setup 安装程序 `MoveFile failed; code 5`

改用直接下载 `OllamaSetup.exe`（1.56GB，15 秒下完），`/VERYSILENT` 安装，退出码 5。
带 `/LOG` 重跑，日志显示：

```
Dest filename: ...\lib\ollama\cuda_v12\msvcp140.dll
MoveFile: The existing file appears to be in use (5). Retrying.   ← 重试 4 次
Defaulting to Abort for suppressed message box
User canceled the installation process.  → Rolling back
```

卡在 **CUDA 目录下的 `msvcp140.dll`**（VC++ 运行时，系统里大量进程加载了同名模块）。
非管理员，无法给 Defender 加排除项，绕不过。

### 坑 3：innoextract 版本太旧

试 `innoextract 1.9` 解包，报 `Could not determine setup data version`
—— 它只支持到 Inno Setup 6.0.5，而这个包是 **6.7.1**。

### 解法：用官方 zip 免安装版

GitHub release 里有 zip：

```
ollama-windows-amd64.zip        1.6GB   主程序
ollama-windows-amd64-rocm.zip   246MB   ROCm 增量包（解压到同一目录）
```

解压到 `D:\ollama-app`，直接 `ollama.exe serve` 就能跑，**完全不需要安装**。

```
D:\ollama-app\          3.1GB   主程序 + ROCm 7.1 库（85 个 dll）
D:\ollama-models\       3.2GB   只保留 qwen3-vl:4b（OLLAMA_MODELS 指到这里，不占 C 盘）
```

> 实测完四个模型后，用户决定只留 `qwen3-vl:4b`，其余三个已 `ollama rm` 删除
> （模型目录 18GB → 3.2GB，释放 14.8GB）。想复现对比随时可重新 `ollama pull`。

## GPU 识别：ROCm 不可用，但 Vulkan 可以

启动日志里两条关键信息：

```
WARN  AMD driver is too old. Update your AMD driver to enable GPU inference.
INFO  inference compute  library=Vulkan  name=Vulkan0
      description="AMD Radeon RX 6600 XT"  total="8.0 GiB"  available="7.2 GiB"
```

**ROCm 路径被驱动版本卡住，但 Ollama 自动走了 Vulkan 后端**，显卡正常工作。

模型加载确认：

```
load_tensors: offloaded 29/29 layers to GPU
load_tensors: Vulkan0 model buffer size = 4168.09 MiB
clip_ctx: CLIP using Vulkan0 backend          ← 视觉编码器也在 GPU
```

## 四个模型实测（同一页 2019 p023：911 字 + 2 个表格）

| 模型 | 每页耗时 | 表格 | 分值 | 重复 | 幻觉 | 结论 |
|---|---|---|---|---|---|---|
| **PaddleOCR-VL**（CPU 基准） | ~300 秒 | HTML+rowspan | ✓ | 无 | 无 | 质量最好 |
| qwen3-vl:8b | 329 秒 | 6 行全对 | ✓ | 已修 | 无 | 显存不够，部分跑 CPU |
| **qwen3-vl:4b** | **139 秒** | 6 行全对 | ✓ | 已修 | 无 | **最佳平衡点** |
| qwen2.5vl:7b | 127 秒 | 缺 1 行 | ✓ | 有 | 轻微 | 字间空格多 |
| qwen2.5vl:3b | 59 秒 | 行错位 | ✗ | 有 | **严重** | 不可用 |

### qwen2.5vl:3b 的幻觉最危险

原卷那两栏是**空白答题格**，模型写出了：

> 「通過多次試驗和數據分析，我們確認了這種方法的有效性」
> 「我們使用量子計算模型進行仿真研究，展示了它對大規模系統問題解決的重要性」

**编造答案提示，比漏字危险得多** —— 学生会以为那是题目要求。

### qwen3-vl 系列的质量明显更高

同样那页，qwen3-vl:8b 和 4b 都把表格 6 行全部识别出来（PaddleOCR-VL 用 rowspan 合并，
纯文本里反而看不出对应关系），`(1分)(2分)` 也都对。

## 五个参数坑

### 1. `repeat_penalty` 不能设 1.25

表格里大量重复的 `|`、`-` 会被惩罚掉，模型直接输出空白：

```
repeat_penalty=1.00 → 146 字（但陷入重复循环）
repeat_penalty=1.10 → 0 字   done_reason=length
repeat_penalty=1.25 → 0 字   done_reason=length
```

**最终用 1.05**。

### 2. Qwen3-VL 的 thinking 关不掉

传 `"think": false` 无效，响应里仍有 `thinking` 字段（实测 944 字）。
`num_predict=2048` 会被思考过程吃光，答案一个字都出不来（`done_reason=length`）。

**必须给 8192**。

### 3. 整页一次送会让 Vulkan 驱动崩溃

```
ggml_vulkan: device fault on Vulkan0: No fault detected
ggml_vulkan: device lost on Vulkan0          ← HTTP 500
```

1700×2200 整页超出驱动承受范围。**必须切片**，3 段（每段约 733px）稳定。

### 4. 切片要处理段间重复

overlap 80px 会让重叠区的文字输出两遍（`(i)` 重复了一次）。
加 `strip_overlap()`：用前段尾部 6 行做集合，从后段头部往下跳过重复行。

### 5. 分辨率不能缩

先设 1400 宽，表格行和分值会漏（字太小被忽略）。**保持原卷 1700 宽**。

## 结论：这次不换

### 为什么

1. **速度优势有限**：4B 是 139–244 秒/页，CPU 版 PaddleOCR-VL 是 300 秒/页，
   只快 1.2–2 倍，不是数量级
2. **8GB 显存卡住了模型规模**：8B 要部分 CPU offload，速度和 CPU 版一样；
   能全放 GPU 的只有 4B
3. **输出没有结构信息**：qwen 给的是纯文本，没有 block 类型（text/table/figure_title/footer）
   和坐标。现有的 `lq1_parse.py` 全靠 `block_label` 过滤噪声（aside_text、footer、
   图内标注），换模型等于重写解析层
4. **PaddleOCR-VL 已经在跑**：剩余 9 份卷 4 小时完成，中途换方案不划算

### 什么时候值得用

**化学、物理的卷二**（预计 300+ 页）如果也要做，值得考虑：

- 用 qwen3-vl:4b 做**初筛**（快 2 倍，抓出题干和表格）
- 关键页再跑 PaddleOCR-VL 精修
- 或者接受「待核对」标记，用 4b 直接出稿 + 人工过一遍

### 想真正提速只有两条路

1. **换 N 卡**（RTX 3060 12GB 起）—— PaddlePaddle GPU 版只认 CUDA
2. **租云 GPU** —— 一次性把生/化/物全部页图跑完，几十块钱

## 文件位置

```
D:\ollama-app\                        Ollama 0.40.14 + ROCm 7.1（解压版，无需安装）
D:\ollama-models\                     4 个模型共 18GB
scratch/_ollama_ocr_test.py           测试脚本（切片 + 去重 + 参数）
scratch/_ollama_ocr/                  各模型的识别结果
scratch/_ollama_serve.log             服务日志
```

### 启动方式

```bash
cd D:/ollama-app
OLLAMA_MODELS="D:\\ollama-models" ./ollama.exe serve
```

### 跑一页

```bash
python scratch/_ollama_ocr_test.py 2019 23 --model qwen3-vl:4b --slices 3
```

## 清理

下载包 3.3GB 已删（`scratch/_dl/` 只剩安装日志）。D 盘剩余 76GB。
