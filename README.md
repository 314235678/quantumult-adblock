# 苹果手机去广告规则（Quantumult X）

一套为 **Quantumult X** 制作的去广告 / 反追踪规则，覆盖：

- 🍎 **Apple**：iAd、Apple Ads、Apple News 广告、各 App 分析埋点
- 🌐 **Google / Meta / X(Twitter) / Telegram** 等国外常用软件
- 📱 **抖音 / TikTok / 穿山甲(Pangle)**、**微信 / QQ / 广点通(GDT)**、**百度 / 阿里(淘宝·UC)** 等国产常用软件
- 🎯 通用移动广告 SDK（AdMob、Unity Ads、AppLovin、Mintegral、IronSource、Chartboost、Vungle、InMobi…）与追踪/分析 SDK（AppsFlyer、Adjust、Branch、友盟、神策、TalkingData、Firebase…）

规则采用 **Quantumult X 原生规则格式**（`HOST-SUFFIX/HOST-KEYWORD/IP-CIDR + REJECT`），
在代理层直接拒绝请求，**无需开启 MITM 也能拦掉"可分离的广告/追踪域名"**，
并通过订阅的 `update-interval` + GitHub Actions 实现**定时自动更新**。

---

## 一、文件说明

| 文件 | 作用 |
|------|------|
| `adblock.list` | **① 域名拒绝层最终清单**（Quantumult X 直接订阅这个文件，无需 MITM） |
| `rewrite.list` | **② 应用内去广告层最终清单**（多源合并版，需 MITM，单条订阅） |
| `custom.txt` | 本地自定义域名层（按 App 分类，可随意增删） |
| `sources.txt` | ① 的上游合并源（AdGuard 基础清单 + blackmatrix7 广告规则 + 217heidai 广告过滤 + Apple 专用清单） |
| `rewrite_sources.txt` | ② 的上游合并源（墨鱼 + 黑名单7 + deezertidal + Moli-X + chxm1023 + fmz200 + app2smile 等 30 个） |
| `wechat_rewrite.conf` | **③ 微信生态专用层**（本地固化，优先级最高）：公众号文章去广告 + 50 余条小程序去广告 |
| `build.py` | 把 custom.txt + sources.txt / rewrite_sources.txt / wechat_rewrite.conf 合并、去重、冲突裁决，生成 adblock.list 与 rewrite.list |
| `verify.py` | **构建产物校验**：数量下限、语法合法性、私有 IP 段、过宽关键词、规则冲突、HTML 污染 |
| `.github/workflows/update.yml` | 定时 + 规则源变更时自动重建并校验，通过后提交回仓库 |
| `quantumult-snippet.conf` | 直接贴进 Quantumult X 配置文件的订阅片段（仅两条链接） |

---

## 二、在 Quantumult X 中使用

规则分两层，**建议都加**。已合并成**两条订阅链接**（完整片段见 `quantumult-snippet.conf`，直接复制粘贴）：

**① 域名拒绝层（无需 MITM，立即生效，约 3 万条）**
覆盖 Apple / Google / Meta / X / 抖音·TikTok / 微信·腾讯 / 百度 / 阿里 + 通用广告&追踪 SDK。
在配置文件的 `[rule_remote]` 段加入：
```
https://raw.githubusercontent.com/314235678/quantumult-adblock/main/adblock.list, tag=去广告域名层, update-interval=86400, enabled=1
```

**② 应用内广告深度去除层（多源合并，需 MITM，约 3300 条有效规则）**
去除微信小程序、微博、B站、网易云、YouTube、Reddit、贴吧、知乎、Keep、闲鱼、小红书、
高德、滴滴、美团等 **App 内的信息流/开屏/界面广告**
（这类广告我那份域名清单拦不掉，只能靠 MITM + 复写）。
在配置文件的 `[rewrite_remote]` 段加入**一条**链接即可（30 个上游已合并去重）：
```
https://raw.githubusercontent.com/314235678/quantumult-adblock/main/rewrite.list, tag=应用内去广告, update-interval=86400, enabled=1
```
> `rewrite.list` 内每个来源都自带 `hostname` 声明，Quantumult X 订阅后会**自动**把这些域名加入 MitM，
> **无需你手动写 `[mitm]` 段**。你只需在 QX 里打开 MitM 开关并安装信任 CA 证书即可。

> 提示：① 是"拒绝连接"型，**不影响** Quantumult X 的代理/节点分流。
> 两条订阅的 `update-interval=86400` 每 24 小时自动拉取（想更"实时"改 `3600`），也可手动点"更新"立即刷新。
>
> 不想编辑配置文件？在手机 UI 的「引用」按钮里分别粘贴上面两个链接也完全等效。

