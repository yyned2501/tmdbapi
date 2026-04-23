from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
from modules.media.models import APICache
import hashlib
import json

class CacheService:
    """API 响应缓存服务"""

    def _generate_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """生成唯一的缓存键"""
        # 排除 api_key，因为它不影响响应内容且可能因请求而异
        filtered_params = {k: v for k, v in params.items() if k != "api_key"}
        # 对参数进行排序以确保一致性
        sorted_params = sorted(filtered_params.items())
        param_str = json.dumps(sorted_params)
        raw_key = f"{endpoint}:{param_str}"
        return hashlib.sha256(raw_key.encode()).hexdigest()

    async def get(self, db: AsyncSession, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取缓存"""
        cache_key = self._generate_key(endpoint, params)
        stmt = select(APICache).where(APICache.cache_key == cache_key)
        result = await db.execute(stmt)
        cache_item = result.scalar_one_or_none()

        if cache_item:
            # 检查是否过期
            if cache_item.expires_at > datetime.now(cache_item.expires_at.tzinfo):
                return cache_item.response_data
            else:
                # 已过期，删除
                await db.delete(cache_item)
                await db.commit()
        
        return None

    async def set(self, db: AsyncSession, endpoint: str, params: Dict[str, Any], data: Dict[str, Any], ttl_hours: int = 24):
        """设置缓存"""
        cache_key = self._generate_key(endpoint, params)
        expires_at = datetime.now() + timedelta(hours=ttl_hours)

        # 检查是否已存在
        stmt = select(APICache).where(APICache.cache_key == cache_key)
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.response_data = data
            existing.expires_at = expires_at
        else:
            new_cache = APICache(
                cache_key=cache_key,
                response_data=data,
                expires_at=expires_at
            )
            db.add(new_cache)
        
        await db.commit()

cache_service = CacheService()

__all__ = ["cache_service"]
