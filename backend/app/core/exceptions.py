"""
统一异常处理：所有未捕获的异常都在这里统一格式化返回。
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    """业务异常基类。"""
    def __init__(self, message: str, code: int = 400, detail: str | None = None):
        self.message = message
        self.code = code
        self.detail = detail
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, code=404)


class ForbiddenException(AppException):
    def __init__(self, message: str = "没有操作权限"):
        super().__init__(message, code=403)


class ConflictException(AppException):
    def __init__(self, message: str = "资源已存在"):
        super().__init__(message, code=409)


class EngineException(AppException):
    """数据库引擎操作异常。"""
    def __init__(self, message: str, db_type: str = ""):
        super().__init__(message, code=500, detail=f"引擎类型: {db_type}")


def _err(code: int, message: str, detail: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"status": code, "msg": message}
    if detail:
        body["detail"] = detail
    return JSONResponse(status_code=code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return _err(exc.code, exc.message, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        return _err(422, "请求参数校验失败", errors)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        import uuid

        from app.core.config import settings

        # 完整异常仅写日志；响应只给通用消息 + 关联 ID，避免泄露内部实现细节（SAG-018）。
        error_id = uuid.uuid4().hex[:12]
        logger.error(
            "unhandled_exception id=%s: %s path=%s",
            error_id,
            str(exc),
            request.url.path,
        )
        if settings.DEBUG:
            return _err(500, "服务器内部错误", f"[{error_id}] {exc}")
        return _err(500, "服务器内部错误", f"关联ID：{error_id}")
