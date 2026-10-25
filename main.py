"""看看福插件：在 Pixiv 检索「#小穴」相关、热度高的非低质图并发送。

用户发送「看看福」时：
1. 用配置的 refresh_token 登录 Pixiv；
2. 在 app-api 上按热度（popular_desc）检索标签（默认 ``#小穴``）；
3. 从结果中挑第一张收藏数达标（非低质图）的作品；
4. 下载原图并发送给用户。

图片因 pixiv 防盗链无法直接以链接发送，插件会把原图字节写入临时文件后发送。
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .kankanfu.client import PixivClient, PixivError
from .kankanfu.formatter import (
    NO_TOKEN_TEXT,
    NOT_HOT_TEXT,
    PROGRESS_TEXT,
    RATE_LIMIT_TEXT,
    SEARCH_FAILED_TEXT,
    TOKEN_INVALID_TEXT,
    TOO_FREQUENT_TEMPLATE,
    format_artwork_info,
)
from .kankanfu.models import parse_artworks, pick_artwork

DEFAULT_SEARCH_WORD = "#小穴"


def _guess_image_filename(data: bytes) -> str:
    """根据文件头猜测图片文件名后缀。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image.png"
    if data.startswith(b"\xff\xd8"):
        return "image.jpg"
    if data.startswith(b"GIF8"):
        return "image.gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image.webp"
    if data.startswith(b"BM"):
        return "image.bmp"
    return "image.jpg"


def _get_str(data: Any, key: str) -> str:
    value = (data or {}).get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _get_int(data: Any, key: str, default: int, _min: int, _max: int) -> int:
    value = (data or {}).get(key, default)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(_min, min(_max, value))


def _get_bool(data: Any, key: str, default: bool) -> bool:
    value = (data or {}).get(key, default)
    if isinstance(value, bool):
        return value
    return default


class KankanFuPlugin(Star):
    """「看看福」插件的入口类。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config

        self._refresh_token = _get_str(config, "refresh_token")
        self._proxy = _get_str(config, "proxy")
        self._search_word = _get_str(config, "search_word") or DEFAULT_SEARCH_WORD
        self._min_bookmarks = _get_int(config, "min_bookmarks", 2000, 0, 100000)
        self._max_results = _get_int(config, "max_results", 30, 1, 300)
        self._timeout = _get_int(config, "timeout_seconds", 30, 5, 120)
        self._send_progress = _get_bool(config, "send_progress", True)
        self._show_info = _get_bool(config, "show_info", True)
        self._cooldown = _get_int(config, "cooldown_seconds", 10, 0, 600)

        self.client = PixivClient(
            refresh_token=self._refresh_token,
            timeout_seconds=float(self._timeout),
            proxy=self._proxy,
        )
        self._last_search_at: dict[str, float] = {}

    # ------------------------------------------------------------------
    # 指令
    # ------------------------------------------------------------------

    @filter.command("看看福")
    async def kankanku(self, event: AstrMessageEvent):
        """看看福：检索 #小穴 高热度图并发给你。"""
        sender_id = str(event.get_sender_id() or "")

        remaining = self._cooldown_remaining(sender_id)
        if remaining > 0:
            yield event.plain_result(TOO_FREQUENT_TEMPLATE.format(seconds=remaining))
            return

        if not self._refresh_token:
            yield event.plain_result(NO_TOKEN_TEXT)
            return

        if self._send_progress:
            yield event.plain_result(PROGRESS_TEXT)

        self._mark_search(sender_id)

        try:
            artworks = parse_artworks(
                await self.client.search_illusts(
                    word=self._search_word,
                    sort="popular_desc",
                    num_results=self._max_results,
                )
            )
        except PixivError as exc:
            logger.warning(f"[KankanFu] Pixiv 检索失败: {exc.message}")
            yield event.plain_result(self._error_text(exc))
            return
        except Exception:
            logger.error("[KankanFu] Pixiv 检索异常", exc_info=True)
            yield event.plain_result(SEARCH_FAILED_TEXT)
            return

        artwork = pick_artwork(artworks, self._min_bookmarks)
        if artwork is None:
            yield event.plain_result(NOT_HOT_TEXT)
            return

        # 下载原图
        try:
            data = await self.client.download_original(artwork.original_url)
        except PixivError as exc:
            logger.warning(f"[KankanFu] 图片下载失败: {exc.message}")
            yield event.plain_result(self._error_text(exc))
            return
        except Exception:
            logger.error("[KankanFu] 图片下载异常", exc_info=True)
            yield event.plain_result(SEARCH_FAILED_TEXT)
            return

        if not data:
            yield event.plain_result(SEARCH_FAILED_TEXT)
            return

        path = await asyncio.to_thread(self._save_temp_image, data)
        if path is None:
            yield event.plain_result(SEARCH_FAILED_TEXT)
            return

        yield event.image_result(path)

        if self._show_info:
            yield event.plain_result(format_artwork_info(artwork))

    # ------------------------------------------------------------------
    # 工具函数
    # ------------------------------------------------------------------

    @staticmethod
    def _save_temp_image(data: bytes) -> str | None:
        """把图片字节写入临时文件，返回路径（失败返回 None）。"""
        filename = _guess_image_filename(data)
        try:
            fd, raw_path = tempfile.mkstemp(suffix=Path(filename).suffix, prefix="kankanfu_")
            with __import__("os").fdopen(fd, "wb") as handle:
                handle.write(data)
            return raw_path
        except OSError:
            logger.error("[KankanFu] 写入临时图片失败", exc_info=True)
            return None

    def _cooldown_remaining(self, sender_id: str) -> int:
        if self._cooldown <= 0:
            return 0
        last = self._last_search_at.get(sender_id, 0.0)
        remaining = int(self._cooldown - (time.monotonic() - last))
        return max(0, remaining)

    def _mark_search(self, sender_id: str) -> None:
        self._last_search_at[sender_id] = time.monotonic()

    def _error_text(self, exc: PixivError) -> str:
        if "401" in exc.message or exc.status == 401 or "refresh_token" in exc.message:
            return self._with_detail(TOKEN_INVALID_TEXT, exc)
        if exc.status == 429:
            return RATE_LIMIT_TEXT
        return self._with_detail(SEARCH_FAILED_TEXT, exc)

    @staticmethod
    def _with_detail(base: str, exc: PixivError) -> str:
        """在基础文案后追加一行真实错误详情，便于排查（可能含有服务端原因）。"""
        message = exc.message or ""
        # 去掉无意义的通用前缀，只保留服务端给出的具体原因
        marker = "| "
        if marker in message:
            detail = message.split(marker, 1)[1].strip()
            if detail and len(detail) <= 200:
                return f"{base}\n（{detail}）"
        return base