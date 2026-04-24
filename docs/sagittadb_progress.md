# SagittaDB 矢准数据 — 项目开发进度文档

> **项目路径：** `/Users/lynn/SynologyDrive/SynologyDrive/Code/SagittaDB`
> **重构基准：** Archery v1.14.0
> **文档版本：** v1.11 · 2026-04-21
> **状态说明：** ✅ 已完成并验证 · 🔧 已开发待测试 · 📋 待开发

---

## 一、项目概览

| 项目 | 内容 |
|---|---|
| 产品名称 | SagittaDB 矢准数据 |
| 品牌标语 | 矢向数据，精准管控 |
| 技术栈（后端） | FastAPI + SQLAlchemy 2.0 async + Celery 5 + PostgreSQL 16 |
| 技术栈（前端） | React 18 + TypeScript + Vite + Ant Design 5 |
| 引擎层 | EngineBase Protocol + sqlglot（替代 goInception 解析） |
| 可观测中心 | Prometheus + Alertmanager + Grafana |
| SaaS 预留 | 全部模型含 tenant_id，初期固定为 1 |
| 部署方式 | Docker Compose（开发/测试）/ K8s + Helm（生产预留）|

---

## 二、整体进度总览

| 阶段 | 内容 | 状态 | 完成度 |
|---|---|---|---|
| Sprint 0 | 项目骨架、基础设施 | ✅ | 100% |
| Sprint 1 | 认证、用户、实例管理 | ✅ | 100% |
| Sprint 2 | 引擎层、在线查询、查询权限 | ✅ | 100% |
| Pack A (S3+S4) | SQL 工单全流程 + 运维工具 | ✅ | 100% |
| Pack B (S5+S6) | 可观测中心 + 迁移脚本 | ✅ | 100% |
| Pack C1 | 系统配置、审计日志、资源组、个人设置 | ✅ | 100% |
| Pack C2 | 实例数据库注册管理 | ✅ | 100% |
| Pack D | 数据脱敏、数据字典、SQL 工单模板、AI Text2SQL | ✅ | 100% |
| Pack E | 多引擎补全、数据归档、SQL 回滚辅助、通知服务 | 🔧 | 85% |
| Pack F | 第三方登录（LDAP/钉钉/飞书/企微/CAS） | ✅ | 100% |
| Pack G | 全链路测试、性能测试、安全扫描 | ✅ | 100% |
| Pack H | Helm Chart、CI/CD 流水线、生产环境配置 | ✅ | 100% |
| 品牌升级 | SagittaDB 品牌 UI 全面更新 | ✅ | 100% |
| Security Hardening | Token 黑名单 fail-close、SECRET_KEY 强制校验、Text2SQL 分层、依赖版本收紧 | ✅ | 100% |
| 多级审批流 | 管理员自定义多节点审批流 + 前端管理页面 | ✅ | 100% |
| 数据库权限管控 | is_active 启停控制、普通用户不可见禁用库、管理员标灰"已禁用" | ✅ | 100% |
| Bug 修复 | MySQL DictCursor 修复、PG 表缺失修复、前端下拉框截断修复、业务弹窗遮罩误关闭修复 | ✅ | 100% |
| 授权体系 v2-lite | 角色系统（superadmin/dba/dba_group/developer）、用户组/资源组职责拆分、库级/表级授权、直属上级审批 | ✅ | 100% |
| 密码安全策略 | 本地账号复杂度、默认/过期密码强制改密、30 天轮换、到期前 7 天提醒 | ✅ | 100% |
| 统一治理视角 | Dashboard、查询权限、SQL 工单统一 self/group/instance_scope/global 视角 | ✅ | 100% |
| 查询权限撤销审计 | 已生效查询权限撤销、撤销记录、历史软删除回填、Dashboard 撤销统计 | ✅ | 100% |

**总体完成度：100%（v1.0-GA），v2-lite 首发范围已完成并进入体验收口与持续验收阶段**

---

## 三、已完成功能详情

### Sprint 0 — 项目骨架 ✅

- FastAPI 应用结构（routers / services / models / engines / schemas）
- SQLAlchemy 2.0 async ORM + Alembic 迁移框架
- Celery 5 + Redis 异步任务队列
- React 18 + TypeScript + Vite + Ant Design 5 前端脚手架
- Docker Compose 多服务编排（backend / frontend / postgres / redis / celery / prometheus / grafana）
- Nginx 反向代理配置（含 WebSocket 支持）

### Sprint 1 — 认证与实例管理 ✅

**认证模块**
- JWT 双 Token（access + refresh）认证，自动刷新
- bcrypt + SHA-256 预处理密码哈希（规避 72 字节限制）
- TOTP 双因素认证（2FA 开启/关闭/验证）
- 密码修改接口
- 本地账号统一密码安全规则：至少 8 位，必须包含数字、大写字母、小写字母和特殊字符
- 登录时识别默认密码、弱密码和已超过 30 天未修改的密码；触发后仅返回短效 `password_change` 令牌，要求先完成改密再重新登录
- `/auth/me/` 返回 `password_expiring_soon` 与 `days_until_password_expiry`，前端在到期前 7 天展示全局提醒
- Alembic migration `0013_user_password_policy.py` 新增 `sql_users.password_changed_at`，用于密码周期管理

