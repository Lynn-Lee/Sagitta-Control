# Sprint 0 功能测试文档 — 项目骨架与基础设施

> **测试版本：** SagittaDB v1.0-beta
> **对应计划：** Sprint 0 — 项目骨架、基础设施
> **测试环境：** http://localhost（前端）/ http://localhost:8000（后端）
> **前置条件：** `docker compose up -d` 启动全部服务，`alembic upgrade head` 已执行
> **测试账号：** admin / Admin@2024!（默认密码会触发强制改密）

---

## 测试范围

| 模块 | 覆盖内容 |
|---|---|
| Docker Compose | 所有服务容器正常启动 |
| 后端 API 服务 | FastAPI 正常响应，文档可访问 |
| 数据库连接 | PostgreSQL 连接池正常 |
| Redis 连接 | Redis 缓存服务正常 |
| Celery 任务队列 | Worker 正常注册 |
| 前端静态服务 | Nginx 反向代理正常 |

---

## 测试用例

### TC-S0-001 所有容器启动状态检查

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-001 |
| **测试场景** | 验证所有 Docker 容器均正常运行 |
| **测试步骤** | 1. 终端执行 `docker compose ps`<br>2. 查看每个服务的 STATUS 列 |
| **预期结果** | postgres、redis 状态为 `healthy`；backend、frontend、celery_worker、celery_beat、flower、prometheus、grafana、alertmanager 均为 `Up` |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-S0-002 健康检查接口

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-002 |
| **测试场景** | 后端健康检查接口正常响应 |
| **测试步骤** | 1. 浏览器访问 http://localhost:8000/health<br>或执行 `curl http://localhost:8000/health` |
| **预期结果** | 返回 `{"status": "ok", "version": "2.0.0"}` |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-S0-003 API 文档可访问性

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-003 |
| **测试场景** | Swagger UI 文档正常加载 |
| **测试步骤** | 1. 浏览器访问 http://localhost:8000/docs<br>2. 查看接口文档页面是否正常加载 |
| **预期结果** | Swagger UI 页面正常显示，可展开各接口分组（auth、instances、workflow 等） |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-S0-004 前端页面加载

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-004 |
| **测试场景** | 前端 React SPA 正常加载 |
| **测试步骤** | 1. 浏览器访问 http://localhost<br>2. 观察页面是否跳转至登录页 |
| **预期结果** | 显示 SagittaDB 登录页（含品牌 Logo、账号密码输入框、第三方登录入口） |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-S0-005 Nginx 反向代理

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-005 |
| **测试场景** | 前端通过 Nginx 转发 API 请求 |
| **测试步骤** | 1. 浏览器访问 http://localhost/api/v1/auth/login/<br>2. 方法 POST，Body `{"username":"admin","password":"Admin@2024!"}` |
| **预期结果** | 返回 HTTP 200；若仍为默认密码，则返回 `password_change_required=true` 和 `password_change_token`；完成强制改密后再次登录返回 access_token 和 refresh_token |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-S0-006 数据库迁移状态

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-006 |
| **测试场景** | Alembic 迁移已运行到最新版本 |
| **测试步骤** | 1. 执行 `docker compose exec backend alembic current`<br>2. 查看输出中的版本号 |
| **预期结果** | 输出包含 `(head)`，版本号为最新 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-S0-007 Celery Worker 注册状态

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-007 |
| **测试场景** | Celery Worker 正常注册，队列可接收任务 |
| **测试步骤** | 1. 浏览器访问 http://localhost:5555（Flower 监控面板）<br>2. 查看 Workers 页签 |
| **预期结果** | 显示至少 1 个在线 Worker，状态为 Online，监听 default/execute/notify/archive/monitor 队列 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-S0-008 Redis 连通性

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-008 |
| **测试场景** | Redis 服务正常，后端可读写 |
| **测试步骤** | 1. 执行 `docker compose exec redis redis-cli -a redis123 ping` |
| **预期结果** | 返回 `PONG` |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-S0-009 PostgreSQL 连通性

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-009 |
| **测试场景** | PostgreSQL 服务正常，核心表已创建 |
| **测试步骤** | 1. 执行 `docker compose exec postgres psql -U sagitta -d sagittadb -c "\dt"` |
| **预期结果** | 显示 sql_users、sql_instance、sql_workflow 等核心数据表 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-S0-010 系统初始化接口

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-S0-010 |
| **测试场景** | 系统初始化接口（幂等性验证） |
| **测试步骤** | 1. POST http://localhost:8000/api/v1/system/init/<br>2. 重复调用 2 次 |
| **预期结果** | 两次均返回 status=0，无报错；第 2 次提示已初始化或权限表已更新 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

## 测试汇总

| 总用例数 | 通过 | 失败 | 未测试 |
|---|---|---|---|
| 10 | 0 | 0 | 10 |

**测试人员：**
**测试日期：**
**备注：**
