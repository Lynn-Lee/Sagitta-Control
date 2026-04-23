# Frontend — React 前端

## 技术栈

- React 18 + TypeScript + Vite
- Ant Design 5（含 Design Token 定制）
- Zustand（全局状态）+ TanStack Query（服务端状态）
- Monaco Editor（SQL 编辑器）
- Recharts（图表）
- React Router v6

## 开发环境启动

```bash
# 安装依赖
npm install

# 启动开发服务器（含 API 代理到 localhost:8000）
npm run dev

# 类型检查
npm run typecheck

# Lint
npm run lint

# 构建生产版本
npm run build
```

## 权限 UI 口径（v2-lite）

前端当前遵循以下实现规则：

- 菜单显示由权限码驱动，不再维护“角色 -> 菜单”的第二套真相
- 路由进入由 `PermissionGuard` 做页面级兜底
- 查询页在收到 403 时，会调用 `/query/access-check/` 展示权限拒绝层级和原因

当前首发范围：

- 查询权限申请仅支持库级 / 表级
- 审批流配置仅支持 `指定用户 / 直属上级 / 任意审批员`
- `developer` 默认不显示监控、运维工具、系统管理、审计日志
- 资源组弹窗只保留“关联数据库实例 / 关联用户组 / 状态”三个核心配置
- 停用资源组不会再出现在用户组编辑弹窗的可选资源组列表中
- 浏览器标题统一为 `矢 准 数 据`
- 数据库类型展示统一为官方命名，例如 `MySQL`、`PostgreSQL`、`TiDB`
- 用户管理页支持统一筛选：`用户名 / 显示名 / 邮箱 / 电话号码`、角色、用户组、部门、职位、状态
- 用户管理导出直接复用当前页筛选条件，支持导出“当前筛选结果”或“当前勾选结果”
- 用户管理支持 Excel / CSV 批量导入导出，导出文件可直接回灌更新
- 用户组管理页支持统一筛选：`组标识 / 中文名`、组长、上级组、关联资源组、状态
- 用户组管理导出直接复用当前页筛选条件，支持导出“当前筛选结果”或“当前勾选结果”
- 用户组管理支持 Excel / CSV 批量导入导出，支持模板下载、失败记录导出与回灌更新
- SQL 工单提交页不再暴露资源组选择，实例与数据库选定后由系统自动解析资源组归属
- SQL 工单列表拆分为 `我的工单 / 审批记录 / 执行记录` 三个标签页，并按视角分别展示不同列
- SQL 工单详情页使用后端返回的 `can_audit / can_execute / can_cancel` 控制操作按钮，审批人无需手动刷新即可看到审批按钮
- SQL 工单列表中的 `审批链路 / 当前节点 / 状态` 已按状态和场景做固定宽度、单行省略和标签化展示
- 实例管理中的数据库/Schema 同步结果始终对齐当前连接用户真实可见范围；本次已不可见的旧记录会在同步后自动清理
- Oracle 实例在普通 Schema 用户下只同步当前用户自身可见 Schema；高权限账号才会同步更大范围
- 实例删除如果被资源组引用，前端会直接展示后端返回的明确阻断提示
- 核心后台列表页已统一固定列宽、横向滚动、关键字段展示和结果表格空态文案
- Dashboard 一期包含“在线查询概览”“SQL 工单概览”“实例与库概览”三大模块
- Dashboard 三个模块均按当前用户权限范围裁剪数据，并支持统一时间范围筛选（`7/14/30/60` 天 + 自定义天数）
- Dashboard 在线查询模块包含 7 个卡片、查询趋势、查询用户 Top 10、治理趋势和单独的待审批库存趋势；其中“治理失败次数”包含查询执行失败及查询权限申请/审批失败
- Dashboard SQL 工单模块包含 10 个卡片、工单提交趋势、工单治理趋势、执行趋势、单独的待审批库存趋势，以及工单提交用户 / 热点实例 / 热点数据库 / 工单相关审批人 / 执行实例 Top 10
- Dashboard 实例与库概览模块包含 4 个卡片、实例类型分布、实例状态分布、库-Schema 状态分布；实例类型展示名统一为 `MySQL / PostgreSQL / Oracle / TiDB / Doris / MSSQL / ClickHouse / MongoDB / Cassandra / Redis / Elasticsearch / OpenSearch`
- Dashboard 中审批相关排行反映的是“当前权限范围内业务对象涉及的审批处理情况”，不等同于当前登录人的个人审批待办/已办工作量
- 在线查询结果区支持自适应浏览器高度、`row_num` 行号列、分页与每页条数切换，以及当前页/全部结果导出
- 在线查询页已收敛为三段式工作台：左侧表浏览器、中间 SQL 编辑器、底部 `DDL 预览 / 结果` Tab；表浏览器支持 `插入表名`、`生成 DDL`
- `DDL 预览` 支持 `可复制 DDL / 原始 DDL` 双模式；`复制 DDL` 会按当前所见版本复制
- 主布局已支持响应式侧栏与移动端抽屉导航，详情页会按路由映射保持侧边菜单高亮
- 登录页已适配窄屏窗口，登录卡片、第三方登录区和底部说明不会再发生横向溢出或遮挡
- 列表页、详情页与工具页正在统一到共享 UI 骨架：`PageHeader / FilterCard / TableEmptyState / SectionLoading / SectionCard`
- 在线查询、脱敏规则、归档、SQL 优化、SQL 回滚辅助等工具页已完成统一页头、区块卡片和空态/加载态收敛
- 数据字典页已补齐 PostgreSQL / Oracle 列注释显示；对应 DDL 预览也会附带 `COMMENT ON COLUMN ...` 语句，便于直接复制到目标环境