**用户权限**
- 用户 CRUD（创建/编辑/禁用/授权）
- 15 种细粒度权限码（sql_submit / sql_review / instance_manage 等）
- 超级管理员（is_superuser）跳过权限检查
- 用户创建、批量导入、个人改密和强制改密共用同一套密码复杂度校验
- 用户批量导入默认密码示例调整为 `Sagitta@2026A`，满足长度、数字、大小写字母和特殊字符规则

**实例管理**
- 11 种数据库类型支持（MySQL/PostgreSQL/Oracle/MongoDB/Redis/ClickHouse/Elasticsearch/OpenSearch/MSSQL/Cassandra/Doris/TiDB）
- 实例 CRUD + 测试连接
- Fernet 对称加密存储密码字段
- SSH 隧道配置（跳板机连接）
- 实例数据库注册（Pack C2）：手动添加 + 从引擎自动同步，各数据库类型字段名称适配（Oracle=Schema，Redis=数据库编号）
- 自动同步改为按“当前连接用户真实可见范围”全量对齐：新增当前可见对象、更新时间、移除当前已不可见旧记录
- Oracle 同步规则已收敛：
  - 高权限账号可同步其真实可见的多个 Schema
  - 普通 Schema 用户仅同步自身真实可见范围
- 实例删除保护：实例若仍被资源组关联，删除接口返回冲突提示并引导先到资源组管理解除关联
- **数据库 is_active 权限管控**：`is_active=False` 的数据库对普通用户全局不可见（API 过滤 + 前端下拉框过滤），管理员可见并标灰显示"已禁用"标签；查询禁用库返回 403

**资源组管理**
- 资源组 CRUD
- 关联数据库实例多选
- 关联用户组管理（资源组不再直接管理成员）
- `is_active` 启停控制

### Sprint 2 — 在线查询 ✅

- Monaco Editor 代码编辑器（SQL 语法高亮 + 自动补全）
- 在线查询执行（SELECT 限制，禁止 DDL/DML）
- 禁用库查询拦截：非超管查询 `is_active=False` 的数据库返回 403
- 行数限制（默认 1000）
- 查询权限申请/审批流程
- 审批通过阶段支持审批人在申请有效期内缩短授权有效期
- 已生效查询权限支持申请用户、资源组 DBA、全局 DBA、超管按权限范围撤销
- 查询权限撤销记录完整保留撤销时间、撤销人、撤销原因；历史软删除记录通过迁移回填为“系统/历史数据”
- 查询权限页新增统一治理视角管理页和“已撤销权限”视图
- 在线查询工作台已重构为：左侧表浏览器、中间 SQL 编辑器、底部 `DDL 预览 / 结果` Tab
- 表浏览器支持 `插入表名`、`生成 DDL`；`DDL 预览` 支持 `可复制 DDL / 原始 DDL` 双模式与 `复制 DDL`
- 数据脱敏（sqlglot 解析所有方言，替代 goInception）：
  - 7 种内置规则（邮箱/手机号/银行卡/身份证/姓名/地址/自定义正则）
  - 按实例/数据库/表/列精确匹配
  - 实时预览脱敏效果

### Pack A — SQL 工单全流程 ✅

**工单核心**
- 工单提交（支持从工单模板快速套用）
- 工单提交（支持从模板创建、保存当前工单为模板）
- 9 种工单状态：待审核→审核通过→执行中→执行成功/异常/已取消
- AuditV2 审批流（支持多级审批）
- Celery 异步执行，WebSocket 实时进度推送
- SQL 预检查（sqlglot 解析，无需 goInception）
- 工单列表已拆分为 `我的工单 / 审批记录 / 执行记录` 三标签
- 工单详情按钮按 `can_audit / can_execute / can_cancel` 能力字段显示，审批人无需手动刷新即可看到审批按钮
- 工单列表中的审批链路、当前节点、状态列已按视角与状态做统一展示
- SQL 工单列表新增“工单视图”，按统一治理视角展示 self/group/instance_scope/global 范围内的工单；具体操作仍由业务能力字段控制
- 审批日志中的操作人优先显示用户显示名

**工单模板（Pack D）**
- 模板 CRUD（个人模板 / 全局模板），使用次数统计
- 支持从模板创建工单、保存当前工单为模板
- 支持复制模板、模板预览、启用 / 停用
- 内置 7 个默认全局模板分类样例
- 点击"使用"自动跳转提交页并填充 SQL

**AI Text2SQL（Pack D）**
- 调用 Anthropic Claude API
- 自动识别实例数据库类型生成对应方言 SQL
- 系统配置中配置 API Key

**运维工具**
- 会话管理（processlist / kill）
- 慢日志分析
- SQL 优化建议（sqlglot 规则）
- 数据字典（三级浏览：实例→数据库→表→字段结构）

