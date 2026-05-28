# SagittaDB 专属 Agent 工作规则

本文件是 SagittaDB 项目专属的 Codex / Agent 工作规则，记录后续研发、交付和测试环境更新时必须遵守的协作约定。每次开始编码、调试、重构、文档或部署任务前，应先阅读并遵守本文；如用户明确给出更具体要求，以用户当次要求为准。

根目录 `AGENT.md` 是本项目唯一有效规则文件；如本地出现 `AGENT_*CaseConflict.md` 等同步冲突副本，一律不作为规则来源，并以当前 `AGENT.md` 为准。

## 项目定位

- SagittaDB 是面向企业数据库治理场景的统一管控平台，覆盖数据库实例管理、SQL 工单、在线查询、数据字典、权限治理、数据脱敏、SQL 洞察、运行诊断、数据归档、审计和企业通知。
- 后端目录为 `backend/`，技术栈为 Python 3.12、FastAPI、SQLAlchemy 2 async、Alembic、Celery、Redis、PostgreSQL。
- 前端目录为 `frontend/`，技术栈为 React 18、Vite、TypeScript、Ant Design 5、TanStack Query、Zustand。
- 部署目录为 `deploy/`，文档目录为 `docs/`。
- 商业发布机制参考 DataFusionX：`main` 只做源码 CI 和版本记录，`release/**` 生成 RC 候选商业包，正式 `vX.Y.Z` tag 或显式手动发布才同步 Public-Releases。

## 语言与文档规则

- 与用户沟通默认使用中文。
- Web 页面默认使用中文。
- 项目文档默认使用中文。
- 代码注释优先使用中文；类名、函数名、字段名、枚举值、配置键、SQL 关键字和第三方 API 名称保持英文。
- 专业术语保留英文，例如 FastAPI、Docker Compose、PostgreSQL、Redis、JWT、RBAC、License、Public-Releases。
- 代码注释只在复杂逻辑、协议边界、安全校验、部署风险或兼容性处理处添加，避免解释显而易见的语句。

## 品牌与界面规则

- 默认品牌名称为 `SagittaDB`，中文品牌名为 `矢准数据`。
- 顶部导航和侧边栏 Logo 下方的默认中文副标为 `矢准数据`，不要再使用旧文案 `数据管控`。
- 登录页默认使用引文版品牌语：`SagittaDB · Aim at Data, Control with Precision`，底部版权署名为 `Lynn-Lee`。
- 如修改品牌、登录页、导航、系统配置展示或默认文案，必须同步更新 `docs/sagittadb_prd.md`、`README.md` 或其他相关文档。
- 前端所有按钮必须遵循统一按钮规划：按钮使用统一高度尺寸；常规业务按钮内容采用“图标 + 文字”形式；登录页第三方登录入口、返回图标、表格行内紧凑工具等空间受限控件可使用纯图标，但必须提供明确的 `aria-label` 和 Tooltip，悬停文案需说明实际动作。
- 按钮功能语义色规划：主操作（新建、保存、提交、执行、登录）使用品牌蓝；查看、管理、刷新使用信息蓝；编辑使用提示橙；复制、导入、导出使用工具青；取消、返回、重置、关闭使用中性灰；删除、终止、拒绝等危险操作使用危险红。后续新增按钮必须按功能归类后复用对应样式。

## 新功能完成规则

每次完成项目新的功能代码或 UI 调整后，必须完成以下收尾动作，除非用户明确要求暂停、只做局部分析或不提交：

- 每次功能完成后都要同步更新本地代码和相关文档，提交到 git 并推送远端，然后更新云 ECS 测试环境到最新源码。

1. 同步更新项目相关文档，包括但不限于 `README.md`、`docs/sagittadb_prd.md`、`docs/user_manual.md`、`docs/operations_guide.md`、`docs/public_commercial_delivery.md` 和本文件。
2. 按改动风险执行必要验证；前端改动至少执行 `npm run build`，后端或部署改动至少执行相关测试、迁移或 Docker Compose 校验。
3. 查看 `git status --short` 和 diff，确认只包含本次任务需要的代码与文档。
4. 提交代码并推送到源端 Git 远端。
5. 推送后检查 GitHub Actions 是否出现对应的 `CI` 和 `Release Version Record` 记录；如 workflow 失败或未触发，最终反馈必须说明。
6. 使用源码方式更新云 ECS 测试环境到刚推送的最新代码，并完成必要的服务重启和健康检查；不再使用商业版更新包或商业发布产物更新测试环境。

