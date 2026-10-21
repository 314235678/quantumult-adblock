#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仅重建 rewrite.list（不碰 adblock.list）。带代理与短超时，便于本地运行。"""
import urllib.request, os, sys

PROXY = "http://127.0.0.1:7897"
if PROXY:
    os.environ['HTTPS_PROXY'] = os.environ['HTTP_PROXY'] = PROXY

def get(u, timeout=12):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'ignore')

base = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(base, 'rewrite_sources.txt'), encoding='utf-8').read()
urls = []
for line in src.splitlines():
    line = line.split('#', 1)[0].strip()
    if line.startswith('http'):
        urls.append(line)

print(f"源数量: {len(urls)}", flush=True)
blocks, ok, fail = [], [], []
for u in urls:
    try:
        txt = get(u)
        blocks.append(f"# ===== source: {u} =====\n" + txt.rstrip() + "\n")
        ok.append(u)
        print(f"[OK {len(txt)}B] {u.split('/')[-1]}", flush=True)
    except Exception as e:
        fail.append(u)
        print(f"[FAIL] {u} -> {e}", flush=True)

out = os.path.join(base, 'rewrite.list')
open(out, 'w', encoding='utf-8').write("\n".join(blocks) + "\n")
print(f"\n写入 rewrite.list: {len(blocks)} 成功 / {len(fail)} 失败", flush=True)
if fail:
    print("失败源(保留原配置,不删除):", flush=True)
    for u in fail:
        print("  ", u, flush=True)