---

## 三、如何托管（订阅需要 URL）

任选其一：

- **推到 GitHub**（最简单，本仓库已配好 GitHub Actions 自动更新）：
  ```bash
  cd quantumult-adblock
  git init
  git add -A
  git commit -m "init apple ads block"
  gh repo create quantumult-adblock --public   # 或用你已有的账号
  git branch -M main
  git push -u origin main
  ```
  订阅地址即 `https://raw.githubusercontent.com/314235678/quantumult-adblock/main/adblock.list`
  （应用内去广告层为 `https://raw.githubusercontent.com/314235678/quantumult-adblock/main/rewrite.list`）
- **GitHub Gist**：把 `adblock.list` 内容建一个公开 Gist，订阅其 raw 链接。
- **任意静态托管**：如 Cloudflare Pages、Vercel、对象存储，只要能返回纯文本即可。

---

## 四、自动更新是怎么实现的

1. **Quantumult X 自带**：订阅上的 `update-interval` 会让客户端按周期重新拉取 `adblock.list` / `rewrite.list`，无需你手动操作。
2. **清单内容也会变新**：`.github/workflows/update.yml` 会在两种情况下自动重建：
   - **定时**：每天北京时间 00:00 跑一次，重新抓取全部上游（AdGuard 每日更新广告域名，blackmatrix7 / 217heidai / 墨鱼也在持续维护）；
   - **规则源变更时**：改过 `custom.txt` / `sources.txt` / `rewrite_sources.txt` / `wechat_rewrite.conf` / `build.py` 并 push，立刻重建（生成产物本身不在触发列表里，不会自激循环）。
3. **先校验再提交**：重建后 `verify.py` 会检查数量下限、语法合法性、私有 IP 段、过宽关键词、规则冲突、HTML 污染。
   **任何一项不通过就中断，不会把坏清单推给你**——这是防止上游集体抽风时订阅变空的关键一环。

想手动更新清单内容？本地跑：
```bash
python3 build.py && python3 verify.py
```
> 注意：本机直接跑 `build.py` 需要能访问 GitHub（抓取上游）。国内网络可先设代理：
> `export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897`
> 清单的"自动变新"主要由 GitHub Actions 云端完成，你不常在本地跑也没关系。

---

## 五、重要实话：哪些广告"拦不彻底"

网络层（域名拒绝）+ 墨鱼复写（MITM）已经能覆盖绝大多数场景，但仍有硬限制：

- **抖音 / TikTok 信息流广告**：目前**没有可靠的规则**能清掉（墨鱼也没有抖音专用规则）。
  原因是抖音的信息流广告与正常视频走**同一接口、且启用了证书锁定**，无法区分也无法拦截，
  强行拦会刷不出内容。只能靠 App 内"减少个性化推荐"等开关缓解。
- **微信朋友圈广告**：**做不到**，不是规则没写对，是原理上行不通。
  朋友圈信息流走微信自研的 **mmtls 私有协议**（在 TLS 1.3 草案上魔改，公钥内置、不校验证书链，
  外层再用业务层二次加密），Quantumult X 的 MITM 只能拿到密文，规则层没有切入点。
  网上流传的"圈X去朋友圈广告"规则，要么是引流，要么是顺手把朋友圈图片 CDN（`wxsnsdy.wxs.qq.com`）
  一起 reject —— 广告没了，图也没了。
- **微信公众号信息流广告**：**做不到**。与正常文章走同一接口、服务端下发，无法区分。
  公众号**文章内**广告是另一回事，见下方（可去除）。
- **微信小程序广告**：**可去除**。已在 `wechat_rewrite.conf` 固化 50 余条接口级规则，
  覆盖企迈点单、永辉、多点、星巴克、麦当劳、必胜客、猫眼、横店、顺丰、申通、中通、
  滴滴、罗森、M Stand、享道、拼多多、哈啰等；但小程序**开屏广告需逐个适配**，
  没有通用解。想更彻底可在微信里开「青少年模式」，iOS 实测能去掉小程序开屏与文章内广告。

- **Telegram**：设计上几乎无广告（仅频道"赞助消息"走主接口），网络拦截收益极低，不拦。
- **X / Twitter 推广推文**：推广推文与正常时间线同接口（`api.twitter.com`），
  域名层只能拦掉 `ads-twitter.com` / `analytics.twitter.com` 等可分离的广告/统计域名，
  无法清掉时间线里的推广推文本身。

