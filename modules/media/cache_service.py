from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, Tuple
from modules.media.models import APICache
from core.config import config
from core.logger import logger
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

    async def get(self, db: AsyncSession, endpoint: str, params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        获取缓存
        返回: (data, is_stale)
        - data: 缓存数据，如果没有或已彻底过期则为 None
        - is_stale: 是否已过优先缓存期（需要尝试更新）
        """
        cache_key = self._generate_key(endpoint, params)
        stmt = select(APICache).where(APICache.cache_key == cache_key)
        result = await db.execute(stmt)
        cache_item = result.scalar_one_or_none()

        if not cache_item:
            return None, False

        now = datetime.now(timezone.utc)
        
        # 1. 检查是否彻底过期（超过 cleanup_cache_hours）
        if cache_item.expires_at <= now:
            logger.info(f"缓存彻底过期，准备删除: {endpoint}")
            try:
                await db.delete(cache_item)
                await db.commit()
            except Exception:
                await db.rollback()
            return None, False

        # 2. 检查是否过了优先缓存期（超过 prefer_cache_hours）
        prefer_hours = config.cache.prefer_cache_hours
        is_stale = cache_item.created_at + timedelta(hours=prefer_hours) <= now
        
        return cache_item.response_data, is_stale

    async def set(self, db: AsyncSession, endpoint: str, params: Dict[str, Any], data: Dict[str, Any]):
        """设置缓存"""
        cache_key = self._generate_key(endpoint, params)
        
        # 使用配置中的时间
        cleanup_hours = config.cache.cleanup_cache_hours
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=cleanup_hours)

        # 使用 PostgreSQL 的 ON CONFLICT 语法处理并发写入
        # 注意：更新时也要更新 created_at 和 expires_at
        stmt = pg_insert(APICache).values(
            cache_key=cache_key,
            response_data=data,
            expires_at=expires_at,
            created_at=now
        ).on_conflict_do_update(
            index_elements=['cache_key'],
            set_={
                'response_data': data,
                'expires_at': expires_at,
                'created_at': now
            }
        )
        
        await db.execute(stmt)
        await db.commit()

cache_service = CacheService()

__all__ = ["cache_service"]
