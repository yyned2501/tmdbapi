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

    async def request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """发起异步请求"""
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        if params is None:
            params = {}
            
        # 注入 API Key (如果没用 Bearer Token)
        if not self.read_access_token:
            params["api_key"] = self.api_key
            
        # 强制注入成人内容解锁
        params["include_adult"] = "true"
        # 注入语言
        if "language" not in params:
            params["language"] = self.language

        # httpx 0.20+ 使用 proxy 参数
        proxy_url = None
        if self.proxy:
            proxy_url = self.proxy.get("https://") or self.proxy.get("http://")

        async with httpx.AsyncClient(proxy=proxy_url, headers=self.headers, timeout=30.0) as client:
            try:
                logger.info(f"正在请求 TMDB: {method} {url} params={params}")
                response = await client.request(method, url, params=params, **kwargs)
                logger.info(f"TMDB 响应状态码: {response.status_code}")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"TMDB API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"TMDB API 请求发生异常: {str(e)}")
                raise

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, **kwargs):
        return await self.request("GET", endpoint, params, **kwargs)

# 单例模式
tmdb_client = TMDBClient()

__all__ = ["tmdb_client"]
