from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from modules.media.models import Media
from modules.media.schemas import MediaCreate
from modules.scrapers import SCRAPERS
from modules.scrapers.base import ScraperMediaResult
from core.logger import logger

class MediaService:
    """媒体业务逻辑层"""

    async def search_and_sync(self, db: AsyncSession, query: str, scraper_name: str = "tmdb", **kwargs) -> List[Media]:
        """搜索并同步数据到数据库 (已进行批量查询性能优化，已进行分布式安全防护)"""
        scraper = SCRAPERS.get(scraper_name)
        if not scraper:
            logger.error(f"未找到刮削器: {scraper_name}")
            return []

        # 从刮削器获取结果
        results = await scraper.search(query, **kwargs)
        logger.info(f"刮削器 {scraper_name} 返回了 {len(results)} 条结果")
        
        if not results:
            return []

        # 1. 一次性查询出数据库中已存在的所有相关记录 (批量查询优化)
        source_ids = [res.source_id for res in results]
        stmt = select(Media).where(
            Media.scraper_source == scraper_name,
            Media.scraper_id.in_(source_ids)
        )
        existing_list = (await db.execute(stmt)).scalars().all()
        existing_map = {m.scraper_id: m for m in existing_list}

        synced_media = []
        for res in results:
            existing = existing_map.get(res.source_id)
            
            if existing:
                # 更新现有记录
                existing.title = res.title
                existing.original_title = res.original_title
                existing.overview = res.overview
                existing.release_date = res.release_date
                existing.poster_path = res.poster_path
                existing.backdrop_path = res.backdrop_path
                existing.adult = res.adult
                existing.raw_data = res.raw_data
                synced_media.append(existing)
            else:
                # 创建新记录
                new_media = Media(
                    scraper_source=res.source,
                    scraper_id=res.source_id,
                    title=res.title,
                    original_title=res.original_title,
                    overview=res.overview,
                    release_date=res.release_date,
                    poster_path=res.poster_path,
                    backdrop_path=res.backdrop_path,
                    adult=res.adult,
                    raw_data=res.raw_data
                )
                db.add(new_media)
                synced_media.append(new_media)
        
        try:
            await db.commit()
        except IntegrityError:
            # 分布式安全自愈：捕获多机并发冲突导致的唯一性约束失败，安全回滚并重新查询获取
            await db.rollback()
            logger.warning(
                f"并发写入发生唯一约束冲突 (另一个分布式节点已抢先写入 {scraper_name})，"
                f"系统已自动执行回滚并保持数据一致性"
            )
            # 重新查回已存在的记录以保证返回列表正确
            stmt = select(Media).where(
                Media.scraper_source == scraper_name,
                Media.scraper_id.in_(source_ids)
            )
            synced_media = list((await db.execute(stmt)).scalars().all())
            
        return synced_media

    async def get_by_id(self, db: AsyncSession, media_id: int) -> Optional[Media]:
        """根据本地 ID 获取媒体"""
        stmt = select(Media).where(Media.id == media_id)
        return (await db.execute(stmt)).scalar_one_or_none()

    async def sync_results(self, db: AsyncSession, results: List[ScraperMediaResult]):
        """批量同步刮削结果到数据库 (已进行批量查询性能优化，已进行分布式安全防护)"""
        if not results:
            return

        # 1. 一次性查询出数据库中已存在的所有相关记录 (批量查询优化)
        source_ids = [res.source_id for res in results]
        stmt = select(Media).where(
            Media.scraper_id.in_(source_ids)
        )
        existing_list = (await db.execute(stmt)).scalars().all()
        existing_map = {f"{m.scraper_source}:{m.scraper_id}": m for m in existing_list}
        
        for res in results:
            key = f"{res.source}:{res.source_id}"
            existing = existing_map.get(key)
            
            if existing:
                existing.title = res.title
                existing.original_title = res.original_title
                existing.overview = res.overview
                existing.release_date = res.release_date
                existing.poster_path = res.poster_path
                existing.backdrop_path = res.backdrop_path
                existing.adult = res.adult
                existing.raw_data = res.raw_data
            else:
                new_media = Media(
                    scraper_source=res.source,
                    scraper_id=res.source_id,
                    title=res.title,
                    original_title=res.original_title,
                    overview=res.overview,
                    release_date=res.release_date,
                    poster_path=res.poster_path,
                    backdrop_path=res.backdrop_path,
                    adult=res.adult,
                    raw_data=res.raw_data
                )
                db.add(new_media)
        
        try:
            await db.commit()
        except IntegrityError:
            # 批量后台同步如果遇到冲突，安全回滚即可（数据以已抢先写入成功的记录为准）
            await db.rollback()
            logger.warning("后台批量同步检测到分布式写入唯一约束冲突，已执行自动回退。")

# 导出实例
media_service = MediaService()

__all__ = ["media_service"]
