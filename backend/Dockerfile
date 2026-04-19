FROM python:3.12-alpine

WORKDIR /app

# Alpine 用 apk，不依赖 Debian apt 源
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    postgresql-dev \
    curl

# 升级 pip
RUN pip install --no-cache-dir --upgrade pip

# 分两步安装：先装编译依赖重的包，再装其余包
# 这样修改业务代码时不会重新编译 C 扩展
RUN pip install --no-cache-dir \
    "uvicorn[standard]>=0.27.0" \
    asyncpg>=0.29.0 \
    psycopg2-binary>=2.9.9 \
    "passlib[bcrypt]>=1.7.4" \
    cryptography>=42.0.0 \
    "redis[hiredis]>=5.0.1"

RUN pip install --no-cache-dir \
    "fastapi>=0.110.0" \
    python-multipart>=0.0.9 \
    "sqlalchemy>=2.0.0" \
    "alembic>=1.13.0" \
    "pydantic>=2.6.0" \
    "pydantic-settings>=2.2.0" \
    "python-jose[cryptography]>=3.3.0" \
    "pyotp>=2.9.0" \
    "celery>=5.3.6" \
    "flower>=2.0.1" \
    "sqlglot>=23.0.0" \
    "httpx>=0.27.0" \
    "aiomysql>=0.2.0" \
    "clickhouse-connect>=0.7.0" \
    "oracledb>=2.2.0" \
    "python-tds>=1.16.0" \
    "pymongo>=4.6.0" \
    "motor>=3.3.0" \
    "structlog>=24.1.0" \
    "python-dotenv>=1.0.1" \
    "arrow>=1.3.0" \
    "jinja2>=3.1.3" \
    "ldap3>=2.9.1" \
    "openpyxl>=3.1.0"

COPY . .

RUN adduser -D -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
