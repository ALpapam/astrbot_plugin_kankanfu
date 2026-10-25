# 看看福（AstrBot 插件）

发送「看看福」，插件会在 Pixiv 上检索 **#小穴** 相关词条，只挑 **收藏数足够高（热度高的非低质图）** 的作品，下载原图发送给你，并附带作品信息。

> ⚠️ 本插件仅用于合法的个人学习与测试用途。请自觉遵守 Pixiv 服务条款、作品版权与当地法律法规，请勿将内容用于任何违反规定的场景。作者不对用户使用行为负责。

## 效果

```
👀 正在看看福，请稍等…
[图片]
📕 例の作品
ID: 123 | 收藏 5000 | 浏览 30000
画师: テスト絵師
```

## 安装

1. 将整个 `astrbot_plugin_kankanfu` 目录放入 AstrBot 的 `data/plugins/` 下：

   ```
   AstrBot/data/plugins/astrbot_plugin_kankanfu/
   ```

2. 在 AstrBot WebUI 的「插件」页面点击刷新 / 重载插件。
3. **配置 Pixiv refresh_token**（必填）：在 WebUI 插件配置的 `refresh_token` 项填入你的 Pixiv refresh_token。
4. 插件依赖 `aiohttp`，AstrBot 已内置；若缺失可执行 `pip install -r requirements.txt`。

## 配置

在 WebUI 的插件配置中修改：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `refresh_token` | string | 空 | **必填**。Pixiv 账号的 refresh_token |
| `proxy` | string | 空 | 访问 pixiv.net 使用的代理，如 `http://127.0.0.1:7890` |
| `search_word` | string | `小穴` | Pixiv 检索关键词（标签）。**注意：不要带 `#` 前缀**，否则搜不到结果 |
| `related_words` | string | `マンコ,オナニー,くぱぁ,パイパン,裸足,足裏` | 相关扩展检索词（逗号分隔）。插件会用 `search_word` 和这里每个词**分别**查 Pixiv 热门预览再合并去重，把“高收藏非AI”候选池扩大数倍（实测可达上百张）、减少重复。可自行增删 |
| `min_bookmarks` | int | 2000 | 最低收藏数，越高越热，用于过滤低质图 |
| `max_results` | int | 5 | 每个检索词的抓取页数（热门预览每页约 30 条）。多词合并后候选可到上百张 |
| `timeout_seconds` | int | 30 | 请求超时（5-120 秒） |
| `send_progress` | bool | true | 检索前是否先发一条「正在看看福」提示 |
| `show_info` | bool | true | 图片后是否附带作品信息（标题 / 收藏数 / 画师） |
| `cooldown_seconds` | int | 10 | 同一用户的请求冷却时间（秒），0 为不限制 |
| `max_photo_bytes` | int | 9 | 发送前允许的图片大小上限（MB，1-20），超出会自动压缩后再发送，避免平台「图片过大」报错 |
| `search_rating` | string | `r18` | 检索内容范围（选择框）：`r18`（仅 R-18，默认）、`全年龄`（不含限制级）、`r18g`（仅 R-18G）。热门预览里同词条可能以某一分级为主，若选某范围总是「没有够福的图」，可换成别的范围 |
| `exclude_ai` | bool | true | 是否过滤掉 AI 生成的作品。Pixiv 返回的作品带 `illust_ai_type` 标记，开启后只发送非 AI 生成的作品 |
| `no_repeat` | bool | true | 短时间内尽量不发送重复的图。挑图时优先避开最近已发过的作品；若候选全被发过则回退发一张以保证出图 |
| `memory_sent_count` | int | 30 | 「不重复」记住最近发送过的图数量（1-500），越大越不易重复 |

> 国内服务器通常需要给 `proxy` 配置代理才能访问 `pixiv.net`。

## 如何获取 Pixiv refresh_token

Pixiv 没有公开的“网页登录拿 token”入口，社区通用的取法：

1. 在浏览器登录 `pixiv.net`；
2. 打开开发者工具（F12）→ Console；
3. 执行社区常用的 refresh_token 获取脚本（可搜索“pixiv refresh_token 获取 / pixivpy 登录”），
   或使用支持 Pixiv OAuth 的第三方工具把一次性 code 兑换成 refresh_token；
4. 将得到的 `refresh_token` 填入插件配置。

> 该 token 本质是你的 Pixiv 会话凭证，请勿泄露给他人。

## 使用

直接发送 `看看福` 即可（是否需要 @机器人 或唤醒前缀取决于 AstrBot 配置）。插件会：

1. 用 refresh_token 登录 Pixiv；
2. 用 `search_word` + `related_words` 每个词分别走 Pixiv 官方「热门预览」接口检索，合并去重为一个大候选池
   （该接口返回被广泛收藏的经典高热度、非 AI 靠前的作品，无需会员）；
3. 从结果里按 `search_rating` 分级、`exclude_ai` 过滤 AI，并筛出 **收藏数 ≥ min_bookmarks** 且**有原图**的作品
   （即“非低质图”），优先避开最近发过的图，在其中**随机挑 1 张**发送；
4. 下载原图（处理 pixiv 防盗链）发送给你，并附带作品信息。

## 常见问题

