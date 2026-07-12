# Sagitta Control 项目综合评估报告（2026-07-10）

> 评估方式：静态结构核查 + 运行时/安全核查，逐项实测验证。
> 代码基线：评估起点 `main` @ `6b9dbda`；处理后状态以本报告所在提交为准。
> 说明：本报告为工程质量评估审计件，用于跟踪优化项进度；发现结论均附 `文件:行号` 或命令证据锚点，可随时复核。

## 1. 总体判断

工程底子扎实：CI 门禁体系完整（前后端 lint/test/build/E2E/依赖审计/引擎契约/Compose 校验/镜像构建）、仓库卫生良好、技术债标记极少、安全设计成体系（Cookie/CSRF/弱密钥门禁、统一 `governance_scope`、`SqlQueryGuard`）。

评估开始时，`main` 因两项 P0 门禁失效不算“持续可交付”；经本次处理后门禁已全部恢复绿色，可交付性已修复。其余为可维护性 / 健壮性层面的渐进优化项，均非线上 Bug。

规模参考：后端 `app` 约 42k 行 / 130 文件，前端约 23k 行 / 125 文件。

## 2. 状态总览

| # | 优先级 | 发现 | 状态 |
|---|---|---|---|
| 1 | P0 | CI 因账户 billing 未启动 | 已解决 |
| 2 | P0 | 前端 lint 红线阻断 CI | 已修复 |
| 3 | P1 | 审计 IP 取最左 XFF 可伪造 | 已修复 |
| 4 | P1 | 在线查询 limit 正则/字符串硬化 | 已修复 |
| 5 | P2 | 类型 strict 门禁只护基础设施层（全量 871 错误 / 66 文件仅 notice） | 已完成（全量 strict 硬门禁） |
| 6 | P2 | 覆盖率门槛偏低（55%，核心面 20–40%） | 进行中（55.42%→58.37%，门禁 55→58） |
| 7 | P3 | 上帝服务 `monitor.py`（单类 58 方法 / 1841 行） | 已完成 |
| 8 | P3 | 权限判定重复实现（观测域实例访问判定） | 已修复 |
| 9 | P3 | 分层泄漏（router 直接写 DB/业务编排） | 已修复 |
| 10 | P3 | 前端超大页面组件（最大 1093 行） | 部分（渐进） |
| 11 | P4 | 部署脚本示例版本过期（`--ref v2.0.0`） | 已修复 |
| 12 | P4 | 本地 venv 解释器失效（改名遗留） | 已修复 |
| 13 | P4 | CI action 仍 target Node 20（官方将废弃） | 已修复 |
| 14 | P4 | CI 缓存 glob 未命中锁文件（缓存永不失效） | 已修复 |

## 3. 已完成项明细

### #1 CI 因 billing 未启动 —— 已解决（by 仓库转 public）

public 仓库标准 runner 免费无限额度。同一次 push 对比：`Release Version Record` 由 4s `failure` → 10s `success`；`CI` 由 4s `failure` → 跑满 5m24s 通过。此前 annotation 原文 `The job was not started because recent account payments have failed or your spending limit needs to be increased` 已消失。

### #2 前端 lint 红线 —— 已修复

`frontend/src/pages/monitor/MonitorPage.tsx:116` 的参数同步 `useEffect` 缺少依赖 `isDiagnostics`、`navigate`、`searchParams`，叠加 eslint `--max-warnings 0`，一个 warning 即阻断 CI 前端门禁。

按仓库既有约定补全依赖数组（重定向由 `!isDiagnostics` 守卫兜底，不会成环）。本地 lint / typecheck / 37 单测 / build 全绿；CI 前后端门禁均通过（后端质量门禁 5m24s、前端质量门禁 1m43s）。提交 `8548c4c`，已推送 `origin` 与 `gitee`。纯 lint 修复、零行为变化，无需更新文档，无需同步 ECS。

### #11 部署脚本示例版本过期 —— 已修复

`deploy/update-prod.sh:85` help 示例 `--ref v2.0.0` 更新为 `--ref v3.0.0`。随 P4 一并提交 `775b786`。

