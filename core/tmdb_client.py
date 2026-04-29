import httpx
from typing import Dict, Any, Optional
from core.config import config
from core.logger import logger

class TMDBClient:
    """底层 TMDB API 客户端"""
    
    def __init__(self):
        self.base_url = config.tmdb.base_url
        self.api_key = config.tmdb.api_key
        self.read_access_token = config.tmdb.read_access_token
        self.language = config.tmdb.language
        
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

    async def get_client(self) -> httpx.AsyncClient:
        """获取或创建异步 HTTP 客户端（复用连接池）"""
        if self._client is None or self._client.is_closed:
            proxy_url = None
            if self.proxy:
                proxy_url = self.proxy.get("https://") or self.proxy.get("http://")
            
            self._client = httpx.AsyncClient(
                proxy=proxy_url, 
                headers=self.headers, 
                timeout=30.0,
                # 显式配置连接池以优化性能
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
            )
        return self._client

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    def get_full_params(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取完整的请求参数（包含注入的 API Key、语言和成人内容设置）"""
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
        **kwargs
    ) -> Dict[str, Any]:
        """发起异步请求"""
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        # 获取完整参数
        full_params = self.get_full_params(params)
        
        # 合并请求头
        request_headers = self.headers.copy()
        if headers:
            request_headers.update(headers)

        client = await self.get_client()
        try:
            logger.info(f"正在请求 TMDB: {method} {url} params={full_params}")
            response = await client.request(method, url, params=full_params, headers=request_headers, **kwargs)
            logger.info(f"TMDB 响应状态码: {response.status_code}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"TMDB API 请求失败: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"TMDB API 请求发生异常: {str(e)}")
            raise

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, **kwargs):
        return await self.request("GET", endpoint, params, headers=headers, **kwargs)

# 单例模式
tmdb_client = TMDBClient()

__all__ = ["tmdb_client"]
