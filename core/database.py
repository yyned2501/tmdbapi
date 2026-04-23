from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_scoped_session
from sqlalchemy.orm import sessionmaker, declarative_base
from asyncio import current_task
from core.config import config

# 创建异步引擎
engine = create_async_engine(
    config.database.url,
    echo=False,
    future=True,
)

# 创建会话工厂
async_session_factory = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# 创建作用域会话 (协程安全)
AsyncScopedSession = async_scoped_session(
    async_session_factory,
    scopefunc=current_task,
)

# 基础模型类
Base = declarative_base()

async def get_session():
    """获取数据库会话的依赖项"""
    async with async_session_factory() as session:
        yield session

__all__ = ["engine", "AsyncScopedSession", "Base", "get_session"]
