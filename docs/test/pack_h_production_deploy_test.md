# Pack H 功能测试文档 — 生产就绪（Helm Chart、CI/CD、备份脚本）

> **测试版本：** SagittaDB v1.0-beta
> **对应计划：** Pack H — Helm Chart（K8s）、生产 Docker Compose、数据库备份、CI/CD 升级
> **测试环境：** 本地 Docker Compose + Kubernetes（可选）+ GitHub Actions
> **前置条件：** Docker Compose 环境运行正常，kubectl + Helm 已安装（K8s 测试）
> **测试账号：** admin / Admin@2024!（默认密码会触发强制改密）

---

## 测试范围

| 模块 | 覆盖内容 |
|---|---|
| 生产 Docker Compose | docker-compose.prod.yml 启动验证 |
| Helm Chart | Chart 结构、lint 验证、模板渲染 |
| 数据库备份 | 备份脚本执行、恢复脚本验证 |
| CI/CD 升级 | GHCR 镜像发布、Helm lint Job |
| Flower 监控 | Celery 任务监控面板 |

---

## 一、生产 Docker Compose 测试

### TC-H-001 生产模式启动验证

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-001 |
| **测试场景** | docker-compose.prod.yml 能正常启动 |
| **测试步骤** | 1. 确保 .env 文件已配置<br>2. 执行 `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`<br>3. 等待约 30 秒<br>4. 执行 `docker compose ps` |
| **预期结果** | 所有容器正常启动，backend 状态 healthy |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-002 生产模式后端进程数

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-002 |
| **测试场景** | 生产模式使用 4 个 uvicorn workers |
| **测试步骤** | 1. 生产模式启动后<br>2. 执行 `docker compose exec backend ps aux \| grep uvicorn` |
| **预期结果** | 显示 4 个 uvicorn worker 进程 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-003 生产模式无代码热重载挂载

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-003 |
| **测试场景** | 生产模式不挂载宿主机代码目录 |
| **测试步骤** | 1. 执行 `docker compose -f docker-compose.prod.yml config \| grep volumes -A5` |
| **预期结果** | backend 服务不再挂载 `./backend:/app`，使用镜像内置代码 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

## 二、Helm Chart 测试

### TC-H-004 Helm Chart 目录结构完整性

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-004 |
| **测试场景** | Helm Chart 包含所有必要文件 |
| **测试步骤** | 执行 `ls deploy/helm/sagittadb/templates/` |
| **预期结果** | 包含：backend-deployment、worker-deployment、beat-deployment、flower-deployment、frontend-deployment、service、ingress、hpa、configmap、secret、serviceaccount、NOTES.txt |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-005 Helm lint 默认 values 通过

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-005 |
| **测试场景** | helm lint 使用默认 values 无错误 |
| **测试步骤** | 执行 `helm lint deploy/helm/sagittadb/` |
| **预期结果** | 输出 `1 chart(s) linted, 0 chart(s) failed` |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-006 Helm lint staging values 通过

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-006 |
| **测试场景** | helm lint 使用 staging values 无错误 |
| **测试步骤** | 执行 `helm lint deploy/helm/sagittadb/ -f deploy/helm/sagittadb/values-staging.yaml` |
| **预期结果** | lint 通过，无错误 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-007 Helm lint prod values 通过

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-007 |
| **测试场景** | helm lint 使用生产 values 无错误 |
| **测试步骤** | 执行 `helm lint deploy/helm/sagittadb/ -f deploy/helm/sagittadb/values-prod.yaml` |
| **预期结果** | lint 通过，无错误 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-008 Helm template 渲染正常

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-008 |
| **测试场景** | helm template 渲染所有模板无报错 |
| **测试步骤** | 执行 `helm template sagittadb deploy/helm/sagittadb/ -f deploy/helm/sagittadb/values-prod.yaml` |
| **预期结果** | 输出所有 YAML 资源清单，无报错 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-009 Beat 副本数锁定为 1

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-009 |
| **测试场景** | Helm 渲染结果中 celery-beat deployment replicas=1 |
| **测试步骤** | 1. 执行 helm template<br>2. 在输出中找到 beat Deployment<br>3. 查看 spec.replicas |
| **预期结果** | celery-beat Deployment 的 replicas 固定为 1，不受 HPA 控制 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-010 initContainer alembic 迁移配置

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-010 |
| **测试场景** | backend Deployment 包含 alembic upgrade head initContainer |
| **测试步骤** | 1. helm template 输出<br>2. 找到 backend Deployment<br>3. 查看 initContainers |
| **预期结果** | 存在 initContainer，命令为 `alembic upgrade head` |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

## 三、数据库备份脚本测试

