# SagittaDB 发布说明模板

> 每次商业交付版本发布时复制本模板，生成 `release-notes-vX.Y.Z.md`。

## 版本信息

| 项目 | 内容 |
|---|---|
| 版本号 | vX.Y.Z |
| 发布日期 | YYYY-MM-DD |
| 发布类型 | GA / Patch / Hotfix |
| 镜像标签 | `ghcr.io/<repo>-backend:vX.Y.Z` / `ghcr.io/<repo>-frontend:vX.Y.Z` |
| 数据库迁移 | Alembic head: `<revision>` |
| 兼容版本 | 从 vX.Y.Z 起支持升级 |

## 发布摘要

- 

## 新增功能

- 

## 修复问题

- 

## 安全与权限变化

- 权限码变化：
- 默认配置变化：
- 安全注意事项：

## 数据库迁移

- 新增迁移：
- 是否可回滚：
- 回滚注意事项：

## 引擎支持边界

本版本引擎支持范围以 `docs/engine_support_matrix.md` 为准。不得将待验证引擎作为标准交付能力承诺。

## 升级步骤

1. 备份 PostgreSQL 元数据库。
2. 备份当前 `.env`、部署清单和客户自定义配置。
3. 拉取新版本镜像或代码。
4. 执行 Alembic 迁移。
5. 重启 Web、Worker、Beat。
6. 运行 `deploy/preflight-check.sh`。
7. 按 `docs/upgrade_rollback_acceptance.md` 完成验收。

## 已知限制

- 

## 验收结果

| 检查项 | 结果 | 备注 |
|---|---|---|
| 健康检查 |  |  |
| 数据库迁移 |  |  |
| 登录和权限 |  |  |
| SQL 工单 |  |  |
| 查询权限和在线查询 |  |  |
| 数据归档 |  |  |
| 通知投递 |  |  |
| License |  |  |
| 回滚演练 |  |  |

## 最新剩余计划任务

本次发布剩余任务以 `docs/remaining_plan.md` 为准。发布说明中应摘录本版本仍未完成或不进入本次发布的 P1/P2 项，并明确是否影响客户上线。
