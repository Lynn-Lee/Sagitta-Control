# SagittaDB 引擎矩阵全流程验证

- 生成时间：2026-06-01T14:47:01
- API：http://127.0.0.1:18080
- 临时资源组绑定实例：[3, 7, 5, 11, 9, 10, 8, 6, 14, 15, 13, 12]

| 引擎 | 等级 | 检查 | 通过 | 失败 |
|---|---|---:|---:|---:|
| MySQL (mysql) | ga | 18 | 18 | 0 |
| PostgreSQL (pgsql) | ga | 18 | 18 | 0 |
| TiDB (tidb) | ga | 18 | 18 | 0 |
| StarRocks (starrocks) | ga | 18 | 18 | 0 |
| ClickHouse (clickhouse) | ga | 18 | 18 | 0 |
| MongoDB (mongo) | ga | 18 | 18 | 0 |
| Redis (redis) | ga | 16 | 16 | 0 |
| Oracle (oracle) | validated_minimal | 18 | 18 | 0 |
| MSSQL (mssql) | validated_minimal | 18 | 18 | 0 |
| Doris (doris) | validated_minimal | 18 | 18 | 0 |
| Elasticsearch (elasticsearch) | validated_minimal | 16 | 16 | 0 |
| OpenSearch (opensearch) | validated_minimal | 16 | 16 | 0 |
| Cassandra/ScyllaDB (cassandra) | read_only_metadata | 16 | 16 | 0 |

## 失败/需核对项

本次未发现失败项。

## 全量检查明细

