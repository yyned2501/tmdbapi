from fastapi import APIRouter, Depends, Query, Path, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
from core.database import get_session
from modules.media.service import media_service
from modules.media.cache_service import cache_service
from core.tmdb_client import tmdb_client
from modules.scrapers.base import ScraperMediaResult
import asyncio
import httpx
from core.logger import logger

router = APIRouter(prefix="/3")

@router.get("/search/movie")
async def search_movie(
    request: Request,
    query: str = Query(..., description="搜索关键词"),
    db: AsyncSession = Depends(get_session)
):
    """兼容 TMDB 的电影搜索接口"""
    return await _proxy_request("search/movie", request, db)

@router.get("/search/tv")
async def search_tv(
    request: Request,
    query: str = Query(..., description="搜索关键词"),
    db: AsyncSession = Depends(get_session)
):
    """兼容 TMDB 的剧集搜索接口"""
    return await _proxy_request("search/tv", request, db)

@router.get("/movie/{movie_id}")
async def get_movie_detail(
    movie_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session)
):
    """兼容 TMDB 的电影详情接口"""
    return await _proxy_request(f"movie/{movie_id}", request, db)

@router.get("/tv/{tv_id}")
async def get_tv_detail(
    tv_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session)
):
    """兼容 TMDB 的剧集详情接口"""
    return await _proxy_request(f"tv/{tv_id}", request, db)

@router.get("/tv/{tv_id}/season/{season_number}")
async def get_tv_season_detail(
    tv_id: str,
    season_number: int,
    request: Request,
    db: AsyncSession = Depends(get_session)
):
    """兼容 TMDB 的剧集季度详情接口"""
    return await _proxy_request(f"tv/{tv_id}/season/{season_number}", request, db)

@router.get("/{path:path}")
async def catch_all_tmdb(path: str, request: Request, db: AsyncSession = Depends(get_session)):
    """兜底转发所有其他 TMDB 请求"""
    return await _proxy_request(path, request, db)

async def _proxy_request(endpoint: str, request: Request, db: AsyncSession):
    # 获取并注入完整参数，确保缓存键一致性
    params = tmdb_client.get_full_params(dict(request.query_params))
    
    # 1. 尝试从缓存获取
    cached_data, is_stale = await cache_service.get(db, endpoint, params)
    
    # 如果命中了新鲜缓存，直接返回
    if cached_data and not is_stale:
        logger.info(f"命中新鲜缓存: {endpoint}")
        return cached_data

    # 2. 调用 TMDB 获取原始数据 (如果缓存不存在，或者已过优先缓存期)
    try:
        if cached_data:
            logger.info(f"缓存已过优先期，尝试请求 TMDB 更新: {endpoint}")
        else:
            logger.info(f"缓存未命中，请求 TMDB: {endpoint}")
            
        data = await tmdb_client.get(endpoint, params=params)
        
        # 请求成功，设置/更新缓存
        await cache_service.set(db, endpoint, params, data)
        
        # 异步触发同步逻辑
        asyncio.create_task(_background_sync(data, endpoint, db))
        
        return data

    except Exception as e:
        # 如果请求失败且有过期缓存，则回退到过期缓存
        if cached_data:
            logger.warning(f"请求 TMDB 失败，回退到过期缓存: {str(e)}")
            return cached_data
        
        # 否则抛出异常
        if isinstance(e, httpx.HTTPStatusError):
            logger.error(f"TMDB API 请求失败: {e.response.status_code} - {endpoint}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"TMDB API error: {e.response.text}"
            )
        else:
            logger.error(f"代理请求发生意外错误: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal Server Error")

async def _background_sync(data: Dict[str, Any], endpoint: str, db: AsyncSession):
    """后台同步逻辑"""
    try:
        results_to_sync = []
        
        # 处理搜索结果列表
        if "results" in data and isinstance(data["results"], list):
            for item in data["results"]:
                res = _map_to_scraper_result(item)
                if res:
                    results_to_sync.append(res)
        # 处理详情单条数据
        elif "id" in data:
            res = _map_to_scraper_result(data)
            if res:
                results_to_sync.append(res)
        
        if results_to_sync:
            # 注意：在后台任务中使用新的 session 或确保当前 session 仍然可用
            # 这里简化处理，实际生产建议从 session_factory 创建新 session
            from core.database import async_session_factory
            async with async_session_factory() as session:
                await media_service.sync_results(session, results_to_sync)
    except Exception as e:
        logger.error(f"后台同步失败: {str(e)}")

def _map_to_scraper_result(item: Dict[str, Any]) -> Optional[ScraperMediaResult]:
    """将 TMDB 原始数据映射为内部通用的 ScraperMediaResult"""
    try:
        if "id" not in item:
            return None
            
        return ScraperMediaResult(
            title=item.get("title") or item.get("name") or "Unknown",
            original_title=item.get("original_title") or item.get("original_name"),
            overview=item.get("overview"),
            release_date=item.get("release_date") or item.get("first_air_date"),
            poster_path=item.get("poster_path"),
            backdrop_path=item.get("backdrop_path"),
            adult=item.get("adult", False),
            source="tmdb",
            source_id=str(item.get("id")),
            raw_data=item
        )
    except Exception:
        return None
