# SagittaDB License v2 运营流程

本文档说明 License v2 的在线授权运营闭环。对无法联网的客户网络，仍支持离线签名 License 导入。

## 产品侧配置

在客户部署环境中配置以下环境变量：

```bash
LICENSE_PUBLIC_KEY=<your Ed25519 public key>
LICENSE_CUSTOMER_ID=<customer id>
LICENSE_SERVER_URL=https://sagitta.loveai.asia
LICENSE_SERVER_TOKEN=<optional bearer token>
LICENSE_AUTO_REFRESH_ENABLED=true
LICENSE_RENEWAL_NOTIFY_DAYS=30,7
LICENSE_DEPLOYMENT_ID=<stable random deployment id>
```

当 `LICENSE_SERVER_URL` 为空时，离线导入仍可使用；在线激活和在线刷新会返回明确的配置错误。

`LICENSE_DEPLOYMENT_ID` 应在每个客户部署中只生成一次，并在后续升级中保持稳定。SagittaDB 会根据客户 ID 和该部署 ID 派生部署指纹；在线激活会把该指纹发送给 License Server。包含 `deployment_fingerprint` 的签名 License 如果被导入到其他部署，会被本地验签流程拒绝。

## 内部授权工具

生成密钥：

```bash
python3 tools/license_authority.py --generate-keypair
```

创建激活码：

```bash
export SAGITTADB_LICENSE_PRIVATE_KEY=<private key>
python3 tools/license_authority.py create-activation \
  --db /secure/license-authority.json \
  --customer-id acme \
  --company-name "Acme Corp" \
  --days 365 \
  --max-instances 20 \
  --max-users 200 \
  --deployment-fingerprint <fingerprint from the SagittaDB license page>
```

查看授权台账：

```bash
python3 tools/license_authority.py list --db /secure/license-authority.json
python3 tools/license_authority.py audit --db /secure/license-authority.json --limit 50
```

续期或调整限额：

```bash
python3 tools/license_authority.py renew \
  --db /secure/license-authority.json \
  --activation-code <code> \
  --days 365 \
  --max-instances 50 \
  --max-users 500
```

正式 License Server 使用私有仓库 `https://github.com/Lynn-Lee/SagittaDB-License-Server`，部署见 `docs/license_server_deploy.md`。下方辅助 API 仅保留给本地开发和迁移测试使用。

启动内部辅助 API：

```bash
export SAGITTADB_LICENSE_PRIVATE_KEY=<private key>
export SAGITTADB_LICENSE_AUTHORITY_TOKEN=<shared internal token>
python3 tools/license_authority.py serve --db /secure/license-authority.json --host 0.0.0.0 --port 8011
```

挂起或吊销激活码：

```bash
python3 tools/license_authority.py set-status \
  --db /secure/license-authority.json \
  --activation-code <code> \
  --status revoked
```

为离线客户导出最近一次签发的签名 License：

```bash
python3 tools/license_authority.py export-license \
  --db /secure/license-authority.json \
  --activation-code <code> \
  --out acme-license.json
```

## 客户流程

- 客户在「系统管理 -> License」页面输入激活码。
- SagittaDB 调用 `/api/v1/licenses/activate`，携带当前部署指纹，收到签名 License 后使用内置公钥在本地验签。
- 刷新授权时调用 `/api/v1/licenses/refresh`，携带同一部署指纹。如果授权服务返回 `revoked` 或 `suspended`，SagittaDB 会把本地 License 标记为无效。
- 当试用或付费 License 剩余 30 天或更少时，SagittaDB 显示续期提醒；剩余 7 天或更少时显示高优先级提醒。
- 离线 License 文件继续使用 `tools/license_issue.py` 生成；传入 `--deployment-fingerprint` 可将离线 License 绑定到单个客户部署。

## 内部生产验证

1. 在 VPS 上部署授权服务，并配置私钥和管理 Token。
2. 在一个内部类生产 SagittaDB 实例中配置 `LICENSE_PUBLIC_KEY`、`LICENSE_SERVER_URL`、`LICENSE_SERVER_TOKEN`、`LICENSE_CUSTOMER_ID` 和稳定的 `LICENSE_DEPLOYMENT_ID`。
3. 创建激活码，并从 SagittaDB License 页面完成在线激活。
4. 从 License 页面执行刷新，确认 `last_online_check_at` 已更新。
5. 将激活码状态改为 `suspended`，再次刷新，确认 SagittaDB 将 License 标记为无效并阻断核心 API。
6. 将激活码恢复为 `active` 或创建新激活码，再次激活，确认核心 API 恢复。

## 最新剩余计划任务

统一任务清单见 `docs/remaining_plan.md`。License 相关剩余任务仅保留当前交付闭环的生产验证；套餐模板、用量可见性、监控告警增强、部署迁移生命周期和商业报表不再作为后续研发任务。
