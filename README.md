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
| `adblock.list` | **最终订阅清单**（Quantumult X 直接订阅这个文件） |
| `custom.txt` | 本地自定义域名层（按 App 分类，可随意增删） |
| `sources.txt` | 上游合并源（AdGuard 基础广告清单 + Apple 专用清单） |
| `build.py` | 把 custom.txt + sources.txt 合并去重，生成 adblock.list |
| `.github/workflows/update.yml` | 每日自动重建 adblock.list（定时更新） |
| `quantumult-snippet.conf` | 直接贴进 Quantumult X 配置文件的订阅片段 |

---

## 二、在 Quantumult X 中使用

1. 把 `adblock.list` 托管到一个可访问的 URL（见第三节）。
2. 打开 Quantumult X → 长按右下角小风车 → **配置文件 → 编辑**。
3. 找到（或新建）`[rule_remote]` 段落，把下面这行加进去（换成你的真实 URL）：

   ```
   https://raw.githubusercontent.com/你的用户名/quantumult-adblock/main/adblock.list, tag=AppleAds, update-interval=86400
   ```

   - `update-interval=86400`：每 24 小时自动拉取一次（想更"实时"可改成 `3600`）。
   - 也可以在 Quantumult X 里手动点"更新"立即刷新。
4. 保存，规则立即生效。

> 提示：这条规则是"拒绝连接"型，**不影响** Quantumult X 的代理/节点分流，只是把命中广告域名的请求丢弃。

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
  订阅地址即 `https://raw.githubusercontent.com/你的用户名/quantumult-adblock/main/adblock.list`
- **GitHub Gist**：把 `adblock.list` 内容建一个公开 Gist，订阅其 raw 链接。
- **任意静态托管**：如 Cloudflare Pages、Vercel、对象存储，只要能返回纯文本即可。

---

## 四、自动更新是怎么实现的

1. **Quantumult X 自带**：订阅上的 `update-interval` 会让客户端按周期重新拉取 `adblock.list`，无需你手动操作。
2. **清单内容也会变新**：`.github/workflows/update.yml` 每天运行一次 `build.py`，
   重新合并上游（AdGuard 每日都在更新广告域名），并把新版本 `adblock.list` 提交回仓库。
   这样你订阅的清单会**持续保持最新**，不是一份写死不动的静态列表。

想手动更新清单内容？本地跑：
```bash
python3 build.py
```

---

## 五、重要实话：哪些广告"拦不彻底"

网络层（域名拒绝）对**横幅广告、开屏广告、SDK 广告、追踪埋点**非常有效，
但下面这些情况**单靠 Quantumult X 规则无法彻底去除**，需要说明：

- **微信朋友圈 / 公众号信息流广告、抖音/TikTok 信息流广告**：
  这类广告与正常内容走**同一个域名、同一个接口**（如 `api.twitter.com`、
  `mmbiz`、`snssdk` 内容接口），且 App 普遍启用了**证书锁定（证书绑定）**，
  Quantumult X 即使开 MITM 也难以解密、更无法区分"这是广告还是正常内容"。
  强行按域名拦截会**直接让 App 刷不出内容**，所以本清单刻意**不拦这些主接口**，
  只拦它们"可分离的"广告/统计子域名（如广点通 `gdt.qq.com`、抖音 `ad.douyin.com`、
  Twitter `ads-twitter.com`）。
- **Telegram**：设计上几乎无广告（仅频道"赞助消息"走主接口），网络拦截收益极低，
  本清单对 Telegram 基本不拦截（避免误伤）。
- 真正"彻底"去信息流广告，通常需要：iOS「设置 → 隐私 → Apple 广告 → 关闭个性化广告」、
  各 App 内的"减少个性化推荐"开关，或越狱/巨魔环境下的专用插件（超出本规则范围）。

一句话：**本规则能让"广告请求"大幅减少、追踪被切断、开屏/横幅/SDK 广告明显变少，
但无法承诺把微信、抖音的信息流原生广告 100% 清空**——那是 App 自己服务端下发的，
不在你 iPhone 的网络规则能力范围内。

---

## 六、自定义 / 维护

- 想加某个域名：直接写进 `custom.txt` 一行一个，跑 `build.py` 重新生成。
- 想接更全的上游：编辑 `sources.txt`（已注释掉一个约 29 万条的超大型列表，
  按需启用，但会拖慢 Quantumult X）。
- 误伤了某个正常功能：把对应域名从 `custom.txt` 删除并重建即可。
