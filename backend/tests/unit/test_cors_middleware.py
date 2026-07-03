from fastapi.middleware.cors import CORSMiddleware

from app.main import app


def test_cors_middleware_uses_explicit_methods_and_headers():
    cors_middleware = next(m for m in app.user_middleware if m.cls is CORSMiddleware)

    assert cors_middleware.kwargs["allow_methods"] == ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    assert cors_middleware.kwargs["allow_headers"] == ["Authorization", "Content-Type", "X-Requested-With"]
