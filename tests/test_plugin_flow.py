"""看看福插件指令处理流程测试（使用 stub 模拟 AstrBot）。"""

from __future__ import annotations

import types
from io import BytesIO

import pytest

from astrbot_plugin_kankanfu import main as plugin_module
from astrbot_plugin_kankanfu.kankanfu.client import PixivError
from astrbot_plugin_kankanfu.kankanfu.formatter import (
    NO_TOKEN_TEXT,
    NOT_HOT_TEXT,
    PROGRESS_TEXT,
    SEARCH_FAILED_TEXT,
)

PIXIV_SEARCH_RESPONSE = {
    "illusts": [
        {
            "id": 123,
            "title": "例の作品",
            "type": "illust",
            "page_count": 1,
            "total_bookmarks": 5000,
            "total_view": 30000,
            "user": {"id": 1, "name": "テスト絵師"},
            "meta_single_page": {"original_image_url": "/img/123/p0/master1200.jpg"},
            "tags": ["R-18", "女の子", "小穴"],
        },
        {
            "id": 456,
            "title": "低热度",
            "type": "illust",
            "page_count": 1,
            "total_bookmarks": 10,
            "total_view": 100,
            "user": {"id": 2, "name": "低質"},
            "meta_single_page": {"original_image_url": "/img/456/p0/master1200.jpg"},
            "tags": [],
        },
    ]
}

IMAGE_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32  # 伪装成 JPEG 文件头


class FakeClient:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload if payload is not None else PIXIV_SEARCH_RESPONSE
        self.error = error
        self.calls: list[str] = []
        self.downloads: list[str] = []

    async def search_illusts(self, word, *, words=None, num_results=30, max_pages=5):
        self.calls.append("search")
        self.words_called = getattr(self, "words_called", []) + [words]
        if self.error:
            raise self.error
        return self.payload

    async def download_original(self, url):
        self.downloads.append(url)
        return IMAGE_BYTES


class FakeEvent:
    def __init__(self, sender_id: str = "10001") -> None:
        self._sender_id = sender_id
        self.outputs: list[dict] = []

    def get_sender_id(self):
        return self._sender_id

    def plain_result(self, text: str):
        item = {"type": "plain", "text": text}
        self.outputs.append(item)
        return item

    def image_result(self, path_or_url):
        item = {"type": "image", "source": path_or_url}
        self.outputs.append(item)
        return item


def make_plugin(payload=None, error=None, **overrides):
    config = {
        "refresh_token": "fake-token",
        "proxy": "",
        "search_word": "小穴",
        "min_bookmarks": 2000,
        "max_results": 5,
        "timeout_seconds": 30,
        "send_progress": False,
        "show_info": True,
        "cooldown_seconds": 0,
    }
    config.update(overrides)
    plugin = plugin_module.KankanFuPlugin(None, config)
    plugin.client = FakeClient(payload, error)
    return plugin


def run_handler(plugin, event) -> list[dict]:
    async def consume():
        async for item in plugin.kankanku(event):
            pass
        return event.outputs

    return asyncio_run(consume())


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def test_happy_path_sends_image_and_info():
    plugin = make_plugin()
    event = FakeEvent()

    outputs = run_handler(plugin, event)

    assert plugin.client.calls == ["search"]
    assert plugin.client.downloads == ["/img/123/p0/master1200.jpg"]
    assert outputs[0]["type"] == "image"
    assert outputs[0]["source"].endswith(".jpg")  # 以 JPEG 保存到临时文件
    # 第一条为纯文本输出（进度关闭），图片后附作品信息
    info = outputs[-1]
    assert info["type"] == "plain"
    assert "例の作品" in info["text"]
    assert "5000" in info["text"]


def test_no_token_returns_hint():
    plugin = make_plugin(refresh_token="")
    event = FakeEvent()

    outputs = run_handler(plugin, event)

    assert outputs[0]["text"] == NO_TOKEN_TEXT
    assert plugin.client.calls == []