### Pack B — 可观测中心 ✅

- Dashboard 在线查询概览（8 个卡片、查询趋势、查询用户 Top 10、治理趋势、待审批库存趋势，按统一治理视角裁剪；治理失败次数包含查询执行失败及查询权限申请/审批失败；新增撤销查询权限数和撤销权限趋势）
- Dashboard SQL 工单概览（10 个卡片、工单提交趋势、工单治理趋势、执行趋势、待审批库存趋势、5 个 Top 图，按权限范围裁剪；审批相关排行按业务对象范围统计而非个人审批待办）
- Dashboard 实例与库概览（4 个卡片、实例类型分布、实例状态分布、库-Schema 状态分布，按权限范围裁剪；实例类型展示名统一为规范命名）
- 在线查询结果区支持自适应高度、分页、`row_num` 行号列、当前页/全部结果导出
- 在线查询新增 `查询历史` 页面：支持时间范围、操作人、实例、数据库、操作类型、脱敏、SQL 关键字筛选，支持 SQL 明细查看、复制和收藏
- 查询历史复用 v2-lite 查询治理范围；查询/导出成功与失败统一写入 `query_log`，迁移新增 `0017_query_log_history_audit` 和 `0018_qlog_snapshot_backfill`
- 监控配置管理（Prometheus Exporter 配置）
- Prometheus + Grafana 集成
- Alertmanager 告警管理
- Prometheus SD（服务发现）端点

### Pack C1 — 系统管理 ✅

**系统配置**
- 7 个配置组：基础设置/邮件通知/钉钉通知/企业微信通知/飞书通知/LDAP 认证/AI 功能
- 敏感字段 Fernet 加密存储
- 各渠道连通性测试（邮件发送测试已验证）
- 配置保存后正确回填（包含敏感字段"已保存"提示）

**审计日志**
- 记录登录（成功/失败）、工单提交、工单审批、配置修改
- 敏感配置变更记录具体字段名（不记录值）
- 支持按操作类型/模块/时间范围筛选

**个人设置**
- 修改密码（当前密码验证）
- 2FA 设置向导

### Pack D — 数据安全与效率工具 ✅

| 功能 | 状态 |
|---|---|
| 数据脱敏规则管理页面（实时预览） | ✅ |
| 数据字典（实例→库→表→字段 / 约束 / 索引） | ✅ |
| 工单模板（个人/全局、从模板创建、保存为模板、默认模板） | ✅ |
| AI Text2SQL（Claude API，多方言适配） | ✅ |

### Pack E — 引擎补全与高级工具 🔧

**多引擎实现**
| 引擎 | 状态 | 说明 |
|---|---|---|
| MySQL | ✅ | 完整实现 |
| PostgreSQL | ✅ | 完整实现（含数据字典列/约束/索引） |
| Oracle | ✅ | 数据字典列/约束/索引已实现，需真实环境验证 |
| MongoDB | ✅ | 完整实现（含 processlist / metrics） |
| Redis | ✅ | 白名单安全控制，16 数据库，INFO 指标 |
| ClickHouse | ✅ | clickhouse-connect HTTP 协议 |
| Elasticsearch | 🔧 | 骨架已有 |
| MSSQL | ✅ | 数据字典最小可用实现已补齐，需真实环境验证 |
| Cassandra | 🔧 | 骨架已有 |
| Doris | 🔧 | 骨架已有 |

**数据字典能力补充**
- 字段信息：列名、数据类型、可空、默认值、注释
- 表约束：主键、唯一键、外键、引用表/列
- 索引信息：主键索引、唯一索引、普通索引、是否联合索引、索引列
- 当前关系型数据库优先支持：`MySQL / TiDB / PostgreSQL / Oracle / MSSQL`
- TiDB 复用 MySQL 元数据实现；Doris / Cassandra / Elasticsearch 仍待补齐或验证
- PostgreSQL / Oracle 列注释链路已补齐：数据字典字段详情可直接展示 `column_comment`
- PostgreSQL / Oracle 生成 DDL 会补充 `COMMENT ON COLUMN ...`；Oracle 同时保留 `DBMS_METADATA.GET_DDL` 原始版本供 DBA 查看

**数据归档**
- 全数据库支持矩阵（不支持的返回明确提示）
- purge 模式：分批删除，各数据库语法适配
- dest 模式：跨实例迁移（INSERT + DELETE）
- dry_run 预估影响行数（默认开启）
- 前端三步引导（配置→估算→确认执行）

**SQL 回滚辅助**
- sqlglot 静态逆向 SQL 生成（INSERT↔DELETE↔UPDATE）
- MySQL/TiDB：my2sql 命令生成器
- PostgreSQL：WAL 查询语句生成
- 各数据库回滚方案说明文档

**通知服务**
- 钉钉/企微/飞书三渠道并发通知
- 已接入工单提交和审批节点
- 签名验证（钉钉 HMAC-SHA256）

### 品牌升级 ✅

