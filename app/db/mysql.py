from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base

settings = get_settings()
logger = logging.getLogger(__name__)

_SCHEMA_LOCK_NAME = 'literature_schema_init'
_SCHEMA_LOCK_TIMEOUT = 45
_SCHEMA_INIT_RETRIES = 5

# ============================================================================
# FastAPI 异步引擎 — mysql+aiomysql://
# ============================================================================

def _web_engine_options() -> dict:
    return {
        'echo': False,
        # aiomysql 0.2.x requires ping(reconnect), while SQLAlchemy's generic
        # pre-ping calls ping() without arguments. Keep explicit SELECT 1 checks
        # in _new_checked_session instead of enabling pool_pre_ping here.
        'pool_pre_ping': False,
        'pool_size': settings.mysql_pool_size,
        'max_overflow': settings.mysql_max_overflow,
        'pool_recycle': settings.mysql_pool_recycle_seconds,
        'pool_timeout': settings.mysql_pool_timeout_seconds,
        'pool_reset_on_return': 'rollback',
        'connect_args': {
            'connect_timeout': settings.mysql_connect_timeout_seconds,
            'init_command': "SET TIME_ZONE = '+08:00'",
        },
    }


engine = create_async_engine(
    settings.mysql_dsn,
    **_web_engine_options(),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession,
)


# ============================================================================
# Celery 同步引擎 — mysql+pymysql://
# ============================================================================

def _celery_sync_dsn() -> str:
    """将异步 DSN (mysql+aiomysql://) 转换为同步 DSN (mysql+pymysql://)。"""
    return settings.mysql_dsn.replace('mysql+aiomysql://', 'mysql+pymysql://', 1)


celery_engine = create_engine(
    _celery_sync_dsn(),
    echo=False,
    pool_pre_ping=True,  # pymysql 驱动支持池化，可以用 pool_pre_ping 回收死连接
    pool_size=1,
    max_overflow=1,
    pool_recycle=settings.mysql_pool_recycle_seconds,
    pool_reset_on_return='rollback',
    pool_timeout=settings.mysql_pool_timeout_seconds,
    connect_args={
        'connect_timeout': settings.mysql_connect_timeout_seconds,
        'init_command': "SET TIME_ZONE = '+08:00'",
    },
)

CelerySessionLocal = sessionmaker(
    celery_engine,
    expire_on_commit=False,
    autoflush=False,
    class_=Session,
)


# ============================================================================
# Web 端异步 session 获取
# ============================================================================

async def _new_checked_session(factory: async_sessionmaker[AsyncSession]) -> AsyncSession:
    retries = max(settings.mysql_connect_retries, 1)
    last_error: Exception | None = None

    for attempt in range(retries):
        session = factory()
        try:
            await session.execute(text('SELECT 1'))
            return session
        except Exception as exc:
            last_error = exc
            try:
                await session.rollback()
            except Exception:
                pass
            try:
                await session.close()
            except Exception:
                pass

            if attempt + 1 >= retries:
                break

            await asyncio.sleep(0.2 * (attempt + 1))

    assert last_error is not None
    raise last_error


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = await _new_checked_session(AsyncSessionLocal)
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ============================================================================
# Celery 同步 session 上下文管理器
# ============================================================================


@contextmanager
def celery_db():
    """
    Celery worker 专用同步 session。

    用法：
        with celery_db() as db:
            paper = db.get(Paper, paper_id)
            db.commit()
    """
    session = CelerySessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def migrate_model_config_schema(conn) -> None:
    """为已有库补齐 model_configs 的场景路由字段。"""
    table_exists = (
        await conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'model_configs'
                LIMIT 1
                """
            )
        )
    ).first()
    if not table_exists:
        return

    rows = (
        await conn.execute(
            text(
                """
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'model_configs'
                  AND COLUMN_NAME IN ('scenario', 'is_primary')
                """
            )
        )
    ).all()
    existing = {row[0] for row in rows}

    if 'scenario' not in existing:
        await conn.execute(text("ALTER TABLE model_configs ADD COLUMN scenario VARCHAR(30) NOT NULL DEFAULT 'default'"))
    if 'is_primary' not in existing:
        await conn.execute(
            text('ALTER TABLE model_configs ADD COLUMN is_primary TINYINT(1) NOT NULL DEFAULT 0')
        )

    await conn.execute(
        text(
            """
            UPDATE model_configs
            SET scenario = 'qa', is_primary = 1
            WHERE model_type = 'llm'
              AND (scenario IS NULL OR scenario = '')
            """
        )
    )
    await conn.execute(
        text(
            """
            UPDATE model_configs
            SET scenario = 'default'
            WHERE model_type <> 'llm'
              AND (scenario IS NULL OR scenario = '')
            """
        )
    )

    if 'scenario' not in existing:
        await conn.execute(
            text("ALTER TABLE model_configs MODIFY COLUMN scenario VARCHAR(30) NOT NULL DEFAULT 'default'")
        )


def _mysql_errno(exc: Exception) -> int | None:
    orig = getattr(exc, 'orig', None)
    args = getattr(orig, 'args', None)
    if args and len(args) >= 1 and isinstance(args[0], int):
        return args[0]
    return None


def _is_transient_schema_error(exc: Exception) -> bool:
    err_no = _mysql_errno(exc)
    if err_no in {1684, 1205, 1213}:
        return True
    message = str(exc).lower()
    return 'being modified by concurrent ddl' in message or 'metadata lock' in message


async def _acquire_schema_lock(conn) -> None:
    for attempt in range(_SCHEMA_INIT_RETRIES):
        result = await conn.execute(
            text(f"SELECT GET_LOCK('{_SCHEMA_LOCK_NAME}', {_SCHEMA_LOCK_TIMEOUT})")
        )
        if result.scalar() == 1:
            return
        await asyncio.sleep(0.3 * (attempt + 1))
    raise RuntimeError('无法获取数据库 schema 初始化锁，请稍后重试')


async def _release_schema_lock(conn) -> None:
    await conn.execute(text(f"SELECT RELEASE_LOCK('{_SCHEMA_LOCK_NAME}')"))


async def create_all_tables() -> None:
    """FastAPI startup 时建表（幂等）。"""
    last_error: Exception | None = None

    for attempt in range(_SCHEMA_INIT_RETRIES):
        try:
            async with engine.begin() as conn:
                await _acquire_schema_lock(conn)
                try:
                    await conn.run_sync(Base.metadata.create_all)
                    await migrate_model_config_schema(conn)
                finally:
                    await _release_schema_lock(conn)
            return
        except OperationalError as exc:
            last_error = exc
            if not _is_transient_schema_error(exc) or attempt + 1 >= _SCHEMA_INIT_RETRIES:
                raise
            logger.warning(
                'schema init retry %s/%s after transient mysql error: %s',
                attempt + 1,
                _SCHEMA_INIT_RETRIES,
                exc,
            )
            await asyncio.sleep(0.5 * (attempt + 1))

    if last_error:
        raise last_error