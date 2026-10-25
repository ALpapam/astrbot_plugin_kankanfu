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
| `min_bookmarks` | int | 2000 | 最低收藏数，越高越热，用于过滤低质图 |
| `max_results` | int | 5 | 抓取检索结果**页数**（每页 30 条，默认 5 页 = 150 条）。Pixiv 热门排序并非严格按收藏数，需跨页抓取才能筛到高收藏作品 |
| `timeout_seconds` | int | 30 | 请求超时（5-120 秒） |
| `send_progress` | bool | true | 检索前是否先发一条「正在看看福」提示 |
| `show_info` | bool | true | 图片后是否附带作品信息（标题 / 收藏数 / 画师） |
| `cooldown_seconds` | int | 10 | 同一用户的请求冷却时间（秒），0 为不限制 |

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
2. 跨页（默认 5 页）按热度检索 `小穴` 标签；
3. 从合并结果里挑 **收藏数最高的** 且 **≥ min_bookmarks**、**有原图** 的作品（即“非低质图”）；
4. 下载原图（处理 pixiv 防盗链）发送给你，并附带作品信息。

## 常见问题

- **提示「还没有配置 Pixiv refresh_token」**：到插件配置填写 `refresh_token`。
- **提示「refresh_token 无效或已过期」**：token 失效，请重新获取并更新配置。
- **提示「被限流」**：请求太频繁，稍后再试或把 `cooldown_seconds` 调大。
- **没有获得够福的图**：本轮没检索到收藏数达标的作品，稍后再抽，或调低 `min_bookmarks`。
- **搜不到任何结果**：确认 `search_word` 没有带 `#` 前缀（例如 `#小穴` 会搜不到，应为 `小穴`）。
- **提示「Pixiv 暂时没有响应」且文案带括号详情**：括号内会给出服务端返回的真实原因（如 HTTP 400/403），可据此排查（代理、token 或参数）。

## 实现说明

- 认证：`POST https://oauth.secure.pixiv.net/auth/token`，用 `refresh_token` 换 `access_token`；
- 检索：`GET https://app-api.pixiv.net/v1/search/illust`，`word=小穴&search_target=partial_match_for_tags&filter=for_ios&sort=popular_desc`；
- 过滤：只保留 `total_bookmarks >= min_bookmarks` 且有原图的作品作为“非低质图”；
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

## 参考

- [AstrBot 插件开发指南](https://astrbot.app/dev/star/plugin-new.html)
- [pixivpy（Pixiv 社区客户端参考）](https://github.com/upbit/pixivpy)
- Pixiv app-api 公共接口文档：<https://app-api.pixiv.net/>