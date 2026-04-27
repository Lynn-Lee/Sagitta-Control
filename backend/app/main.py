"""
SagittaDB — FastAPI 应用入口
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import register_exception_handlers
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

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("SagittaDB starting env=%s version=2.0.0", settings.APP_ENV)
    yield
    await engine.dispose()
    logger.info("SagittaDB shutdown complete")


app = FastAPI(
    title="SagittaDB — 矢准数据",
    description="企业级数据库工单审核、在线查询、可观测中心 API",
    version="2.0.0",
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
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 异常处理 ─────────────────────────────────────────────────
register_exception_handlers(app)

# ─── 路由注册 ─────────────────────────────────────────────────
API_V1 = "/api/v1"

app.include_router(auth.router,       prefix=f"{API_V1}/auth",      tags=["认证"])
app.include_router(instance.router,   prefix=f"{API_V1}/instances",  tags=["实例管理"])
app.include_router(workflow.router,   prefix=f"{API_V1}/workflow",   tags=["SQL 工单"])
app.include_router(query.router,      prefix=f"{API_V1}/query",      tags=["在线查询"])
app.include_router(query_priv.router, prefix=f"{API_V1}/query",      tags=["查询权限"])
app.include_router(slowlog.router,    prefix=f"{API_V1}/slowlog",    tags=["慢日志"])
app.include_router(slowlog.router,    prefix=f"{API_V1}/sql-analysis", tags=["SQL 分析"])
app.include_router(diagnostic.router, prefix=f"{API_V1}/diagnostic", tags=["会话诊断"])
app.include_router(archive.router,    prefix=f"{API_V1}/archive",    tags=["数据归档"])
app.include_router(optimize.router,   prefix=f"{API_V1}/optimize",   tags=["SQL 优化"])
app.include_router(monitor.router,    prefix=f"{API_V1}/monitor",    tags=["可观测中心"])
app.include_router(system.router,     prefix=f"{API_V1}/system",     tags=["系统管理"])
app.include_router(ai.router,            prefix=f"{API_V1}/ai",             tags=["AI 能力"])
app.include_router(approval_flow.router, prefix=f"{API_V1}/approval-flows",  tags=["审批流管理"])
app.include_router(masking.router,        prefix=f"{API_V1}/masking",         tags=["数据脱敏"])
app.include_router(masking.template_router, prefix=f"{API_V1}/workflow-templates", tags=["工单模板"])

from app.routers.monitor import sd_router  # noqa: E402

app.include_router(sd_router, prefix="/internal", tags=["内部接口"])


@app.get("/health", tags=["健康检查"])
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/", tags=["健康检查"])
async def root():
    return {"message": "SagittaDB 矢准数据", "docs": "/docs"}