### TC-H-011 PostgreSQL 备份脚本执行

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-011 |
| **测试场景** | 备份脚本成功生成 .sql.gz 备份文件 |
| **测试步骤** | 1. 确保 PostgreSQL 容器正在运行<br>2. 执行 `bash deploy/backup/backup-postgres.sh`<br>3. 查看输出和生成的文件 |
| **预期结果** | 生成 `sagittadb_YYYYMMDD_HHMMSS.sql.gz` 文件，脚本输出"备份完成" |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-012 备份文件可解压验证

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-012 |
| **测试场景** | 生成的备份文件可正常解压，内容为有效 SQL |
| **测试步骤** | 1. 找到备份文件（如 `/tmp/backup/sagittadb_xxx.sql.gz`）<br>2. 执行 `gzip -t sagittadb_xxx.sql.gz`（验证完整性）<br>3. 执行 `zcat sagittadb_xxx.sql.gz \| head -20` |
| **预期结果** | gzip 检查通过，SQL 内容包含 `PostgreSQL database dump` 标识 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-013 PostgreSQL 恢复脚本执行

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-013 |
| **测试场景** | 恢复脚本能从备份文件恢复数据库 |
| **测试步骤** | 1. 创建测试恢复库：`createdb sagittadb_restore_test`<br>2. 执行 `bash deploy/backup/restore-postgres.sh /path/to/backup.sql.gz sagittadb_restore_test`<br>3. 确认交互提示后恢复 |
| **预期结果** | 恢复成功，可连接 sagittadb_restore_test 库并查看数据 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-014 备份脚本自动清理过期文件

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-014 |
| **测试场景** | 备份脚本自动清理超过保留天数的旧备份 |
| **测试步骤** | 1. 手动创建一个旧备份文件（修改时间戳）：`touch -d "8 days ago" /tmp/backup/old_backup.sql.gz`<br>2. 执行备份脚本（RETENTION_DAYS=7）<br>3. 检查旧文件是否被删除 |
| **预期结果** | 超过 7 天的旧备份文件被自动删除 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

## 四、CI/CD 升级验证

### TC-H-015 GitHub Actions Helm lint Job

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-015 |
| **测试场景** | CI 中 helm-lint Job 对三套 values 均通过 |
| **测试步骤** | 1. 访问 https://github.com/Lynn-Lee/SagittaDB/actions<br>2. 打开最近一次 CI 运行<br>3. 查看 helm-lint Job 日志 |
| **预期结果** | helm-lint Job 显示绿色，日志中三套 values 均 lint 通过 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-016 GHCR Docker 镜像发布

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-016 |
| **测试场景** | push main 分支后 Docker 镜像自动发布到 GHCR |
| **测试步骤** | 1. 查看 CI docker-publish Job 是否成功<br>2. 访问 https://github.com/Lynn-Lee/SagittaDB/pkgs/container/sagittadb |
| **预期结果** | GHCR 上存在 `ghcr.io/lynn-lee/sagittadb/backend:latest` 镜像，发布时间与最近 push 一致 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-017 Docker 镜像可正常拉取

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-017 |
| **测试场景** | 从 GHCR 拉取的镜像可正常运行 |
| **测试步骤** | 1. 执行 `docker pull ghcr.io/lynn-lee/sagittadb/backend:latest`<br>2. 执行 `docker run --rm ghcr.io/lynn-lee/sagittadb/backend:latest python -c "import app; print('OK')"` |
| **预期结果** | 镜像拉取成功，Python 导入正常 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

## 五、Flower 监控面板测试

### TC-H-018 Flower 面板显示 Worker 状态

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-018 |
| **测试场景** | Flower 面板正常显示 Celery Worker 信息 |
| **测试步骤** | 1. 访问 http://localhost:5555<br>2. 点击 Workers 页签 |
| **预期结果** | 显示在线 Worker，监听队列：default、execute、notify、archive、monitor |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

### TC-H-019 Flower 面板任务历史记录

| 项目 | 内容 |
|---|---|
| **用例编号** | TC-H-019 |
| **测试场景** | 执行工单后 Flower 中显示任务记录 |
| **测试步骤** | 1. 执行一个工单<br>2. 访问 Flower → Tasks 页签 |
| **预期结果** | 显示任务执行记录，包含任务 ID、状态（SUCCESS/FAILURE）、执行时间 |
| **实际结果** | |
| **状态** | ⬜ 未测试 |

---

## 测试汇总

| 总用例数 | 通过 | 失败 | 未测试 |
|---|---|---|---|
| 19 | 0 | 0 | 19 |

**测试人员：**
**测试日期：**
**备注：** K8s 实际部署测试（TC-H-008 等）需要 kubectl 集群环境，可选执行
