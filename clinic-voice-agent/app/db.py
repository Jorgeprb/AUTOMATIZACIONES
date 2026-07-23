"""SQLAlchemy database primitives."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@lru_cache
def get_engine() -> Engine:
    """Build and cache the process-wide SQLAlchemy engine."""
    settings = get_settings()
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "pool_recycle": settings.database_pool_recycle_seconds,
    }
    if settings.database_url.startswith("postgresql+"):
        kwargs.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            connect_args={
                "options": (
                    f"-c statement_timeout={settings.database_statement_timeout_ms} "
                    "-c lock_timeout=10000 -c application_name=clinic_voice_agent"
                )
            },
        )
    return create_engine(settings.database_url, **kwargs)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Build and cache the SQLAlchemy session factory."""
    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        expire_on_commit=False,
        autoflush=False,
    )


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and roll back failed requests consistently."""
    with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
