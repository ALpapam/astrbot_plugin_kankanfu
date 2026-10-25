"""输出文案与作品信息格式化。

该模块只依赖标准库，便于脱离 AstrBot 单独测试。
"""

from __future__ import annotations

from .models import Artwork

#: 没有配置 refresh_token。
NO_TOKEN_TEXT = (
    "**看看福失败了**\n\n"
    "还没有配置 Pixiv refresh_token，请到插件配置里填写后再试～\n"
    "获取方式参见插件说明（README）。"
)

#: token 无效 / 失效。
TOKEN_INVALID_TEXT = (
    "**看看福失败了**\n\n"
    "Pixiv refresh_token 无效或已过期，请到插件配置里重新获取再试～"
)

#: 网络 / Pixiv 服务异常。
SEARCH_FAILED_TEXT = (
    "**看看福失败了**\n\n"
    "Pixiv 暂时没有响应，请稍后再试；如果经常失败，可以检查网络/代理设置，"
    "或在插件配置中填写可用的 refresh_token。"
)

#: Pixiv 被限流。
RATE_LIMIT_TEXT = (
    "**看看福失败了**\n\n"
    "Pixiv 请求太频繁被限流了，请等一会再试～"
)

#: 找不到符合热度标准的作品。
NOT_HOT_TEXT = (
    "**没有找到够福的图**\n\n"
    "本轮没有检索到收藏数够高的作品，可以稍后再抽，或到插件配置里调低 "
    "「最低收藏数」再试～"
)

#: 冷却提示。
TOO_FREQUENT_TEMPLATE = "别急，福要慢慢找～请 {seconds} 秒后再试。"

#: 正在检索的提示。
PROGRESS_TEXT = "👀 正在看看福，请稍等…"


def format_artwork_info(artwork: Artwork) -> str:
    """把作品信息格式化为一行文本。"""
    return (
        f"📕 {artwork.title}\n"
        f"ID: {artwork.illust_id} | 收藏 {artwork.total_bookmarks} | "
        f"浏览 {artwork.total_view}\n"
        f"画师: {artwork.user_name}"
    )