# -*- coding: utf-8 -*-
"""LQ 参考答案识别 —— 多进程并行版。

为什么需要它
------------
`lq_vl.py` 是单进程串行，实测 CPU 上约 **3.9 分钟/页**（PaddleOCR-VL 0.9B
自回归生成，batch=1）。参考页图共 156 页，串行要 10 小时。

关键观察：自回归解码是**访存 + 小批量算力**瓶颈，单条序列喂不满 i5-13600KF
的 20 个逻辑核 —— 实测单进程跑满页时 CPU 利用率长期在 30~50% 徘徊。
所以「多进程 × 每进程少线程」能拿到接近线性的吞吐提升。

本脚本
------
  · 按**页**粒度把 (年份, 页号) 平铺给进程池，任何一页失败都不阻塞其它页
  · 每个 worker 进程各自加载一次模型（约 80 秒），之后逐页复用
  · 幂等：已存在的 pNNN.json 直接跳过，中断后重跑不会浪费
  · 每页结果立刻落盘，进程被杀也不丢进度

用法
----
  # 全量（推荐 4 workers，14 份卷约 5 小时）
  python scripts/pastpaper/lq_vl_par.py --workers 4

  # 只跑某几份
  python scripts/pastpaper/lq_vl_par.py --workers 4 2023 PP

  # 从第 3 页开始（跳过 MC 答案表页）
  python scripts/pastpaper/lq_vl_par.py --workers 4 --first-page 3 2019
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.environ.get("LQ_PAGES_DIR") or os.path.join(_ROOT, "scratch", "_lq_pages")
OUT = os.environ.get("LQ_OUT_DIR") or os.path.join(_ROOT, "scratch", "_lq_vl")

_pipe = None


def _page_list(key, first_page):
    """列出该来源所有待识别的页（图存在且结果未生成）。"""
    d = os.path.join(PAGES, key)
    if not os.path.isdir(d):
        return []
    pages = []
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith((".jpg", ".png", ".jpeg")):
            continue
        try:
            n = int(f[1:4])
        except ValueError:
            continue
        if n < first_page:
            continue
        if os.path.exists(os.path.join(OUT, key, "p%03d.json" % n)):
            continue
        pages.append((key, n))
    return pages


def _pipe_for_worker():
    global _pipe
    if _pipe is None:
        from paddleocr import PaddleOCRVL
        _pipe = PaddleOCRVL()
    return _pipe


def _do_page(task):
    """worker 入口：识别一页。返回 (key, n, status, blocks, secs)。"""
    key, n = task
    src = os.path.join(PAGES, key, "p%03d.jpg" % n)
    t0 = time.time()
    try:
        out = _pipe_for_worker().predict(src)
    except Exception as e:  # 识别异常不应拖垮整批
        return (key, n, "err:%s" % e, 0, time.time() - t0)
    payload = None
    for res in out:
        d = None
        for attr in ("json", "to_json"):
            v = getattr(res, attr, None)
            if v is None:
                continue
            d = v() if callable(v) else v
            break
        if d is None:
            continue
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except Exception:
                continue
        payload = d
    if payload is None:
        return (key, n, "fail", 0, time.time() - t0)
    os.makedirs(os.path.join(OUT, key), exist_ok=True)
    dst = os.path.join(OUT, key, "p%03d.json" % n)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    blocks = (payload.get("res") or payload).get("parsing_res_list", [])
    return (key, n, "ok", len(blocks), time.time() - t0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--first-page", type=int, default=1)
    args = ap.parse_args()

    keys = args.keys
    if not keys:
        base = os.path.join(PAGES)
        keys = sorted(d for d in os.listdir(base)
                      if os.path.isdir(os.path.join(base, d)))

    tasks = []
    for k in keys:
        tasks.extend(_page_list(k, args.first_page))
    if not tasks:
        print("[done] 没有待识别的页（全部已生成）")
        return

    print("[plan] %d 页 / %d workers" % (len(tasks), args.workers), flush=True)
    t0 = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_do_page, t) for t in tasks]
        for fu in as_completed(futs):
            key, n, status, blocks, secs = fu.result()
            done += 1
            el = time.time() - t0
            eta = el / done * (len(tasks) - done) / 60
            print("  %-4s p%03d  %-8s %2d blocks  %4.0fs  [%d/%d, 剩余~%.0f分]"
                  % (key, n, status, blocks, secs, done, len(tasks), eta), flush=True)
    print("[done] 共 %d 页，用时 %.0f 分钟" % (done, (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    main()
