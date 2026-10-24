#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重写脚本存活检查 (check_scripts.py)
------------------------------------
扫描 rewrite.list 里所有 script-path，逐个请求，找出已失效的脚本地址。

为什么需要它：
  QX 里每条引用失效脚本的规则都会显示「Status code 404 / 需要更新」，
  资源页顶部汇总成「N 个问题存在于子资源」。用户看到的是一个数字，
  根本不知道是哪些行、哪个脚本死了。本脚本直接把这些行列出来。

判定标准：
  · 404 / 410  -> 真失效（确定性问题，退出码 1）
  · 网络超时 / 5xx / 429 -> 临时问题（仅提示，不影响退出码）

用法：
  python3 check_scripts.py            # 检查并报告
  python3 check_scripts.py --list     # 额外打印每条失效规则
"""
import os
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REWRITE = os.path.join(HERE, "rewrite.list")
TIMEOUT = 20
WORKERS = 16

SCRIPT_ACTIONS = ("script-response-body", "script-request-body",
                  "script-response-header", "script-request-header")


def fetch_status(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            r.read(64)
        return url, 200, ""
    except Exception as e:
        code = getattr(e, "code", None)
        return url, code, str(e)[:60]


def repo_of(url):
    p = urlparse(url)
    parts = [x for x in p.path.split("/") if x]
    if p.hostname == "raw.githubusercontent.com" and len(parts) >= 2:
        return "/".join(parts[:2])
    return p.hostname or "?"


def main():
    if not os.path.exists(REWRITE):
        print("找不到 rewrite.list，请先运行 build.py")
        return 1

    lines = [l.strip() for l in open(REWRITE, encoding="utf-8")
             if l.strip() and not l.startswith("#")]

    urls = set()
    for l in lines:
        parts = l.split()
        # 格式：<匹配正则> url <动作> <脚本地址> [...]
        # 只能取动作之后那个地址；第一列是匹配正则，里面也含 https?:// 字样，
        # 误当成脚本地址去请求会得到一堆假 404。
        if len(parts) >= 4 and parts[2].lower() in SCRIPT_ACTIONS:
            u = parts[3].rstrip(")")
            if u.startswith("http"):
                urls.add(u)

    print(f"待检查脚本 {len(urls)} 个（来自 {len(lines)} 条规则）...")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(fetch_status, sorted(urls)))

    dead = {u: c for u, c, _ in results if c in (404, 410)}
    flaky = {u: c for u, c, _ in results if c not in (404, 410) and c != 200}

    # 统计每条失效脚本牵连多少规则行
    hit_lines = Counter()
    for l in lines:
        for u in dead:
            if u in l:
                hit_lines[u] += 1
                break

    total_affected = sum(hit_lines.values())

    print()
    print("=" * 66)
    print(f"存活 {len(urls) - len(dead) - len(flaky)} / "
          f"失效 {len(dead)} / 临时异常 {len(flaky)}")
    print("=" * 66)

    if dead:
        by_repo = defaultdict(list)
        for u in dead:
            by_repo[repo_of(u)].append(u)
        print(f"\n【失效脚本】影响 {total_affected} 条规则 —— "
              f"这就是 QX 里「N 个问题存在于子资源」的来源")
        for repo, us in sorted(by_repo.items(), key=lambda x: -len(x[1])):
            print(f"\n  仓库 {repo}")
            for u in us:
                print(f"    {hit_lines.get(u, 0):>3} 条规则  {u}")
                if "--list" in sys.argv:
                    for l in lines:
                        if u in l:
                            print(f"            {l[:150]}")
        print("\n  处理方式：把失效地址与可用镜像地址填进 script_fixes.txt；"
              "实在没有镜像就写 DROP。")

    if flaky:
        print(f"\n【临时异常】{len(flaky)} 个（网络超时/限流，可稍后重试，不算错误）")
        for u, c in list(flaky.items())[:5]:
            print(f"    [{c}] {u}")

    if not dead and not flaky:
        print("\n全部脚本可用，没有 404。")

    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
