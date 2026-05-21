import asyncio
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_factory, get_session, run_with_db_recovery
from core.logger import logger
from core.tmdb_client import tmdb_client
from modules.media.cache_service import cache_service
from modules.media.service import media_service
from modules.scrapers.base import ScraperMediaResult

router = APIRouter(prefix="/3")

# 限制后台同步任务的并发数，防止内存泄漏和数据库压力
sync_semaphore = asyncio.Semaphore(5)


@router.get("/search/movie")
async def search_movie(
    request: Request,
    background_tasks: BackgroundTasks,
    query: str = Query(..., description="搜索关键词"),
    db: AsyncSession = Depends(get_session),
):
    """兼容 TMDB 的电影搜索接口。"""
    return await _proxy_request("search/movie", request, db, background_tasks)


@router.get("/search/tv")
async def search_tv(
    request: Request,
    background_tasks: BackgroundTasks,
    query: str = Query(..., description="搜索关键词"),
    db: AsyncSession = Depends(get_session),
):
    """兼容 TMDB 的剧集搜索接口。"""
    return await _proxy_request("search/tv", request, db, background_tasks)


@router.get("/movie/{movie_id}")
async def get_movie_detail(
    movie_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    """兼容 TMDB 的电影详情接口。"""
    return await _proxy_request(f"movie/{movie_id}", request, db, background_tasks)


@router.get("/tv/{tv_id}")
async def get_tv_detail(
    tv_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    """兼容 TMDB 的剧集详情接口。"""
    return await _proxy_request(f"tv/{tv_id}", request, db, background_tasks)


@router.get("/tv/{tv_id}/season/{season_number}")
async def get_tv_season_detail(
    tv_id: str,
    season_number: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    """兼容 TMDB 的剧集季度详情接口。"""
    return await _proxy_request(f"tv/{tv_id}/season/{season_number}", request, db, background_tasks)


@router.get("/{path:path}")
async def catch_all_tmdb(
    path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    """兜底转发所有其他 TMDB 请求。"""
    return await _proxy_request(path, request, db, background_tasks)


async def _load_cache(
    db: AsyncSession,
    endpoint: str,
    params: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], bool]:
    return await run_with_db_recovery(
        lambda: cache_service.get(db, endpoint, params),
        context=f"cache_get:{endpoint}",
    )


async def _save_cache(
    db: AsyncSession,
    endpoint: str,
    params: Dict[str, Any],
    data: Dict[str, Any],
) -> None:
    await run_with_db_recovery(
        lambda: cache_service.set(db, endpoint, params, data),
        context=f"cache_set:{endpoint}",
    )


async def _fetch_tmdb_data(
    endpoint: str,
    params: Dict[str, Any],
    headers: Optional[Dict[str, str]],
    request_query_params: Dict[str, Any],
    auth_header: Optional[str],
) -> Dict[str, Any]:
    try:
        return await tmdb_client.get(endpoint, params=params, headers=headers)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401 and (auth_header or "api_key" in request_query_params):
            logger.warning(
                f"用户提供的凭据无效，尝试使用系统默认凭据重试: "
                f"endpoint={endpoint} type={type(exc).__name__} detail={repr(exc)}"
            )
            retry_query_params = dict(request_query_params)
            retry_query_params.pop("api_key", None)
            full_retry_params = tmdb_client.get_full_params(retry_query_params)
            return await tmdb_client.get(endpoint, params=full_retry_params)
        raise


async def _proxy_request(
    endpoint: str,
    request: Request,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
):
    """处理 TMDB 代理请求，并对数据库与代理异常做自愈降级。"""
    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else None
    request_query_params = dict(request.query_params)
    params = tmdb_client.get_full_params(request_query_params)

    cached_data: Optional[Dict[str, Any]] = None
    is_stale = False

    try:
        cached_data, is_stale = await _load_cache(db, endpoint, params)
    except Exception as exc:
        logger.warning(
            f"读取缓存失败，将降级为直连 TMDB: endpoint={endpoint} "
            f"type={type(exc).__name__} detail={repr(exc)}"
        )

    if cached_data and not is_stale:
        logger.info(f"命中新鲜缓存: endpoint={endpoint}")
        return cached_data

    try:
        if cached_data:
            logger.info(f"缓存已过优先期，尝试请求 TMDB 更新: endpoint={endpoint}")
        else:
            logger.info(f"缓存未命中，请求 TMDB: endpoint={endpoint}")

        data = await _fetch_tmdb_data(
            endpoint,
            params,
            headers,
            request_query_params,
            auth_header,
        )

        try:
            await _save_cache(db, endpoint, params, data)
        except Exception as exc:
            logger.warning(
                f"写入缓存失败，本次请求继续返回 TMDB 数据: endpoint={endpoint} "
                f"type={type(exc).__name__} detail={repr(exc)}"
            )

        background_tasks.add_task(_background_sync, data, endpoint)
        return data

    except Exception as exc:
        if cached_data:
            logger.warning(
                f"请求 TMDB 失败，回退到过期缓存: endpoint={endpoint} "
                f"type={type(exc).__name__} detail={repr(exc)}"
            )
            return cached_data

        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            log_func = logger.warning if status_code == 404 else logger.error
            log_func(
                f"TMDB API 请求失败: endpoint={endpoint} status_code={status_code} "
                f"type={type(exc).__name__} detail={repr(exc)}"
            )
            raise HTTPException(
                status_code=status_code,
                detail=f"TMDB API error: {exc.response.text}",
            )

        logger.error(
            f"代理请求发生意外错误: endpoint={endpoint} type={type(exc).__name__} detail={repr(exc)}"
        )
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def _background_sync(data: Dict[str, Any], endpoint: str):
    """后台同步逻辑。"""
    async with sync_semaphore:
        try:
            results_to_sync = []

            if "results" in data and isinstance(data["results"], list):
                for item in data["results"]:
                    res = _map_to_scraper_result(item)
                    if res:
                        results_to_sync.append(res)
            elif "id" in data:
                res = _map_to_scraper_result(data)
                if res:
                    results_to_sync.append(res)

            if not results_to_sync:
                return

            async def _sync_operation() -> None:
                async with async_session_factory() as session:
                    await media_service.sync_results(session, results_to_sync)

            await run_with_db_recovery(
                _sync_operation,
                context=f"background_sync:{endpoint}",
            )
            logger.info(f"后台同步完成: endpoint={endpoint} synced_count={len(results_to_sync)}")
        except Exception as exc:
            logger.warning(
                f"后台同步失败，已跳过本次同步: endpoint={endpoint} "
                f"type={type(exc).__name__} detail={repr(exc)}"
            )


def _map_to_scraper_result(item: Dict[str, Any]) -> Optional[ScraperMediaResult]:
    """将 TMDB 原始数据映射为内部通用的 ScraperMediaResult。"""
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
            raw_data=item,
        )
    except Exception as exc:
        logger.warning(
            f"映射 TMDB 数据失败，已跳过该条记录: type={type(exc).__name__} detail={repr(exc)}"
        )
        return None