### #12 本地 venv 失效 —— 已修复

删除并用 `uv venv --python 3.12` 重建 `backend/.venv`，解释器已指向 uv 托管 CPython 3.12；从 `requirements.lock` 安装依赖，冒烟验证 `mypy`/`ruff`/`pytest` 可用、`app.main` 可导入、基线 mypy 目标通过。属本地环境修复，`.venv` 已被 gitignore，不入库。

### #13 CI action Node 20 废弃 —— 已修复

源码 CI 链路（`ci.yml`、`release-version-record.yml`）action 升级到 node24 运行时：checkout v4→v5、setup-node v4→v5、setup-python v5→v6、setup-uv v5→v7、setup-buildx-action v3→v4、build-push-action v5→v7、upload-artifact v4→v7；版本均经各 action.yml `runs.using` 核验为 node24。CI run 29097876592 已确认 `Node.js 20 is deprecated` 告警消失。`commercial-release.yml` 属商业发布链路按规则未动，且其 `login-action`/`cosign-installer` 最高仅 v3=node20，无更高大版本可升。

### #14 CI 缓存 glob 未命中 —— 已修复

`ci.yml` setup-uv 步骤显式指定 `cache-dependency-glob: backend/requirements.lock`。CI run 29097876592 已确认 `No file matched` 告警消失，后端门禁耗时由约 5m24s 降至约 4m2s。

### #3 审计 IP 可伪造 —— 已修复

原 `query.py`、`audit_log.py` 直接取 `X-Forwarded-For` 最左值（客户端可控、可伪造）。新增共享解析器 `backend/app/core/net.py::resolve_client_ip`，按可信反向代理层数 `TRUSTED_PROXY_COUNT`（新增配置，默认 1=单层 nginx；0=直连无代理，忽略 XFF）从 XFF **右侧**取最外层可信代理注入的真实客户端 IP；条目数不足时回退 socket 对端地址。两处取 IP 收敛到该解析器，并同步 `.env.example` 与 `installation_deployment.md` 生产安全检查项。防伪造前提是 backend 仅经可信代理内网可达（已在部署文档强调）。随 `692ec34` 提交。

### #4 在线查询 limit 硬化 —— 已修复

原基类 `apply_limit` 用正则 `\blimit\b` 判断 + 字符串拼接，会把字符串字面量/注释中的 `limit` 误判为已有上限，导致 DB 执行无界查询、海量行进入后端内存（数据越权已由执行后 Python 行截断兜底，此项为内存/DoS 加固）。改用 sqlglot AST 注入/检测顶层 LIMIT，正确处理字符串、注释、ORDER BY、CTE、UNION；AST 不可用时回退保守字符串追加。Oracle（ROWNUM 子查询）、MSSQL（TOP 子查询）保持既有子查询封装以兼容 11g/T-SQL；Elasticsearch 因索引名转义敏感仅用 AST 检测已有 LIMIT、保持原 SQL 文本。新增边界用例单测（字符串/注释含 limit、已有 LIMIT、ORDER BY、CTE/UNION）。随 `692ec34` 提交。

### #8 观测域实例访问判定重复 —— 已修复

`MonitorService` 与 `MonitorAlertService` 各自重复实现了逐字节相同的 `_can_access_instance`（另有 `slowlog.py:359` 经 `MonitorService` 调用），存在逻辑漂移风险。注：`governance_scope` 自身文档界定「视角只决定数据可见范围，操作权限由业务服务判断」，故此项不并入 governance_scope。将 canonical 保留在叶子模块 `MonitorAlertService`（与 `monitor.py` 既有门面委托 8 个观测原语的模式一致），`MonitorService._can_access_instance` 改为委托，消除重复实现，行为不变（5 类用户场景等价性已验证）。随 `b907589` 提交。

### #9 router 分层泄漏 —— 已修复