- 产品名：`数据库管理平台 2.0` → `SagittaDB 矢准数据`
- 主色：`#1558A8` → `#165DFF`（Space Tech Blue）
- 深色背景：`#0A2540` → `#0F172A`（Tech Charcoal）
- 字体：系统字体栈 → Inter + Noto Sans SC + JetBrains Mono
- Logo：六边形矢标 SVG（明暗双版）
- 登录页：深色 Hero 风格（背景光晕 + 网格纹理 + 磨砂玻璃卡片）
- 登录页强制改密流程改为页内表单，规则提示与后端实际校验保持一致
- 第三方登录入口：LDAP/CAS/钉钉/飞书/企微（Pack F 已完整接入）
- 主布局顶部用户入口使用单行 flex 排版，头像、用户名和通知入口不再因宽度变化换行
- Favicon 更新

### Pack F — 第三方登录集成 ✅

**统一 OAuth2 登录架构**
- 前端点击按钮 → 调后端 `GET /auth/{provider}/authorize/` 获取授权 URL → 重定向至平台
- 平台回调 `GET /auth/{provider}/callback/` → 后端换取用户信息 → 自动 provision 本地用户
- 回调成功后重定向至前端 `/oauth/callback?access_token=...&refresh_token=...`
- Redis 存储 state（5分钟 TTL）防御 CSRF

**LDAP 企业目录登录**
- 三步验证：service bind → 用户搜索（支持自定义过滤器） → user re-bind 密码验证
- 配置项：服务器地址、Bind DN/密码、搜索 Base DN、用户过滤器、属性映射（username/email/displayName）
- 自动 provision：`auth_type='ldap'`，先按 external_id（DN）查，再按用户名兼容迁移
- 依赖：`ldap3>=2.9.1`（Dockerfile + pyproject.toml 已同步）

**钉钉扫码登录（DingTalk New API v2）**
- 授权：`login.dingtalk.com/oauth2/auth`，scope=openid
- 换 token：`api.dingtalk.com/v1.0/oauth2/userAccessToken`
- 获取用户：`api.dingtalk.com/v1.0/contact/users/me`（x-acs-dingtalk-access-token）
- 配置项：登录 AppKey / AppSecret / 启用开关（独立于通知 Webhook）

**飞书扫码登录（Feishu OIDC）**
- 授权：`accounts.feishu.cn/open-apis/authen/v1/authorize`
- 换 token：Basic Auth + `open.feishu.cn/open-apis/authen/v1/oidc/access_token`
- 获取用户：`open.feishu.cn/open-apis/authen/v1/user_info`
- 复用系统配置中已有的 App ID / App Secret，新增独立登录启用开关

**企业微信扫码登录（WeCom qrConnect）**
- 授权：`open.work.weixin.qq.com/wwopen/sso/qrConnect`
- 获取企业 token → code 换 UserId → 拉取用户详情（name/email/biz_mail）
- 配置项：CorpID / 自建应用 AgentId / 应用 Secret / 启用开关

**CAS 通用 SSO**
- 支持 Keycloak / Okta / Azure AD / 任意 CAS Provider
- 标准 authorization_code 流程，支持 userinfo endpoint 或 id_token payload 解码
- 配置项：Client ID/Secret、授权端点、Token 端点、UserInfo 端点（独立 cas 配置组）

**系统配置扩展**
- CONFIG_GROUPS 新增 `cas` 分组
- 钉钉配置组新增 3 项登录参数；飞书新增登录开关；企微新增 4 项登录参数
- 共新增 11 个 system_config 配置项，全部可在 UI「系统配置」页面管理

**前端交互**
- 登录页各 OAuth 按钮点击时显示独立 loading 状态（⏳ 图标 + 边框高亮）
- 新增 `/oauth/callback` 路由（OAuthCallbackPage）：自动读取 token → 调 /auth/me/ → 跳 dashboard
- 错误时显示 oauth_error 并 3 秒后自动返回登录页
- LDAP 登录表单保持原有方案（URL 参数 `?method=ldap` + 表单切换）
- 业务 `Modal` / `Drawer` 统一设置 `maskClosable={false}`，避免用户误点遮罩导致表单内容丢失；右上角 `X`、`Esc` 与取消按钮仍保留正常关闭行为

**测试覆盖**
- `test_ldap_auth.py`：5 个单元测试（未启用/配置缺失/用户不存在/密码错误/库未安装）
- `test_oauth_auth.py`：8 个单元测试（不支持的 provider/各 provider 禁用/URL 构造/缺失配置）

### Security Hardening — 安全加固 ✅

**Token 黑名单 fail-close（`backend/app/core/deps.py`）**
- 原实现：Redis 连接失败时静默放行（fail-open），存在被伪造已注销 Token 的风险
- 修复后：Redis 不可达时返回 503 而非放行，fail-close 安全策略

**SECRET_KEY 生产环境强制校验（`backend/app/core/config.py`）**
- 使用 Pydantic `model_validator(mode="after")` 跨字段校验
- 生产环境（`APP_ENV=production`）使用默认密钥时直接 `ValueError` 阻断启动
- 非生产环境降级为 `warnings.warn` 提示

