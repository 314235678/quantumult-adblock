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

import ipaddress
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
# 本地固化的重写源（优先级最高，排在最前）：微信生态去广告
REWRITE_LOCAL_FILE = os.path.join(HERE, "wechat_rewrite.conf")

# 需要从合并结果里剔除的上游重写行（按正则匹配，命中即丢弃）
# 说明：ddgksf2013 / fmz200 的 getappmsgad 旧写法是把响应体里的 "advertisement"
# 字符串整体替换成作者名，属于破坏性 hack，作者本人已标注【已失效】；而且它排在
# chxm1023 那条真正有效的 script-response-body 规则前面，会抢占同一个 URL，
# 导致公众号文章去广告实际不生效。故统一剔除，只保留有效实现。
REWRITE_DROP_PATTERNS = [
    # ① ddgksf2013 / fmz200 旧写法：把响应体里的 "advertisement" 字符串整体替换成
    #    作者名，属于破坏性 hack，作者本人已标注【已失效】。
    re.compile(r"getappmsgad.*response-body\s+advertisement\s+response-body", re.I),
    # ② Moli-X 写法：用正则直接改 JSON 文本（"advertisement_num":\d -> 0）。
    #    与 ① 同理，会和上面那条真正有效的 script-response-body 抢同一个 URL；
    #    且它依赖字段顺序与相邻性，公众号改版就会失效，不如脚本解析 JSON 稳。
    re.compile(r"getappmsgad.*response-body\s+[\"']advertisement_num", re.I),
]

IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9*](?:[a-z0-9-*]*[a-z0-9])?\.)+[a-z]{2,}$", re.I)

# IP 规则统一补 no-resolve。
# 原因：Quantumult X 的 IP-CIDR 规则默认会对每个待匹配域名触发一次 DNS 解析，
# 上万条规则叠加后启动和浏览都会明显变慢；加 no-resolve 表示只对已解析出的 IP 生效。
IP_RULE_TAIL = ",no-resolve"

# HOST-KEYWORD 安全阀。
# 关键词是子串匹配，过于宽泛的词（如 ad / api / cdn）会大面积误杀正常网站。
# 这里做两道保护：长度 <4 一律丢弃，命中黑名单一律丢弃。
KEYWORD_DENY = {
    "ad", "ads", "adv", "advert", "adserver", "log", "logs", "api", "img",
    "image", "images", "cdn", "static", "video", "pic", "sdk", "app", "apps",
    "data", "stat", "stats", "track", "m", "w", "www", "com", "net", "cn",
    "io", "co", "go", "new", "hot", "top", "vip", "pay", "user",
}
KEYWORD_MIN_LEN = 4

rules = set()  # 去重后的规则行
dropped_keywords = []  # 被安全阀拦下的关键词（用于构建日志）
ip_stat = {"skipped_private": 0, "skipped_broad": 0}  # IP 规则安全阀统计

# Quantumult X 重写行合法的关键字（第 2 个空白分隔字段）
REWRITE_KEYWORDS = {
    "url",
    "script-request-header", "script-request-body",
    "script-response-header", "script-response-body",
    "script-echo-response", "script-analyze-echo-response",
    "request-header", "response-header",
}

