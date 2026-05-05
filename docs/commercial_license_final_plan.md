# SagittaDB 商业 License 最终方案

本文档定义 License 平台成为完整商业系统所需的收尾工作。目标不是只完成产品侧激活闭环，而是形成可运营、可审计、可恢复的授权体系。

## 目标

SagittaDB 客户应接收带版本号的产品镜像，并获得在线激活码或离线签名 License。内部运营人员应能创建客户、签发和续期 License、调整限额、挂起或吊销访问、审计所有操作，并在不丢失客户数据的前提下恢复 License 服务。

## P0 范围

1. 产品侧部署绑定
   - 生成并展示部署指纹。
   - 在线激活和刷新时发送部署指纹。
   - 拒绝包含其他部署指纹的签名 License。
   - 将部署指纹写入 `license_record`，用于支持和审计。

2. 生产 License Server
   - 在 PostgreSQL 中维护客户、激活码、License、状态变更、续期和审计日志。
   - 若未预先配置指纹，激活码首次使用时绑定当前部署指纹。
   - 拒绝来自其他部署指纹的激活或刷新请求。
   - 支持 `active`、`suspended`、`revoked` 状态流转。
   - 面向客户部署暴露 `/api/v1/licenses/activate` 和 `/api/v1/licenses/refresh`。

3. 运营管理端
   - 提供私有 Web 管理端，支持客户、激活、续期、限额和状态操作。
   - 要求管理端认证，并记录操作者、动作、对象、旧值、新值、IP 和时间。
   - 隐藏管理路径，签名私钥只保存在 License Server 上。

4. 客户交付验证
   - 验证在线激活、刷新、续期、挂起、吊销和恢复。
   - 验证离线 License 导入、离线部署指纹不匹配拒绝、过期 License 阻断。
   - 验证客户部署包固定版本镜像，且不使用 `latest`。

## P1 范围（已取消）

以下 License 后续增强不再进入当前产品路线，除非后续重新立项：

- 版本与套餐模板。
- 用量可见性。
- License Server 告警增强。
- 客户遗失部署 ID 的专项支持流程。

## P2 范围（已取消）

以下 License 长线能力不再进入当前产品路线，除非后续重新立项：

- 激活生命周期迁移、解绑和重新绑定。
- 同一客户多个部署。
- 商业报表和 License 台账导出。

## 验收清单

- 可以创建新客户并签发激活码。
- 客户首次激活会绑定部署指纹。
- 同一激活码不能激活其他部署。
- active 激活码刷新后返回续期后的签名 License。
- suspended 或 revoked 激活码刷新后会阻断受保护的 SagittaDB API。
- 指纹错误的离线签名 License 会在本地被拒绝。
- 过期 License 会阻断受保护的 SagittaDB API。
- License Server 私钥不会出现在客户镜像、日志或部署包中。
- 所有运营写操作都会进入 License Server 审计日志。
- 客户发布包包含固定版本镜像、`.env.example`、`upgrade.sh` 和 `verify-license.sh`。

## 当前收口状态

产品侧 License v2、部署指纹绑定、在线激活/刷新、本地验签和客户侧页面已进入 GA 收口状态。当前 License 剩余任务仅保留生产验证、基础备份恢复和运营审计确认；其他 License 后续增强不再规划。

最新剩余计划任务见 `docs/remaining_plan.md`。
