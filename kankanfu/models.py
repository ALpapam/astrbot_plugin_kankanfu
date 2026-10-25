"""Pixiv 作品模型与热度过滤工具。

该模块只依赖标准库，便于脱离 AstrBot 单独测试。
"""

from __future__ import annotations

import random
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


def _extract_original_url(data: dict[str, Any]) -> str:
    """从 app-api 作品条目里提取可下载的原图 URL。

    Pixiv 的原图地址分布在不同字段：
    - 单 P 作品：``meta_single_page.original_image_url``
    - 多 P 作品：顶层没有原图，原图在 ``meta_pages[0].image_urls.original``
      （顶层 ``image_urls`` 只有 large/缩略图，``original`` 常为 None）
    因此依次回退，保证多 P 的收藏大户也能被识别为可下载。
    """
    meta_single = data.get("meta_single_page")
    if isinstance(meta_single, dict):
        url = _first_text(meta_single.get("original_image_url"))
        if url:
            return url

    meta_pages = data.get("meta_pages")
    if isinstance(meta_pages, list) and meta_pages:
        first = meta_pages[0]
        first = first if isinstance(first, dict) else {}
        images = first.get("image_urls")
        if isinstance(images, dict):
            url = _first_text(images.get("original"))
            if url:
                return url

    # 最后回退到顶层 image_urls 的 large/medium
    images = data.get("image_urls")
    if isinstance(images, dict):
        for key in ("original", "large", "medium"):
            url = _first_text(images.get(key))
            if url:
                return url
    return ""


def parse_artwork(data: dict[str, Any]) -> Artwork | None:
    """把 app-api 返回的单条作品转换为 Artwork。"""
    if not isinstance(data, dict):
        return None

    illust_id = _to_int(data.get("id"))
    if not illust_id:
        return None

    original_url = _extract_original_url(data)

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


def parse_artworks(payload: dict[str, Any] | list[dict[str, Any]]) -> list[Artwork]:
    """把 app-api 检索响应转换为 Artwork 列表（按 API 返回顺序）。

    兼容两种入参形式：
    - 完整响应字典 ``{"illusts": [...]}``（API 原始返回）
    - 直接传入 ``illusts`` 列表（``search_illusts`` 返回的就是列表）
    """
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("illusts")
    else:
        return []
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


def pick_artwork(
    artworks: list[Artwork],
    min_bookmarks: int,
    rng: random.Random | None = None,
) -> Artwork | None:
    """从符合高热度标准（收藏达标 + 有原图）的作品里随机挑 1 张。

    检索响应按 ``popular_desc`` 返回但并非严格按收藏数排序，
    先筛出全部符合条件（收藏达标 + 有原图）的作品，再在其中随机抽取一张，
    避免每次都发收藏数最高的同一张。可用 ``rng`` 注入随机源以方便测试。
    """
    rng = rng if rng is not None else random
    candidates = [
        artwork for artwork in artworks if is_high_quality(artwork, min_bookmarks)
    ]
    if not candidates:
        return None
    return rng.choice(candidates)