# 重写动作分类，用于「同一 URL 多动作」的冲突裁决
SCRIPT_ACTIONS = {
    "script-response-body", "script-response-header",
    "script-echo-response", "script-analyze-echo-response",
    "script-request-body", "script-request-header",
}
REJECT_ACTIONS = {
    "reject", "reject-dict", "reject-200", "reject-img",
    "reject-array", "reject-drop",
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


def ip_cidr_rule(cidr: str):
    """把 IP / CIDR 规范化为 Quantumult X 的 REJECT 规则。

    会做三件事：
      1) 纯 IP 补 /32（Quantumult X 要求 IP-CIDR 必须带掩码）；
      2) 拒绝私有段/保留段（10/8、172.16/12、192.168/16、127/8、0/8、
         169.254/16、组播等）——上游广告清单里混入过 10.72.25.0/24 这类条目，
         照收会把用户自己的局域网整段墙掉；
      3) 拒绝掩码短于 /16 的超大段（误杀面太大），并补 no-resolve。
    """
    d = cidr.strip().lower()
    if not d:
        return
    if "/" not in d:
        d = d + "/32"
    try:
        net = ipaddress.ip_network(d, strict=False)
    except ValueError:
        return
    if net.version != 4:
        return
    if net.prefixlen < 16:
        ip_stat["skipped_broad"] += 1
        return
    if (
        net.is_private
        or net.is_loopback
        or net.is_multicast
        or net.is_reserved
        or net.is_link_local
        or net.is_unspecified
    ):
        ip_stat["skipped_private"] += 1
        return
    rules.add(f"IP-CIDR,{net},REJECT{IP_RULE_TAIL}")


def add_host_suffix(domain: str):
    d = domain.strip().lower().lstrip("*.").rstrip(".")
    if not d or d in ("*",):
        return
    if IP_RE.match(d):
        ip_cidr_rule(d)
        return
    if DOMAIN_RE.match(d):
        rules.add(f"HOST-SUFFIX,{d},REJECT")


def add_host_keyword(kw: str):
    kw = kw.strip()
    if not kw:
        return
    low = kw.lower()
    if len(kw) < KEYWORD_MIN_LEN or low in KEYWORD_DENY:
        dropped_keywords.append(kw)
        return
    rules.add(f"HOST-KEYWORD,{kw},REJECT")


def parse_line(line: str):
    s = line.strip()
    if not s or s.startswith(("!", "#", "/", ";")):
        return
    # AdBlock 例外规则（@@）直接跳过
    if s.startswith("@@"):
        return

    # Quantumult X / Surge 原生 IP 规则：IP-CIDR,1.2.3.4/32,策略[,no-resolve]
    # 关键点：上游清单里的策略名往往是 Advertising / REJECT 等任意值，
    # 早期版本只认 HOST/DOMAIN 前缀，导致整批 IP 规则被静默丢弃。
    m = re.match(r"^IP-?CIDR6?\s*,\s*([^,]+)\s*,", s, re.I)
    if m:
        ip_cidr_rule(m.group(1))
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


def _drop_reason(line: str):
    """返回该行被剔除的原因；None 表示保留。"""
    for pat in REWRITE_DROP_PATTERNS:
        if pat.search(line):
            return f"命中剔除规则 {pat.pattern[:40]}"
    return None


def _pattern(line: str) -> str:
    """取重写行的 URL 正则部分（第一个字段）。"""
    p = line.split(None, 1)
    return p[0] if p else ""


def _action(line: str) -> str:
    """取重写行的动作类型（第三个字段，如 reject-dict / script-response-body）。"""
    p = line.split()
    return p[2].lower() if len(p) >= 3 else ""


def build_rewrite():
    """两阶段合并重写规则为单条订阅用的 rewrite.list。

    阶段一：抓取全部来源（本地固化源优先），做语法清洗 + 失效行剔除。
    阶段二：裁决「同一 URL 模式多种动作」的冲突，再按来源分块输出并全局去重。

    冲突裁决策略：
      同一个 URL 正则下，如果既有脚本型规则（script-response-body，保留接口、
      只清广告数据）又有整条拒绝型规则（reject*），保留脚本、丢弃拒绝。
      原因：整条拒绝会把接口整个打掉，常导致 App 页面空白或报错；
      脚本清洗只摘掉广告部分，功能不受影响。
      其余情形（如 reject 与 reject-200 并存）差异不影响功能，保持原样。

    任何来源抓取失败都跳过，保证已有 rewrite.list 不被清空。
    """
    sources = []  # [(来源标签, [行])]

    # ① 本地固化源优先
    if os.path.exists(REWRITE_LOCAL_FILE):
        with open(REWRITE_LOCAL_FILE, "r", encoding="utf-8") as f:
            cleaned = sanitize_rewrite(f.read(), "wechat_rewrite.conf")
        if cleaned:
            sources.append(
                ("本地固化 · 微信生态去广告 (wechat_rewrite.conf)", cleaned.splitlines())
            )

    # ② 上游各源
    urls = []
    if os.path.exists(REWRITE_SOURCES_FILE):
        with open(REWRITE_SOURCES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line and line.startswith("http"):
                    urls.append(line)

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                txt = resp.read().decode("utf-8", "ignore")
            cleaned = sanitize_rewrite(txt, url)
            if cleaned is not None:
                sources.append((url, cleaned.splitlines()))
        except Exception as e:
            print(f"[跳过] 重写抓取失败，已忽略: {url}  ({e})")

    # ---- 阶段一：剔除失效行 ----
    filtered = []
    for label, lines in sources:
        kept = []
        for raw in lines:
            s = raw.strip()
            if not s:
                continue
            reason = _drop_reason(s)
            if reason:
                print(f"[剔除] {label}: {reason} -> {s[:90]}")
                continue
            kept.append(s)
        filtered.append((label, kept))

    # ---- 阶段二：冲突裁决 ----
    prec = {}
    for _, lines in filtered:
        for s in lines:
            if s.startswith("#") or re.match(r"^hostname\s*=", s, re.I):
                continue
            if not is_valid_qx_rewrite_line(s):
                continue
            prec.setdefault(_pattern(s), set()).add(_action(s))

    script_wins = {
        pat for pat, acts in prec.items()
        if (acts & SCRIPT_ACTIONS) and (acts & REJECT_ACTIONS)
    }

    blocks = []
    seen = set()
    total = 0
    for label, lines in filtered:
        out = []
        for s in lines:
            if s in seen:
                continue
            seen.add(s)
            is_rule = not s.startswith("#") and not re.match(r"^hostname\s*=", s, re.I)
            if is_rule and _action(s) in REJECT_ACTIONS and _pattern(s) in script_wins:
                print(f"[裁决] {label}: 整条拒绝让位给脚本规则 -> {s[:90]}")
                continue
            out.append(s)
        if out:
            total += len(out)
            blocks.append(f"# ===== source: {label} =====\n" + "\n".join(out) + "\n")

    if blocks:
        with open(REWRITE_OUTPUT, "w", encoding="utf-8") as f:
            f.write("\n".join(blocks) + "\n")
        print(f"[完成] 重写清单共 {len(blocks)} 个来源，{total} 条去重后规则 -> {REWRITE_OUTPUT}")
        if script_wins:
            print(f"[裁决] 共 {len(script_wins)} 个 URL 模式按「脚本优先于整条拒绝」处理")
        print(f"[完成] 重写清单共 {len(blocks)} 个来源，{len(seen)} 条去重后规则 -> {REWRITE_OUTPUT}")


def main():
    load_custom()
    load_sources()
    build_rewrite()
    rules_list = sorted(rules)
    kinds = {}
    for r in rules_list:
        k = r.split(",")[0]
        kinds[k] = kinds.get(k, 0) + 1
    header = [
        "# NAME: Apple-Ads-Block (Quantumult X)",
        "# DESC: 苹果手机去广告/反追踪规则（覆盖 Apple/Google/Meta/X/TikTok-抖音/"
        "微信-腾讯/百度/阿里 + 通用广告与追踪 SDK），支持订阅自动更新。",
        f"# COUNT: {len(rules_list)}"
        f" (HOST-SUFFIX {kinds.get('HOST-SUFFIX', 0)}"
        f" / HOST-KEYWORD {kinds.get('HOST-KEYWORD', 0)}"
        f" / IP-CIDR {kinds.get('IP-CIDR', 0)})",
        "# UPDATE: 由 build.py 生成，建议配合 Quantumult X update-interval 或 GitHub Actions 定时重建",
        "",
    ]
    out = header + rules_list
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"[完成] 共写入 {len(rules_list)} 条规则 -> {OUTPUT_FILE}")
    print(f"        分布: {kinds}")
    if dropped_keywords:
        print(f"[安全阀] 丢弃过宽关键词 {len(dropped_keywords)} 个: "
              f"{', '.join(sorted(set(dropped_keywords))[:20])}")
    print(f"[安全阀] IP 规则: 跳过私有/保留段 {ip_stat['skipped_private']} 条, "
          f"跳过过大网段 {ip_stat['skipped_broad']} 条")


if __name__ == "__main__":
    if "-o" in sys.argv:
        idx = sys.argv.index("-o")
        OUTPUT_FILE = os.path.abspath(sys.argv[idx + 1])
    main()
