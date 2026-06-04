# SagittaDB ECS 引擎真实验证报告

生成时间：2026-06-04 20:20:33 CST

验证环境：

- 控制台：http://47.102.146.147
- 后端健康检查：http://127.0.0.1:8000/health -> `{"status":"ok","version":"2.2.0"}`
- 前端健康检查：http://127.0.0.1/health -> `{"status":"ok","version":"2.2.0"}`
- 登录账号：`admin`
- Docker Compose project：`sagittadb-source-test`

## 验证范围

本轮使用控制台已接入的 14 个真实 Docker 数据库实例执行验证，覆盖：

- 连接测试
- 库列表同步
- 已注册库列表
- 数据字典库/表/字段/DDL/索引元数据
- 在线只读查询
- 原生监控手动采集
- 原生监控详情
- 实时会话
- SQL 洞察采集

本轮未执行写入 SQL、Kill 会话、归档迁移或其他破坏性操作。

## 实例结果

| 引擎 | 实例 | 结论 | 说明 |
|---|---|---|---|
| MySQL | MySQL84-Test | 通过 | 连接、字典、查询、监控、会话和 SQL 洞察接口均通过。 |
| PostgreSQL | PostgreSQL16-Test | 通过 | 连接、字典、查询、监控、会话和 SQL 洞察接口均通过。 |
| TiDB | TiDB85-Test | 通过 | 连接、字典、查询、监控、会话和 SQL 洞察接口均通过。 |
| StarRocks | StarRocks35-Test | 通过 | 连接、字典、查询、监控、会话和 SQL 洞察接口均通过。 |
| ClickHouse | ClickHouse24-Docker-RealTest | 通过 | 连接、字典、查询、监控、会话和 SQL 洞察接口均通过。 |
| MongoDB | MongoDB7-Docker-RealTest | 通过 | 连接、库/集合字典、只读查询和监控接口均通过。 |
| Redis | Redis7-Docker-RealTest | 通过 | 连接、DB/key 类型字典、`PING` 查询、监控和会话接口均通过。 |
| Redis | Redis7-Test | 通过 | 连接、DB/key 类型字典、`PING` 查询、监控和会话接口均通过。 |
| Oracle | Oracle11202XE-Test | 通过 | 连接、库列表、Oracle 只读查询和观测接口通过；当前测试实例未选中业务表做完整字段/DDL 链路。 |
| MSSQL | SQLServer2017-Compat2012-Test | 通过 | 连接、字典、查询、监控、会话和 SQL 洞察接口均通过。 |
| Doris | Doris210-ECS-RealTest | 通过，带降级提示 | 核心链路通过；Compaction 指标因目标容器系统表能力受限返回 `missing_groups.doris_compactions`，按降级链路记录。 |
| Elasticsearch | Elasticsearch812-ECS-RealTest | 通过 | 连接、索引字典、字段、映射 DDL、在线查询、监控和 SQL 洞察接口均通过。 |
| OpenSearch | OpenSearch215-ECS-RealTest | 已修复后通过 | 初测发现 `SELECT * FROM "sagitta-orders"` 会被 OpenSearch SQL 插件识别为带引号索引名并报 404；已在 OpenSearch 引擎中归一化为反引号引用。 |
| Cassandra | Cassandra41-ECS-RealTest | 通过，边界内缺口 | 连接、Keyspace/Table/Column、DDL、主键/索引、只读查询和基础监控通过；SQL 洞察返回“未找到可用的 SQL 执行信息采集来源”，符合只读/元数据边界，深度指标需 JMX/sidecar。 |

## 收口项

- 修复 OpenSearch SQL 插件对连字符索引名的引用兼容：发往 OpenSearch SQL API 前将 `FROM "index-with-dash"` / `JOIN "index-with-dash"` 归一化为反引号引用。
- 增加 OpenSearch 查询与 Explain 单元测试，覆盖连字符索引名场景。
- 更新用户手册，说明 OpenSearch SQL 插件引用兼容处理。

## 验证命令

```bash
cd backend && .venv/bin/ruff check app/engines/opensearch.py tests/unit/test_elasticsearch_engine.py
backend/.venv/bin/pytest backend/tests/unit/test_elasticsearch_engine.py -q
backend/.venv/bin/pytest backend/tests/unit/test_elasticsearch_engine.py backend/tests/unit/test_query_guard.py backend/tests/unit/test_engine_registry.py -q
backend/.venv/bin/python scripts/validate-engine-matrix-contract.py
```

结果：

- `All checks passed!`
- `12 passed`
- `346 passed`
- `Engine matrix contract passed: 13 matrix entries, 13 registered engines.`

## 后续建议

- 将 Cassandra 的 SQL 活动采集继续标注为“不承诺/需 JMX sidecar”，不要在商业矩阵中承诺 SQL 洞察深度指标。
- 将 OpenSearch 连字符索引名加入客户同构验证用例。
- 后续正式客户验证时，应补充 Oracle 业务表字段/DDL/索引的完整链路样例。