## 目录说明

```
src/
├── styles/          全局样式 + CSS 设计 Token
├── main.tsx         应用入口，Ant Design Token 配置
├── App.tsx          路由定义
├── store/           Zustand 全局状态（auth、ui 等）
├── api/             Axios 请求客户端 + 各模块 API 函数
├── types/           TypeScript 类型定义
├── utils/           工具函数（时间、格式化、Prometheus step 等）
├── components/
│   ├── common/      通用组件（AuthGuard、PageHeader、FilterCard、SectionCard 等）
│   ├── layout/      布局组件（MainLayout、Header、Sider）
│   ├── editor/      SQL 编辑器（Monaco 封装）
│   └── monitor/     可观测中心组件（指标卡、趋势图等）
└── pages/           页面组件（按路由模块划分）
    ├── auth/        登录、2FA
    ├── dashboard/   Dashboard
    ├── workflow/    SQL 工单
    ├── query/       在线查询
    ├── monitor/     可观测中心
    ├── instance/    实例管理
    ├── system/      系统管理
    └── audit/       审计日志
```

## UI 设计规范

参考设计文档第十章，核心原则：

- **字体**：系统字体栈（Mac→SF Pro，Win→Segoe UI），零包体积，JetBrains Mono 仅用于代码编辑器
- **主色**：`#165DFF`（Space Tech Blue），用于主按钮、链接、选中态
- **深色背景**：`#0F172A`（Tech Charcoal），用于 Header 等深色区域
- **层级**：无阴影，用背景色 + 边框区分层次
- **圆角**：按钮 6px，卡片 6px，Modal 8px
- **间距**：8px 基础网格

所有 Ant Design 5 Token 已在 `src/main.tsx` 中统一配置。

### 本轮 UI 收敛补充

- `MainLayout`：桌面侧栏 + 移动端抽屉双模式，内容区内边距随断点自适应
- `MainLayout`：主导航与系统管理子菜单支持统一的自定义 SVG 图标，图标保持 Ant Design 默认尺寸、颜色继承与选中态表现
- `MainLayout`：`SQL 工单`、`在线查询`、`运维工具` 子菜单已补齐对应的自定义 SVG 图标；“慢日志分析”图标额外做了可视边界收紧，保证与同列菜单图标的视觉尺寸一致
- `QueryPage`：查询结果表格只渲染当前页数据，结果区支持统一导出、权限排查与自适应高度
- `LoginPage`：登录卡片支持窄屏自适应，OAuth 按钮区改为可换行布局
- `DashboardPage`：统计卡片文案与后端真实聚合语义对齐
- 公共骨架组件：
  - `PageHeader`：统一页面标题、说明文案和右侧操作区
  - `FilterCard`：统一筛选区卡片边框、圆角和内边距
  - `TableEmptyState`：统一表格空状态文案与呈现
  - `SectionLoading`：统一区块级加载占位
  - `SectionCard`：统一详情页、工具页、表单页的内容卡片

## 整体进度（v1.0-GA 基线 + v2-lite 权限收敛）

| 模块 | 状态 |
|---|---|
| Sprint 0 — 骨架、路由、布局、登录页 | ✅ 完成 |
| Sprint 1 — 认证流程、实例管理页面 | ✅ 完成 |
| Sprint 2 — 在线查询（Monaco + 结果表格）| ✅ 完成 |
| Sprint 3 — SQL 工单（提交/审核/执行/WebSocket）| ✅ 完成 |
| Sprint 4 — 运维工具页面 | ✅ 完成 |
| Sprint 5 — 可观测中心（Recharts 趋势图）| ✅ 完成 |
| Sprint 6 — 联调测试、品牌升级 | ✅ 完成 |
| 权限前端收敛 | ✅ 完成（菜单权限码化、页面级 PermissionGuard、查询权限排查展示） |