**Text2SQL 服务分层（`backend/app/services/text2sql.py`）**
- 从 `routers/ai.py` 提取全部业务逻辑至独立 Service 层
- Router 仅做 HTTP 适配，service 提供 `generate_sql()` 单一入口
- 修复 AI Router 未注册至 `main.py` 的问题（原 `/api/v1/ai/` 端点 404）

**依赖版本收紧（`backend/pyproject.toml`）**
- 使用 `~=`（compatible release）替代宽松 `>=`
- 防止 minor/major 版本自动升级引入破坏性变更

---

### 多级审批流 ✅

**后端**
- 新增数据模型：`ApprovalFlow`（审批流模板）+ `ApprovalFlowNode`（节点，支持顺序编号）
- 三种审批人类型：`users`（指定用户）/ `manager`（直属上级）/ `any_reviewer`（任意审批员）
- 快照机制：工单创建时将审批流节点复制为 `audit_auth_groups_info` JSON，模板变更不影响在途工单
- Alembic migration `0005_approval_flow.py`：新增两张表 + `sql_workflow.flow_id` 外键
- `ApprovalFlowService`：CRUD（列表/详情/创建/更新/停用）+ `snapshot_for_workflow()`
- 修改 `WorkflowService.create()`：自动读取 flow_id 生成快照，向后兼容 flow_id=None 旧模式

**前端**
- `frontend/src/api/approvalFlow.ts`：封装 5 个 API 调用（list/get/create/update/deactivate）
- `frontend/src/pages/system/ApprovalFlowPage.tsx`：
  - 审批流列表（名称、节点数、状态、创建人）
  - Drawer 表单：审批流基本信息 + `Form.List` 动态节点编辑
  - 节点审批人类型联动：选 `any_reviewer` 隐藏选择框，选 `users` 展示审批人选择，`manager` 无需额外选择
- `MainLayout.tsx` 菜单：系统管理 → 审批流管理（`ApartmentOutlined` 图标）
- `App.tsx` 路由：`/system/approval-flows` lazy import

---

## 四、待开发功能（Pack G+）

### Pack G — 质量保障 ✅

**单元测试**
- `tests/unit/test_auth.py`：密码哈希/JWT/字段加密/Schema 校验/密码安全策略（27 个测试）
- `tests/unit/test_masking.py`：sqlglot 列提取/表引用/脱敏规则（17 个测试）
- `tests/unit/test_engine_registry.py`：引擎注册表（已有）
- `tests/unit/test_data_dict_relational.py`：关系型数据库数据字典归一化（MySQL/TiDB/PostgreSQL/Oracle/MSSQL）
- `tests/unit/test_data_dict_sql_generation.py`：关系型数据库数据字典 SQL 生成层
- `tests/unit/test_instance_router_data_dict.py`：数据字典 API 路由（columns/constraints/indexes）
- `tests/unit/test_instance_service.py`：数据字典服务层归一化与兼容字段映射
- `tests/unit/test_mysql_engine.py`：MySQL 引擎（已有）
- `tests/unit/test_mongo_engine.py`：MongoDB 引擎（已有）
- `tests/unit/test_ldap_auth.py`：LDAP 认证服务（5 个测试）
- `tests/unit/test_oauth_auth.py`：OAuth2 服务（8 个测试）
- `tests/unit/test_rollback.py`：SQL 回滚辅助（24 个测试）— generate_reverse_sql/my2sql/pg_wal
- `tests/unit/test_notify.py`：通知服务（14 个测试）— 钉钉/飞书/企微 mock HTTP
- `tests/unit/test_system_config.py`：配置服务（15 个测试）— get_value/update_batch/敏感字段加密
- `tests/unit/test_workflow_service.py`：工单服务（11 个测试）— 状态枚举/格式化/check_sql
- **总计：159 个单元测试全部通过，覆盖率 37.2%（单元测试层）**

**集成测试**
- `tests/integration/test_health.py`：健康检查端点
- `tests/integration/test_auth_api.py`：登录/Token 刷新/me 接口/登出（14 个测试）
- `tests/integration/test_instance_api.py`：实例 CRUD + 权限校验（8 个测试）
- `tests/integration/test_workflow_api.py`：工单列表/提交/详情（9 个测试）

**性能测试（Locust）**
- `tests/perf/locustfile.py`：AuthUser（认证流程）+ APIUser（业务查询）
- 运行方式：`locust -f tests/perf/locustfile.py --host http://localhost:8000`

**安全扫描 CI（GitHub Actions）**
- `.github/workflows/security.yml`：Bandit SAST + pip-audit 依赖漏洞 + Trivy 容器扫描 + CodeQL
- 每周一定时执行 + main 分支 push 触发
- HIGH 级别 Bandit 问题阻断 CI

**其他质量基础设施**
- `.coveragerc`：配置覆盖率报告（分支覆盖，排除 migrations/main.py）
- `ci.yml` 更新：单元测试覆盖率门限 35%，集成测试独立阶段，Docker 构建验证

