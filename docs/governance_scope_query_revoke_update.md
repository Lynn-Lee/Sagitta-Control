# 统一治理视角与查询权限撤销审计升级说明

> **文档版本：** v1.0 · 2026-04-21
> **适用范围：** Dashboard、在线查询权限、SQL 工单
> **涉及迁移：** `0014_query_priv_revoke_audit`、`0015_priv_revoke_backfill`

---

## 一、功能概览

本次升级围绕“治理视角统一”和“查询权限撤销可追踪”两条主线展开。

### 1.1 统一治理视角

后端新增统一 `GovernanceScopeService`，Dashboard、查询权限管理视图、SQL 工单视图统一复用同一套范围判断。

| 视角 | 说明 | 数据范围 |
|---|---|---|
| `self` | 普通用户 | 本人数据 |
| `group` | 用户组组长 | 组内有效成员 + 本人 |
| `instance_scope` | 资源组 DBA | 关联资源组实例范围 |
| `global` | 全局 DBA / 超管 | 全量数据 |

统一治理视角只决定“看见哪些数据”，不自动放大业务操作权限。查询权限撤销、SQL 工单审批、执行、取消等操作仍由各业务服务按原有能力字段和权限规则判断。

### 1.2 查询权限管理视图

查询权限页新增治理视角入口：

- 普通用户继续使用“我的权限”。
- 组长可查看组内成员权限，只读。
- 资源组 DBA 可查看资源组实例范围内权限，并可撤销范围内权限。
- 全局 DBA / 超管可查看全量权限，并可撤销。

新增接口：

```http
GET /api/v1/query/privileges/manage/
```

支持参数：

```text
page, page_size, instance_id, user_id, db_name, status
```

其中 `status` 支持：

| status | 说明 |
|---|---|
| `active` | 当前有效且未撤销的查询权限 |
| `revoked` | 已撤销 / 历史软删除的查询权限 |

### 1.3 SQL 工单治理视图

SQL 工单页保留原有任务型入口：

- 我的工单
- 审批记录
- 执行记录

同时新增“工单视图”，按统一治理视角查看范围内工单：

```http
GET /api/v1/workflow/?view=scope
```

操作按钮仍由现有 `can_audit`、`can_execute`、`can_cancel` 等字段控制，不因工单可见而自动放权。

### 1.4 Dashboard 对齐

Dashboard 在线查询概览和 SQL 工单概览改为复用统一治理视角。

返回结构继续保留：

```json
{
  "scope": {
    "mode": "self",
    "label": "我的数据"
  }
}
```

前端会在 Dashboard、查询权限页、SQL 工单页展示一致的视角标签。

---

## 二、查询权限撤销审计

查询权限撤销后不再只是 `is_deleted=1` 的软删除状态，而是记录完整撤销信息。

### 2.1 新增字段

迁移 `0014_query_priv_revoke_audit` 为 `query_privilege` 新增字段：

| 字段 | 说明 |
|---|---|
| `revoked_at` | 撤销时间 |
| `revoked_by_id` | 撤销人用户 ID |
| `revoked_by_name` | 撤销人名称 |
| `revoke_reason` | 撤销原因 |

撤销接口继续复用：

```http
DELETE /api/v1/query/privileges/{priv_id}/
```

请求体可选：

```json
{
  "reason": "撤销原因"
}
```

### 2.2 已撤销权限列表

查询权限页新增“已撤销权限”视图，用于查看已经撤销过的权限记录。

普通用户可看到自己名下已撤销权限；组长、资源组 DBA、全局 DBA、超管按统一治理视角看到对应范围内的已撤销权限。

### 2.3 历史数据回填

迁移 `0015_priv_revoke_backfill` 会回填旧的软删除记录：

```sql
WHERE is_deleted = 1
  AND revoked_at IS NULL
```

回填规则：

| 字段 | 回填值 |
|---|---|
| `revoked_at` | `updated_at`，为空时兜底 `created_at / CURRENT_TIMESTAMP` |
| `revoked_by_name` | `系统/历史数据` |
| `revoke_reason` | `历史软删除记录兼容回填` |

这样“已撤销权限”列表和 Dashboard 撤销统计会保持一致。

### 2.4 Dashboard 撤销统计口径

Dashboard 在线查询概览新增：

