"""Pixiv 作品模型与热度过滤工具。

该模块只依赖标准库，便于脱离 AstrBot 单独测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


@dataclass(slots=True)
class Artwork:
    """一条 Pixiv 作品（用于发送的图片）。"""

    illust_id: int
    title: str
    page_count: int
    total_bookmarks: int
    total_view: int
    user_name: str
    page_url: str
    original_url: str
    tags: list[str]

    @property
    def is_multi_page(self) -> bool:
        """是否为多 P 作品（只取第一张原图）。"""
        return self.page_count > 1


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _extract_tags(data: dict[str, Any]) -> list[str]:
    tags = data.get("tags")
    if not isinstance(tags, list):
        return []
    result: list[str] = []
    for item in tags:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name:
                result.append(name)
    return result


def parse_artwork(data: dict[str, Any]) -> Artwork | None:
    """把 app-api 返回的单条作品转换为 Artwork。"""
    if not isinstance(data, dict):
        return None

    illust_id = _to_int(data.get("id"))
    if not illust_id:
        return None

    meta_single = data.get("meta_single_page")
    meta_single = meta_single if isinstance(meta_single, dict) else {}
    original_url = _first_text(meta_single.get("original_image_url"))

    user = data.get("user")
    user = user if isinstance(user, dict) else {}
    user_name = _first_text(user.get("name"), "未知画师")

    return Artwork(
        illust_id=illust_id,
        title=_first_text(data.get("title"), "无标题"),
        page_count=_to_int(data.get("page_count"), 1),
        total_bookmarks=_to_int(data.get("total_bookmarks")),
        total_view=_to_int(data.get("total_view")),
        user_name=user_name,
        page_url=f"https://www.pixiv.net/artworks/{illust_id}",
        original_url=original_url,
        tags=_extract_tags(data),
    )


def parse_artworks(payload: dict[str, Any]) -> list[Artwork]:
    """把 app-api 检索响应转换为 Artwork 列表（按 API 返回顺序）。"""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("illusts")
    if not isinstance(raw, list):
        return []
    works: list[Artwork] = []
    for item in raw:
        artwork = parse_artwork(item)
        if artwork is not None:
            works.append(artwork)
    return works


def is_high_quality(artwork: Artwork, min_bookmarks: int) -> bool:
    """是否属于「非低质图」：收藏数达标且存在可下载的原图。"""
    if artwork.total_bookmarks < min_bookmarks:
        return False
    return bool(artwork.original_url)


def pick_artwork(artworks: list[Artwork], min_bookmarks: int) -> Artwork | None:
    """从已经热度排序的作品里，挑第一张符合高热度标准的可下载图片。"""
    for artwork in artworks:
        if is_high_quality(artwork, min_bookmarks):
            return artwork
    return None