**数据字典测试补强**
- 引擎 SQL 生成层：校验各数据库命中的系统视图与关键字段
- 服务层：统一归一化 `columns / constraints / indexes`
- 路由层：覆盖 `/instances/{id}/columns`、`/constraints`、`/indexes`
- 前端：`DataDictPage` 渲染字段、约束、索引三块内容

### Pack H — 生产就绪 ✅

**Helm Chart (`deploy/helm/sagittadb/`)**
- `Chart.yaml`：声明 bitnami/postgresql + bitnami/redis 依赖（可选，支持外部托管数据库）
- `values.yaml`：完整默认值（镜像、资源限制、HPA、Ingress、PVC）
- `values-staging.yaml`：Staging 环境覆盖（单副本、小资源）
- `values-prod.yaml`：生产覆盖（3+ 副本、HPA 启用、外部 RDS/ElastiCache、cert-manager TLS）
- `templates/`：backend+worker+beat+flower+frontend Deployment、Service、Ingress、HPA、PVC、ConfigMap、Secret、ServiceAccount、NOTES.txt
- initContainer 自动运行 `alembic upgrade head`
- Beat 副本锁定为 1（防止定时任务重复触发）

**生产 Docker Compose (`docker-compose.prod.yml`)**
- 覆盖开发版：去除代码热挂载，生产命令（4 workers），资源 limit/reservation

**数据库备份 (`deploy/backup/`)**
- `backup-postgres.sh`：pg_dump + gzip，支持 S3 上传，cron 定时备份，自动清理过期文件
- `restore-postgres.sh`：从本地文件或 S3 URI 恢复，交互确认防误操作

**CI/CD 升级 (`.github/workflows/ci.yml`)**
- 新增 `docker-publish` job：push main 后自动构建并推送 GHCR（Docker 层缓存加速）
- 新增 `helm-lint` job：lint 三套 values + template render 验证

---

## 五、已知问题与技术债

| 问题 | 严重级别 | 说明 |
|---|---|---|
| Celery Worker 健康检查 unhealthy | 低 | 无 HTTP 健康检查端点，功能正常但状态显示异常 |
| Oracle/MSSQL/Cassandra/Elasticsearch/OpenSearch 引擎未全量验证 | 中 | 骨架已实现，需真实环境测试 |
| Alembic 迁移文件需手动执行 | 低 | 新建表均有对应 SQL 脚本，需补充 CI 自动执行 |
| totp_secret 字段已扩展至 500 | 已修复 | 原 100 字节不足，已通过 ALTER TABLE 修复 |
| OAuth 回调 URL 需与各平台后台配置一致 | 低 | 部署时需在钉钉/飞书/企微管理后台填写正确的 callback URL |

---

## 六、Hotfix 记录摘要

| 编号 | 修复内容 |
|---|---|
| hotfix1~5 | docker-compose 位置、Alpine 镜像、structlog→logging、语法错误、alembic 同步 |
| hotfix6~10 | exceptions 关键字参数、user.py PG INSERT ON CONFLICT、security.py bcrypt 直调、registry instanceof 移除 |
| hotfix11~15 | frontend Dockerfile 两阶段构建、tsconfig strict 关闭、App.tsx 路由修复、MainLayout 布局重构、AuthGuard 修复 |
| hotfix16~19 | 工单状态语义、docker-compose frontend 挂载方式、WorkflowList 状态选项 |
| packC1_hotfix | totp_secret 扩展、审计日志写入、资源组 Transfer 穿梭框 |
| packC1_hotfix2 | system_config update_batch 返回 change_summary、表单回填 useEffect 修复 |
| packC2_hotfix | instance.py TunnelService import 修复 |
| packD_hotfix | WorkflowSubmit Modal 未 import、MainLayout/App 菜单路由未更新 |
| packD_hotfix2 | WorkflowSubmit extra prop AI 按钮插入修复 |
| packE_request_import | workflow.py router 缺少 Request import |
| brand_hotfix1~2 | LoginPage login 方法不存在、/auth/me/ token 时序问题 |
| brand_hotfix_password | bcrypt 哈希算法 hexdigest→base64 修正 |
| packF_ldap | LDAP 三步验证 + 用户自动 provision，ldap3 依赖接入 |
| packF_oauth | 钉钉/飞书/企微/CAS OAuth2 全流程，Redis state CSRF 防护，OAuthCallbackPage |
| packG_tests | 152 单元测试 + 31 集成测试；Locust 性能测试；Bandit+pip-audit+Trivy 安全扫描 CI |
| rollback_hotfix | exp.AlterTable → exp.Alter（sqlglot 版本兼容修复）|
| packH_deploy | Helm Chart（12 模板文件）+ docker-compose.prod.yml + 备份脚本 + GHCR 发布 + Helm lint CI |
| security_hardening | Token 黑名单 fail-close / SECRET_KEY 生产强制校验 / Text2SQL 分层 / AI 路由注册修复 / 依赖版本收紧 |
| approval_flow | 多级审批流后端（model/service/migration/router）+ 前端管理页面完整实现 |
| db_permission_control | 数据库 is_active 权限管控：普通用户 API 过滤 + 前端下拉框已禁用标签 + 查询 403 拦截 |
| bugfix_dictcursor | MySQL DictCursor 导致数据库名显示为 dict 字符串（3 处后端代码修复 + SQL 脏数据清理） |
| bugfix_pg_tables | PostgreSQL masking_rule/workflow_template 表缺失（迁移遗漏，直接 SQL 补建） |
| bugfix_dropdown_truncate | 6 个前端页面数据库下拉框长名字截断（popupMatchSelectWidth=false + maxWidth） |

