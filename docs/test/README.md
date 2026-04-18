# SagittaDB 功能测试文档索引

> **项目：** SagittaDB 矢准数据 v1.0-beta
> **文档版本：** v1.2 · 2026-04-13
> **测试环境：** http://localhost（前端）/ http://localhost:8000（后端）
> **默认账号：** admin / Admin@2024!

---

## 测试文档列表

| 文档 | 对应开发计划 | 用例数 | 核心覆盖内容 |
|---|---|---|---|
| [Sprint 0 — 基础设施](./sprint0_infrastructure_test.md) | Sprint 0 | 10 | Docker 服务启动、健康检查、数据库连接、Celery |
| [Sprint 1 — 认证与实例](./sprint1_auth_user_instance_test.md) | Sprint 1 | 19 | 登录认证、JWT、2FA、用户 CRUD、实例管理、资源组 |
| [Sprint 2 — 查询引擎](./sprint2_query_engine_test.md) | Sprint 2 | 13 | 多引擎查询、DDL/DML 拦截、行数限制、查询权限申请 |
| [Pack A — SQL 工单](./pack_a_workflow_test.md) | Pack A (S3+S4) | 20 | 工单提交/审批/执行、三标签列表、审批按钮可见性、9 种状态流转、运维工具 |
| [Pack B — 可观测中心](./pack_b_observability_test.md) | Pack B (S5+S6) | 20 | Dashboard 在线查询概览、Dashboard SQL 工单概览、Dashboard 实例与库概览、Prometheus、Grafana、Alertmanager |
| [Pack C1 — 系统管理](./pack_c1_system_admin_test.md) | Pack C1 | 16 | 系统配置（7组）、审计日志、资源组、个人设置 |
| [Pack C2 — 数据库注册](./pack_c2_instance_database_test.md) | Pack C2 | 10 | 手动添加/引擎同步、启停用、类型字段适配 |
| [Pack D — 数据安全](./pack_d_data_security_test.md) | Pack D | 14 | 脱敏规则（7种）、数据字典、工单模板、AI Text2SQL |
| [Pack E — 引擎与归档](./pack_e_engines_archive_test.md) | Pack E | 17 | 多引擎验证、数据归档（purge/dest）、回滚辅助、通知服务 |
| [Pack F — 第三方登录](./pack_f_third_party_auth_test.md) | Pack F | 17 | LDAP、钉钉/飞书/企微 OAuth2、CAS、CSRF 防护 |
| [Pack G — 质量保障](./pack_g_quality_assurance_test.md) | Pack G | 19 | 单元测试 152 个、集成测试 36 个、Locust 压测、安全扫描 |
| [Pack H — 生产就绪](./pack_h_production_deploy_test.md) | Pack H | 19 | Helm Chart、生产 Compose、备份脚本、GHCR 发布、Flower |
| [v2-lite 权限本地验证清单](./v2_lite_auth_local_validation.md) | v2-lite auth | 20+ | 本地快速验证角色、资源范围、查询授权、审批流 |
| [v2-lite 权限完整验证文档](./v2_lite_auth_full_validation.md) | v2-lite auth | 30+ | 完整验证角色、资源组、用户组、状态变更、查询权限、审批流、监控范围 |

**总用例数：184+ 个**

---

## 测试进度汇总

| Sprint/Pack | 总用例 | 通过 | 失败 | 未测试 | 通过率 |
|---|---|---|---|---|---|
| Sprint 0 | 10 | | | 10 | — |
| Sprint 1 | 19 | | | 19 | — |
| Sprint 2 | 13 | | | 13 | — |
| Pack A | 15 | | | 15 | — |
| Pack B | 20 | | | 20 | — |
| Pack C1 | 16 | | | 16 | — |
| Pack C2 | 10 | | | 10 | — |
| Pack D | 14 | | | 14 | — |
| Pack E | 17 | | | 17 | — |
| Pack F | 17 | | | 17 | — |
| Pack G | 19 | | | 19 | — |
| Pack H | 19 | | | 19 | — |
| **合计** | **182** | **0** | **0** | **182** | **—** |

---

## 测试优先级建议

### P0 — 核心流程（必测）
1. Sprint 0：基础服务启动（TC-S0-001 ~ TC-S0-003）
2. Sprint 1：登录认证（TC-S1-001 ~ TC-S1-006）
3. Sprint 2：在线查询基本功能（TC-S2-004 ~ TC-S2-006）
4. Pack A：工单完整流转（TC-A-001、TC-A-005、TC-A-008）
5. Pack G：CI 全绿验证（TC-G-018、TC-G-019）

### P1 — 重要功能（建议测试）
- Pack C1：系统配置和审计日志
- Pack D：数据脱敏规则生效
- Pack H：备份脚本、Helm lint

### P2 — 可选验证（有对应基础设施时测试）
- Pack F：第三方登录（需各平台应用配置）
- Pack E：真实引擎验证（需对应数据库实例）
- Pack B：Grafana Dashboard 导入

---

## 测试环境快速启动

```bash
# 1. 启动所有服务
cd SagittaDB
docker compose up -d

# 2. 等待 30 秒后检查状态
docker compose ps

# 3. 初始化系统（首次）
curl -X POST http://localhost:8000/api/v1/system/init/

# 4. 访问前端
open http://localhost          # 登录页
open http://localhost:8000/docs # API 文档
open http://localhost:5555      # Flower
open http://localhost:9090      # Prometheus
open http://localhost:3000      # Grafana (admin/admin)
```

---

*SagittaDB 矢准数据 · 功能测试文档 v1.1 · 2026-04-11*