def test_no_hot_artwork_returns_not_hot():
    payload = {"illusts": [PIXIV_SEARCH_RESPONSE["illusts"][1]]}  # 只有低热度
    plugin = make_plugin(payload=payload)
    event = FakeEvent()

    outputs = run_handler(plugin, event)

    assert outputs[0]["text"] == NOT_HOT_TEXT
    assert plugin.client.downloads == []


def test_lowering_min_bookmarks_takes_effect_immediately():
    """改低收藏门槛后，无需重载插件，下一次请求即生效。"""
    payload = {"illusts": [PIXIV_SEARCH_RESPONSE["illusts"][1]]}  # 只有收藏 10 的作品
    # 用「全年龄」范围，让该无分级标签的作品能通过评分过滤，单独验证收藏门槛
    plugin = make_plugin(payload=payload, search_rating="全年龄")
    # 先把门槛调到 100 以下也搜不到
    plugin.config["min_bookmarks"] = 50
    outputs = run_handler(plugin, FakeEvent())
    assert outputs[0]["text"] == NOT_HOT_TEXT  # 收藏 10 < 50，仍不达标

    # 再把门槛降到 5，收藏 10 的作品即可通过
    plugin.config["min_bookmarks"] = 5
    outputs = run_handler(plugin, FakeEvent())
    assert outputs[0]["type"] == "image"
    assert plugin.client.downloads == ["/img/456/p0/master1200.jpg"]


def test_pixiv_error_returns_retry_text():
    plugin = make_plugin(error=PixivError("boom"))
    event = FakeEvent()

    outputs = run_handler(plugin, event)

    assert SEARCH_FAILED_TEXT in outputs[0]["text"]


def test_too_frequent_cooldown():
    plugin = make_plugin(cooldown_seconds=60)
    event = FakeEvent()

    run_handler(plugin, event)  # 第一次
    outputs = run_handler(plugin, FakeEvent())  # 第二次立即触发冷却

    assert plugin.client.calls == ["search"]  # 只有第一次真正调用了检索
    assert "别急" in outputs[0]["text"]


def test_progress_message_sent_when_enabled():
    plugin = make_plugin(send_progress=True)
    event = FakeEvent()

    outputs = run_handler(plugin, event)

    assert outputs[0]["text"] == PROGRESS_TEXT
    assert outputs[1]["type"] == "image"


def test_related_words_are_passed_to_search():
    """配置里的 related_words 应经过拆分后传给检索，用于扩大候选池。"""
    plugin = make_plugin(related_words="マンコ,オナニー, 裸足 ")
    event = FakeEvent()
    outputs = run_handler(plugin, event)
    assert outputs and outputs[0]["type"] == "image"  # 正常出图
    # 拆分后应去掉空白、不把空串算进去
    assert plugin.client.words_called[-1] == ["マンコ", "オナニー", "裸足"]


def test_compress_image_below_limit_returned_as_is():
    small = b"tiny-bytes"
    out = plugin_module.KankanFuPlugin._compress_image(small, 1024)
    assert out is small


def test_large_image_is_compressed_under_limit():
    """超大图片应被压缩到不超上限且仍可被 Pillow 打开。"""
    pytest.importorskip("PIL")
    from PIL import Image

    # 用随机噪声生成一张真·大体积图，避免纯色被 PNG 压到很小
    rnd = __import__("random").Random(1)
    big_img = Image.new("RGB", (3000, 3000))
    big_img.putdata([(rnd.randint(0, 255),) * 3 for _ in range(3000 * 3000)])
    buf = BytesIO()
    big_img.save(buf, format="JPEG", quality=95)
    big = buf.getvalue()
    limit = 512 * 1024  # 512KB，保证必然触发压缩
    assert len(big) > limit  # 前置假设：输入确实超大
    out = plugin_module.KankanFuPlugin._compress_image(big, limit)
    assert len(out) <= limit
    assert len(out) < len(big)
    reopen = Image.open(BytesIO(out))
    reopen.load()