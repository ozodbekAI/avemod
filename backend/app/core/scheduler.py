from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings

settings = get_settings()


def build_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(timezone=settings.scheduler_timezone)
