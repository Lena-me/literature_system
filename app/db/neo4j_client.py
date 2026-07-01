from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from neo4j import AsyncGraphDatabase
from neo4j._async.driver import AsyncDriver
from neo4j._async.work.session import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class Neo4jManager:
    """Neo4j 数据库连接池管理器（单例模式）。"""

    _instance: Neo4jManager | None = None

    def __new__(cls) -> Neo4jManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self._driver: AsyncDriver | None = None

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = self._create_driver()
        return self._driver

    def _create_driver(self) -> AsyncDriver:
        logger.info(
            '初始化 Neo4j 驱动, uri=%s, user=%s',
            settings.neo4j_uri,
            settings.neo4j_user,
        )
        return AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=settings.neo4j_max_connection_pool_size,
            connection_acquisition_timeout=settings.neo4j_connection_acquisition_timeout,
        )

    async def close(self) -> None:
        if self._driver is not None:
            logger.info('关闭 Neo4j 驱动')
            await self._driver.close()
            self._driver = None

    async def verify_connectivity(self) -> None:
        """验证 Neo4j 连接是否可达。"""
        await self.driver.verify_connectivity()
        logger.info('Neo4j 连接验证成功')


# ============================================================================
# 全局单例
# ============================================================================

neo4j_manager = Neo4jManager()


# ============================================================================
# FastAPI 依赖注入
# ============================================================================

async def get_neo4j_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：提供 Neo4j 异步 session，路由退出后自动关闭。"""
    session = neo4j_manager.driver.session()
    try:
        yield session
    finally:
        await session.close()
