#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quantumult X 去广告规则构建脚本
---------------------------------
读取 custom.txt（本地自定义域名）与 sources.txt（上游合并源），
统一转换为 Quantumult X 规则格式（HOST-SUFFIX/HOST-KEYWORD/IP-CIDR + REJECT），
去重后写出 adblock.list。

支持的上游格式自动识别：
  - AdBlock / uBlock 语法： ||domain^  |https://domain^  @@ 例外(跳过)
  - DNS hosts 语法：        0.0.0.0 domain  /  127.0.0.1 domain
  - Quantumult X / Surge：  HOST,domain,Policy  /  DOMAIN-SUFFIX,domain,Policy
  - 纯域名：                domain

用法：
  python3 build.py            # 生成 ./adblock.list
  python3 build.py -o out.list
"""

import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CUSTOM_FILE = os.path.join(HERE, "custom.txt")
SOURCES_FILE = os.path.join(HERE, "sources.txt")
OUTPUT_FILE = os.path.join(HERE, "adblock.list")
REWRITE_SOURCES_FILE = os.path.join(HERE, "rewrite_sources.txt")
REWRITE_OUTPUT = os.path.join(HERE, "rewrite.list")

IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9*](?:[a-z0-9-*]*[a-z0-9])?\.)+[a-z]{2,}$", re.I)

rules = set()  # 去重后的规则行

# Quantumult X 重写行合法的关键字（第 2 个空白分隔字段）
REWRITE_KEYWORDS = {
    "url",
    "script-request-header", "script-request-body",
    "script-response-header", "script-response-body",
    "script-echo-response", "script-analyze-echo-response",
    "request-header", "response-header",
}


def is_valid_qx_rewrite_line(line: str) -> bool:
    """校验一行是否为合法的 Quantumult X 重写规则/注释/hostname。"""
    s = line.strip()
    if not s:
        return False
    if s.startswith(("#", ";", "!")):
        return True
    if re.match(r"^hostname\s*=", s, re.I):
        return True
    parts = s.split()
    if len(parts) < 3:
        return False
    return parts[1].lower() in REWRITE_KEYWORDS


def sanitize_rewrite(content: str, src_label: str):
    """清洗单个重写源：剔除非法行；若整体像 HTML 网页则返回 None（整源弃用）。"""
    lines = content.splitlines()
    # 源级 HTML 检测
    html_markers = sum(
        1 for l in lines
        if re.search(r"<(html|head|body|div|style|script|meta|title)\b|data-theme|--bg-|:hover|@media|<title>", l, re.I)
    )
    if html_markers > 5:
        print(f"[弃用] 源内容为 HTML 网页而非规则: {src_label} (HTML特征行 {html_markers})")
        return None
    kept, dropped = [], 0
    for l in lines:
        if is_valid_qx_rewrite_line(l):
            kept.append(l)
        else:
            if l.strip():
                dropped += 1
    if dropped:
        print(f"[清洗] {src_label}: 剔除 {dropped} 条非 QX 语法行")
    return "\n".join(kept) + "\n"


def add_host_suffix(domain: str):
    d = domain.strip().lower().lstrip("*.").rstrip(".")
    if not d or d in ("*",):
        return
    if IP_RE.match(d):
        # Quantumult X 要求 IP-CIDR 必须带掩码：纯 IP 补 /32
        if "/" not in d:
            d = f"{d}/32"
        rules.add(f"IP-CIDR,{d},REJECT")
        return
    if DOMAIN_RE.match(d):
        rules.add(f"HOST-SUFFIX,{d},REJECT")


def add_host_keyword(kw: str):
    kw = kw.strip()
    if kw:
        rules.add(f"HOST-KEYWORD,{kw},REJECT")


def parse_line(line: str):
    s = line.strip()
    if not s or s.startswith(("!", "#", "/", ";")):
        return
    # AdBlock 例外规则（@@）直接跳过
    if s.startswith("@@"):
        return

    # AdBlock / uBlock: ||domain^  |https://domain^  |http://domain|
    if s.startswith("||") or s.startswith("|http") or s.startswith("|https"):
        m = re.match(r"^\|*https?://([^/\^\*]+)", s)
        if not m:
            m = re.match(r"^\|\|([^/\^\*]+)", s)
        if m:
            add_host_suffix(m.group(1))
        return

    # DNS hosts: 0.0.0.0 domain  /  127.0.0.1 domain
    m = re.match(r"^(?:\d{1,3}\.){3}\d{1,3}\s+(\S+)", s)
    if m:
        add_host_suffix(m.group(1))
        return

    # Quantumult X / Surge: HOST,domain,Policy  / DOMAIN-SUFFIX,domain,Policy
    m = re.match(r"^(?:HOST|DOMAIN-SUFFIX|DOMAIN|HOST-KEYWORD),([^,]+),", s)
    if m:
        target = m.group(1).strip()
        if s.upper().startswith("HOST-KEYWORD"):
            add_host_keyword(target)
        else:
            add_host_suffix(target)
        return

    # 纯域名
    if DOMAIN_RE.match(s):
        add_host_suffix(s)
        return

    # 含空格/制表符的纯域名（兜底）
    parts = s.split()
    if parts and DOMAIN_RE.match(parts[-1]):
        add_host_suffix(parts[-1])


def load_custom():
    if not os.path.exists(CUSTOM_FILE):
        return
    with open(CUSTOM_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()  # 去掉行内注释
            if not line:
                continue
            parse_line(line)


def load_sources():
    if not os.path.exists(SOURCES_FILE):
        return
    urls = []
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line and line.startswith("http"):
                urls.append(line)
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read().decode("utf-8", "ignore")
            count_before = len(rules)
            for ln in data.splitlines():
                parse_line(ln)
            print(f"[OK] 已合并上游: {url}  (新增 {len(rules) - count_before} 条)")
        except Exception as e:
            print(f"[跳过] 上游抓取失败，已忽略: {url}  ({e})")


def build_rewrite():
    """抓取墨鱼(ddgksf2013)各 App 重写规则，合并为单条订阅用的 rewrite.list。
    任何来源抓取失败都跳过，保证已有 rewrite.list 不被清空。"""
    if not os.path.exists(REWRITE_SOURCES_FILE):
        return
    urls = []
    with open(REWRITE_SOURCES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line and line.startswith("http"):
                urls.append(line)
    if not urls:
        return
    blocks = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                txt = resp.read().decode("utf-8", "ignore")
            cleaned = sanitize_rewrite(txt, url)
            if cleaned is None:
                continue
            blocks.append(f"# ===== source: {url} =====\n" + cleaned.rstrip() + "\n")
            print(f"[OK] 已合并重写: {url}  ({len(cleaned)}B)")
        except Exception as e:
            print(f"[跳过] 重写抓取失败，已忽略: {url}  ({e})")
    if blocks:
        with open(REWRITE_OUTPUT, "w", encoding="utf-8") as f:
            f.write("\n".join(blocks) + "\n")
        print(f"[完成] 重写清单共 {len(blocks)} 个来源 -> {REWRITE_OUTPUT}")


def main():
    load_custom()
    load_sources()
    build_rewrite()
    rules_list = sorted(rules)
    header = [
        "# NAME: Apple-Ads-Block (Quantumult X)",
        "# DESC: 苹果手机去广告/反追踪规则（覆盖 Apple/Google/Meta/X/TikTok-抖音/"
        "微信-腾讯/百度/阿里 + 通用广告与追踪 SDK），支持订阅自动更新。",
        f"# COUNT: {len(rules_list)}",
        "# UPDATE: 由 build.py 生成，建议配合 Quantumult X update-interval 或 GitHub Actions 定时重建",
        "",
    ]
    out = header + rules_list
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"[完成] 共写入 {len(rules_list)} 条规则 -> {OUTPUT_FILE}")


if __name__ == "__main__":
    if "-o" in sys.argv:
        idx = sys.argv.index("-o")
        OUTPUT_FILE = os.path.abspath(sys.argv[idx + 1])
    main()
