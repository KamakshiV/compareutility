from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.database_url import (
    align_supabase_pooler_username,
    connect_args_for_asyncpg,
    log_effective_db_target,
    log_supabase_pooler_hint_if_render,
    normalize_database_url,
    normalize_pooler_typo_in_database_url,
    rewrite_supabase_direct_to_session_pooler_on_render,
    validate_database_url_dns_on_render,
)

settings = get_settings()
_normalized_url = normalize_database_url(settings.database_url)
_after_pooler = rewrite_supabase_direct_to_session_pooler_on_render(_normalized_url)
_database_url = normalize_pooler_typo_in_database_url(align_supabase_pooler_username(_after_pooler))
if _database_url == _normalized_url:
    log_supabase_pooler_hint_if_render(_normalized_url)
log_effective_db_target(_database_url)
validate_database_url_dns_on_render(_database_url)

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
