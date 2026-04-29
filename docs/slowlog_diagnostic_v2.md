# SQL 洞察与会话诊断说明

> 更新时间：2026-04-29
> 覆盖范围：观测中心会话洞察、SQL 洞察、SQL 执行信息采集、采集任务与验证

## 功能概览

观测中心已升级为实例优先的数据库运行态诊断中心，会话与 SQL 不再作为独立运维工具堆叠，而是围绕当前实例共享同一套诊断上下文。

- **会话洞察**：连接/会话视角在线清单、Kill 会话、平台侧会话快照历史、Oracle ASH/AWR 活跃采样入口。
- **SQL 洞察**：SQL 执行信息采集、SQL 样本、SQL 指纹聚合、实时 SQL、执行计划分析、优化诊断与结构化建议。

权限口径沿用 v2-lite：

- 超管和具备 `observability_instance_all` 的用户可查看全量实例观测数据。
- 资源组 DBA/运维用户只能查看自己用户组关联资源组内的实例。
- SQL 采集配置与手动采集使用 `observability_collect_manage`。
- 会话查看、Kill、SQL 查看和 SQL 分析分别使用 `observability_session_view`、`observability_session_kill`、`observability_sql_view`、`observability_sql_analyze`。

## 数据模型与迁移

新增 Alembic 迁移：

| 迁移 | 内容 |
|---|---|
| `0019_session_snapshot` | 新增 `session_snapshot`，保存周期性会话快照 |
| `0020_slow_query_log` | 新增 `slow_query_log`，统一保存平台和原生慢查询记录 |
| `0021_slow_query_v2` | 新增 `slow_query_config`，保存实例级 SQL 采集配置和最近采集状态 |
| `0024_session_duration_ms` | 为历史会话补充毫秒兼容字段 |
| `0025_session_duration_fields` | 为会话快照补充连接/状态/当前操作/事务时长字段 |
| `0030_observability_permission_rework` | 将旧监控/运维会话权限迁移到新观测权限体系 |
| `0031_sql_activity_collect_semantics` | 为 `slow_query_config` 增加最近采集来源与来源说明，清理旧 unsupported 状态 |

核心表：

| 表 | 说明 |
|---|---|
| `session_snapshot` | 会话历史快照，字段包含实例、DB 类型、会话 ID、用户、主机、命令、状态、连接时长、状态时长、当前操作时长、事务时长、SQL 上下文、等待事件、阻塞会话、采集错误与原始行 |
| `slow_query_log` | SQL 样本明细，字段包含来源、实例、库名、SQL 文本、指纹、耗时、扫描/返回行数、用户、客户端、发生时间、分析标签、原始数据 |
| `slow_query_config` | SQL 采集配置，字段包含启用状态、阈值、采集间隔、保留天数、采集上限、最近采集时间/状态/错误/新增条数、采集来源和来源说明 |

## 后端 API

会话诊断：

| API | 说明 |
|---|---|
| `GET /api/v1/diagnostic/sessions/online/` | 查询指定实例在线会话 |
| `POST /api/v1/diagnostic/sessions/kill/` | Kill 指定会话 |
| `GET /api/v1/diagnostic/sessions/history/` | 查询平台采集的会话历史 |
| `GET /api/v1/diagnostic/oracle/ash/` | 查询 Oracle ASH/AWR 历史（仅 Oracle 引擎支持） |

SQL 洞察：