一句话：**开屏、横幅、SDK、追踪埋点、以及一批 App 的界面/信息流广告能被清掉；
但抖音信息流、微信公众号图文广告、Twitter 推广推文这类"同接口+证书锁定"的原生广告，
单靠 Quantumult X 规则无法 100% 清空**——那是 App 服务端下发的，超出网络规则能力。

---

## 六、自定义 / 维护

- 想加某个域名：直接写进 `custom.txt` 一行一个，跑 `build.py && verify.py` 重新生成并自检。
- 想接更全的上游：编辑 `sources.txt` 末尾的可选区（anti-AD 11 万条 / hagezi pro 20 万条 / oisd small 5.9 万条），
  一次只开一个 —— 规则数超过约 5 万条后，低端机会明显卡顿、续航下降。
- 想加某个 App 的去广告重写：优先加到 `rewrite_sources.txt`（会随上游自动更新）；
  若是自己写的、或需要修上游的错，加到 `wechat_rewrite.conf` 这类本地固化文件（永远排最前、不会被上游覆盖）。
- 误伤了某个正常功能：把对应域名从 `custom.txt` 删除并重建即可；若来自上游，
  在 `build.py` 的 `REWRITE_DROP_PATTERNS`（重写层）或 `KEYWORD_DENY`（关键词层）里登记剔除规则。

---

## 七、微信去广告专项（`wechat_rewrite.conf`）

微信生态的规则单独固化在 `wechat_rewrite.conf`，由 `build.py` **优先合并到 `rewrite.list` 最前面**。
单独放本地而不是订阅上游，是为了三件事：

**1. 修掉上游"已失效却抢占 URL"的坏规则**

`mp.weixin.qq.com/mp/getappmsgad` 这个接口，之前被 **4 条规则同时匹配**：

| 来源 | 写法 | 状态 |
|------|------|------|
| ddgksf2013 `Applet.conf` | `response-body advertisement → 替换成作者名` | 作者标注【已失效】 |
| ddgksf2013 `WeChat.conf` | 同上 | 作者标注【已失效】 |
| fmz200 `rewrite.snippet` | 同上 | 破坏性 hack |
| chxm1023 `AppAd.conf` | `script-response-body wxgzhad.js` | ✅ 真正有效 |

前三条排在前面，会把第四条盖住，导致公众号文章去广告**实际不生效**。
现在 `build.py` 用 `REWRITE_DROP_PATTERNS` 把前三条统一剔除，并对全量规则**按行去重**，
同一个 URL 只保留一条规则。

**2. 补齐仓库缺失的小程序规则**

从 `fmz200/wool_scripts` 的 `WeChatMiniAds.plugin` 转换并筛选出 50 余条接口级规则
（已按 Quantumult X 语法修正，并把上游没转义的 `?` 正确转义）。

**3. 隔离高风险规则**

上游同批规则里有 9 条是「整站 / 整段 CDN / 首页主接口」级 reject，开了会打断正常功能
（极兔整站、哈啰整站、货拉拉图片 CDN、如家首页三接口等）。这些统一移到文件末尾的
**风险区**并默认注释，需要时自行开启。

> 文件内还有微信广告素材 CDN（`wxsnsdy.wxs.qq.com` 等）三条，因有人反馈会影响朋友圈图片加载，
> 同样默认注释并附了验证方法。

---

## 八、规则规模与性能

当前产物规模（每次构建后 `verify.py` 会打印实际值）：

| 清单 | 规模 | 构成 |
|------|------|------|
| `adblock.list` | 约 2.07 万条 | HOST-SUFFIX 约 2.0 万 + HOST-KEYWORD 约 270 + IP-CIDR 约 570 |
| `rewrite.list` | 约 3200 条有效规则 | 31 个上游 + 1 个本地固化层，去重后；MitM 域名约 1500 个 |

这个量级是刻意控制的：Quantumult X 启动时要把全部规则载入内存逐条匹配，
**5 万条以上**在低端机上会出现启动变慢、滚动掉帧、续航下降。如果你想要更极致的覆盖，
`sources.txt` 末尾有 anti-AD / hagezi / oisd 可选源，但请一次只开一个，并自行观察耗电。

嫌 3 万条太多？把 `sources.txt` 里的「217heidai」或「blackmatrix7」注释掉任意一条，
规模会回到 1.5 万条左右，覆盖仍然远超改造前的 1400 条。

---

## 九、构建链路做过的关键修复

规则本身之外，构建脚本曾经有几个"看不见但致命"的问题，现已全部修掉：

