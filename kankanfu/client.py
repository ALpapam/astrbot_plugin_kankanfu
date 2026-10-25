"""Pixiv 客户端：refresh_token 认证 + app-api 检索 + 图片下载。

基于 aiohttp 的异步实现。

认证：
- Pixiv 并没有官方公开的 public client_id/client_secret，社区常用的 app-api
  public client 凭证是固定的，普遍用于第三方客户端。这里默认使用社区已知的
  public OAuth 客户端标识，可通过 ``client_id`` / ``client_secret`` 配置覆盖。

检索：
- ``GET https://app-api.pixiv.net/v1/search/illust``
  - ``word`` 关键词（默认 ``小穴``，不要带 ``#`` 前缀）
  - ``search_target`` ``partial_match_for_tags``（标签部分匹配，pixivpy 默认）
  - ``filter`` ``for_ios``（pixivpy 默认，对齐 app-api）
  - ``sort`` ``popular_desc``（热门排序；注意并非严格按总收藏，需跨页抓取再筛高热度）

图片下载：
- ``GET https://i.pximg.net/{urls.original}``，需要带 ``referer``（pixiv 防盗链）
  与鉴权头。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import aiohttp

logger = logging.getLogger("astrbot_plugin_kankanfu.client")

TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"
APP_API_BASE = "https://app-api.pixiv.net"
IMAGE_HOST = "https://i.pximg.net"

#: 社区广泛使用的 Pixiv app-api public client 凭证（与 pixivpy 一致）。
DEFAULT_CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
DEFAULT_CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"

#: pixivpy 使用的登录加密密钥，用于生成 x-client-hash。
DEFAULT_HASH_SECRET = "28c1fdd170a5204386cb1313c7077b34f83e4aaf4aa829ce78c231e05b0bae2c"

DEFAULT_TIMEOUT_SECONDS = 30

DEFAULT_USER_AGENT = "PixivIOSApp/7.13.3 (iOS 14.6; iPhone13,2)"

_APP_JSON_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "App-OS": "ios",
    "App-OS-Version": "14.6",
    "App-Version": "7.13.3",
    "Accept-Language": "zh-cn",
    "Accept": "application/json",
}


class PixivError(Exception):
    """Pixiv 请求或响应异常。"""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _parse_json_object(body: str) -> dict[str, Any]:
    text = (body or "").strip()
    if not text:
        raise PixivError("Pixiv 返回了空响应")
    if not text.startswith("{"):
        raise PixivError("Pixiv 返回了非 JSON 响应")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PixivError("Pixiv 返回的 JSON 解析失败") from exc
    if not isinstance(payload, dict):
        raise PixivError("Pixiv 返回的数据格式异常")
    return payload


class PixivClient:
    """Pixiv 异步客户端。"""

    def __init__(
        self,
        refresh_token: str = "",
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        proxy: str = "",
        client_id: str = DEFAULT_CLIENT_ID,
        client_secret: str = DEFAULT_CLIENT_SECRET,
        hash_secret: str = DEFAULT_HASH_SECRET,
    ) -> None:
        self.refresh_token = (refresh_token or "").strip()
        self.timeout_seconds = timeout_seconds
        self.proxy = (proxy or "").strip()
        self.client_id = client_id
        self.client_secret = client_secret
        self.hash_secret = hash_secret
        self._access_token = ""

    # ------------------------------------------------------------------
    # 认证
    # ------------------------------------------------------------------

    async def refresh_access_token(self, session: aiohttp.ClientSession) -> str:
        """用 refresh_token 换取 access_token。"""
        local_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        client_hash = hashlib.md5(
            (local_time + self.hash_secret).encode("utf-8")
        ).hexdigest()
        auth_headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "x-client-time": local_time,
            "x-client-hash": client_hash,
            "App-OS": "ios",
            "App-OS-Version": "14.6",
            "App-Version": "7.13.3",
            "Accept-Language": "zh-cn",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "get_secure_url": 1,
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with session.post(
                TOKEN_URL,
                data=data,
                headers=auth_headers,
                proxy=self.proxy or None,
                timeout=timeout,
            ) as response:
                body = await response.text()
                status = response.status
        except asyncio.TimeoutError:
            raise PixivError("登录 Pixiv 请求超时，请检查网络/代理") from None
        except aiohttp.ClientError as exc:
            raise PixivError(f"登录 Pixiv 时网络错误: {type(exc).__name__}") from exc

        if status != 200:
            raise PixivError(
                f"登录 Pixiv 失败（HTTP {status}），请检查 refresh_token", status=status
            )
        payload = _parse_json_object(body)
        token = (
            payload.get("response", {})
            if isinstance(payload.get("response"), dict)
            else {}
        ).get("access_token")
        if not token:
            raise PixivError("Pixiv 登录响应中缺少 access_token，refresh_token 可能已失效")
        self._access_token = str(token)
        return self._access_token

    async def _authorized_headers(self) -> dict[str, str]:
        return {
            **_APP_JSON_HEADERS,
            "Authorization": f"Bearer {self._access_token}",
        }

    @staticmethod
    def _hint_from_body(body: str) -> str:
        """从非 200 响应体里尽量提取 Pixiv 给出的错误原因。"""
        text = (body or "").strip()
        if not text:
            return ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            snippet = re.sub(r"\\s+", " ", text)[:120]
            return f" | {snippet}" if snippet else ""
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            user_m = error.get("user_message")
            detail = (user_m or message or "").strip()
            if detail:
                return f" | {detail[:160]}"
            reason = error.get("reason")
            if isinstance(reason, dict):
                hint = reason.get("message") or reason.get("user_message")
                if hint:
                    return f" | {str(hint)[:160]}"
        return ""

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    async def search_illusts(
        self,
        word: str,
        *,
        sort: str = "popular_desc",
        num_results: int = 30,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """按热度检索插画，跨页抓取后合并返回原始作品条目。

        走 Pixiv 官方的 ``popular-preview``（热门预览）接口：它专门为免费
        账号提供该词条下被广泛收藏的经典高热度作品（非会员即可访问、无需
        会员细分），返回的是真正的高收藏作品，且带 ``illust_ai_type`` 标记，
        可供调用方过滤 AI 生成内容。

        ``popular-preview`` 返回数量有限（每页约 30 条），因此这里跨页抓取
        最多 ``max_pages`` 页，全部合并后由调用方按收藏数/分级/是否 AI 筛。
        """
        if not self._access_token:
            await self._ensure_token()
        params = {
            "word": word,
            "search_target": "partial_match_for_tags",
            "filter": "for_ios",
        }
        result_by_url: dict[str, dict[str, Any]] = {}
        next_url: str | None = urljoin(APP_API_BASE, "/v1/search/popular-preview/illust")
        page = 0
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                while (
                    next_url and len(result_by_url) < num_results and page < max_pages
                ):
                    request_url = (
                        next_url if page > 0 else urljoin(APP_API_BASE, "/v1/search/popular-preview/illust")
                    )
                    async with session.get(
                        request_url,
                        params=(params if page == 0 else None),
                        headers=await self._authorized_headers(),
                        proxy=self.proxy or None,
                    ) as response:
                        body = await response.text()
                        status = response.status
                        if status == 401:
                            # token 过期，重新换取后再试一次
                            await self.refresh_access_token(session)
                            async with session.get(
                                request_url,
                                params=(params if page == 0 else None),
                                headers=await self._authorized_headers(),
                                proxy=self.proxy or None,
                            ) as retry:
                                body = await retry.text()
                                status = retry.status
                        if status == 429:
                            raise PixivError("Pixiv 检索被限流（HTTP 429），请稍后再试", status=429)
                        if status != 200:
                            detail = self._hint_from_body(body)
                            raise PixivError(
                                f"Pixiv 检索失败（HTTP {status}）{detail}", status=status
                            )
                        payload = _parse_json_object(body)
                    batch = payload.get("illusts")
                    if not isinstance(batch, list) or not batch:
                        # 诊断：记录这一页到底收到了什么，便于排查空结果
                        logger.warning(
                            "[KankanFu] 检索第 %d 页结果为空: status=%d, word=%r, "
                            "response keys=%r, body head=%r",
                            page + 1,
                            status,
                            word,
                            list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
                            body[:160],
                        )
                        break
                    for item in batch:
                        if isinstance(item, dict) and item.get("id") is not None:
                            result_by_url[str(item["id"])] = item
                    page += 1
                    next_url = payload.get("next_url")
                    if not next_url:
                        break
        except aiohttp.ClientError as exc:
            raise PixivError(f"检索 Pixiv 时网络错误: {type(exc).__name__}") from exc

        return list(result_by_url.values())[:num_results]

    async def _ensure_token(self) -> None:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                await self.refresh_access_token(session)
        except aiohttp.ClientError as exc:
            raise PixivError(f"登录 Pixiv 时网络错误: {type(exc).__name__}") from exc

    # ------------------------------------------------------------------
    # 图片下载
    # ------------------------------------------------------------------

    async def download_original(
        self,
        url: str,
        *,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ) -> bytes:
        """下载原始图片字节（处理 pixiv 防盗链 referer）。"""
        if not self._access_token:
            await self._ensure_token()
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": "https://www.pixiv.net/",
            "Authorization": f"Bearer {self._access_token}",
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    urljoin(IMAGE_HOST, url),
                    headers=headers,
                    proxy=self.proxy or None,
                ) as response:
                    data = await response.read()
                    status = response.status
        except aiohttp.ClientError as exc:
            raise PixivError(f"下载图片时网络错误: {type(exc).__name__}") from exc
        if status != 200:
            raise PixivError(f"下载图片失败（HTTP {status}）", status=status)
        return data