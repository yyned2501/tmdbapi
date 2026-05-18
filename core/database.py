from asyncio import current_task
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, InterfaceError
from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import config
from core.logger import logger

T = TypeVar("T")


# 基础模型类
Base = declarative_base()


def _get_pool_recycle_seconds() -> int:
    """读取连接回收时间，默认 30 分钟。"""
    recycle_seconds = int(getattr(config.database, "pool_recycle_seconds", 1800))
    return recycle_seconds if recycle_seconds > 0 else 1800


# 创建异步引擎
engine = create_async_engine(
    config.database.url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=_get_pool_recycle_seconds(),
)

# 创建会话工厂
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 创建作用域会话 (协程安全)
AsyncScopedSession = async_scoped_session(
    async_session_factory,
    scopefunc=current_task,
)


async def _dispose_engine_safely() -> None:
    """安全释放连接池中的失效连接。"""
    try:
        await engine.dispose()
        logger.warning("数据库连接池已释放，后续请求将自动重建连接")
    except Exception as exc:
        logger.error(
            f"释放数据库连接池失败: type={type(exc).__name__} detail={repr(exc)}"
        )


async def ensure_database_ready() -> bool:
    """执行一次显式数据库探活。"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("数据库探活成功")
        return True
    except Exception as exc:
        logger.error(
            f"数据库探活失败: type={type(exc).__name__} detail={repr(exc)}"
        )
        await _dispose_engine_safely()
        return False


def is_database_connection_error(exc: Exception) -> bool:
    """判断是否为可恢复的数据库连接错误。"""
    if isinstance(exc, (InterfaceError, DBAPIError)):
        return True

    message = str(exc).lower()
    detail = repr(exc).lower()
    keywords = [
        "connection is closed",
        "connection was closed",
        "connection not open",
        "server closed the connection",
        "terminating connection",
        "connection reset",
        "broken pipe",
    ]
    return any(keyword in message or keyword in detail for keyword in keywords)


async def run_with_db_recovery(
    operation: Callable[[], Awaitable[T]],
    *,
    context: str,
    retries: int = 1,
) -> T:
    """在数据库连接失效时自动释放连接池并重试。"""
    attempt = 0
    while True:
        try:
            return await operation()
        except Exception as exc:
            if attempt >= retries or not is_database_connection_error(exc):
                raise

            attempt += 1
            logger.warning(
                f"检测到数据库连接异常，准备自愈重试: context={context} "
                f"attempt={attempt}/{retries} type={type(exc).__name__} detail={repr(exc)}"
            )
            await _dispose_engine_safely()


async def get_session():
    """获取数据库会话的依赖项。"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


__all__ = [
    "engine",
    "async_session_factory",
    "AsyncScopedSession",
    "Base",
    "get_session",
    "ensure_database_ready",
    "is_database_connection_error",
    "run_with_db_recovery",
]
