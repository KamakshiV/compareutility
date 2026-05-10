from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()


def _connect_args(url: str) -> dict:
    """asyncpg needs explicit SSL for cloud Postgres (e.g. Supabase); local Docker usually has no TLS."""
    u = url.lower()
    if "127.0.0.1" in u or "localhost" in u:
        return {}
    # Remote hosts (Render → Supabase, etc.): enable TLS without relying on query-string quirks.
    return {"ssl": True}


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    connect_args=_connect_args(settings.database_url),
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
