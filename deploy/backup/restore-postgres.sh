#!/usr/bin/env bash
# ─── Sagitta Control PostgreSQL 恢复脚本 ────────────────────────────────────────────
# 用法:
#   ./restore-postgres.sh /path/to/sagitta_control_sagitta_control_20260101_020000.sql.gz
#   ./restore-postgres.sh s3://my-bucket/sagitta-control/db/sagitta_control_sagitta_control_20260101_020000.sql.gz

set -euo pipefail

BACKUP_FILE="${1:-}"
if [[ -z "${BACKUP_FILE}" ]]; then
  echo "用法: $0 <备份文件路径或 S3 URI>"
  exit 1
fi

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-sagitta}"
POSTGRES_DB="${POSTGRES_DB:-sagitta_control}"

export PGPASSWORD="${POSTGRES_PASSWORD:-}"

# ─── 从 S3 下载（如果是 S3 URI）──────────────────────────────────────────────
if [[ "${BACKUP_FILE}" == s3://* ]]; then
  LOCAL_FILE="/tmp/$(basename "${BACKUP_FILE}")"
  echo "[$(date)] 从 S3 下载: ${BACKUP_FILE}..."
  aws s3 cp "${BACKUP_FILE}" "${LOCAL_FILE}"
  BACKUP_FILE="${LOCAL_FILE}"
fi

echo "[$(date)] 准备恢复到 ${POSTGRES_DB}..."
echo "⚠️  警告：此操作将清空并重建数据库 ${POSTGRES_DB}！"
read -rp "输入 'yes' 确认继续: " CONFIRM
if [[ "${CONFIRM}" != "yes" ]]; then
  echo "操作已取消"
  exit 0
fi

# ─── 终止现有连接 ──────────────────────────────────────────────────────────────
psql \
  -h "${POSTGRES_HOST}" \
  -p "${POSTGRES_PORT}" \
  -U "${POSTGRES_USER}" \
  -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${POSTGRES_DB}' AND pid <> pg_backend_pid();"

# ─── 删除并重建数据库 ──────────────────────────────────────────────────────────
psql \
  -h "${POSTGRES_HOST}" \
  -p "${POSTGRES_PORT}" \
  -U "${POSTGRES_USER}" \
  -d postgres \
  -c "DROP DATABASE IF EXISTS ${POSTGRES_DB}; CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

# ─── 恢复数据 ──────────────────────────────────────────────────────────────────
echo "[$(date)] 恢复中..."
zcat "${BACKUP_FILE}" | psql \
  -h "${POSTGRES_HOST}" \
  -p "${POSTGRES_PORT}" \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --single-transaction \
  --set ON_ERROR_STOP=1

echo "[$(date)] ✅ 恢复完成: ${POSTGRES_DB}"
