# app/tools/init_schema.py
from __future__ import annotations
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

# Важно: подтянуть Base и ВСЕ модели, чтобы они зарегистрировались в Base.metadata
from app.infrastructure.db.base import Base
# Если у тебя есть модуль, который импортирует все модели — импортни его:
# например, так:
from app.infrastructure.db import models as _models  # noqa: F401  (просто чтобы side-effect импорта сработал)

from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    dsn = settings.DATABASE_URL  # например: postgresql+asyncpg://app:app@db:5432/app
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")

    engine = create_async_engine(dsn, pool_pre_ping=True, echo=False)
    async with engine.begin() as conn:
        # Если нужна “чистая” база всякий раз — сначала раскомментируй drop_all:
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
