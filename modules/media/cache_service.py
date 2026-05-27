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
        # 分布式安全优化：读取时检测到过期不执行被动 db.delete 以消灭并发 StaleDataError，
        # 直接判定失效并返回 None，由系统后台定时任务安全统一回收。
        if cache_item.expires_at <= now:
            logger.info(f"缓存彻底过期 (返回失效，留待后台定时任务统一回收): {endpoint}")
            return None, False

        # 2. 检查是否过了优先缓存期（超过 prefer_cache_hours）
        prefer_hours = config.cache.prefer_cache_hours
        is_stale = cache_item.created_at + timedelta(hours=prefer_hours) <= now
        
        return cache_item.response_data, is_stale

    def _is_valid_response(self, endpoint: str, data: Any) -> bool:
        """
        保存缓存前的响应前置检查。
        如果缺少必要数据或响应格式非法，返回 False。
        """
        if data is None:
            logger.warning(f"缓存前置检查失败: 接口 {endpoint} 响应数据为 None")
            return False

        # 如果是列表，通常是合法的配置或多项关联数据（例如 configuration/languages）
        if isinstance(data, list):
            if not data:
                logger.warning(f"缓存前置检查失败: 接口 {endpoint} 响应数据为空列表")
                return False
            return True

        if not isinstance(data, dict):
            logger.warning(f"缓存前置检查失败: 接口 {endpoint} 响应数据非字典或列表类型: {type(data)}")
            return False

        # 1. 检查 TMDB 的标准错误响应格式
        # 例如: {"status_code": 34, "status_message": "...", "success": false}
        if data.get("success") is False:
            logger.warning(f"缓存前置检查失败: 接口 {endpoint} 返回成功标志为 False: {data}")
            return False
        if "status_code" in data and "status_message" in data:
            logger.warning(f"缓存前置检查失败: 接口 {endpoint} 返回异常响应: {data}")
            return False

        # 2. 根据不同的接口路径进行针对性的前置数据校验
        parts = [p.strip() for p in endpoint.lower().split("/") if p.strip()]
        if not parts:
            return True

        primary = parts[0]

        # 2.1 搜索/发现/流行等列表接口
        is_list_endpoint = primary in ("search", "discover", "trending") or (
            len(parts) > 1 and parts[1] in ("popular", "top_rated", "upcoming", "now_playing", "airing_today", "on_the_air")
        )
        if is_list_endpoint:
            # 必须含有 results 字段，且 results 必须为 list 类型
            if "results" not in data or not isinstance(data["results"], list):
                logger.warning(f"缓存前置检查失败: 列表接口 {endpoint} 响应缺少 'results' 字段或类型不符")
                return False
            return True

        # 2.2 分类/流派接口 (genre/movie/list, genre/tv/list)
        if primary == "genre" and len(parts) >= 3 and parts[2] == "list":
            if "genres" not in data or not isinstance(data["genres"], list):
                logger.warning(f"缓存前置检查失败: 流派接口 {endpoint} 响应缺少 'genres' 字段或类型不符")
                return False
            return True

        # 2.3 详情接口 (movie/{id}, tv/{id}, person/{id})
        if primary in ("movie", "tv", "person") and len(parts) == 2:
            id_str = parts[1]
            if id_str.isdigit():
                # 详情接口必须包含 'id'
                if "id" not in data:
                    logger.warning(f"缓存前置检查失败: 详情接口 {endpoint} 响应缺少 'id' 字段")
                    return False
                # 针对 movie 额外校验 title 或 original_title
                if primary == "movie" and not (data.get("title") or data.get("original_title")):
                    logger.warning(f"缓存前置检查失败: 电影详情接口 {endpoint} 响应缺少 'title' 或 'original_title' 属性")
                    return False
                # 针对 tv 额外校验 name 或 original_name
                if primary == "tv" and not (data.get("name") or data.get("original_name")):
                    logger.warning(f"缓存前置检查失败: 剧集详情接口 {endpoint} 响应缺少 'name' 或 'original_name' 属性")
                    return False
                return True

        # 2.4 季度详情接口 (tv/{id}/season/{season_number})
        if primary == "tv" and len(parts) == 4 and parts[2] == "season":
            id_str, season_str = parts[1], parts[3]
            if id_str.isdigit() and season_str.isdigit():
                if "id" not in data:
                    logger.warning(f"缓存前置检查失败: 季度详情接口 {endpoint} 响应缺少 'id' 字段")
                    return False
                if "episodes" not in data or not isinstance(data["episodes"], list):
                    logger.warning(f"缓存前置检查失败: 季度详情接口 {endpoint} 响应缺少 'episodes' 字段或类型不符")
                    return False
                return True

        # 2.5 兜底检查：如果是普通的字典结构，不应为空字典
        if not data:
            logger.warning(f"缓存前置检查失败: 接口 {endpoint} 响应数据为空字典")
            return False

        return True

    async def set(self, db: AsyncSession, endpoint: str, params: Dict[str, Any], data: Any) -> bool:
        """设置缓存"""
        # 前置数据有效性检查
        if not self._is_valid_response(endpoint, data):
            logger.info(f"由于响应缺少必要数据，跳过本次缓存保存: endpoint={endpoint}")
            return False

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
        return True

cache_service = CacheService()

__all__ = ["cache_service"]
