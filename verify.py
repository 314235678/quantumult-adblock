#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建产物校验（verify.py）
---------------------------
在 build.py 之后运行，检查 adblock.list / rewrite.list 是否"可用且安全"。
CI 里跑一次，防止上游抽风时把空清单或坏规则推给订阅者。

检查项：
  A. adblock.list 规则数量下限（防止上游集体抓取失败导致清单变空）
  B. 规则语法合法（只允许 HOST-SUFFIX / HOST-KEYWORD / IP-CIDR）
  C. IP-CIDR 必须带 no-resolve，且不得包含私有/保留网段
  D. HOST-KEYWORD 不得过短或过于宽泛
  E. rewrite.list 有效行数量下限 + 每行语法合法
  F. 公众号去广告必须只剩一条有效规则（曾经的冲突 bug 回归检查）
  G. 不得混入 HTML 网页内容

用法：python3 verify.py   （全部通过返回 0，否则返回 1）
"""
import ipaddress
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import KEYWORD_DENY, KEYWORD_MIN_LEN, is_valid_qx_rewrite_line  # noqa: E402

ADBLOCK = os.path.join(HERE, "adblock.list")
REWRITE = os.path.join(HERE, "rewrite.list")

MIN_DOMAIN_RULES = 5000
MIN_REWRITE_RULES = 1000

errors = []
warnings = []
infos = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def read(path):
    if not os.path.exists(path):
        err(f"文件不存在: {os.path.basename(path)}")
        return ""
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


# ---------------- A~D：域名拒绝层 ----------------
text = read(ADBLOCK)
lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]

if len(lines) < MIN_DOMAIN_RULES:
    err(f"adblock.list 规则过少：{len(lines)} 条（下限 {MIN_DOMAIN_RULES}），疑似上游集体抓取失败")

bad_kind = set()
ip_missing_noresolve = 0
ip_private = []
kw_too_wide = []
for ln in lines:
    kind = ln.split(",")[0].strip().upper()
    if kind not in ("HOST-SUFFIX", "HOST-KEYWORD", "IP-CIDR"):
        bad_kind.add(kind)
        continue
    if kind == "IP-CIDR":
        if "no-resolve" not in ln.lower():
            ip_missing_noresolve += 1
        cidr = ln.split(",")[1].strip() if ln.count(",") >= 2 else ""
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            if (net.is_private or net.is_loopback or net.is_multicast
                    or net.is_reserved or net.is_link_local or net.is_unspecified):
                ip_private.append(ln)
            if net.prefixlen < 16:
                ip_private.append(ln)
        except ValueError:
            err(f"IP-CIDR 格式非法: {ln}")
    elif kind == "HOST-KEYWORD":
        kw = ln.split(",")[1].strip() if ln.count(",") >= 2 else ""
        if len(kw) < KEYWORD_MIN_LEN or kw.lower() in KEYWORD_DENY:
            kw_too_wide.append(ln)

if bad_kind:
    err(f"adblock.list 含非法规则类型: {sorted(bad_kind)}")
if ip_missing_noresolve:
    warn(f"{ip_missing_noresolve} 条 IP-CIDR 缺少 no-resolve（会引发多余 DNS 解析）")
if ip_private:
    err(f"{len(ip_private)} 条 IP-CIDR 命中私有/保留/超大网段，"
        f"可能误伤局域网: {ip_private[:5]}")
if kw_too_wide:
    err(f"{len(kw_too_wide)} 条 HOST-KEYWORD 过宽，可能大面积误杀: {kw_too_wide[:5]}")

# 基础设施白名单回归检查：
# 这些域名承载着订阅与脚本，一旦被自己推送的规则拦掉，用户会陷入
# 「开了去广告 → 所有订阅都更新失败」且极难自查的死循环。
from build import CRITICAL_ALLOW  # noqa: E402

crit_hit = [
    l for l in lines
    if l.startswith("HOST-SUFFIX,") and l.split(",")[1].strip().lower() in CRITICAL_ALLOW
]
if crit_hit:
    err(f"域名层拦了基础设施域名（会导致订阅/脚本全部拉不到）: {crit_hit}")

crit_kw = [
    l for l in lines
    if l.startswith("HOST-KEYWORD,")
    and any(l.split(",")[1].strip().lower() in a for a in CRITICAL_ALLOW)
]
if crit_kw:
    err(f"关键词层会连带封锁基础设施域名: {crit_kw}")

# ---------------- E~G：应用内重写层 ----------------
rtext = read(REWRITE)
rlines = [l.strip() for l in rtext.splitlines() if l.strip()]
effective = [l for l in rlines if not l.startswith("#") and not re.match(r"^hostname\s*=", l, re.I)]

if len(effective) < MIN_REWRITE_RULES:
    err(f"rewrite.list 有效重写行过少：{len(effective)} 条（下限 {MIN_REWRITE_RULES}）")

bad_rw = [l for l in effective if not is_valid_qx_rewrite_line(l)]
if bad_rw:
    err(f"rewrite.list 含 {len(bad_rw)} 条非法重写行，示例: {bad_rw[:3]}")

# QX 不支持的动作用户侧表现为「N 个问题存在于子资源」，必须在发布前清零
from build import SUPPORTED_REWRITE_ACTIONS  # noqa: E402

bad_action = []
for l in effective:
    p = l.split()
    if len(p) >= 3 and p[2].lower() not in SUPPORTED_REWRITE_ACTIONS:
        bad_action.append(l)
if bad_action:
    err(f"rewrite.list 含 {len(bad_action)} 条 QX 不支持的动作"
        f"（导入后会被报错忽略）: {[x[:80] for x in bad_action[:3]]}")

# 自洽性检查（本轮「58 个子资源有问题」事故的防回归）：
# 域名层绝不能拦掉重写脚本所在的托管域名，否则脚本下载失败，
# 用户看到的是「N 个问题存在于子资源」+「其他订阅无法连接服务器」。
from urllib.parse import urlparse  # noqa: E402

script_hosts = set()
for l in effective:
    for u in re.findall(r"https?://[^\s,]+", l):
        h = (urlparse(u).hostname or "").lower()
        if h:
            script_hosts.add(h)
blocked_hosts = {
    l.split(",")[1].strip().lower()
    for l in lines if l.startswith("HOST-SUFFIX,") and l.count(",") >= 2
}
self_block = sorted(h for h in script_hosts if h in blocked_hosts)
if self_block:
    err(f"域名层拦掉了重写脚本的托管域名，会导致脚本下载失败: {self_block}")
print(f"[信息] 重写脚本引用 {len(script_hosts)} 个托管域名，"
      f"其中被域名层拦截的: {len(self_block)} 个")

# 公众号去广告回归检查：曾经有 3 条"已失效"旧写法抢占同一个 URL
gam = [l for l in effective if "getappmsgad" in l]
if len(gam) != 1:
    err(f"公众号去广告规则应为 1 条，实际 {len(gam)} 条（冲突回归）: {gam}")
elif "script-response-body" not in gam[0]:
    err(f"公众号去广告规则不是有效的脚本型: {gam[0]}")
elif "wxgzhad.js" not in gam[0]:
    warn("公众号去广告脚本已不是预期的 wxgzhad.js，请确认上游是否仍有效")

# HTML 污染检查（上游 302 到网页时最容易发生）
# 注意：只在「整行以 HTML 标签开头」时才算污染。
# 合法的重写规则本身可能含 HTML 片段（例如往 <head> 注入 CSS 的规则），不能误报。
for name, body in (("adblock.list", text), ("rewrite.list", rtext)):
    html_hit = [
        l for l in body.splitlines()
        if re.match(r"^\s*<(?:\!DOCTYPE|html|head|body)\b", l, re.I)
    ]
    if html_hit:
        err(f"{name} 以 HTML 标签开头（{len(html_hit)} 行），疑似上游返回了网页: "
            f"{[h.strip()[:60] for h in html_hit[:3]]}")

# 同 URL 模式的规则冲突检测：
# Quantumult X 对同一 URL 只应用首条匹配的重写，其余静默失效。
#   · 有害冲突：脚本型（清洗响应、保留功能）被整条拒绝型盖住 → App 页面可能空白，算错误
#   · 无害冲突：reject / reject-200 / reject-dict 之间并存，都是拦截，方式不同而已
from collections import defaultdict  # noqa: E402
from build import REJECT_ACTIONS, SCRIPT_ACTIONS  # noqa: E402

pat_map = defaultdict(set)
for l in effective:
    parts = l.split()
    if len(parts) >= 3:
        pat_map[parts[0]].add(parts[2].lower())
harmful = {}
benign = 0
for p, acts in pat_map.items():
    if len(acts) < 2:
        continue
    if (acts & SCRIPT_ACTIONS) and (acts & REJECT_ACTIONS):
        harmful[p] = sorted(acts)
    else:
        benign += 1
if harmful:
    err(f"{len(harmful)} 个 URL 模式的脚本规则被整条拒绝规则盖住（会导致页面空白）: "
        f"{list(harmful.items())[:3]}")
if benign:
    infos.append(f"{benign} 个 URL 模式存在多种拦截方式（reject / reject-200 等），"
                 f"功能等价，无需处理")

# hostname 声明检查：重写层若没有任何 hostname，MitM 不会生效
if not re.search(r"^hostname\s*=", rtext, re.M | re.I):
    err("rewrite.list 缺少 hostname 声明，Quantumult X 不会为这些域名启用 MitM")

# MitM 不得覆盖订阅/脚本托管域名（否则拉订阅可能走中间人而失败）
from build import SUBSCRIPTION_INFRA  # noqa: E402

mitm_hosts = set()
for m in re.finditer(r"^hostname\s*=\s*(.+)$", rtext, re.M | re.I):
    for h in m.group(1).split(","):
        h = h.strip().lower().lstrip("*.")
        if h:
            mitm_hosts.add(h)
mitm_bad = sorted(
    h for h in mitm_hosts
    if any(h == a or h.endswith("." + a) for a in SUBSCRIPTION_INFRA)
)
if mitm_bad:
    err(f"MitM 覆盖了订阅托管域名（会导致订阅更新异常）: {mitm_bad}")
print(f"[信息] MitM 域名共 {len(mitm_hosts)} 个，覆盖订阅托管域名的: {len(mitm_bad)} 个")

# ---------------- 输出 ----------------
print("=" * 62)
print("构建产物校验")
print("=" * 62)
print(f"adblock.list : {len(lines):>6d} 条规则")
print(f"rewrite.list : {len(effective):>6d} 条有效重写行, "
      f"{len(re.findall(r'^hostname', rtext, re.M | re.I))} 条 hostname 声明")
print(f"公众号去广告 : {len(gam)} 条")
print()
for i in infos:
    print(f"[提示] {i}")
for w in warnings:
    print(f"[警告] {w}")
for e in errors:
    print(f"[错误] {e}")

if errors:
    print(f"\n校验未通过：{len(errors)} 项错误、{len(warnings)} 项警告")
    sys.exit(1)
print(f"\n校验通过（{len(warnings)} 项警告）")
sys.exit(0)
