# Sagitta Control 专属 Agent 工作规则

本文件是 Sagitta Control 项目专属的 Codex / Agent 工作规则。本文记录后续研发、交付和测试环境更新时必须遵守的协作约定。每次开始编码、调试、重构、文档或部署任务前，应先阅读并遵守本文；如用户明确给出更具体要求，以用户当次要求为准。

根目录 `AGENT.md` 是本项目唯一有效规则文件；如本地出现 `AGENT_*CaseConflict.md` 等同步冲突副本，一律不作为规则来源，并以当前 `AGENT.md` 为准。

## 项目定位

- Sagitta Control 是面向企业数据库安全管控场景的统一平台，覆盖数据库实例管理、SQL 工单、在线查询、数据字典、权限治理、数据脱敏、SQL 洞察、运行诊断、数据归档、审计和企业通知。
- 后端目录为 `backend/`，技术栈为 Python 3.12、FastAPI、SQLAlchemy 2 async、Alembic、Celery、Redis、PostgreSQL。
- 前端目录为 `frontend/`，技术栈为 React 18、Vite、TypeScript、Ant Design 5、TanStack Query、Zustand。
- 部署目录为 `deploy/`，文档目录为 `docs/`。
- 商业发布机制参考 DataFusionX：`main` 只做源码 CI 和版本记录，`release/**` 生成 RC 候选商业包，正式 `vX.Y.Z` tag 或显式手动发布才同步 `Lynn-Lee/Sagitta-Deploy` 公开交付仓库。
- 商业部署版、商业交付包和 `Lynn-Lee/Sagitta-Deploy` 不随每次功能或 UI 调整自动更新；只有用户明确下达商业版更新、商业发布或同步公开发布仓库指令时才执行。

## 语言与文档规则

- 与用户沟通默认使用中文。
- Web 页面默认使用中文。
- 项目文档默认使用中文。
- 页面、菜单、按钮、表单、功能释义、提示说明、空状态、错误提示和确认弹窗等可见文案默认使用中文；仅专业术语、产品名、协议名、配置键、代码标识和第三方服务名称保留英文。
- 日期选择器和日期范围选择器按全站中文化最终口径处理：月份、星期、`Today`、`Select date`、`Start date`、`End date` 等 Ant Design 默认文案必须显示为简体中文，例如 `今天`、`请选择日期`、`开始日期`、`结束日期`；日期格式、配置键和 API 字段名可保留英文或 ISO 格式。
- 页面、表格、详情、抽屉、弹窗、通知和运维面板中的日期时间类数据统一显示为 `YYYY-MM-DD HH:mm:ss`，例如 `2026-06-02 22:32:33`；纯日期业务字段如授权有效期可保留 `YYYY-MM-DD`，但不得使用浏览器本地化的斜杠日期、上下午或仅月日时间格式。
- 登录页英文 slogan、Logo 或品牌素材自带英文、登录入口接入方式名称、分页页码和分页翻页符号不按中文化硬性要求处理，允许保持英文、数字或图标形式。
- 代码注释优先使用中文；类名、函数名、字段名、枚举值、配置键、SQL 关键字和第三方 API 名称保持英文。
- 专业术语保留英文，例如 FastAPI、Docker Compose、PostgreSQL、Redis、JWT、RBAC、License、GHCR、GitHub Releases。
- 代码注释只在复杂逻辑、协议边界、安全校验、部署风险或兼容性处理处添加，避免解释显而易见的语句。

## 品牌与界面规则