- **提示「还没有配置 Pixiv refresh_token」**：到插件配置填写 `refresh_token`。
- **提示「refresh_token 无效或已过期」**：token 失效，请重新获取并更新配置。
- **提示「被限流」**：请求太频繁，稍后再试或把 `cooldown_seconds` 调大。
- **没有获得够福的图**：本轮没检索到收藏数达标的作品（已自动兼容多 P 作品）。先确认「最低收藏数」是不是太高、`search_word` 是否带 `#`；改完配置**无需重载插件**，直接再发一条「看看福」即可生效。若仍失败再调低 `min_bookmarks`。
- **搜不到任何结果**：确认 `search_word` 没有带 `#` 前缀（例如 `#小穴` 会搜不到，应为 `小穴`）。
- **提示「Pixiv 暂时没有响应」且文案带括号详情**：括号内会给出服务端返回的真实原因（如 HTTP 400/403），可据此排查（代理、token 或参数）。

## 实现说明

- 认证：`POST https://oauth.secure.pixiv.net/auth/token`，用 `refresh_token` 换 `access_token`；
- 检索：`GET https://app-api.pixiv.net/v1/search/popular-preview/illust`，`word=小穴&search_target=partial_match_for_tags&filter=for_ios`，
  这是 Pixiv 专门给免费账号返回「热门预览」的高收藏作品接口（非会员即可访问、无需会员细分）；对 `search_word` 与 `related_words` 每个词各查一次并按作品 ID 合并去重，扩大候选池；
- 过滤：按 `search_rating` 分级、`exclude_ai` 排除 AI 后，筛出 `total_bookmarks >= min_bookmarks` 且有原图的作品作为“非低质图”，再随机挑一张发送；
- 原图提取：依次尝试单 P 的 `meta_single_page.original_image_url`、多 P 的 `meta_pages[0].image_urls.original`、以及顶层 `image_urls`（large/medium）回退，确保多 P 收藏大户也能识别；
- 下载：`GET https://i.pximg.net/{urls.original}`，携带 `Referer: https://www.pixiv.net/` 与鉴权头处理防盗链；
- 图片以字节写入临时文件后发送，避免平台无法访问 pixiv 图片链接；
- 只依赖 AstrBot 插件 API 与 `aiohttp`，不写入任何持久化数据。

## 目录结构

```
astrbot_plugin_kankanfu/
├── main.py                  # 插件入口、指令处理
├── metadata.yaml            # 插件元数据
├── _conf_schema.json        # WebUI 配置 schema
├── requirements.txt
├── kankanfu/
│   ├── client.py            # Pixiv 异步客户端（认证/检索/下载）
│   ├── models.py            # app-api 响应解析与热度过滤
│   ├── formatter.py         # 输出文案格式化
│   └── __init__.py
└── tests/                   # 离线单元测试（不访问网络）
```

## 测试

在插件目录运行：

```bash
python -m pytest tests -q
```

测试使用本地 stub 模拟 AstrBot API，不访问 Pixiv。

> 若你本机装了 `hydra`（其内置的 `hydra_pytest` 插件因 antlr 版本问题无法加载），
> 可能要用 `python -m pytest tests -q -p no:hydra_pytest`；正常 AstrBot 环境不受影响。

## 更新日志

- **v0.0.17**：**扩大搜索范围、减少重复问题**。热门预览单词只返回固定几十张，用几次必重复。新增
  `related_words` 配置：用 `search_word` + 每个相关词**分别**查热门预览再按作品 ID 合并去重，把“高收藏
  非AI”候选池扩大到数百张（实测 5-7 个相关词能合并出 120-150 张），配合上一版的 `no_repeat` 明显降低重复。
- **v0.0.16**：新增「短时间内不重复发图」功能。配置 `no_repeat`（默认开启）+ `memory_sent_count`
  （默认记住最近 30 张），挑图时优先避开最近已发过的作品；若候选全被发过则回退发一张以保证出图。
- **v0.0.15**：**修复「没有够福的图」**。根因：`search/illust` 的 `popular_desc` 排序返回的是“刚上传的近期低收藏/AI 图”，高收藏作品排不进来。现改为走 Pixiv 官方「热门预览」接口 `search/popular-preview/illust`，免费账号即可拿到该词条下被广泛收藏的经典高收藏作品（带 `illust_ai_type` 标记），配合分级/非 AI/收藏/随机挑图，各配置都能稳定出图。
- **v0.0.14**：新增「过滤 AI 生成作品」开关 `exclude_ai`（默认开启）。Pixiv 作品带
  `illust_ai_type` 标记，开启后只发送非 AI 生成的作品，避免发到 AI 图。
- **v0.0.13**：新增「检索内容范围」选择框配置 `search_rating`，可选 `r18`（默认）/`全年龄`/`r18g`，
  在面板配置里下拉切换即可；检索后按作品的 R-18 / R-18G 标签过滤，再挑一张发送。
- **v0.0.12**：发送前自动压缩超大图片。Telegram 单张照片约 10MB 上限，
  当原图超过 `max_photo_bytes`（默认 9MB）时，用 Pillow 自动降质/缩尺寸压到范围内后再发送，
  避免「图片过大发送失败」。若 Pillow 不可用则按原始尺寸发送。
- **v0.0.11**：改为在符合热度标准（收藏达标 + 有原图）的作品里**随机挑 1 张**，
  不再固定发收藏数最高的同一张，避免每次都是同一幅图。
- **v0.0.10**：修复「总是提示没有找到够福的图」。根因：`search_illusts` 直接返回
  `illusts` 列表，而 `parse_artworks` 只接受带 `illusts` 键的响应字典，导致所有作品
  都被解析成 0 条。现兼容字典与裸列表两种入参（新增回归测试）。

## 参考

- [AstrBot 插件开发指南](https://astrbot.app/dev/star/plugin-new.html)
- [pixivpy（Pixiv 社区客户端参考）](https://github.com/upbit/pixivpy)
- Pixiv app-api 公共接口文档：<https://app-api.pixiv.net/>