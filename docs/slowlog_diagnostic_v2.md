# 慢日志分析与会话诊断说明

> 更新时间：2026-04-24
> 覆盖范围：在线/历史会话管理、慢日志分析 v1/v2、采集任务与验证

## 功能概览

本轮补齐了两个运维诊断能力：

- **会话诊断**：在线会话查看、Kill 会话、平台侧会话快照历史、Oracle ASH 历史入口。
- **慢日志分析 v2**：平台查询历史 + 原生慢日志采集、SQL 指纹聚合、实例级采集配置、指纹详情、MySQL/PostgreSQL 执行计划分析与结构化优化建议。

权限口径沿用 v2-lite：

- 超管和具备 `monitor_all_instances` 的用户可查看全量实例。
- 资源组 DBA/运维用户只能查看自己用户组关联资源组内的实例。
- 慢日志配置与手动采集沿用 `menu_ops`，暂不新增独立权限码。

## 数据模型与迁移

新增 Alembic 迁移：

| 迁移 | 内容 |
|---|---|
| `0019_session_snapshot` | 新增 `session_snapshot`，保存周期性会话快照 |
| `0020_slow_query_log` | 新增 `slow_query_log`，统一保存平台和原生慢查询记录 |
| `0021_slow_query_v2` | 新增 `slow_query_config`，保存实例级慢日志采集配置和最近采集状态 |

核心表：

| 表 | 说明 |
|---|---|
| `session_snapshot` | 会话历史快照，字段包含实例、DB 类型、会话 ID、用户、主机、运行秒数、SQL 文本、等待事件、阻塞会话、采集错误与原始行 |
| `slow_query_log` | 慢 SQL 明细，字段包含来源、实例、库名、SQL 文本、指纹、耗时、扫描/返回行数、用户、客户端、发生时间、分析标签、原始数据 |
| `slow_query_config` | 慢日志采集配置，字段包含启用状态、阈值、采集间隔、保留天数、采集上限、最近采集时间/状态/错误/新增条数 |

## 后端 API

会话诊断：

| API | 说明 |
|---|---|
| `GET /api/v1/diagnostic/sessions/online/` | 查询指定实例在线会话 |
| `POST /api/v1/diagnostic/sessions/kill/` | Kill 指定会话 |
| `GET /api/v1/diagnostic/sessions/history/` | 查询平台采集的会话历史 |
| `GET /api/v1/diagnostic/oracle/ash/` | 查询 Oracle ASH/AWR 历史（仅 Oracle 引擎支持） |

慢日志分析：

| API | 说明 |
|---|---|
| `GET /api/v1/slowlog/configs/` | 慢日志采集配置列表 |
| `POST /api/v1/slowlog/configs/` | 创建或覆盖实例级慢日志采集配置 |
| `PUT /api/v1/slowlog/configs/{id}/` | 更新慢日志采集配置 |
| `GET /api/v1/slowlog/overview/` | 慢 SQL 总览卡片和趋势 |
| `GET /api/v1/slowlog/logs/` | 慢 SQL 明细列表 |
| `GET /api/v1/slowlog/fingerprints/` | SQL 指纹聚合排行 |
| `GET /api/v1/slowlog/fingerprints/{fingerprint}/detail/` | 指纹详情、趋势、分布、建议与样例 |
| `GET /api/v1/slowlog/fingerprints/{fingerprint}/samples/` | 指纹样例 SQL |
| `POST /api/v1/slowlog/explain/` | MySQL/PostgreSQL 执行计划分析 |
| `POST /api/v1/slowlog/collect/` | 手动触发慢日志采集 |
| `GET /api/v1/slowlog/` | 兼容旧接口，查看实时慢查询 |

## 采集与引擎能力

Celery Beat 新增两类监控队列任务：

- `collect_session_snapshots`：每分钟采集活跃实例在线会话并写入 `session_snapshot`。
- `collect_slow_queries`：每 5 分钟按 `slow_query_config` 判断是否需要采集慢 SQL，并清理过期慢日志。

当前慢日志真实采集能力：

| 引擎 | 慢日志来源 | 执行计划 |
|---|---|---|
| MySQL / TiDB 兼容协议 | `performance_schema.events_statements_summary_by_digest` | `EXPLAIN FORMAT=JSON` |
| PostgreSQL | `pg_stat_statements` | `EXPLAIN (FORMAT JSON, BUFFERS, VERBOSE)` |
| Redis | `SLOWLOG` | 不适用 |
| 其他引擎 | 入口保留，返回“不支持原生慢日志采集” | 第三版分批适配 |

慢日志也会从平台在线查询历史 `query_log.cost_time_ms` 同步，默认阈值为 `1000ms`，并支持在实例级配置中覆盖。

## 前端页面

会话诊断页：

- 在线会话：按实例查看当前会话，支持 Kill。
- 历史会话：支持平台快照历史与 Oracle ASH 来源切换。
- 筛选条件：时间范围、用户、数据库、SQL 关键字、最小运行秒数。

慢日志分析页：

- 总览：慢 SQL 数、影响实例、平均/P95/最大耗时、趋势和最慢 SQL。
- 慢 SQL 明细：按实例、库、来源、时间、阈值、SQL 关键字过滤。
- 指纹聚合：展示调用次数、平均/P95/最大耗时、扫描/返回行数和风险标签。
- 指纹详情：展示趋势、实例/库/用户/来源分布、结构化建议和样例。
- 实时慢查询：保留第一版实时会话视角。
- 采集配置：实例级阈值、采集间隔、保留天数、采集上限和最近采集状态。

## 验证命令

```bash
cd backend
python3 -m compileall app
./.venv/bin/python -m pytest tests/unit/test_session_diagnostic.py tests/unit/test_slowlog_service.py -q

cd ../frontend
npm run typecheck
./node_modules/.bin/eslint src/pages/diagnostic/DiagnosticPage.tsx src/api/diagnostic.ts src/pages/slowlog/SlowlogPage.tsx src/api/slowlog.ts --ext ts,tsx --report-unused-disable-directives --max-warnings 0
```

当前全量前端 lint 仍会被既有 `DataDictPage.tsx` hook warning 拦截；慢日志和会话诊断相关文件已单独通过 ESLint。