- 默认对外品牌名称为 `Sagitta Control`，中文产品名为 `矢准数据库安全管控平台`，软著备案推荐名称为 `矢准数据库安全管控平台软件`。
- 顶部导航品牌区默认只展示 Logo 图标和英文名称 `Sagitta Control`，不再显示中文副标；不要再使用旧中文副标。
- 登录页 Logo 下方展示中文简称 `矢准管控`，视觉文案统一为 `矢 准 管 控`，默认使用精简品牌语：`Aim at Data, Govern with Precision`，底部版权署名为 `Lynn-Lee`，并链接到 `https://github.com/Lynn-Lee`。
- 登录页底部版本描述统一为 `Sagitta Control v2.3.0 · Database Security Control Platform · Full Engine Compatibility, End-to-End Observability`。
- 如修改品牌、登录页、导航、系统配置展示或默认文案，必须同步更新 `docs/sagitta_control_prd.md`、`README.md` 或其他相关文档。
- 页面、菜单、按钮、表单控件、弹窗和抽屉等前端界面必须保持统一字体和字号体系，优先复用 Ant Design 主题 Token 或项目已有全局样式，不得在局部页面随意新增不一致的字体、字号或行高。
- 前端所有按钮必须遵循统一按钮规划：按钮高度保持统一；按钮宽度根据图标和文字内容自适应，不固定成同一长度；按钮内容统一采用“图标 + 文字”形式，图标需按功能选择最合适的语义图标；按钮文字颜色、图标颜色和背景色需与功能语义及主题色协调。
- 登录入口接入方式的图标按钮、分页页码按钮和分页翻页按钮不按“图标 + 文字”和“宽度按图标文字自适应”硬性要求处理，可继续使用纯图标、数字页码、等宽分页控件或 Ant Design 默认分页按钮样式，但仍需保证可访问性和交互状态清晰。
- 按钮功能语义色规划：主操作（新建、保存、提交、执行、登录）使用品牌蓝；查看、管理、刷新使用信息蓝；编辑使用提示橙；复制、导入、导出使用工具青；取消、返回、重置、关闭使用中性灰；删除、终止、拒绝等危险操作使用危险红。后续新增按钮必须按功能归类后复用对应样式，并优先使用 lucide-react 或 Ant Design Icons 中的现成图标。
- 前端所有表单控件必须保持统一高度体系，包括输入框、选择器、日期选择器、数字输入、上传入口、搜索框和筛选项；同一表单区域内不得混用不同高度的控件，确需紧凑模式时必须在整个区域内统一使用。

## 新功能完成规则

每次完成项目新的功能代码或 UI 调整后，必须完成以下收尾动作，除非用户明确要求暂停、只做局部分析或不提交：

- 每次功能完成后都要同步更新本地代码和相关文档，提交到 git 并推送 GitHub 主远端和 Gitee 国内镜像远端，然后更新云 ECS 测试环境到最新源码。
- 上述默认收尾只针对源码仓库和云 ECS 源码测试环境；商业部署版、商业部署包、商业镜像和 `Lynn-Lee/Sagitta-Deploy` 后续仅按用户明确指令更新。

1. 同步更新项目相关文档，包括但不限于 `README.md`、`docs/sagitta_control_prd.md`、`docs/user_manual.md`、`docs/operations_guide.md`、`docs/public_commercial_delivery.md` 和本文件。
2. 按改动风险执行必要验证；前端改动至少执行 `npm run build`，后端或部署改动至少执行相关测试、迁移或 Docker Compose 校验。
3. 查看 `git status --short` 和 diff，确认只包含本次任务需要的代码与文档。
4. 提交代码并推送到 GitHub 主远端 `origin` 和 Gitee 国内镜像远端 `gitee`。
5. 推送后检查 GitHub Actions 是否出现对应的 `CI` 和 `Release Version Record` 记录；如 workflow 失败或未触发，最终反馈必须说明。
6. 使用源码方式更新云 ECS 测试环境到刚推送的最新代码；服务器源码拉取优先使用 Gitee 国内镜像，避免 GitHub 直连慢或超时。完成必要的服务重启和健康检查；不再使用商业版更新包或商业发布产物更新测试环境。

如果当前环境缺少运行时、网络、Git 权限、SSH 权限、数据库或其他外部凭据，不能假装完成；必须说明阻塞点，并列出已经完成的本地变更和验证结果。

## Git 规则

