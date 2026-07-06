from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db.base import Base

settings = get_settings()


# ============================================================================
# FastAPI 异步引擎 — mysql+aiomysql://
# ============================================================================

def _web_engine_options() -> dict:
    return {
        'echo': False,
        'pool_pre_ping': settings.mysql_pool_pre_ping,
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


async def migrate_model_config_schema() -> None:
    """为已有库补齐 model_configs 的场景路由字段。"""
    from sqlalchemy import text

    async with engine.begin() as conn:
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
            await conn.execute(text('ALTER TABLE model_configs ADD COLUMN scenario VARCHAR(30) NULL'))
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


async def create_all_tables() -> None:
    """FastAPI startup 时建表（幂等）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await migrate_model_config_schema()