三处 router 直接操作数据库（含 `db.commit`/`db.add`/`delete`/`insert`）的业务编排/写操作下沉到对应 service，router 仅保留编排与响应封装：观测中心手动采集整段编排 → `MonitorService.collect_native_now`；查询日志收藏切换 → `QueryPrivService.toggle_favorite`；资源组成员 join 查询与用户组关联增删 → `UserGroupService.list_members_for_resource_group` / `update_resource_group_user_groups`。清理下沉后的孤儿 import，新增 4 个断言级单测锁定行为（原端点无覆盖），全量 1030 单测通过、覆盖率 55.21%。随 `3af75ea` 提交。余下 router 中「按 id 取实体传给 service」的轻量只读取值属可接受的编排前置，未纳入本次改动。

### #7 上帝服务 `monitor.py` 拆分 —— 已完成

原 `MonitorService` 单类 58 方法 / 1841 行，混合配置 CRUD、权限工单、指标采集、告警、容量、TopSQL 六类职责。对照评估原文要求「至少拆为 Config / Collect / Alert / Capacity 服务」，四域已全部下沉到叶子服务：告警域 `MonitorAlertService`（`monitor_alerts.py`，随 #8 `b907589`）、容量域 `MonitorCapacityService`（`monitor_capacity.py`，`e64cf86`）、采集引擎域 `MonitorCollectService`（`monitor_collect.py`，`23ffb81`）、配置与权限域 `MonitorConfigService`（`monitor_config.py`，`72ae039`）。`monitor.py` 由 1841→968 行，保留为门面（委托叶子原语），外部 35 处调用零改动，全量 1030 单测通过。判定为已完成。

## 4. 待处理 / 渐进项明细（含证据锚点）

### P2 · 类型与测试债

- **#5 类型门禁只护基础设施层 —— 已完成（全量 strict 硬门禁）**：全量 `mypy app`（`strict = true`）现零错误（134 源文件全绿），CI 由 notice 审计翻转为**硬门禁**，增量 `mypy-baseline.txt` 逐文件门禁已完成使命并移除。清偿路径：monitor 6 文件（`87d2ae7`/`e6311ea`）→ engines 9（`4eaccf9`）→ models/schemas 7（`ca39281`）→ services 24（`8372660`）→ routers 22 + main + exceptions（`cde7a04`），累计清 811 处 strict 错误。绝大多数为机械补全（`dict/list` 泛型参数、函数注解），少量语义修正均保持行为并经全量 1030 单测回归：tidb `_processlist_sql` 与父类签名冲突消歧、SMTP/SMTP_SSL 分支类型统一、instance 数据字典辅助函数返回类型纠正、引擎非协议调用以 `cast(Any, engine)` 局部收敛、FastAPI 中间件/异常处理器签名补全等。新增后端代码此后必须保持 strict 清洁。
- **#6 覆盖率门槛偏低 —— 进行中（第一阶段达标）**：起点总覆盖 55.42%。第一阶段以 AsyncMock 隔离 DB 补测服务层核心低覆盖文件，已推进到 **58.37%**，CI 门禁由 `--cov-fail-under=55` 抬至 **58**（新实测地板），全量 1161 单测通过。已补测明细：
  - `services/audit_log.py` 23.94%→97.18%
  - `services/query_priv.py` 41.40%→61.76%（三级授权、有效 limit、pg search_path、权限列表）
  - `services/approval_flow.py` 21.85%→100%
  - `services/masking_rule.py` 21.17%→92.79%（脱敏规则 + 工单模板）
  - `services/instance_database.py` 17.52%→96.35%
  - `services/user.py` 21.86%→35.21%（用户/资源组核心方法）
  - 附带修复 `tests/unit/test_authz_v2_lite.py` 3 处直接 setattr 未复原的测试隔离缺陷（改用 monkeypatch）。
  第二阶段（待续）：继续补测 `services/user.py`/`role.py`/`archive.py`/`commercial_ops.py` 等大体量文件与 router 层（需集成 client），逐模块推进至 65%。

### P3 · 结构可维护性