| API | 说明 |
|---|---|
| `GET /api/v1/slowlog/configs/` | SQL 采集配置列表 |
| `POST /api/v1/slowlog/configs/` | 创建或覆盖实例级 SQL 采集配置 |
| `PUT /api/v1/slowlog/configs/{id}/` | 更新 SQL 采集配置 |
| `GET /api/v1/slowlog/overview/` | SQL 样本总览卡片和趋势 |
| `GET /api/v1/slowlog/logs/` | SQL 样本明细列表 |
| `GET /api/v1/slowlog/fingerprints/` | SQL 指纹聚合排行 |
| `GET /api/v1/slowlog/fingerprints/{fingerprint}/detail/` | 指纹详情、趋势、分布、建议与样例 |
| `GET /api/v1/slowlog/fingerprints/{fingerprint}/samples/` | 指纹样例 SQL |
| `POST /api/v1/slowlog/explain/` | MySQL/PostgreSQL 执行计划分析 |
| `POST /api/v1/slowlog/collect/` | 手动触发 SQL 执行信息采集 |
| `GET /api/v1/slowlog/` | 兼容旧接口，查看实时 SQL |

## 采集与引擎能力

Celery Beat 新增两类监控队列任务：

- `collect_session_snapshots`：每分钟采集活跃实例在线会话并写入 `session_snapshot`。
- `collect_slow_queries`：每 5 分钟按 `slow_query_config` 判断是否需要采集 SQL 执行信息，并清理过期 SQL 样本。任务名保留兼容，业务语义已升级为 SQL 活动采集。

当前 SQL 执行信息采集能力：

| 引擎 | SQL 采集来源 | 执行计划 |
|---|---|---|
| MySQL | `performance_schema.events_statements_summary_by_digest` + 平台历史 | `EXPLAIN FORMAT=JSON` |
| TiDB | `information_schema.CLUSTER_PROCESSLIST / PROCESSLIST` + 平台历史 | 兼容 MySQL 计划入口 |
| StarRocks | `SHOW PROCESSLIST` + 平台历史 | `EXPLAIN COSTS` |
| PostgreSQL | `pg_stat_statements` + 平台历史 | `EXPLAIN (FORMAT JSON, BUFFERS, VERBOSE)` |
| Oracle | `v$session / v$sql` + 平台历史 | Oracle 执行计划入口 |
| Redis | `SLOWLOG` | 不适用 |
| 其他关系型引擎 | 平台历史兜底，后续按引擎系统视图增强 | 按引擎分批适配 |

SQL 洞察会从平台在线查询历史 `query_log.cost_time_ms` 同步，默认阈值为 `1000ms`，并支持在实例级配置中覆盖。若数据库侧采集不可用但平台历史可用，配置页显示 `success` 或 `partial`，不再暴露“原生慢日志是否支持”的实现细节。

## 前端页面

会话诊断页：

- 在线会话：按实例查看当前完整连接清单（含空闲连接），支持隐藏空闲会话和 Kill。
- 历史会话：支持平台采样快照与 Oracle ASH/AWR 活跃采样来源切换；Oracle ASH/AWR 不等同于全量连接历史。
- 核心字段：连接时长、状态时长、当前操作时长、事务时长；SQL 仅作为会话上下文展示。
- 筛选条件：时间范围、用户、数据库、状态、命令、SQL 关键字、最小连接时长、最小状态时长、最小当前操作时长。

SQL 洞察页：

- 总览：SQL 样本数、影响实例、平均/P95/最大耗时、趋势和最慢 SQL。
- SQL 样本明细：按实例、库、采集来源、时间、阈值、SQL 关键字过滤。
- 指纹聚合：展示调用次数、平均/P95/最大耗时、扫描/返回行数和风险标签。
- 指纹详情：展示趋势、实例/库/用户/来源分布、结构化建议和样例。
- 实时 SQL：保留第一版实时会话视角。
- 采集配置：实例级阈值、采集间隔、保留天数、采集上限、最近采集状态、采集来源和来源说明。

## 验证命令

```bash
cd backend
python3 -m compileall app
./.venv/bin/python -m pytest tests/unit/test_session_diagnostic.py tests/unit/test_slowlog_service.py -q

cd ../frontend
npm run typecheck
npm run build
```

当前验证以类型检查和生产构建为准；SQL 洞察和会话洞察相关单测覆盖服务层采集语义。
