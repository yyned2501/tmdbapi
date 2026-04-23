from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from core.database import get_session
from modules.media.service import media_service
from modules.media.schemas import MediaRead

router = APIRouter(prefix="/media", tags=["media"])

@router.get("/search", response_model=List[MediaRead])
async def search_media(
    query: str = Query(..., description="搜索关键词"),
    scraper: str = Query("tmdb", description="刮削器名称"),
    db: AsyncSession = Depends(get_session)
):
    """搜索并同步媒体数据"""
    try:
        results = await media_service.search_and_sync(db, query, scraper)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{media_id}", response_model=MediaRead)
async def get_media_detail(
    media_id: int,
    db: AsyncSession = Depends(get_session)
):
    """获取本地存储的媒体详情"""
    media = await media_service.get_by_id(db, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="媒体未找到")
    return media
