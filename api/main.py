import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from api.v1.media import router as media_router
from api.v1.tmdb_proxy import router as tmdb_router
from core import config
from core.database import Base, engine, ensure_database_ready, async_session_factory
from core.logger import logger

async def cache_cleanup_loop():
    """后台循环，定期清理已过期的 API 缓存。"""
    cleanup_interval = 3600 * 6  # 每 6 小时清理一次
    logger.info("后台缓存清理任务已启动 (轮询周期: 6 小时)")
    # 启动时先等待一小会儿，避开高负载的启动期
    await asyncio.sleep(60)
    while True:
        try:
            logger.info("开始执行定期 API 缓存清理...")
            from sqlalchemy import delete
            from modules.media.models import APICache
            from datetime import datetime, timezone
            
            async with async_session_factory() as session:
                now = datetime.now(timezone.utc)
                stmt = delete(APICache).where(APICache.expires_at <= now)
                result = await session.execute(stmt)
                await session.commit()
                deleted_count = result.rowcount if hasattr(result, "rowcount") else "未知"
                logger.info(f"定期 API 缓存清理完成，清除了 {deleted_count} 条过期缓存")
        except asyncio.CancelledError:
            logger.info("后台缓存清理任务已取消")
            break
        except Exception as exc:
            logger.error(f"执行后台缓存清理时发生异常: type={type(exc).__name__} detail={repr(exc)}")
        
        await asyncio.sleep(cleanup_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # [Startup 阶段]
    logger.info("正在启动应用...")

    database_ready = await ensure_database_ready()
    startup_check_required = bool(getattr(config.database, "startup_check_required", False))
    if not database_ready:
        message = (
            "启动阶段数据库不可用，应用将以降级模式继续运行，待数据库恢复后自动自愈"
            if not startup_check_required
            else "启动阶段数据库不可用，当前配置要求数据库必须可用，应用启动终止"
        )
        logger.warning(message)
        if startup_check_required:
            raise RuntimeError(message)
    else:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("数据库表已同步")
        except Exception as exc:
            logger.error(
                f"启动阶段同步数据库表失败: type={type(exc).__name__} detail={repr(exc)}"
            )
            if startup_check_required:
                raise

    # 启动后台缓存清理循环
    cleanup_task = asyncio.create_task(cache_cleanup_loop())

    yield  # 挂起，此时应用对外提供服务

    # [Shutdown 阶段]
    logger.info("正在关闭应用...")
    
    # 取消后台缓存清理任务
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    from core.tmdb_client import tmdb_client
    await tmdb_client.close()
    logger.info("TMDB Client 已关闭")


app = FastAPI(
    title="TMDB API 媒体元数据管理后端",
    description="支持 TMDB 和 MDC 刮削的媒体元数据管理服务",
    version="0.1.0",
    lifespan=lifespan,
)

# 注册路由
app.include_router(media_router, prefix="/api/v1")
app.include_router(tmdb_router)  # 兼容 TMDB 的 /3 前缀路由


@app.get("/")
async def root():
    return {"message": "TMDB API 媒体元数据管理后端已就绪", "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
