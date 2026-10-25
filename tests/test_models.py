"""Pixiv 作品模型解析与热度过滤测试（不访问网络）。"""

from __future__ import annotations

from kankanfu.models import (
    is_high_quality,
    parse_artwork,
    parse_artworks,
    pick_artwork,
)

RAW_HOT = {
    "id": 123,
    "title": "例の作品",
    "type": "illust",
    "page_count": 1,
    "total_bookmarks": 5000,
    "total_view": 30000,
    "user": {"id": 1, "name": "テスト絵師"},
    "meta_single_page": {
        "original_image_url": "/img/123/p0/master1200.jpg",
    },
    "tags": ["女の子", "小穴"],
}

RAW_COLD = {
    "id": 456,
    "title": "低热度",
    "type": "illust",
    "page_count": 1,
    "total_bookmarks": 10,
    "total_view": 100,
    "user": {"id": 2, "name": "低質"},
    "meta_single_page": {
        "original_image_url": "/img/456/p0/master1200.jpg",
    },
    "tags": [],
}

RAW_NO_IMAGE = {
    "id": 789,
    "title": "无图",
    "type": "illust",
    "page_count": 1,
    "total_bookmarks": 9000,
    "total_view": 90000,
    "user": {"id": 3, "name": "無図"},
    "tags": [],
}


def test_parse_artwork_hot():
    artwork = parse_artwork(RAW_HOT)
    assert artwork is not None
    assert artwork.illust_id == 123
    assert artwork.title == "例の作品"
    assert artwork.total_bookmarks == 5000
    assert artwork.original_url == "/img/123/p0/master1200.jpg"
    assert artwork.page_url == "https://www.pixiv.net/artworks/123"
    assert artwork.tags == ["女の子", "小穴"]
    assert not artwork.is_multi_page


def test_parse_artwork_invalid():
    assert parse_artwork({}) is None
    assert parse_artwork({"id": 0}) is None
    assert parse_artwork(None) is None


def test_parse_artworks_filters_invalid():
    payload = {"illusts": [RAW_HOT, {"id": 0}, RAW_COLD]}
    artworks = parse_artworks(payload)
    assert [a.illust_id for a in artworks] == [123, 456]


def test_parse_artworks_empty():
    assert parse_artworks({}) == []
    assert parse_artworks({"illusts": []}) == []
    assert parse_artworks({"illusts": "bad"}) == []


def test_is_high_quality():
    hot = parse_artwork(RAW_HOT)
    assert hot is not None
    assert is_high_quality(hot, 2000) is True
    assert is_high_quality(hot, 10000) is False

    no_image = parse_artwork(RAW_NO_IMAGE)
    assert no_image is not None
    assert is_high_quality(no_image, 1) is False  # 没有原图，不算高质量


def test_pick_artwork_prefers_first_hot():
    hot = parse_artwork(RAW_HOT)
    cold = parse_artwork(RAW_COLD)
    artworks = [cold, hot]
    picked = pick_artwork(artworks, 2000)
    assert picked is hot


def test_pick_artwork_none_when_all_cold():
    cold = parse_artwork(RAW_COLD)
    assert pick_artwork([cold], 2000) is None