- **#10 前端超大页面组件 —— 部分（渐进）**：`MonitorPage.tsx` 1093 行、`LoginPage.tsx` 916 等仍偏大。数据层已用 TanStack Query，基础良好。已完成 4 个安全切片（均为纯逻辑/重复抽离，无浏览器可验证、零行为变化）：
  - `1c9ceac`：从 `UserManagement` 抽离导入/导出纯工具（782→735 行）；
  - `b19aa48`：拆分 `UserGroupManagement`（810→765）并把三处页面重复内联的 `extractFileName`/`triggerDownload` 收敛到共享 `utils/fileDownload.ts`（附单测）；`QueryPage` 764→748；
  - `155fddc`：归档/工单列表/查询权限三页重复的风险标签渲染与 low/medium/high 元数据收敛到 `utils/riskLevel.ts` + `components/common/renderRiskTag.tsx`（附单测，各页回落语义可注入保持不变）；
  - `efbba49`：`normalizeTemplateText`（2 工单页）与 `renderDateTimeCell`（2 查询页）两处逐字节重复工具分别收敛到 `pages/workflow/templateText.ts`（附单测）与 `components/common/renderDateTimeCell.tsx`。
  - `b85e204`（扫尾）：`STATUS_COLOR`（工单状态色）在 WorkflowList/WorkflowDetail 逐字节重复 → `pages/workflow/workflowStatus.ts`（附单测）。另经核查 `renderDate`（Diagnostic 返回字符串 vs WorkflowList 返回 JSX，实现不同）、`statusColor`（Monitor vs License 不同业务域不同键值）**不宜合并**，保持原样。

  **深拆阶段**（子组件抽离，取纯展示边界降回归面，均附 testing-library 渲染单测替代全栈交互验证）：
  - `6735420`+`2e44c97`：`MonitorPage` 统一采集配置弹窗 → `components/MonitorConfigModal.tsx`（open/scope/form + onOk/onClose 回调，mutation 逻辑留父组件），1093→1016 行，附渲染单测；
  - `7066d37`：`LoginPage` 二步验证分支 → `components/TwoFactorLoginForm.tsx`（onSubmit/onBack 回调），916→871 行，附渲染单测（覆盖表单校验提交通路）。

  前端单测 37→56。两大页面仍可继续按同法增量抽（MonitorPage 的实例总览表/各 workbench 面板、LoginPage 的 LDAP/SMS/强制改密子表单等），每片保持纯展示边界 + 渲染单测。

> #7 已完成，明细见第 3 节「已完成项明细」；P4 各项（#11–#14）已处理，明细同见第 3 节。

## 5. 建议推进顺序

P0、P1（#3/#4 安全项）、P2 之 #5（类型 strict 全量硬门禁）、P3（#7/#8/#9 结构项）、P4 已闭环。剩余：

1. **#6 覆盖率**（P2，进行中）：第一阶段已完成——服务层核心文件补测使总覆盖由 55.42% 升至 **58.37%**，`--cov-fail-under` 已抬到新实测地板 **58**。抬至 65% 仍需净增约 1200 行受测语句，属跨模块、DB 集成级的大批量补测工作，分阶段推进：第二阶段继续覆盖 `services/user.py`/`role.py`/`archive.py`/`commercial_ops.py`/`notify.py` 等大体量文件及 router 层（需集成 client）。
2. **#10 前端大组件**：已完成多片纯逻辑/重复抽离，并完成 `MonitorPage` 配置弹窗、`LoginPage` 二步验证表单两个深拆切片。`MonitorPage`、`LoginPage`、`ArchivePage`、`QueryPrivPage` 等仍适合继续按纯展示边界 + 渲染单测方式增量拆分。

## 6. 附：两份评估的互补性

- 运行时/安全镜头：抓到 #1–#4（CI/lint 当前红、审计 IP 伪造、query limit 硬化），纠正了“main 健康可交付”的早期误判。
- 静态结构镜头：量化了 #5、#7–#9（类型债规模、上帝服务、权限重复、分层泄漏）。

两者不冲突，合并即完整画像：前者偏运行时健康与安全暴露面，后者偏静态结构与类型债。
