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
| `rewrite.list` | **② 应用内去广告层最终清单**（墨鱼规则合并版，需 MITM，单条订阅） |
| `custom.txt` | 本地自定义域名层（按 App 分类，可随意增删） |
| `sources.txt` | ① 的上游合并源（AdGuard 基础广告清单 + Apple 专用清单） |
| `rewrite_sources.txt` | ② 的上游合并源（墨鱼 18 个 App 重写规则链接） |
| `build.py` | 把 custom.txt + sources.txt / rewrite_sources.txt 合并去重，生成 adblock.list 与 rewrite.list |
| `.github/workflows/update.yml` | 每日自动重建 adblock.list 与 rewrite.list（定时更新） |
| `quantumult-snippet.conf` | 直接贴进 Quantumult X 配置文件的订阅片段（仅两条链接） |

---

## 二、在 Quantumult X 中使用

规则分两层，**建议都加**。已合并成**两条订阅链接**（完整片段见 `quantumult-snippet.conf`，直接复制粘贴）：

**① 域名拒绝层（无需 MITM，立即生效）**
覆盖 Apple / Google / Meta / X / 抖音·TikTok / 微信·腾讯 / 百度 / 阿里 + 通用广告&追踪 SDK。
在配置文件的 `[rule_remote]` 段加入：
```
https://raw.githubusercontent.com/314235678/quantumult-adblock/main/adblock.list, tag=去广告域名层, update-interval=86400, enabled=1
```

**② 应用内广告深度去除层（墨鱼 ddgksf2013，需 MITM）**
去除微信小程序、微博、B站、网易云、YouTube、Reddit、贴吧、Keep、闲鱼等 **App 内的信息流/开屏/界面广告**
（这类广告我那份域名清单拦不掉，只能靠 MITM + 复写）。
在配置文件的 `[rewrite_remote]` 段加入**一条**链接即可（已把墨鱼 18 个 App 规则合并）：
```
https://raw.githubusercontent.com/314235678/quantumult-adblock/main/rewrite.list, tag=墨鱼应用内去广告, update-interval=86400, enabled=1
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
2. **清单内容也会变新**：`.github/workflows/update.yml` 每天运行一次 `build.py`，
   重新合并上游（AdGuard 每日都在更新广告域名；墨鱼也会更新各 App 复写规则），并把新版本 `adblock.list` 与 `rewrite.list` 提交回仓库。
   这样你订阅的清单会**持续保持最新**，不是一份写死不动的静态列表。

想手动更新清单内容？本地跑：
```bash
python3 build.py
```
> 注意：本机直接跑 `build.py` 需要能访问 GitHub（抓取上游）。清单的"自动变新"主要由 GitHub Actions 云端完成，你不常在本地跑也没关系。

---

## 五、重要实话：哪些广告"拦不彻底"

网络层（域名拒绝）+ 墨鱼复写（MITM）已经能覆盖绝大多数场景，但仍有硬限制：

- **抖音 / TikTok 信息流广告**：目前**没有可靠的规则**能清掉（墨鱼也没有抖音专用规则）。
  原因是抖音的信息流广告与正常视频走**同一接口、且启用了证书锁定**，无法区分也无法拦截，
  强行拦会刷不出内容。只能靠 App 内"减少个性化推荐"等开关缓解。
- **微信朋友圈 / 公众号信息流广告**：微信小程序广告、部分界面广告可被墨鱼 `Applet.conf` 等
  复写去除；但**公众号图文信息流广告的复写规则已失效**（墨鱼标注），目前无解。
- **Telegram**：设计上几乎无广告（仅频道"赞助消息"走主接口），网络拦截收益极低，不拦。
- **X / Twitter 推广推文**：推广推文与正常时间线同接口（`api.twitter.com`），
  域名层只能拦掉 `ads-twitter.com` / `analytics.twitter.com` 等可分离的广告/统计域名，
  无法清掉时间线里的推广推文本身。

一句话：**开屏、横幅、SDK、追踪埋点、以及一批 App 的界面/信息流广告能被清掉；
但抖音信息流、微信公众号图文广告、Twitter 推广推文这类"同接口+证书锁定"的原生广告，
单靠 Quantumult X 规则无法 100% 清空**——那是 App 服务端下发的，超出网络规则能力。

---

## 六、自定义 / 维护

- 想加某个域名：直接写进 `custom.txt` 一行一个，跑 `build.py` 重新生成。
- 想接更全的上游：编辑 `sources.txt`（已注释掉一个约 29 万条的超大型列表，
  按需启用，但会拖慢 Quantumult X）。
- 误伤了某个正常功能：把对应域名从 `custom.txt` 删除并重建即可。
