from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from modules.media.models import Media
from modules.media.schemas import MediaCreate
from modules.scrapers import SCRAPERS
from core.logger import logger

class MediaService:
    """媒体业务逻辑层"""

    async def search_and_sync(self, db: AsyncSession, query: str, scraper_name: str = "tmdb", **kwargs) -> List[Media]:
        """搜索并同步数据到数据库"""
        scraper = SCRAPERS.get(scraper_name)
        if not scraper:
            logger.error(f"未找到刮削器: {scraper_name}")
            return []

        # 从刮削器获取结果
        results = await scraper.search(query, **kwargs)
        logger.info(f"刮削器 {scraper_name} 返回了 {len(results)} 条结果")
        
        synced_media = []
        for res in results:
            # 检查数据库是否已存在
            stmt = select(Media).where(
                Media.scraper_source == res.source,
                Media.scraper_id == res.source_id
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
            
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
        
        await db.commit()
        return synced_media

    async def get_by_id(self, db: AsyncSession, media_id: int) -> Optional[Media]:
        """根据本地 ID 获取媒体"""
        stmt = select(Media).where(Media.id == media_id)
        return (await db.execute(stmt)).scalar_one_or_none()

    async def sync_results(self, db: AsyncSession, results: List[ScraperMediaResult]):
        """批量同步刮削结果到数据库"""
        for res in results:
            stmt = select(Media).where(
                Media.scraper_source == res.source,
                Media.scraper_id == res.source_id
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
            
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
        
        await db.commit()

# 导出实例
media_service = MediaService()

__all__ = ["media_service"]
