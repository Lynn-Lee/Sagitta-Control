#!/usr/bin/env bash
# ─── SagittaDB PostgreSQL 备份脚本 ────────────────────────────────────────────
# 用法:
#   ./backup-postgres.sh                       # 手动备份
#   0 2 * * * /path/to/backup-postgres.sh      # 每天凌晨 2 点自动备份
#
# 依赖: pg_dump, gzip, aws-cli（可选，S3 上传）
# 环境变量（可通过 .env 注入）:
#   POSTGRES_HOST     数据库主机（默认 localhost）
#   POSTGRES_PORT     端口（默认 5432）
#   POSTGRES_USER     用户名（默认 sagitta）
#   POSTGRES_PASSWORD 密码
#   POSTGRES_DB       库名（默认 sagittadb）
#   BACKUP_DIR        本地备份目录（默认 /data/sagittadb/backups）
#   BACKUP_RETAIN_DAYS 本地保留天数（默认 7）
#   S3_BUCKET         S3 存储桶名（留空跳过上传）
#   S3_PREFIX         S3 路径前缀（默认 sagittadb/db）

set -euo pipefail

# ─── 配置 ─────────────────────────────────────────────────────────────────────
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-sagitta}"
POSTGRES_DB="${POSTGRES_DB:-sagittadb}"
BACKUP_DIR="${BACKUP_DIR:-/data/sagittadb/backups}"
BACKUP_RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-7}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-sagittadb/db}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="sagittadb_${POSTGRES_DB}_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

# ─── 创建备份目录 ──────────────────────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"

# ─── 执行备份 ──────────────────────────────────────────────────────────────────
echo "[$(date)] 开始备份 ${POSTGRES_DB}..."

export PGPASSWORD="${POSTGRES_PASSWORD:-}"

pg_dump \
  -h "${POSTGRES_HOST}" \
  -p "${POSTGRES_PORT}" \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --no-owner \
  --no-acl \
  --format=plain \
  | gzip > "${FILEPATH}"

BACKUP_SIZE=$(du -sh "${FILEPATH}" | cut -f1)
echo "[$(date)] 备份完成: ${FILEPATH} (${BACKUP_SIZE})"

# ─── 上传到 S3 ────────────────────────────────────────────────────────────────
if [[ -n "${S3_BUCKET}" ]]; then
  echo "[$(date)] 上传到 s3://${S3_BUCKET}/${S3_PREFIX}/${FILENAME}..."
  aws s3 cp "${FILEPATH}" "s3://${S3_BUCKET}/${S3_PREFIX}/${FILENAME}" \
    --storage-class STANDARD_IA
  echo "[$(date)] S3 上传完成"
fi

# ─── 清理过期备份 ──────────────────────────────────────────────────────────────
echo "[$(date)] 清理 ${BACKUP_RETAIN_DAYS} 天前的备份..."
find "${BACKUP_DIR}" -name "sagittadb_*.sql.gz" -mtime "+${BACKUP_RETAIN_DAYS}" -delete
echo "[$(date)] 备份流程结束"