---

## 七、关键技术决策记录

| 决策 | 内容 |
|---|---|
| 密码哈希 | bcrypt 直接调用 + SHA-256 + base64 预处理（规避 72 字节限制） |
| 本地密码策略 | 至少 8 位，必须包含数字、大写字母、小写字母和特殊字符；默认/弱/过期密码登录时强制改密；30 天轮换，到期前 7 天提醒 |
| 字段加密 | Fernet 对称加密（cryptography 库） |
| SQL 解析 | sqlglot 替代 goInception（支持 20+ 方言，零外部进程依赖） |
| 工单状态 | 整数枚举 0-8（0=待审核，6=成功，7=异常，8=取消） |
| 数据库注册 | instance_database 表解耦实例连接与数据库名，Oracle=Schema，Redis=数字索引；is_active 字段控制启停和权限 |
| 数据库权限管控 | is_active=False 的库：普通用户 API 不可见 + 前端下拉框不显示；管理员可见并标灰提示"已禁用"；查询接口 403 拦截 |
| 归档实现 | 纯 Python 通过引擎层执行，不依赖 pt-archiver，各数据库分批语法独立适配 |
| Binlog 回滚 | 重定位为"SQL 回滚辅助"，my2sql 做命令生成器而非直接执行 |
| 品牌主色 | #165DFF（Space Tech Blue，ARCO Design 标准色） |
| OAuth2 回调架构 | 后端处理 code 交换 → JWT → 重定向前端，前端无需保存 client_secret，安全且符合 SPA 最佳实践 |
| LDAP 密码验证 | 使用 user re-bind 方式（而非 compare），兼容更多 LDAP Server |
| OAuth state 存储 | Redis（5min TTL），优于 Session/DB，天然支持多实例无状态部署 |
| Token 黑名单安全策略 | fail-close：Redis 不可达时拒绝请求（503），而非放行，防御已注销 Token 被复用 |
| SECRET_KEY 校验方式 | `model_validator(mode="after")` 跨字段校验（`field_validator` 仅支持单字段），生产环境使用默认密钥直接 ValueError 阻断启动 |
| 审批流快照机制 | 工单创建时快照节点信息，确保模板变更不破坏在途审批；node 顺序由数组下标重新赋值，确保连续性 |
| 审批人类型设计 | 三级颗粒度（指定用户 / 资源组全员 / 任意审批权限），覆盖从精确到宽松的全部场景 |

---

## 八、授权体系 v2-lite 收敛（100% — 已完成）

> 详细方案请见 [sagittadba_auth_redesign_v2.md](sagittadba_auth_redesign_v2.md)

### 核心变更

| 变更项 | 现状（v1） | 当前落地（v2-lite） |
|---|---|---|
| 权限模型 | 26 个权限码直绑 User（扁平） | Role → Permission（4个内置角色 + 自定义角色） |
| 实例隔离 | User → ResourceGroup → Instance | UserGroup → ResourceGroup → Instance |
| 查询授权 | QueryPrivilege 仅授权给用户 | 首发仅启用“授权给用户本人 + database/table 两级粒度” |
| DBA 角色 | 无（is_superuser 或扁平权限码） | dba（全局）/ dba_group（资源组内） |
| 审批流 | 指定用户 / 资源组 / 任意审批人 | 首发仅启用 users / manager / any_reviewer |
| 用户信息 | 无工号/部门/岗位/直属上级 | + employee_id / department / title / manager_id |
| 认证方式 | 密码 + OTP + LDAP + OAuth×4 | + 短信验证码 |
| 资源组 | 用户 + 实例多对多 | 仅实例（用户通过用户组间接关联） |

### 已完成

