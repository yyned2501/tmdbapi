from fastapi import FastAPI

from api.v1.media import router as media_router
from api.v1.tmdb_proxy import router as tmdb_router
from core import config
from core.database import Base, engine, ensure_database_ready
from core.logger import logger

app = FastAPI(
    title="TMDB API 媒体元数据管理后端",
    description="支持 TMDB 和 MDC 刮削的媒体元数据管理服务",
    version="0.1.0",
)

# 注册路由
app.include_router(media_router, prefix="/api/v1")
app.include_router(tmdb_router)  # 兼容 TMDB 的 /3 前缀路由


@app.on_event("startup")
async def startup():
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
        return

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


@app.on_event("shutdown")
async def shutdown():
    logger.info("正在关闭应用...")
    from core.tmdb_client import tmdb_client

    await tmdb_client.close()
    logger.info("TMDB Client 已关闭")


@app.get("/")
async def root():
    return {"message": "TMDB API 媒体元数据管理后端已就绪", "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
