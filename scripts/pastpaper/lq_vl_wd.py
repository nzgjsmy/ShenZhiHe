# -*- coding: utf-8 -*-
"""带看门狗的并行识别：某页迟迟不出结果就跳过，不让整批陪葬。

背景
----
PaddleOCR-VL 在少数页上会长时间不结束：实测 2018 p021 之后、2022 p022 之后
都出现过「CPU 满载但 20~60 分钟不出结果」。原来的 `lq_vl_par.py` 用
`ProcessPoolExecutor`，运行中的任务无法中断，只能整批干等 —— 两批各卡一次，
白等了近两小时。

做法
----
改用 `multiprocessing.Pool` + 停滞检测：

  1. 主进程每 15 秒数一次该年份已产出的 json 数量；
  2. 连续 `--stall` 秒没有新增 → 判定卡住，`terminate()` 整个池（能真正杀掉卡住的
     worker），重建后重试未完成的页；
  3. 同一页连续卡 `--max-hits` 次就跳过，记进 `_skipped.json`，事后可单独重试。

代价：每次重启池要重新加载模型（约 80 秒 × workers），但比无限等划算。

用法
----
    LQ_PAGES_DIR=scratch/_pp_pages LQ_OUT_DIR=scratch/_p1_vl \\
        python scripts/pastpaper/lq_vl_wd.py --workers 3 2022 SP 2020 2021
"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lq_vl_par import OUT, PAGES, _do_page, _page_list  # noqa: E402

# 各年卷一乙部起始页（甲部 MC 页要跳过）：2020 的乙部从 p12 起，其余 p11
FIRST_PAGE = {"2020": 12}


def done_count(key):
    d = os.path.join(OUT, key)
    if not os.path.isdir(d):
        return 0
    return sum(1 for f in os.listdir(d) if f.startswith("p") and f.endswith(".json"))


def out_path(task):
    return os.path.join(OUT, task[0], "p%03d.json" % task[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--stall", type=int, default=900, help="连续多少秒无新增判定卡住")
    ap.add_argument("--max-hits", type=int, default=2, help="同一页卡几次后跳过")
    ap.add_argument("--first-page", type=int, default=None, help="强制指定起始页")
    a = ap.parse_args()

    if not a.keys:
        print("用法: lq_vl_wd.py [--workers 3] 2022 SP ...")
        return

    pending = []
    for k in a.keys:
        fp = a.first_page if a.first_page is not None else FIRST_PAGE.get(k, 11)
        tasks = _page_list(k, fp)
        print("%-5s 待识别 %d 页（从 p%03d 起）" % (k, len(tasks), fp), flush=True)
        pending.extend(tasks)

    if not pending:
        print("没有待识别的页。")
        return

    keys = sorted({t[0] for t in pending})
    hits, skipped = {}, []
    t_start = time.time()

    while pending:
        print("\n=== 本轮 %d 页，池 %d worker ===" % (len(pending), a.workers), flush=True)
        pool = mp.Pool(a.workers)
        try:
            asyncs = [(pool.apply_async(_do_page, (t,)), t) for t in pending]
            last_done = sum(done_count(k) for k in keys)
            last_t = time.time()
            while True:
                if all(x.ready() for x, _ in asyncs):
                    break
                time.sleep(15)
                now = sum(done_count(k) for k in keys)
                if now > last_done:
                    last_done, last_t = now, time.time()
                elif time.time() - last_t > a.stall:
                    print("  !! 停滞 %d 秒，重启进程池" % a.stall, flush=True)
                    break

            for x, t in asyncs:
                if not x.ready():
                    continue
                try:
                    k, n, st, blk, sec = x.get(timeout=5)
                    print("  %-5s p%03d  %-6s %2d blocks  %ds" % (k, n, st, blk, sec), flush=True)
                except Exception as e:
                    print("  %-5s p%03d  异常 %s" % (t[0], t[1], e), flush=True)
        finally:
            pool.terminate()
            pool.join()

        nxt = []
        for t in pending:
            if os.path.exists(out_path(t)):
                continue
            hits[t] = hits.get(t, 0) + 1
            if hits[t] >= a.max_hits:
                skipped.append(t)
                print("  跳过 %s p%03d（连续卡 %d 次）" % (t[0], t[1], hits[t]), flush=True)
            else:
                nxt.append(t)
        pending = nxt

    # 记下跳过的页，方便事后单独重试
    if skipped:
        dst = os.path.join(OUT, "_skipped.json")
        json.dump([{"key": k, "page": n} for k, n in skipped],
                  open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n跳过的页已记到 %s" % dst)
        for k, n in skipped:
            print("  %s p%03d" % (k, n))

    print("\n完成，用时 %.1f 分钟" % ((time.time() - t_start) / 60))


if __name__ == "__main__":
    main()
