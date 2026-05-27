from typing import Any, Dict, Optional

import anyio
import httpx

from core.config import config
from core.logger import logger


class TMDBClient:
    """底层 TMDB API 客户端。"""

    def __init__(self):
        self.base_url = config.tmdb.base_url
        self.api_key = config.tmdb.api_key
        self.read_access_token = config.tmdb.read_access_token
        self.language = config.tmdb.language
        self.max_retries = int(getattr(config.tmdb, "request_retries", 1))

        # 设置请求头
        self.headers = {
            "accept": "application/json",
        }
        if self.read_access_token:
            self.headers["Authorization"] = f"Bearer {self.read_access_token}"

        # 设置代理
        self.proxy = None
        if config.proxy.enabled:
            self.proxy = {
                "http://": config.proxy.http,
                "https://": config.proxy.https,
            }

        self._client: Optional[httpx.AsyncClient] = None

    def _get_proxy_url(self) -> Optional[str]:
        if not self.proxy:
            return None
        return self.proxy.get("https://") or self.proxy.get("http://")

    def _should_recreate_client(self, exc: Exception) -> bool:
        # 支持所有 httpx 请求类异常及 anyio 关闭资源异常（涵盖连接、超时、代理、协议及资源关闭错误）
        recoverable_types = (
            httpx.RequestError,
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadError,
            httpx.ReadTimeout,
            httpx.WriteError,
            httpx.WriteTimeout,
            httpx.CloseError,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
            httpx.ProxyError,
            anyio.ClosedResourceError,
        )
        if isinstance(exc, recoverable_types):
            return True

        if type(exc).__name__ == "ClosedResourceError":
            return True

        detail = repr(exc).lower()
        keywords = [
            "connection refused",
            "connection reset",
            "connection aborted",
            "connection closed",
            "broken pipe",
            "proxy",
            "closedresourceerror",
        ]
        return any(keyword in detail for keyword in keywords)

    async def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            proxy=self._get_proxy_url(),
            headers=self.headers,
            timeout=30.0,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def get_client(self) -> httpx.AsyncClient:
        """获取或创建异步 HTTP 客户端（复用连接池）。"""
        if self._client is None or self._client.is_closed:
            self._client = await self._create_client()
        return self._client

    async def reset_client(self, reason: str) -> None:
        """主动释放并重建 HTTP 客户端。"""
        if self._client and not self._client.is_closed:
            try:
                await self._client.aclose()
            except Exception as exc:
                logger.warning(
                    f"关闭 TMDB HTTP 客户端时发生异常: reason={reason} "
                    f"type={type(exc).__name__} detail={repr(exc)}"
                )
        self._client = None
        logger.warning(f"TMDB HTTP 客户端已重置: reason={reason}")

    async def close(self):
        """关闭客户端。"""
        await self.reset_client("application_shutdown")

    def get_full_params(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取完整的请求参数（包含注入的 API Key、语言和成人内容设置）。"""
        full_params = dict(params) if params else {}

        # 注入 API Key (如果参数中没有且没用 Bearer Token)
        if not self.read_access_token and "api_key" not in full_params:
            full_params["api_key"] = self.api_key

        # 强制注入成人内容解锁
        full_params["include_adult"] = "true"

        # 注入语言
        if "language" not in full_params:
            full_params["language"] = self.language

        return full_params

    async def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """发起异步请求，并在连接异常时自动重建客户端。"""
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        full_params = self.get_full_params(params)

        request_headers = self.headers.copy()
        if headers:
            request_headers.update(headers)

        for attempt in range(self.max_retries + 1):
            client = await self.get_client()
            try:
                logger.info(
                    f"正在请求 TMDB: method={method} endpoint={endpoint} url={url} "
                    f"attempt={attempt + 1}/{self.max_retries + 1} proxy_enabled={bool(self.proxy)} "
                    f"params={full_params}"
                )
                response = await client.request(
                    method,
                    url,
                    params=full_params,
                    headers=request_headers,
                    **kwargs,
                )
                logger.info(
                    f"TMDB 响应成功: endpoint={endpoint} status_code={response.status_code}"
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                log_func = logger.warning if status_code == 404 else logger.error
                log_func(
                    f"TMDB API 请求失败: endpoint={endpoint} status_code={status_code} "
                    f"type={type(exc).__name__} detail={repr(exc)}"
                )
                raise
            except Exception as exc:
                if attempt >= self.max_retries or not self._should_recreate_client(exc):
                    logger.error(
                        f"TMDB API 请求最终失败: endpoint={endpoint} attempt={attempt + 1}/{self.max_retries + 1} "
                        f"proxy_enabled={bool(self.proxy)} type={type(exc).__name__} detail={repr(exc)}"
                    )
                    raise

                logger.warning(
                    f"TMDB API 请求发生异常（准备重试）: endpoint={endpoint} attempt={attempt + 1}/{self.max_retries + 1} "
                    f"proxy_enabled={bool(self.proxy)} type={type(exc).__name__} detail={repr(exc)}"
                )

                await self.reset_client(
                    f"request_retry endpoint={endpoint} attempt={attempt + 1}"
                )

                # 引入指数退避延迟，避免因网络/代理短时波动导致立即重试同样失败
                import asyncio
                backoff_delay = 2 * (attempt + 1)
                logger.info(f"由于网络/代理异常，将在 {backoff_delay} 秒后重试...")
                await asyncio.sleep(backoff_delay)

        raise RuntimeError(f"TMDB 请求重试逻辑异常结束: endpoint={endpoint}")

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        return await self.request("GET", endpoint, params, headers=headers, **kwargs)


# 单例模式
tmdb_client = TMDBClient()

__all__ = ["tmdb_client"]
