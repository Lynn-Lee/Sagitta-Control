# SagittaDB 引擎矩阵全流程验证

- 生成时间：2026-06-01T14:18:35
- 临时资源组绑定实例：[3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

| 引擎 | 等级 | 检查 | 通过 | 失败 |
|---|---|---:|---:|---:|
| MySQL (mysql) | ga | 18 | 18 | 0 |
| PostgreSQL (pgsql) | ga | 18 | 18 | 0 |
| TiDB (tidb) | ga | 18 | 17 | 1 |
| StarRocks (starrocks) | ga | 18 | 18 | 0 |
| ClickHouse (clickhouse) | ga | 18 | 18 | 0 |
| MongoDB (mongo) | ga | 18 | 18 | 0 |
| Redis (redis) | ga | 16 | 15 | 1 |
| Oracle (oracle) | validated_minimal | 18 | 17 | 1 |
| MSSQL (mssql) | validated_minimal | 18 | 17 | 1 |
| Doris (doris) | validated_minimal | 18 | 15 | 3 |
| Elasticsearch (elasticsearch) | validated_minimal | 16 | 16 | 0 |
| OpenSearch (opensearch) | validated_minimal | 16 | 15 | 1 |
| Cassandra/ScyllaDB (cassandra) | read_only_metadata | 16 | 16 | 0 |

## 失败/需核对项

| 引擎 | 功能 | 检查 | 期望 | 详情 |
|---|---|---|---|---|
| tidb | 运维工具 | 执行计划 Explain | True | {"detail": "EXPLAIN 失败：(1105, \"explain format 'json' is not supported now\")"} |
| redis | SQL 工单 | 不承诺边界提交应被拒绝 | False | {"status": 0, "msg": "工单提交成功", "data": {"id": 24, "workflow_name": "矩阵验收-redis-141823"}} |
| oracle | 运维工具 | 执行计划 Explain | True | {"detail": "EXPLAIN 失败：ORA-00604: error occurred at recursive SQL level 1\nORA-12899: value too large for column \"SYS\".\"PLAN_TABLE$\".\"STATEMENT_ID\" (actual: 32, maximum: 30)"} |
| mssql | 运维工具 | 执行计划 Explain | True | {"detail": "EXPLAIN 失败：('The SET SHOWPLAN statements must be the only statements in the batch.', None)"} |
| doris | 数据字典 | 约束元数据 | True | {"status": 500, "msg": "服务器内部错误", "detail": "获取约束信息失败：(1105, \"ParseException, msg: \\nmismatched input 'SEPARATOR' expecting {')', ','}(line 1, pos 144)\\n\")"} |
| doris | 数据字典 | 索引元数据 | True | {"status": 500, "msg": "服务器内部错误", "detail": "获取索引信息失败：(1105, \"ParseException, msg: \\nmismatched input 'SEPARATOR' expecting {')', ','}(line 1, pos 226)\\n\")"} |
| doris | 运维工具 | 会话/活动列表 | True | {"detail": "获取会话列表失败：(1105, \"ParseException, msg: \\nmissing {'INT', 'INTEGER'} at ')'(line 11, pos 33)\\n\")"} |
| opensearch | 运维工具 | 执行计划 Explain | True | {"detail": "EXPLAIN 失败：RequestError(400, '{\\n  \"error\": {\\n    \"reason\": \"Invalid SQL query\",\\n    \"details\": \"Query must start with SELECT, DELETE, SHOW or DESCRIBE: EXPLAIN SELECT * FROM `sagitta-orders` LIMIT 1\",\\n    \"type\": \"SQLFeatureNotSupportedException\"\\n  },\\n  \"status\": 400\\n}')"} |