| 问题 | 后果 | 修复 |
|------|------|------|
| `parse_line` 只认 `HOST`/`DOMAIN` 前缀，不认 `IP-CIDR,x,x,策略` | 上游**486 条 IP 规则被静默丢弃**，规则数长期偏低 | 显式解析 `IP-CIDR`/`IP-CIDR6`，并统一改写为 `REJECT` |
| IP 规则不带 `no-resolve` | QX 对每条域名规则都触发一次 DNS 解析，白白拖慢 | 统一补 `,no-resolve` |
| 上游 IP 清单里混有私有网段（如 `10.72.25.0/24`） | 照收会**把你自己的局域网整段墙掉** | 过滤私有/保留/组播段，以及掩码短于 /16 的超大段 |
| `HOST-KEYWORD` 无任何约束 | 一旦上游出现 `ad`、`api` 这类宽泛词，会大面积误杀正常网站 | 长度 <4 或命中黑名单的词一律丢弃 |
| 同一 URL 既有脚本重写又有整条拒绝 | 整条拒绝会盖掉脚本，导致 App 页面空白（如滴滴动态、百度地图、什么值得买） | 「脚本优先于整条拒绝」，按 URL 模式自动裁决（本次处理 5 个模式） |
| CI 只提交 `adblock.list` | 重写层的自动更新从来没生效过，订阅收到的永远是首次推送的旧版 | 改为两个产物一起提交 |
| CI 无任何校验 | 上游集体抽风时会直接把空清单推给订阅者 | 增加 `verify.py` 闸门，不通过即中断 |
| 旧脚本 `build_rewrite_only.py` 残留 | 不做清洗/去重/剔除，跑一次就会把上述修复全部覆盖掉 | 已删除 |
| AdGuard **路径级**规则被当成整域规则 | `\|\|github.com/_private/browser/stats` 被转成 `HOST-SUFFIX,github.com,REJECT` —— **因为一条统计接口把整个 GitHub 封了** | 带 `/路径` 的规则一律丢弃（域名层无法精确表达），本轮丢弃 14360 条 |
| AdGuard **修饰符**规则被兜底逻辑误判 | `$csp=... www.googletagmanager.com jsdelivr.net` 这类行被取末位 token，生成 `HOST-SUFFIX,jsdelivr.net,REJECT` —— **把 CDN 封了** | 删除「取末位 token 当域名」的兜底，无法识别的行一律丢弃 |
| `jsonjq-response-body` / `echo-response` 等 QX 不支持的动作 | 导入订阅时 QX 报「N 个问题存在于子资源」并逐条忽略 | 建立动作白名单，白名单外全部剔除（本轮剔 38 条） |

---

## 十、事故记录：一次「去广告把自己订阅封掉」的事故

**现象**：订阅本仓库的 `rewrite.list` 后，QX 提示「58 个问题存在于子资源」；
随后**其他所有订阅都显示「无法连接服务器」**。取消勾选重写层仍不恢复，取消勾选**分流层**才恢复。

**根因**（两个缺陷叠加，都在构建脚本里）：

1. 上游 `217heidai/adblockfilters` 里有 `||github.com/_private/browser/stats` 这种**路径级**规则。
   `parse_line` 把它当整域处理，生成了 `HOST-SUFFIX,github.com,REJECT`。
2. AdGuard 的**修饰符**规则（`$csp=` / `$denyallow=` 等）里含有空格，
   旧兜底逻辑「取最后一个空白分隔的 token 当域名」把 `jsdelivr.net` 也封了。

结果就是：`github.com`、`raw.githubusercontent.com`、`jsdelivr.net` 全被自己的规则拒绝 ——
而这些正是**所有订阅与重写脚本的托管地**。本仓库 144 个脚本里有 **134 个**在 GitHub 上，
拉不到就直接表现为「子资源有问题」+「订阅连不上」。

**修复**：
- 路径级 AdGuard 规则不再降级成整域规则，直接丢弃（宁可少拦，不可错拦）；
- 删除危险的兜底解析；
- 新增 `CRITICAL_ALLOW` 基础设施白名单，任何上游都封不到 GitHub / jsDelivr / ghproxy 等；
- 重写层的 MitM 域名同样排除这些域名；
- `verify.py` 增加**自洽性检查**：域名层若拦掉了重写脚本的托管域名，或 MitM 覆盖了订阅域名，直接判定构建失败。

**你自己如何自查这类问题**：
1. 订阅更新失败时，先停用**域名层**（`[rule_remote]` 那条），不要只停重写层 —— 主因通常在分流。
2. 打开 QX → 引用 → 找到报错的资源 → 长按复制链接，看它的域名是否在你订阅的规则里被 `REJECT`。
3. 若用的是本仓库，直接看 Actions 里最近一次的 `verify.py` 输出，`[信息]` 行会打印「被域名层拦截的脚本托管域名数」，正常应为 0。



