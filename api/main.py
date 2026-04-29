from fastapi import FastAPI
from api.v1.media import router as media_router
from api.v1.tmdb_proxy import router as tmdb_router
from core.database import engine, Base
from core.logger import logger

app = FastAPI(
    title="TMDB API 媒体元数据管理后端",
    description="支持 TMDB 和 MDC 刮削的媒体元数据管理服务",
    version="0.1.0"
)

# 注册路由
app.include_router(media_router, prefix="/api/v1")
app.include_router(tmdb_router)  # 兼容 TMDB 的 /3 前缀路由

@app.on_event("startup")
async def startup():
    logger.info("正在启动应用...")
    # 自动创建表 (开发环境下方便，生产环境建议用 Alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表已同步")

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
