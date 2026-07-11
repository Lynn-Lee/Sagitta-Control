"""
Sagitta Control — FastAPI 应用入口
"""
from typing import Any
import logging
from contextlib import asynccontextmanager

from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.auth_cookies import CSRF_HEADER_NAME, validate_csrf_request
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.exceptions import register_exception_handlers
from app.core.integrity import verify_startup_integrity
from app.core.logging import configure_logging
from app.routers import (
    ai,
    approval_flow,
    archive,
    auth,
    diagnostic,
    instance,
    masking,
    monitor,
    optimize,
    query,
    query_priv,
    slowlog,
    system,
    workflow,
)
from app.services.license import LicenseService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    verify_startup_integrity()
    logger.info("Sagitta Control starting env=%s version=3.0.0", settings.APP_ENV)
    yield
    await engine.dispose()
    logger.info("Sagitta Control shutdown complete")


app = FastAPI(
    title="Sagitta Control — 矢准数据库安全管控平台",
    description="企业级数据库安全管控、SQL 工单审核、在线查询、观测中心 API",
    version="3.0.0",
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url="/redoc" if settings.APP_ENV == "development" else None,
    lifespan=lifespan,
)

# ─── 中间件 ────────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", CSRF_HEADER_NAME],
)


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    csrf_error = validate_csrf_request(request)
    if csrf_error is not None:
        return csrf_error
    return await call_next(request)


@app.middleware("http")
async def license_enforcement_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    try:
        async with AsyncSessionLocal() as db:
            check = await LicenseService.check_access(db, request.url.path, request.method)
    except Exception:
        logger.exception("license_check_failed")
        if settings.APP_ENV == "production":
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "License 校验暂时不可用",
                    "code": "LICENSE_UNAVAILABLE",
                },
            )
        return await call_next(request)
    if not check.allowed:
        return JSONResponse(
            status_code=403,
            content={
                "detail": check.reason,
                "code": "LICENSE_REQUIRED",
                "license_status": check.status,
                "feature": check.feature,
            },
        )
    return await call_next(request)

# ─── 异常处理 ─────────────────────────────────────────────────
register_exception_handlers(app)

# ─── 路由注册 ─────────────────────────────────────────────────
API_V1 = "/api/v1"

app.include_router(auth.router,       prefix=f"{API_V1}/auth",      tags=["认证"])
app.include_router(instance.router,   prefix=f"{API_V1}/instances",  tags=["实例管理"])
app.include_router(workflow.router,   prefix=f"{API_V1}/workflow",   tags=["SQL 工单"])
app.include_router(query.router,      prefix=f"{API_V1}/query",      tags=["在线查询"])
app.include_router(query_priv.router, prefix=f"{API_V1}/query",      tags=["查询权限"])
app.include_router(query.router,      prefix=f"{API_V1}/sql-exec",   tags=["在线查询"])
app.include_router(query_priv.router, prefix=f"{API_V1}/sql-exec",   tags=["查询权限"])
app.include_router(slowlog.router,    prefix=f"{API_V1}/slowlog",    tags=["慢日志"])
app.include_router(slowlog.router,    prefix=f"{API_V1}/sql-analysis", tags=["SQL 洞察"])
app.include_router(diagnostic.router, prefix=f"{API_V1}/diagnostic", tags=["会话诊断"])
app.include_router(archive.router,    prefix=f"{API_V1}/archive",    tags=["数据归档"])
app.include_router(optimize.router,   prefix=f"{API_V1}/optimize",   tags=["SQL 优化"])
app.include_router(monitor.router,    prefix=f"{API_V1}/monitor",    tags=["观测中心"])
app.include_router(system.router,     prefix=f"{API_V1}/system",     tags=["系统管理"])
app.include_router(ai.router,            prefix=f"{API_V1}/ai",             tags=["AI 能力"])
app.include_router(approval_flow.router, prefix=f"{API_V1}/approval-flows",  tags=["审批流管理"])
app.include_router(masking.router,        prefix=f"{API_V1}/masking",         tags=["数据脱敏"])
app.include_router(masking.template_router, prefix=f"{API_V1}/workflow-templates", tags=["工单模板"])

from app.routers.monitor import sd_router  # noqa: E402

app.include_router(sd_router, prefix="/internal", tags=["内部接口"])


@app.get("/health", tags=["健康检查"])
async def health_check() -> dict[str, Any]:
    return {"status": "ok", "version": "3.0.0"}


@app.get("/", tags=["健康检查"])
async def root() -> dict[str, Any]:
    return {"message": "Sagitta Control 矢准数据库安全管控平台", "docs": "/docs"}