如果当前环境缺少运行时、网络、Git 权限、SSH 权限、数据库或其他外部凭据，不能假装完成；必须说明阻塞点，并列出已经完成的本地变更和验证结果。

## Git 规则

- 开始改动前先检查 `git status --short --branch`。
- 不要回滚用户已有改动；如果工作区已有无关变更，只处理当前任务相关文件。
- 不要使用 `git reset --hard`、`git checkout -- <file>`、`docker compose down -v`、`docker volume rm` 等破坏性命令，除非用户明确要求。
- 提交前查看 staged diff，确保没有误提交 `.env`、真实数据库连接串、Token、私钥、License、激活码或客户数据。
- 提交信息应简洁说明本次变化，默认使用中文或项目已有提交风格；专业术语、配置项和产品名保留英文。
- 推送失败、远端拒绝、Actions 失败或当前环境不是 Git 仓库时，必须明确说明，不能声称已提交或已推送。

## 云 ECS 测试环境规则

- 每次完成新功能代码、同步文档并推送 Git 后，必须同步更新云 ECS 服务器上的测试环境到最新代码。
- 云 ECS 测试环境必须使用源码方式更新和运行，不再使用商业版更新包、`dist-commercial/` 产物或 Public-Releases 商业部署包更新。
- 云 ECS 登录方式统一使用：

```bash
alias sagitta='ssh -i ~/.ssh/zovjudan.pem ecs-user@47.102.146.147 -p 2222'
ssh -i ~/.ssh/zovjudan.pem ecs-user@47.102.146.147 -p 2222
```

- 云 ECS 源码测试环境目录固定为：

```bash
/opt/sagittadb/source
```

- 云 ECS 测试环境直接从 GitHub 源码仓库 clone/fetch。若私有仓库需要 token，只能通过临时 `GIT_ASKPASS`、临时环境变量或一次性输入使用；不得把 token 写入 git remote、`.env`、脚本、文档或 shell profile。
- 旧商业部署测试环境已经废弃；需要重建测试环境时，可以清理旧商业 compose project、商业部署包目录和旧数据卷，再使用源码重新部署。
- 源码测试环境 Compose project 固定为：

```bash
COMPOSE_PROJECT_NAME=sagittadb-source-test
```

- 源码测试环境不得强制启用商业镜像完整性 Manifest；如果从商业部署包迁移 `.env`，必须确保测试环境中 `APP_INTEGRITY_REQUIRED=false`，避免源码镜像因缺少 `COMMERCIAL-MANIFEST.json` 启动失败。
- 因源码 Compose 文件位于 `deploy/docker-compose.yml`，Docker Compose 做变量插值时需要能在 `deploy/` 目录读取 `.env`；ECS 源码环境必须保留以下软链接，避免 PostgreSQL、Redis 等基础服务误用默认密码：

```bash
ln -sfn ../.env deploy/.env
```

- 标准源码部署命令：

```bash
COMPOSE_PROJECT_NAME=sagittadb-source-test bash deploy/update-prod.sh
```

- 更新前后应记录当前分支、提交 SHA、服务重建结果和健康检查结果。至少验证：

```bash
git rev-parse --short HEAD
sudo docker compose -f deploy/docker-compose.yml ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

- 如果 SSH 不可达、ECS Git 镜像未更新、Docker 权限不足、构建失败、迁移失败或健康检查失败，最终反馈必须说明具体阻塞点和已完成步骤。

## 常用验证命令

前端构建：

```bash
cd frontend
npm run build
```

Compose 配置校验：

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.yml config --quiet
```

后端镜像构建：

```bash
docker compose -f deploy/docker-compose.yml build backend
```

GitHub Actions 状态：

```bash
gh run list --limit 5
```