- 开始改动前先检查 `git status --short --branch`。
- 标准远端约定：`origin` 指向 GitHub 主仓库 `https://github.com/Lynn-Lee/Sagitta-Control.git`，用于主源码记录和 GitHub Actions；`gitee` 指向 Gitee 国内镜像仓库 `git@gitee.com:lynn-lee/sagitta-control.git`，用于国内网络环境下的源码拉取和部署更新。
- 不要回滚用户已有改动；如果工作区已有无关变更，只处理当前任务相关文件。
- 不要使用 `git reset --hard`、`git checkout -- <file>`、`docker compose down -v`、`docker volume rm` 等破坏性命令，除非用户明确要求。
- 提交前查看 staged diff，确保没有误提交 `.env`、真实数据库连接串、Token、私钥、License、激活码或客户数据。
- 提交信息应简洁说明本次变化，默认使用中文或项目已有提交风格；专业术语、配置项和产品名保留英文。
- 功能开发完成后的默认推送流程为先推送 `origin main`，再推送 `gitee main`；如当前分支不是 `main`，按当次任务实际分支同步推送对应远端分支。
- Gitee SSH 访问统一使用本机或服务器上的 Gitee 账号级 SSH key；本机默认 key 为 `~/.ssh/lynn-lee-gitee`，通过 `~/.ssh/config` 的 `Host gitee.com` 统一绑定。
- 推送失败、远端拒绝、Gitee 镜像未同步、Actions 失败或当前环境不是 Git 仓库时，必须明确说明，不能声称已提交、已推送或已同步镜像。

## 云 ECS 测试环境规则

- 每次完成新功能代码、同步文档并推送 GitHub 与 Gitee 后，必须同步更新云 ECS 服务器上的测试环境到最新代码。
- 云 ECS 测试环境必须使用源码方式更新和运行，不再使用商业版更新包、`dist-commercial/` 产物或公开交付仓库商业部署包更新。
- 云 ECS 登录方式统一使用：

```bash
alias sagitta='ssh -i ~/.ssh/zovjudan.pem ecs-user@47.102.146.147 -p 2222'
sagitta
ssh -i ~/.ssh/zovjudan.pem ecs-user@47.102.146.147 -p 2222
```

- 云 ECS 源码测试环境目录固定为：

```bash
/opt/sagitta-control/source
```

- 云 ECS 测试环境直接从 Gitee 国内镜像源码仓库 clone/fetch；GitHub 保留为主源码和 Actions 远端，不作为服务器源码更新的优先拉取源。若私有仓库需要 token，只能通过临时 `GIT_ASKPASS`、临时环境变量或一次性输入使用；不得把 token 写入 git remote、`.env`、脚本、文档或 shell profile。
- 云 ECS 和生产内网服务器使用源码方式更新时，推荐 remote 为：

```bash
git@gitee.com:lynn-lee/sagitta-control.git
```

并在服务器上单独配置 Gitee SSH 公钥，避免复用个人开发机私钥。
- 旧商业部署测试环境已经废弃；需要重建测试环境时，可以清理旧商业 compose project、商业部署包目录和旧数据卷，再使用源码重新部署。
- 源码测试环境 Compose project 固定为：

```bash
COMPOSE_PROJECT_NAME=sagitta-control-source-test
```

- 源码测试环境不得强制启用商业镜像完整性 Manifest；如果从商业部署包迁移 `.env`，必须确保测试环境中 `APP_INTEGRITY_REQUIRED=false`，避免源码镜像因缺少 `COMMERCIAL-MANIFEST.json` 启动失败。
- 因源码 Compose 文件位于 `deploy/docker-compose.yml`，Docker Compose 做变量插值时需要能在 `deploy/` 目录读取 `.env`；ECS 源码环境必须保留以下软链接，避免 PostgreSQL、Redis 等基础服务误用默认密码：

```bash
ln -sfn ../.env deploy/.env
```

- 标准源码部署命令：

```bash
COMPOSE_PROJECT_NAME=sagitta-control-source-test bash deploy/update-prod.sh
```

- `deploy/update-prod.sh` 会根据当前版本到目标版本的变更路径自动判断是否执行 PostgreSQL 备份、Alembic 迁移、镜像构建和服务重建；只有 Alembic、模型、数据库连接核心文件或 Compose/Helm 部署配置变化时才默认 `pg_dump` 和迁移。`backend/` 变更只构建一次后端共享镜像并重建 backend、celery_worker、celery_beat、flower；`frontend/` 变更只构建并重建 frontend；普通文档、CI 或验证报告变更应自动跳过镜像构建和服务重建。如确需全量更新可传 `--full`，如确需留档备份可传 `--force-backup`，如已人工确认可传 `--skip-backup`。
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
