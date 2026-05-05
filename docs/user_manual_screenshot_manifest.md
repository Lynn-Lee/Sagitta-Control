# SagittaDB 用户手册截图采集清单

> 截图输出目录：`docs/screenshots/user-manual/`。采集前请启动本地演示环境，并准备一个具备超管权限的演示账号。

## 采集要求

- 浏览器宽度建议使用 1440px，避免移动端折叠影响说明。
- 演示数据应使用脱敏的测试实例、测试用户和测试 SQL。
- 不展示真实客户域名、数据库密码、Access Token、License 私钥或内部 API Key。
- 截图文件名应保持稳定，便于用户手册引用。

## 截图清单

| 文件名 | 页面/路径 | 内容要求 |
|---|---|---|
| `01-login.png` | `/login` | 账号密码登录入口和第三方登录入口。 |
| `02-dashboard.png` | `/dashboard/query` | Dashboard 查询、工单、实例统计卡片。 |
| `03-instance-list.png` | `/instance` | 实例列表、连接测试、数据库管理按钮。 |
| `04-instance-databases.png` | `/instance` | 数据库注册弹窗，展示同步和启停状态。 |
| `05-workflow-submit.png` | `/workflow/submit` | SQL 工单提交表单、实例/数据库选择和 SQL 编辑器。 |
| `06-workflow-list.png` | `/workflow` | 我的工单、审批视角、执行视角或筛选区。 |
| `07-workflow-detail.png` | `/workflow/:id` | 工单详情、审批链路、执行结果。 |
| `08-query-workbench.png` | `/query` | 表浏览器、SQL 编辑器、DDL/结果区。 |
| `09-query-privilege.png` | `/query/privileges` | 查询权限申请、审批或权限列表。 |
| `10-data-dictionary.png` | `/schema` | 表字段、约束、索引和 DDL。 |
| `11-masking-rule.png` | `/masking` | 脱敏规则列表和新增/编辑入口。 |
| `12-monitor.png` | `/monitor` | 观测中心实例、会话或 SQL 洞察视图。 |
| `13-archive.png` | `/archive` | 归档申请、作业状态和操作按钮。 |
| `14-user-management.png` | `/system/users` | 用户管理列表、角色和外部通知身份。 |
| `15-role-management.png` | `/system/roles` | 角色权限配置。 |
| `16-resource-group.png` | `/system/groups` | 资源组与实例/用户组关联。 |
| `17-approval-flow.png` | `/system/approval-flows` | 审批流节点配置。 |
| `18-system-config.png` | `/system/config` | 认证、通知、AI 和安全配置。 |
| `19-audit-log.png` | `/audit` | 审计日志筛选和列表。 |
| `20-license.png` | `/system/license` | License 状态、离线导入和在线激活区域。 |

## 用户手册替换规则

截图采集完成后，将 `docs/user_manual.md` 中的“截图占位”替换为 Markdown 图片引用：

```markdown
![登录页](screenshots/user-manual/01-login.png)
```

如果某个页面在客户交付版本中不开放，应删除对应截图引用，并在该章节说明权限边界。

## 最新剩余计划任务

统一任务清单见 `docs/remaining_plan.md`。截图相关剩余任务是最终版本截图校对和自动化截图/冒烟 E2E；如果 UI 在发布前调整，应重新采集受影响页面。