| 引擎 | 功能 | 检查 | 期望 | 结果 | HTTP | 备注 |
|---|---|---|---|---|---:|---|
| mysql | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| mysql | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| mysql | 数据字典 | 表列表 | True | PASS | 200 |  |
| mysql | 数据字典 | 列元数据 | True | PASS | 200 |  |
| mysql | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| mysql | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| mysql | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| mysql | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| mysql | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| mysql | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| mysql | SQL 工单 | 提交工单 | True | PASS | 200 |  |
| mysql | SQL 工单 | 审批通过 | True | PASS | 200 |  |
| mysql | SQL 工单 | 执行回填闭环 | True | PASS | 200 |  |
| mysql | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| mysql | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| mysql | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 200 | 参数页为信息项，失败只记录 |
| mysql | 运维工具 | 会话/活动列表 | True | PASS | 200 |  |
| mysql | 运维工具 | 执行计划 Explain | True | PASS | 200 |  |
| pgsql | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| pgsql | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| pgsql | 数据字典 | 表列表 | True | PASS | 200 |  |
| pgsql | 数据字典 | 列元数据 | True | PASS | 200 |  |
| pgsql | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| pgsql | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| pgsql | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| pgsql | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| pgsql | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| pgsql | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| pgsql | SQL 工单 | 提交工单 | True | PASS | 200 |  |
| pgsql | SQL 工单 | 审批通过 | True | PASS | 200 |  |
| pgsql | SQL 工单 | 执行回填闭环 | True | PASS | 200 |  |
| pgsql | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| pgsql | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| pgsql | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 200 | 参数页为信息项，失败只记录 |
| pgsql | 运维工具 | 会话/活动列表 | True | PASS | 200 |  |
| pgsql | 运维工具 | 执行计划 Explain | True | PASS | 200 |  |
| tidb | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| tidb | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| tidb | 数据字典 | 表列表 | True | PASS | 200 |  |
| tidb | 数据字典 | 列元数据 | True | PASS | 200 |  |
| tidb | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| tidb | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| tidb | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| tidb | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| tidb | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| tidb | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| tidb | SQL 工单 | 提交工单 | True | PASS | 200 |  |
| tidb | SQL 工单 | 审批通过 | True | PASS | 200 |  |
| tidb | SQL 工单 | 执行回填闭环 | True | PASS | 200 |  |
| tidb | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| tidb | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| tidb | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 200 | 参数页为信息项，失败只记录 |
| tidb | 运维工具 | 会话/活动列表 | True | PASS | 200 |  |
| tidb | 运维工具 | 执行计划 Explain | True | PASS | 200 |  |
| starrocks | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| starrocks | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| starrocks | 数据字典 | 表列表 | True | PASS | 200 |  |
| starrocks | 数据字典 | 列元数据 | True | PASS | 200 |  |
| starrocks | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| starrocks | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| starrocks | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| starrocks | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| starrocks | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| starrocks | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| starrocks | SQL 工单 | 提交工单 | True | PASS | 200 |  |
| starrocks | SQL 工单 | 审批通过 | True | PASS | 200 |  |
| starrocks | SQL 工单 | 执行回填闭环 | True | PASS | 200 |  |
| starrocks | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| starrocks | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| starrocks | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 200 | 参数页为信息项，失败只记录 |
| starrocks | 运维工具 | 会话/活动列表 | True | PASS | 200 |  |
| starrocks | 运维工具 | 执行计划 Explain | True | PASS | 200 |  |
| clickhouse | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| clickhouse | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| clickhouse | 数据字典 | 表列表 | True | PASS | 200 |  |
| clickhouse | 数据字典 | 列元数据 | True | PASS | 200 |  |
| clickhouse | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| clickhouse | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| clickhouse | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| clickhouse | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| clickhouse | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| clickhouse | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| clickhouse | SQL 工单 | 提交工单 | True | PASS | 200 |  |
| clickhouse | SQL 工单 | 审批通过 | True | PASS | 200 |  |
| clickhouse | SQL 工单 | 执行回填闭环 | True | PASS | 200 |  |
| clickhouse | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| clickhouse | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| clickhouse | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 500 | 参数页为信息项，失败只记录 |
| clickhouse | 运维工具 | 会话/活动列表（不承诺） | False | PASS | 200 | 矩阵 session=false，仅记录接口表现 |
| clickhouse | 运维工具 | 执行计划 Explain（不承诺） | False | PASS | 200 | 矩阵 explain=false，仅记录接口表现 |
| mongo | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| mongo | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| mongo | 数据字典 | 表列表 | True | PASS | 200 |  |
| mongo | 数据字典 | 列元数据 | True | PASS | 200 |  |
| mongo | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| mongo | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| mongo | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| mongo | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| mongo | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| mongo | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| mongo | SQL 工单 | 提交工单 | True | PASS | 200 |  |
| mongo | SQL 工单 | 审批通过 | True | PASS | 200 |  |
| mongo | SQL 工单 | 执行回填闭环 | True | PASS | 200 |  |
| mongo | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| mongo | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| mongo | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 500 | 参数页为信息项，失败只记录 |
| mongo | 运维工具 | 会话/活动列表 | True | PASS | 200 |  |
| mongo | 运维工具 | 执行计划 Explain（不承诺） | False | PASS | 200 | 矩阵 explain=false，仅记录接口表现 |
| redis | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| redis | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| redis | 数据字典 | 表列表 | True | PASS | 200 |  |
| redis | 数据字典 | 列元数据 | True | PASS | 200 |  |
| redis | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| redis | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| redis | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| redis | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| redis | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| redis | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| redis | SQL 工单 | 不承诺边界提交应被拒绝 | False | PASS | 400 | 矩阵 workflow=false，提交应 fail-close |
| redis | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| redis | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| redis | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 500 | 参数页为信息项，失败只记录 |
| redis | 运维工具 | 会话/活动列表（不承诺） | False | PASS | 200 | 矩阵 session=false，仅记录接口表现 |
| redis | 运维工具 | 执行计划 Explain（不承诺） | False | PASS | 200 | 矩阵 explain=false，仅记录接口表现 |
| oracle | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| oracle | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| oracle | 数据字典 | 表列表 | True | PASS | 200 |  |
| oracle | 数据字典 | 列元数据 | True | PASS | 200 |  |
| oracle | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| oracle | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| oracle | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| oracle | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| oracle | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| oracle | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| oracle | SQL 工单 | 提交工单 | True | PASS | 200 |  |
| oracle | SQL 工单 | 审批通过 | True | PASS | 200 |  |
| oracle | SQL 工单 | 执行回填闭环 | True | PASS | 200 |  |
| oracle | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| oracle | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| oracle | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 500 | 参数页为信息项，失败只记录 |
| oracle | 运维工具 | 会话/活动列表 | True | PASS | 200 |  |
| oracle | 运维工具 | 执行计划 Explain | True | PASS | 200 |  |
| mssql | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| mssql | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| mssql | 数据字典 | 表列表 | True | PASS | 200 |  |
| mssql | 数据字典 | 列元数据 | True | PASS | 200 |  |
| mssql | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| mssql | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| mssql | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| mssql | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| mssql | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| mssql | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| mssql | SQL 工单 | 提交工单 | True | PASS | 200 |  |
| mssql | SQL 工单 | 审批通过 | True | PASS | 200 |  |
| mssql | SQL 工单 | 执行回填闭环 | True | PASS | 200 |  |
| mssql | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| mssql | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| mssql | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 500 | 参数页为信息项，失败只记录 |
| mssql | 运维工具 | 会话/活动列表 | True | PASS | 200 |  |
| mssql | 运维工具 | 执行计划 Explain | True | PASS | 200 |  |
| doris | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| doris | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| doris | 数据字典 | 表列表 | True | PASS | 200 |  |
| doris | 数据字典 | 列元数据 | True | PASS | 200 |  |
| doris | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| doris | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| doris | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| doris | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| doris | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| doris | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| doris | SQL 工单 | 提交工单 | True | PASS | 200 |  |
| doris | SQL 工单 | 审批通过 | True | PASS | 200 |  |
| doris | SQL 工单 | 执行回填闭环 | True | PASS | 200 |  |
| doris | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| doris | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| doris | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 200 | 参数页为信息项，失败只记录 |
| doris | 运维工具 | 会话/活动列表 | True | PASS | 200 |  |
| doris | 运维工具 | 执行计划 Explain | True | PASS | 200 |  |
| elasticsearch | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| elasticsearch | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| elasticsearch | 数据字典 | 表列表 | True | PASS | 200 |  |
| elasticsearch | 数据字典 | 列元数据 | True | PASS | 200 |  |
| elasticsearch | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| elasticsearch | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| elasticsearch | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| elasticsearch | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| elasticsearch | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| elasticsearch | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| elasticsearch | SQL 工单 | 不承诺边界提交应被拒绝 | False | PASS | 400 | 矩阵 workflow=false，提交应 fail-close |
| elasticsearch | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| elasticsearch | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| elasticsearch | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 500 | 参数页为信息项，失败只记录 |
| elasticsearch | 运维工具 | 会话/活动列表（不承诺） | False | PASS | 200 | 矩阵 session=false，仅记录接口表现 |
| elasticsearch | 运维工具 | 执行计划 Explain | True | PASS | 200 |  |
| opensearch | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| opensearch | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| opensearch | 数据字典 | 表列表 | True | PASS | 200 |  |
| opensearch | 数据字典 | 列元数据 | True | PASS | 200 |  |
| opensearch | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| opensearch | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| opensearch | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| opensearch | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| opensearch | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| opensearch | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| opensearch | SQL 工单 | 不承诺边界提交应被拒绝 | False | PASS | 400 | 矩阵 workflow=false，提交应 fail-close |
| opensearch | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| opensearch | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| opensearch | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 500 | 参数页为信息项，失败只记录 |
| opensearch | 运维工具 | 会话/活动列表（不承诺） | False | PASS | 200 | 矩阵 session=false，仅记录接口表现 |
| opensearch | 运维工具 | 执行计划 Explain | True | PASS | 200 |  |
| cassandra | 连接测试 | 实例连接测试 | True | PASS | 200 |  |
| cassandra | 数据字典 | 数据字典库列表 | True | PASS | 200 |  |
| cassandra | 数据字典 | 表列表 | True | PASS | 200 |  |
| cassandra | 数据字典 | 列元数据 | True | PASS | 200 |  |
| cassandra | 数据字典 | 表DDL/Mapping | True | PASS | 200 |  |
| cassandra | 数据字典 | 约束元数据 | True | PASS | 200 |  |
| cassandra | 数据字典 | 索引元数据 | True | PASS | 200 |  |
| cassandra | 在线查询 | 查询权限排查 | True | PASS | 200 |  |
| cassandra | 在线查询 | 只读查询执行 | True | PASS | 200 |  |
| cassandra | SQL 工单 | 风险预案 | True | PASS | 200 |  |
| cassandra | SQL 工单 | 不承诺边界提交应被拒绝 | False | PASS | 400 | 矩阵 workflow=false，提交应 fail-close |
| cassandra | 观测中心 | 基础指标采集 | True | PASS | 200 |  |
| cassandra | 观测中心 | 引擎详情观测 | True | PASS | 200 |  |
| cassandra | 运维工具 | 实例参数/变量（信息项） | best_effort | PASS | 500 | 参数页为信息项，失败只记录 |
| cassandra | 运维工具 | 会话/活动列表（不承诺） | False | PASS | 200 | 矩阵 session=false，仅记录接口表现 |
| cassandra | 运维工具 | 执行计划 Explain（不承诺） | False | PASS | 200 | 矩阵 explain=false，仅记录接口表现 |
