from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from weakref import WeakKeyDictionary

from sqlalchemy import BigInteger, DateTime, MetaData, func
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.core.config import get_settings
from app.core.dedupe import compute_dedupe_key_for_instance

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower()


class BigIntPKMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


@event.listens_for(Base, "before_insert", propagate=True)
def _assign_dedupe_key_before_insert(mapper, connection, target) -> None:
    if not hasattr(target, "dedupe_key"):
        return
    dedupe_key = compute_dedupe_key_for_instance(target)
    if dedupe_key is not None:
        target.dedupe_key = dedupe_key


@event.listens_for(Base, "before_update", propagate=True)
def _assign_dedupe_key_before_update(mapper, connection, target) -> None:
    if not hasattr(target, "dedupe_key"):
        return
    dedupe_key = compute_dedupe_key_for_instance(target)
    if dedupe_key is not None:
        target.dedupe_key = dedupe_key


settings = get_settings()
_engines_by_loop: WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncEngine] = (
    WeakKeyDictionary()
)
_sessionmakers_by_loop: WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    async_sessionmaker[AsyncSession],
] = WeakKeyDictionary()


def _current_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError as exc:
        raise RuntimeError(
            "Async database sessions must be created inside a running event loop"
        ) from exc


def _create_engine() -> AsyncEngine:
    connect_args = {}
    if settings.database_url.startswith("postgresql+asyncpg"):
        connect_args = {
            "server_settings": {
                "application_name": "finance-backend",
                "statement_timeout": str(settings.database_statement_timeout_ms),
                "lock_timeout": str(settings.database_lock_timeout_ms),
                "idle_in_transaction_session_timeout": str(
                    settings.database_idle_in_transaction_timeout_ms
                ),
            }
        }
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_recycle=settings.database_pool_recycle_seconds,
        pool_use_lifo=True,
    )


def get_async_engine() -> AsyncEngine:
    loop = _current_loop()
    engine = _engines_by_loop.get(loop)
    if engine is None:
        engine = _create_engine()
        _engines_by_loop[loop] = engine
    return engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    loop = _current_loop()
    sessionmaker = _sessionmakers_by_loop.get(loop)
    if sessionmaker is None:
        sessionmaker = async_sessionmaker(
            get_async_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
        _sessionmakers_by_loop[loop] = sessionmaker
    return sessionmaker


class _LoopBoundSessionFactory:
    def __call__(self, *args, **kwargs) -> AsyncSession:
        return get_sessionmaker()(*args, **kwargs)


class _LoopBoundEngineProxy:
    def __getattr__(self, name: str):
        return getattr(get_async_engine(), name)


engine = _LoopBoundEngineProxy()
SessionLocal = _LoopBoundSessionFactory()

# Ensure every mapped table is registered in SQLAlchemy metadata before
# runtime flushes touch cross-module foreign keys such as action_recommendations.
from app.core.model_registry import load_all_models  # noqa: E402

load_all_models()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def dispose_all_engines() -> None:
    engines = list(_engines_by_loop.values())
    _sessionmakers_by_loop.clear()
    _engines_by_loop.clear()
    for db_engine in engines:
        await db_engine.dispose()
