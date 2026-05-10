from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.database_url import (
    connect_args_for_asyncpg,
    log_supabase_pooler_hint_if_render,
    normalize_database_url,
)

settings = get_settings()
_database_url = normalize_database_url(settings.database_url)
log_supabase_pooler_hint_if_render(_database_url)

engine = create_async_engine(
    _database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    connect_args=connect_args_for_asyncpg(_database_url),
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