| 子项 | 状态 | 说明 |
|---|---|---|
| Role + UserGroup 模型 | ✅ | `models/role.py` — Role / UserGroup / 3 关联表 |
| Users v2 字段 | ✅ | role_id / manager_id / employee_id / department / title |
| Alembic 迁移 0006-0009 | ✅ | 新建表 + 扩展字段 + v2 扩展 + 旧表清理 |
| 内置角色种子数据 | ✅ | superadmin / dba / dba_group / developer |
| Role + UserGroup CRUD API | ✅ | /roles/ + /user-groups/ + 资源组用户组关联 |
| 权限链路升级 | ✅ | current_user 仅读角色权限（不再合并 user_permission） |
| 资源组访问链路 | ✅ | 仅通过用户组（不再查 user_resource_group） |
| QueryPrivilege 收敛 | ✅ | 首发只启用 user + database/table，保留兼容字段 |
| 查询权限安全修复 | ✅ | 查询先校验实例资源范围，再校验库/表授权 |
| ApprovalFlowNode 收敛 | ✅ | 首发只启用 users / manager / any_reviewer |
| 短信验证码认证 | ✅ | 阿里云/腾讯云/自定义 HTTP，Redis 限流 |
| LDAP/OAuth 字段同步 | ✅ | employee_id / department / title / manager_id |
| 前端角色管理页面 | ✅ | RoleManagement.tsx |
| 前端用户组管理页面 | ✅ | UserGroupManagement.tsx（白屏修复：补充 Modal 导入） |
| 前端路由 + 菜单 | ✅ | 菜单按权限码过滤，路由统一加 PermissionGuard |
| 用户管理 v2 字段 | ✅ | 角色选择 / 用户组（显示名称 Tag）/ 直属上级 / 工号 / 部门 / 职位 |
| 资源组管理 v2 | ✅ | 展示关联数据库实例列表 + 用户组穿梭框，移除直接成员穿梭框 |
| 资源组用户组关联 | ✅ | 前端穿梭框 + 后端 GET/PUT API |
| 资源组停用约束 | ✅ | 停用资源组不能再被用户组新关联，前后端双重拦截 |
| 数据库类型显示统一 | ✅ | 前端统一展示为 MySQL / PostgreSQL / TiDB / ClickHouse 等官方命名 |
| 品牌页签统一 | ✅ | 浏览器标题更新为 `矢 准 数 据` |
| 用户批量导入导出 | ✅ | 支持 Excel / CSV 模板下载、导出回灌、失败记录导出 |
| 用户页统一筛选导出 | ✅ | 顶部筛选支持角色 / 用户组 / 部门 / 职位 / 状态，多条件交集后导出筛选结果或勾选结果 |
| 用户组批量导入导出 | ✅ | 支持 Excel / CSV 模板下载、导出回灌、失败记录导出 |
| 用户组页统一筛选导出 | ✅ | 顶部筛选支持组标识 / 中文名、组长、上级组、关联资源组、状态，多条件交集后导出筛选结果或勾选结果 |
| SQL 工单资源组解析 | ✅ | 提交页移除手动资源组选择，后端按用户组→资源组→实例自动归属 |
| 后台表格体验统一 | ✅ | 核心页面统一固定列宽 / 横向滚动 / 关键字段展示 / 结果表格空态 |
| 数据迁移脚本 | ✅ | scripts/migrate_v1_to_v2.py（dry-run + 实际运行验证） |
| 权限 API | ✅ | get_merged_permissions 仅查 role_permission（grant/revoke 操作角色权限） |
| Phase 4 旧表清理 | ✅ | 删除 user_permission / user_resource_group 表及所有代码引用 |
| 查询权限排查接口 | ✅ | `/api/v1/query/access-check/` 返回 `allowed/reason/layer` |
| 验证闭环 | ✅ | 前端 typecheck + 后端 v2-lite 授权单测通过 |

### 四个内置角色

| Role | 中文名 | 关键特征 |
|---|---|---|
| `superadmin` | 超级管理员 | is_superuser=True，绕过一切检查 |
| `dba` | 全局 DBA | 运维权限 + query_all_instances + monitor_all_instances |
| `dba_group` | 资源组 DBA | 运维权限，实例范围限于资源组 |
| `developer` | 开发工程师 | 工单提交 + 查询申请，需授权才能查库 |

### 本次补充验证

| 检查项 | 结果 |
|---|---|
| `frontend: npm run typecheck` | ✅ 通过 |
| `backend: python3 -m compileall app` | ✅ 通过 |
| `backend: ./.venv/bin/python -m pytest tests/unit/test_authz_v2_lite.py` | ✅ 13 passed |
| 停用资源组关联拦截 | ✅ 通过（后端容器内直接验证 `site-db` 被拒绝关联） |

### 首发未启用但保留兼容位

- `QueryPrivilege.user_group_id`
- `QueryPrivilege.resource_group_id`
- `scope_type = resource_group / instance`
- `ApprovalFlow.approver_type = user_group / role`

### 迁移计划（已全部完成）

1. **Phase 1**（已完成）：新增表 + 扩展字段 + 短信认证 + LDAP 同步 + 前端页面
2. **Phase 2**（已完成）：数据迁移脚本（user_permission → Role，user_resource_group → UserGroup + ResourceGroup）
3. **Phase 3**（已完成）：切换逻辑（require_perm 读角色权限，资源组路径改用户组→资源组→实例）
4. **Phase 4**（已完成）：清理旧表（user_permission / user_resource_group）+ 前端资源组展示实例 + 用户组/用户管理修复

---

*文档最后更新：2026-04-20 · SagittaDB v1.0-GA + v2-lite 权限收敛与后台表格体验收口持续完成中*