- `撤销查询权限数` 卡片
- 治理趋势中的 `撤销权限数`

统计口径：

```text
当前治理视角内，最近 N 天 revoked_at >= period_start 且 is_deleted = 1 的查询权限数量
```

注意：该指标统计的是“当前视角范围内被撤销的权限”，不是“当前用户本人执行的撤销动作数”。

---

## 三、生产升级步骤

以下步骤以 Docker Compose 生产部署为例。执行前请确认当前生产分支、镜像构建方式和 `.env` 配置。

### 3.1 升级前备份

进入生产项目目录：

```bash
cd /opt/SagittaDB
```

确认服务状态：

```bash
docker compose ps
```

备份 PostgreSQL：

```bash
mkdir -p /data/sagittadb/backups
docker compose exec postgres pg_dump -U sagitta -d sagittadb \
  | gzip > /data/sagittadb/backups/sagittadb_$(date +%Y%m%d_%H%M%S).sql.gz
```

如生产库用户名或库名不同，请以 `.env` 中的 `POSTGRES_USER`、`POSTGRES_DB` 为准。

### 3.2 拉取最新代码

```bash
git fetch origin
git status
git pull --ff-only origin main
```

如果生产环境固定使用 tag 或 release 分支，请切换到对应 tag/分支后再继续。

### 3.3 重新构建并启动服务

```bash
docker compose build backend frontend
docker compose up -d backend frontend
```

如果生产环境还运行 Celery Worker / Beat，也建议一起重建并重启：

```bash
docker compose build celery celery-beat
docker compose up -d celery celery-beat
```

具体服务名以生产 `docker-compose.yml` 为准。

### 3.4 执行数据库迁移

```bash
docker compose exec backend alembic upgrade head
```

确认迁移版本：

```bash
docker compose exec postgres psql -U sagitta -d sagittadb -c "select * from alembic_version;"
```

期望版本：

```text
0015_priv_revoke_backfill
```

### 3.5 重启后端与前端

```bash
docker compose restart backend frontend
```

如有 Celery：

```bash
docker compose restart celery celery-beat
```

### 3.6 验证

健康检查：

```bash
curl -s http://127.0.0.1:8000/health
```

功能验证建议：

1. 普通用户登录，Dashboard 显示“我的数据”，查询权限页可看到“已撤销权限”。
2. 撤销一条自己的已生效查询权限，确认该权限从“我的权限”消失，并进入“已撤销权限”。
3. Dashboard 在线查询概览的“撤销查询权限数”与已撤销列表在相同时间范围下口径一致。
4. 组长登录，确认可看到“权限视图”和“工单视图”，但查询权限行不展示撤销按钮。
5. 资源组 DBA 登录，确认只能看到资源组实例范围内权限和工单，并可撤销范围内查询权限。
6. 全局 DBA / 超管登录，确认可看到全量权限、全量工单及撤销按钮。

### 3.7 回滚建议

如升级后需要回滚代码，先保留数据库备份和升级日志。

数据库迁移回滚命令：

```bash
docker compose exec backend alembic downgrade 0013_user_password_policy
```

注意：回滚到 `0013` 会删除查询权限撤销审计字段，撤销审计数据会丢失。生产环境不建议轻易执行迁移回滚，优先通过修复代码并重新发布解决。

---

## 四、变更文件索引

后端核心：

- `backend/app/services/governance_scope.py`
- `backend/app/services/monitor.py`
- `backend/app/services/query_priv.py`
- `backend/app/services/workflow.py`
- `backend/app/routers/query_priv.py`
- `backend/app/routers/workflow.py`
- `backend/app/models/query.py`
- `backend/app/schemas/query.py`

数据库迁移：

- `backend/alembic/versions/0014_query_privilege_revoke_audit.py`
- `backend/alembic/versions/0015_backfill_query_privilege_revoke_audit.py`

前端核心：

- `frontend/src/pages/dashboard/DashboardPage.tsx`
- `frontend/src/pages/query/QueryPrivPage.tsx`
- `frontend/src/pages/workflow/WorkflowList.tsx`
- `frontend/src/api/query.ts`
- `frontend/src/api/workflow.ts`

测试：

- `backend/tests/unit/test_authz_v2_lite.py`
- `backend/tests/unit/test_workflow_service.py`
