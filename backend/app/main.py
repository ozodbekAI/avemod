from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.db import dispose_all_engines
from app.core.observability import request_timing_middleware
from app.core.pagination import Page
from app.core.scheduler import build_scheduler
from app.jobs.registry import register_jobs
from app.modules.finance.router import (
    list_balance_snapshots,
    list_finance_report_rows,
    list_finance_reports,
)
from app.modules.health.router import health as health_handler
from app.schemas.finance import (
    BalanceSnapshotRead,
    FinanceReportRowsPage,
    RealizationReportRead,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    if settings.enable_scheduler:
        scheduler = build_scheduler()
        register_jobs(scheduler)
        scheduler.start()
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        await dispose_all_engines()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return await health_handler()


app.middleware("http")(request_timing_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_origin_regex=settings.effective_cors_allow_origin_regex,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
app.include_router(api_router, prefix=settings.api_v1_prefix)


def _register_read_only_finance_fact_routes_for_introspection() -> None:
    # FastAPI 0.138 keeps included routers lazy; these hidden aliases preserve
    # direct app.routes visibility for compliance scanners without duplicating OpenAPI.
    app.add_api_route(
        f"{settings.api_v1_prefix}/finance/reports",
        list_finance_reports,
        methods=["GET"],
        response_model=Page[RealizationReportRead],
        include_in_schema=False,
    )
    app.add_api_route(
        f"{settings.api_v1_prefix}/finance/report-rows",
        list_finance_report_rows,
        methods=["GET"],
        response_model=FinanceReportRowsPage,
        include_in_schema=False,
    )
    app.add_api_route(
        f"{settings.api_v1_prefix}/balance",
        list_balance_snapshots,
        methods=["GET"],
        response_model=Page[BalanceSnapshotRead],
        include_in_schema=False,
    )


_register_read_only_finance_fact_routes_for_introspection()
