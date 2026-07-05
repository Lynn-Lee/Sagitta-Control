# SagittaDB / Sagitta Control 优化实施手册

> 基于对本仓库的全方位评估（产品/架构/安全/工程质量）整理。每一项都给出：问题定位（文件:行号）、修改前后代码、验证方式、验收标准。按 P0→P3 顺序实施，P0 建议在下一次发版前完成。
> 本手册为一次性工作文档，不建议纳入 `docs/` 正式文档目录（依据 README.md:94「源码仓库只保留长期维护文档和客户交付模板；历史计划、一次性验证报告、阶段性测试记录不再作为正式文档入口维护」的约定），实施过程中可自行拆成 Issue/任务卡。
>
> **v2 修订说明**：经第三方（Codex）独立复核并逐条核实代码后，修正了 v1 的 3 处实质性错误（P0-3 范围误判 instance.py 也缺 L2 校验、P1-1 低估了 engine 泄露的实际模式、P1-2 编造了不存在的任务名且误述 Celery 重试机制）和 3 处表述不准确（P2-1 测试文件其实已存在、P3-2 截图张数、P3-3 preflight 脚本其实已有部分检查）。
>
> **v3 修订说明**：v2 又经过一轮独立复核，发现 v2 的 P0-3 补丁本身有懒加载风险且权限域用错、P0-1 的参数化改法与真实函数结构不符、P1-2 的验收命令验证不了重试是否生效、文档规则引用来源写错。本次已逐条用代码核实并修正，v2 中标"**已核实**"的内容如与本次冲突，以本次（v3）为准。

---

## 阶段总览

| 阶段 | 主题 | 项数 | 建议工期 | 是否阻断发版 |
|---|---|---|---|---|
| P0 | 安全阻断项 | 4 | 1-2 天 | 是 |
| P1 | 工程健壮性 | 4 | 3-5 天 | 建议阻断 |
| P2 | 测试与类型债务 | 2 | 1-2 周（持续） | 否，但需排期 |
| P3 | 仓库与交付卫生 | 3 | 半天 | 否 |

---

## 阶段 P0：安全阻断项

### P0-1｜MySQL/StarRocks 标识符转义逻辑错误（SQL 注入）

**问题**：`escape_string()` 用反斜杠转义反引号，但 MySQL 反引号标识符里反斜杠不是转义字符，正确做法是把反引号加倍。当前实现会被拼接进 f-string SQL，理论上可造成标识符级注入。

**文件**：[backend/app/engines/mysql.py:97-99](../backend/app/engines/mysql.py)（`StarRocksEngine`、`TidbEngine` 继承自 `MysqlEngine`，会一并修复）

```python
# 修改前
def escape_string(self, value: str) -> str:
    """简单转义，仅用于标识符（库名、表名）。变量值请用参数化查询。"""
    return value.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'")

# 修改后
def escape_string(self, value: str) -> str:
    """仅用于反引号标识符（库名、表名）转义：双写反引号。变量值一律走参数化查询。"""
    return value.replace("`", "``")
```

同时检查调用点是否还依赖旧的单引号转义行为：

```bash
grep -n "escape_string" backend/app/engines/mysql.py backend/app/engines/starrocks.py backend/app/engines/tidb.py
```
- [mysql.py:673](../backend/app/engines/mysql.py)（`command_filter = f" AND p.COMMAND = '{self.escape_string(command_type)}'"`）—— 这一处是**字符串字面量**场景（用在单引号内），不是标识符场景，修复后 `escape_string` 不再转义单引号会破坏这里。

  **v3 修正（原 v2 示例代码结构不对）**：这行代码实际在 `_processlist_sql()`（[mysql.py:624](../backend/app/engines/mysql.py)，`tidb.py:143` 有独立的同名重写版本）内部，这个方法当前签名是 `def _processlist_sql(self, *, command_type=..., ...) -> str`，**只负责拼出 SQL 字符串返回**，不直接执行查询；真正调用 `self.query()` 的地方在调用方 `processlist()`（[mysql.py:610](../backend/app/engines/mysql.py)，循环调用 3 次；`tidb.py` 在 [:109/:118/:128](../backend/app/engines/tidb.py) 调用 3 次）。v2 写的"在同一行里 build sql 后直接 `self.query(..., parameters=...)`"是编造的调用形态，和真实的"构建函数只返回字符串，另一个函数负责执行"结构对不上，必须同时改函数签名（返回 `(sql, params)` 元组）和所有调用点。

  ```python
  # 修改前（mysql.py:624-673，节选）
  def _processlist_sql(
      self, *, command_type: str = "Query",
      include_performance_schema: bool = True, include_innodb_trx: bool = True,
  ) -> str:
      ...
      command_filter = ""
      if command_type and command_type != "ALL":
          command_filter = f" AND p.COMMAND = '{self.escape_string(command_type)}'"
      return f"""
          SELECT ...
          WHERE 1 = 1
          {command_filter}
      """

  # 调用方（mysql.py:595-621，节选）
  async def processlist(self, command_type: str = "Query", **kwargs: Any) -> ResultSet:
      ...
      for label, include_performance_schema, include_innodb_trx in attempts:
          sql = self._processlist_sql(
              command_type=command_type,
              include_performance_schema=include_performance_schema,
              include_innodb_trx=include_innodb_trx,
          )
          rs = await self.query(db_name="", sql=sql, limit_num=0)
          ...

  # 修改后：_processlist_sql 改为返回 (sql, params) 元组，调用方同步改为传 parameters
  def _processlist_sql(
      self, *, command_type: str = "Query",
      include_performance_schema: bool = True, include_innodb_trx: bool = True,
  ) -> tuple[str, dict[str, Any]]:
      ...
      command_filter = ""
      params: dict[str, Any] = {}
      if command_type and command_type != "ALL":
          command_filter = " AND p.COMMAND = %(command_type)s"
          params["command_type"] = command_type
      sql = f"""
          SELECT ...
          WHERE 1 = 1
          {command_filter}
      """
      return sql, params

  async def processlist(self, command_type: str = "Query", **kwargs: Any) -> ResultSet:
      ...
      for label, include_performance_schema, include_innodb_trx in attempts:
          sql, params = self._processlist_sql(
              command_type=command_type,
              include_performance_schema=include_performance_schema,
              include_innodb_trx=include_innodb_trx,
          )
          rs = await self.query(db_name="", sql=sql, parameters=params, limit_num=0)
          ...
  ```

  `self.query()` 已经在别处（如 `get_all_columns_by_tb`）支持 `parameters={"db": ..., "tb": ...}` 配合 `%(db)s` 占位符的用法，这里是同一种调用约定，不需要改 `query()` 本身。

- [tidb.py:143-197 附近](../backend/app/engines/tidb.py)（`command_filter = f" AND COMMAND = '{self.escape_string(command_type)}'"`）是 `TidbEngine` 自己重写的同名方法（不是继承 `MysqlEngine` 的），结构与上面完全一致，按同样方式改：签名改回 `tuple[str, dict[str, Any]]`，`processlist()` 里 3 处调用点（[tidb.py:109/118/128](../backend/app/engines/tidb.py)）都要同步解包 `sql, params` 并传给 `self.query(..., parameters=params, ...)`。

**验证**：
1. 单测：新增 `backend/tests/unit/test_mysql_engine.py` 用例，输入 `db_name = "a`b"`（含反引号），断言 `escape_string` 输出 `` a``b ``，且 `get_all_tables("a`b")` 生成的 SQL 不会被截断（可 mock 连接后断言拼出的 SQL 字符串）。
2. 回归 `command_filter` 相关的会话/进程列表接口不因去掉单引号转义而报错。

**验收标准**：`grep -rn "escape_string" backend/app/engines/*.py` 之后，标识符场景只做双写反引号，字符串字面量场景全部走参数化，无遗留混用。

**落地状态（2026-07-04）**：已完成。`MysqlEngine.escape_string()` 已改为仅双写反引号，`MysqlEngine.processlist()` 与 `TidbEngine.processlist()` 的 `command_type` 过滤已改为 `%(command_type)s` 参数化传参。新增/更新单测覆盖反引号标识符、单引号非标识符转义责任、`` get_all_tables("a`b") `` SQL 生成，以及 MySQL/TiDB processlist 注入向量不进入 SQL 字符串。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_mysql_engine.py -q`（26 passed，保留默认 SECRET_KEY warning）。

---

### P0-2｜ClickHouse `describe_table` 完全没有转义（比 P0-1 更直接）

**文件**：[backend/app/engines/clickhouse.py:94-100](../backend/app/engines/clickhouse.py)（`describe_table` 定义），[clickhouse.py:50-51](../backend/app/engines/clickhouse.py)（既有 `escape_string`）

> **已核实**：`clickhouse.py:50-51` 现有的 `escape_string` 是 `value.replace("'", "\\'")`，专门用于**字符串字面量**场景（转义单引号），和标识符转义（反引号加倍）完全是两回事，**不能直接复用**。必须新增一个专门给标识符用的转义方法，不要和现有的 `escape_string` 混在一起（避免同名不同义）。

```python
# 修改前（clickhouse.py:94-100）
async def describe_table(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
    rs = ResultSet()
    try:
        r = self._client(db_name).query(f"DESCRIBE TABLE `{db_name}`.`{tb_name}`")
        rs.column_list = list(r.column_names)
        rs.rows = list(r.result_rows)
    except Exception as e:
        rs.error = str(e)
    return rs

# 修改后：新增标识符专用转义方法，并在 describe_table 中使用
def _escape_identifier(self, value: str) -> str:
    """仅用于反引号标识符（库名、表名）转义：双写反引号，与字符串字面量转义 escape_string 区分开。"""
    return value.replace("`", "``")

async def describe_table(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
    rs = ResultSet()
    try:
        db_safe = self._escape_identifier(db_name)
        tb_safe = self._escape_identifier(tb_name)
        r = self._client(db_name).query(f"DESCRIBE TABLE `{db_safe}`.`{tb_safe}`")
        rs.column_list = list(r.column_names)
        rs.rows = list(r.result_rows)
    except Exception as e:
        rs.error = str(e)
    return rs
```

**验证**：同 P0-1，补充针对 ClickHouse 引擎的单测，额外验证 `escape_string`（字符串字面量转义）和 `_escape_identifier`（标识符转义）没有被误用/互换。

**验收标准**：全仓库搜索 `f"DESCRIBE\|f"SHOW\|f"CREATE TABLE` 等标识符拼接模式，确认每一处要么走参数化查询，要么调用了本引擎的标识符专用转义方法（例如 `_escape_identifier`），不要误用字符串字面量转义方法 `escape_string`。建议执行一次全局排查：
```bash
grep -rn 'f"[A-Z ]*`{' backend/app/engines/*.py
```
确认清单里的每一行都已处理。

**落地状态（2026-07-04）**：已完成。`ClickHouseEngine.describe_table()` 已新增并使用 `_escape_identifier()` 双写反引号，保留 `escape_string()` 只处理字符串字面量单引号转义。新增单测覆盖 `DESCRIBE TABLE` 库名/表名反引号注入向量，并确认两类转义职责没有混用。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_clickhouse_engine.py -q`（4 passed，保留默认 SECRET_KEY warning）。全局排查 `rg -n 'f"[^\"]*`\\{' backend/app/engines -g '*.py'` 后，ClickHouse 未再直接拼接未转义反引号标识符；剩余命中为 MySQL/StarRocks 已走各自标识符转义方法，以及 OpenSearch 的 index quoting helper。

---

### P0-3｜观测诊断接口缺少资源组（L2）校验（范围已修正：仅 diagnostic.py，instance.py 不受影响）

> **修正说明**：初版手册误判 `instance.py` 的数据字典入口也缺少资源组校验，经复核为误判——[instance.py:84-95](../backend/app/routers/instance.py) 的 `_ensure_instance_access` 已经实现了正确的资源组交集校验（`user_rg_ids & instance_rg_ids`），[instance.py:21-38](../backend/app/routers/instance.py) 的 `_ensure_data_dict_access` 也确实调用了它，加上 `QueryPrivService.check_data_dict_access` 做 L3 授权校验，L1/L2/L3 三层在 instance.py 侧是完整的。**缺口只在 `diagnostic.py`**。这也意味着不需要新建 `GovernanceScopeService.observability` 域，直接照抄 `instance.py` 里已经跑通的 `_ensure_instance_access` 模式即可，成本更低、和现有代码风格更一致。

**问题**：[backend/app/routers/diagnostic.py:32-37](../backend/app/routers/diagnostic.py) 的 `_get_instance` 只查实例是否存在/启用，不检查请求者的资源组是否覆盖该实例。`kill_session`（[:253](../backend/app/routers/diagnostic.py)）等接口只做了权限码校验（L1"能不能做"），持有 `observability_session_kill` 权限码的资源组 DBA 理论上可以对其他资源组的实例执行 Kill 会话等操作。

**文件**：[backend/app/routers/diagnostic.py:1-37](../backend/app/routers/diagnostic.py)

> **v3 修正（原 v2 补丁有两个实质错误）**：
> 1. `instance.py:84-95` 的 `_ensure_instance_access` 内部调用的是 `InstanceService.get_by_id()`（[instance.py:480](../backend/app/services/instance.py)），其底层 `_load_instance` 对 `resource_groups` 做了 `selectinload` 预加载（[instance.py:413-415](../backend/app/services/instance.py)）。v2 补丁里裸写 `select(Instance).where(...)` 后直接访问 `inst.resource_groups`，没有预加载，在 async SQLAlchemy 下访问未加载的 lazy 关系属性会触发 `MissingGreenlet` 报错，必须显式 `selectinload`。
> 2. diagnostic.py 属于"观测/诊断"域，同级文件 `monitor.py`/`slowlog.py`/`monitor_alerts.py` 的全局豁免权限码统一是 `observability_instance_all`（例如 [monitor.py:76](../backend/app/services/monitor.py)、[slowlog.py:377](../backend/app/services/slowlog.py)），`role.py` 里 `dba` 角色也是把 `query_all_instances`（查询域）和 `observability_instance_all`（观测域）分开定义的两个权限码。v2 错误地抄了 query 域的 `query_all_instances`，域用错了，改为 `observability_instance_all`。

```python
# 修改前（diagnostic.py:32-37）
async def _get_instance(db: AsyncSession, instance_id: int) -> Instance:
    result = await db.execute(select(Instance).where(Instance.id == instance_id, Instance.is_active))
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(404, f"实例 ID={instance_id} 不存在")
    return inst

# 修改后：预加载 resource_groups，避免懒加载报错；全局豁免改用观测域权限码
from sqlalchemy.orm import selectinload

async def _get_instance(db: AsyncSession, user: dict, instance_id: int) -> Instance:
    result = await db.execute(
        select(Instance)
        .options(selectinload(Instance.resource_groups))
        .where(Instance.id == instance_id, Instance.is_active)
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(404, f"实例 ID={instance_id} 不存在")
    if user.get("is_superuser") or "observability_instance_all" in user.get("permissions", []):
        return inst
    user_rg_ids = set(user.get("resource_groups", []))
    instance_rg_ids = {rg.id for rg in inst.resource_groups}
    if not (user_rg_ids & instance_rg_ids):
        raise HTTPException(403, "实例不在你的资源组内")
    return inst
```

> 没有直接调用 `InstanceService.get_by_id()` 复用，是因为它不过滤 `is_active`，而 diagnostic.py 原有行为是对已停用实例返回 404——如果直接换成 `get_by_id()` 会静默改变这个行为。所以这里保留原有的 `select(Instance).where(..., Instance.is_active)` 查询，只额外加 `selectinload`，是改动面最小、且不改变既有行为的写法。

需要同步更新该文件里全部 `_get_instance(db, instance_id)` 调用点（[diagnostic.py:70](../backend/app/routers/diagnostic.py)、[:167](../backend/app/routers/diagnostic.py)、[:197](../backend/app/routers/diagnostic.py)、[:232](../backend/app/routers/diagnostic.py)、[:274](../backend/app/routers/diagnostic.py) 等），改为 `_get_instance(db, user, instance_id)`。由于这些路由函数都已经通过 `Depends(current_user)` 注入了 `user`，改造成本很低，纯签名传参改动。

**验证**：
1. 集成测试：构造一个只属于资源组 A 的 `dba_group` 用户，尝试对资源组 B 的实例调用 `kill_session`、会话/SQL 诊断类接口，断言返回 403。
2. 回归 superadmin/持有 `observability_instance_all` 权限码的用户（如 `dba` 角色）仍可正常访问全部实例。
3. 回归 `instance.py` 数据字典相关接口行为不变（本次未改动该文件）。

**验收标准**：`backend/tests/integration/` 下新增至少 2 个用例覆盖"跨资源组访问被拒绝"和"全局权限用户不受影响"。

**落地状态（2026-07-04）**：已完成。`diagnostic.py` 的 `_get_instance()` 已改为预加载 `Instance.resource_groups` 并执行观测域 L2 资源组校验；超级管理员或持有 `observability_instance_all` 的用户保留全局访问，其余用户只能访问所属资源组实例。全部诊断路由调用点已同步传入 `user`，停用实例仍保持 404 行为。新增集成测试覆盖 `kill_session` 跨资源组拒绝与全局观测权限放行。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/integration/test_diagnostic_resource_scope.py -q`（2 passed，保留默认 SECRET_KEY warning）。

---

### P0-4｜SECRET_KEY 只做默认值等值校验，无长度/熵校验

**文件**：[backend/app/core/config.py:93-106](../backend/app/core/config.py)

```python
# 修改前（示意，保留原有默认值判断逻辑）
@model_validator(mode="after")
def _validate_secret_key(self) -> "Settings":
    if _default_key == self.SECRET_KEY:
        if self.APP_ENV == "production":
            raise ValueError(
                "生产环境禁止使用默认 SECRET_KEY，"
                "请设置环境变量 SECRET_KEY 为至少 32 字符的随机字符串。\n"
            )
        logger.warning("SECRET_KEY 使用默认值，请在生产环境中替换！")
    return self

# 修改后：额外加长度与低熵值黑名单校验
_WEAK_SECRET_PATTERNS = re.compile(r"^(.)\1*$|^(0123456789|abcdefgh|password|changeme).*", re.IGNORECASE)

@model_validator(mode="after")
def _validate_secret_key(self) -> "Settings":
    if _default_key == self.SECRET_KEY:
        if self.APP_ENV == "production":
            raise ValueError(
                "生产环境禁止使用默认 SECRET_KEY，"
                "请设置环境变量 SECRET_KEY 为至少 32 字符的随机字符串。\n"
            )
        logger.warning("SECRET_KEY 使用默认值，请在生产环境中替换！")
    elif self.APP_ENV == "production":
        if len(self.SECRET_KEY) < 32:
            raise ValueError("生产环境 SECRET_KEY 长度不足 32 字符。")
        if _WEAK_SECRET_PATTERNS.match(self.SECRET_KEY):
            raise ValueError("生产环境 SECRET_KEY 疑似弱密钥（重复字符/常见弱口令模式），请更换为随机字符串。")
    return self
```

同步更新：
- `.env.example`、`docs/operations_guide.md` 里补一句"生产环境启动时会硬校验长度和弱模式，不满足会直接拒绝启动"。
- `deploy/preflight-check.sh` / `deploy/customer/go-live-check.sh` 如果有独立的 SECRET_KEY 检查逻辑，同步这条规则，避免脚本判定和后端启动校验不一致。

**验证**：单测覆盖三种场景：默认值+production（拒绝）、短密钥+production（拒绝）、合规密钥+production（通过）。

**验收标准**：`APP_ENV=production` 且 `SECRET_KEY` 长度 <32 或命中弱模式时，`uvicorn app.main:app` 启动阶段直接失败退出，不会带着弱密钥跑起来。

> **落地注意**：上面的示例片段用 `logger.warning(...)` 表达告警意图；实际修改 `backend/app/core/config.py` 时，应先看当前文件已有的告警方式。如果文件仍使用 `warnings.warn(...)`，优先沿用现有写法，避免为了示例额外引入无关 logger 变更。

**落地状态（2026-07-04）**：已完成。`Settings.validate_production_secrets()` 已在生产环境拒绝默认 `SECRET_KEY`、长度不足 32 字符的密钥，以及重复字符、`0123456789`、`abcdefgh`、`password`、`changeme` 等常见弱模式；开发环境默认值仍沿用既有 `warnings.warn(...)` 告警。`deploy/preflight-check.sh` 与 `deploy/customer/go-live-check.sh` 已同步同类检查，`.env.example` 与运维手册已补充生产启动硬校验说明。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_config.py -q`、`bash -n deploy/preflight-check.sh deploy/customer/go-live-check.sh`、`git diff --check`。

---

## 阶段 P1：工程健壮性

### P1-1｜Celery 任务中 engine 创建后靠散落的手动 dispose 兜底，而不是单一 try/finally

> **修正说明**：初版手册把这个问题想简单了，以为只是"try 位置"没放对。实地核对 [execute_sql.py:58-224](../backend/app/tasks/execute_sql.py) 后发现：`engine = create_async_engine(...)`（第 58 行）后面**根本没有外层 try**，而是在 4 个不同的提前返回分支里各自手写 `await engine.dispose(); return`（第 71-72、79-80、95-96 行，以及函数末尾第 182、223-224 行）。`archive.py` 也是同样模式（[archive.py:44-64](../backend/app/tasks/archive.py)，两处 `create_async_engine` + 手动 `dispose()` + `return`）。这意味着：只要在 `db.execute(select(...))` 之类还没走到任何一个手动 dispose 分支之前抛异常，engine 就会泄露——"把 try 挪到 create_async_engine 后面"这种小改动不够，需要把整个函数体收进一个 try/finally，并删掉所有散落的手动 dispose。

**文件**：先跑一遍拿到完整清单，再逐个处理：

```bash
grep -rln "create_async_engine" backend/app/tasks/
```

**以 `execute_sql.py` 为例的修复模式**：

```python
# 修改前（execute_sql.py:58-96，节选，示意早退分支）
engine = create_async_engine(settings.DATABASE_URL)
async_session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async with async_session_local() as db:
    result = await db.execute(select(SqlWorkflow)...)
    wf = result.scalar_one_or_none()
    if not wf:
        logger.error("workflow not found: %s", workflow_id)
        await engine.dispose()
        return
    if wf.status not in (WorkflowStatus.QUEUING, WorkflowStatus.TIMING_TASK):
        logger.warning(...)
        await engine.dispose()
        return
    ...
    if not inst:
        wf.status = WorkflowStatus.EXCEPTION
        await db.commit()
        await engine.dispose()
        return
    ...
    # 函数末尾还有 engine.dispose() + return

# 修改后：整个函数体收进 try/finally，去掉所有散落的手动 dispose，早退分支只保留 return
async def _execute_async(workflow_id: int, operator_id: int):
    ...
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async_session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session_local() as db:
            result = await db.execute(select(SqlWorkflow)...)
            wf = result.scalar_one_or_none()
            if not wf:
                logger.error("workflow not found: %s", workflow_id)
                return
            if wf.status not in (WorkflowStatus.QUEUING, WorkflowStatus.TIMING_TASK):
                logger.warning(...)
                return
            ...
            if not inst:
                wf.status = WorkflowStatus.EXCEPTION
                await db.commit()
                return
            ...
            # 函数末尾正常结束，不再手动 dispose
    finally:
        await engine.dispose()
```

`archive.py` 的两处（约 [:44](../backend/app/tasks/archive.py)、[:59](../backend/app/tasks/archive.py) 附近的两个函数）按同样方式改：函数体整体收进 try，`finally` 统一 dispose，删除函数内所有手动 `await engine.dispose()`。

**验收标准**：
1. `grep -n "engine.dispose()" backend/app/tasks/*.py`，每个使用了 `create_async_engine` 的函数应该**只有一处** `dispose()` 调用，且位于该函数的 `finally` 块里；不应再出现"函数体中间某个 return 分支手动 dispose"的写法。
2. 补一个单测：mock 数据库查询在早退分支之前抛异常，断言 `engine.dispose()` 依然被调用到（可以用 `unittest.mock` 包一层 `create_async_engine` 断言 `dispose` 调用次数为 1）。

**落地状态（2026-07-04）**：已完成。`execute_sql.py`、`archive.py` 与 `notify.py` 中由 Celery 任务临时创建的 async engine 均已收敛为 `try/finally` 统一释放，早退分支不再手写 `dispose()`；`license.py` 与 `monitor.py` 既有 `_run_with_session` / `_run_with_task_session` 已符合该模式。新增单测覆盖 SQL 工单执行、预约工单调度、归档执行、归档调度和通知发送在查询/服务异常时仍会释放 engine。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_execute_sql_task.py tests/unit/test_archive_task.py tests/unit/test_notify_task.py -q`（13 passed，保留默认 SECRET_KEY warning）；`grep -n "engine.dispose()" backend/app/tasks/*.py` 确认所有命中均位于 `finally` 释放点或已有会话 helper 中。

---

### P1-2｜关键 Celery 任务禁用重试，且需要用正确的 Celery 重试机制

> **修正说明**：初版手册里的任务名是编造的，真实任务名（[backend/app/tasks/notify.py:13-14](../backend/app/tasks/notify.py)、[backend/app/tasks/monitor.py:152/217/230](../backend/app/tasks/monitor.py)）是 `send_notification_event`、`collect_session_snapshots`、`collect_slow_queries`、`collect_native_monitoring`。更关键的错误是技术语义：**仅仅在 `task_annotations`/装饰器参数里配置 `max_retries`、`default_retry_delay` 不会让任务自动重试**——Celery 只有在任务代码里显式调用 `self.retry()`，或者装饰器上声明了 `autoretry_for=(...)`，才会触发重试；`max_retries` 只是这两种机制生效时的重试次数上限，单独配置它没有任何效果。

**文件**：[backend/app/tasks/notify.py:13-14](../backend/app/tasks/notify.py)、[backend/app/tasks/monitor.py:152-231](../backend/app/tasks/monitor.py)

**处理原则**：不是所有任务都应该重试——SQL 执行类任务（`execute_sql.py`）重试可能造成重复执行（非幂等），需要谨慎；通知、监控采集类任务本身是"读取/推送"性质，重试相对安全。

```python
# 修改前（notify.py:13-14）
@celery_app.task(bind=True, name="send_notification_event", max_retries=0, queue="notify")
def send_notification_event_task(self, payload: dict):
    ...

# 修改后：用 autoretry_for 声明式重试（推荐，改动最小）
@celery_app.task(
    bind=True,
    name="send_notification_event",
    queue="notify",
    autoretry_for=(ConnectionError, TimeoutError),  # 按实际会抛出的瞬时性异常类型调整
    retry_backoff=True,       # 指数退避，避免风暴式重试打满通知渠道
    retry_backoff_max=120,
    max_retries=3,
)
def send_notification_event_task(self, payload: dict):
    ...
```

```python
# monitor.py 的三个任务（collect_session_snapshots / collect_slow_queries / collect_native_monitoring）同样处理
# 修改前（monitor.py:152）
@celery_app.task(name="collect_session_snapshots", queue="monitor")
def collect_session_snapshots(retention_days: int = 30) -> dict:
    ...

# 修改后
@celery_app.task(
    name="collect_session_snapshots",
    queue="monitor",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=2,
)
def collect_session_snapshots(retention_days: int = 30) -> dict:
    ...
```

**待决策**：`execute_sql.py`、`archive.py` 里的任务如果要支持重试，必须先设计幂等键（例如按工单 ID + 执行批次号做唯一约束防止重复执行），这是一项独立的设计任务，不建议在这次 P1 里顺带做，本次改动**不涉及** `execute_sql`/`archive` 任务的重试配置，保持现状的"失败即停"。

**验证**：
1. 单测/集成测试：设置 `celery_app.conf.task_always_eager = True`，mock 通知发送函数抛出 `ConnectionError`，直接调用 `send_notification_event_task.apply(args=[payload])`（或 `.delay()`），断言 mock 函数被调用次数 > 1（说明确实重试了），或断言捕获到的任务对象 `request.retries` > 0。
2. 确认 `autoretry_for` 里列出的异常类型确实是通知/采集代码路径里会抛出的类型（不要写成过于宽泛的 `Exception`，否则业务逻辑错误也会被无意义地重试）。

**验收标准（v3 修正：原 v2 的验收命令验证不了任何东西）**：`celery -A app.celery_app inspect registered` 只能证明任务已经注册到 Celery，**不会显示** `autoretry_for`/`max_retries` 等重试配置或运行时行为，不能作为验收依据。正确的验收方式二选一：
1. 直接读取任务对象的属性确认配置已生效：
   ```python
   from app.celery_app import celery_app
   task = celery_app.tasks["send_notification_event"]
   assert set(task.autoretry_for) == {ConnectionError, TimeoutError}
   assert task.max_retries == 3
   ```
2. 跑上面"验证"里的 eager 模式重试用例并通过 CI。
`execute_sql`、`archive` 队列的任务定义和行为本次不做任何改动（回归测试确认无变化）。

**落地状态（2026-07-04）**：已完成。`send_notification_event` 已改为只对 `ConnectionError`、`TimeoutError` 做声明式 `autoretry_for`，指数退避上限 120 秒，最多重试 3 次；`collect_session_snapshots`、`collect_slow_queries`、`collect_native_monitoring` 已改为只对 `ConnectionError`、`TimeoutError`、`OSError` 做声明式重试，指数退避上限 60 秒，最多重试 2 次。`execute_sql`、`archive` 队列保持无自动重试，避免非幂等任务重复执行。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_notify_task.py -q`（5 passed，保留默认 SECRET_KEY warning）。

---

### P1-3｜CORS `allow_methods`/`allow_headers` 显式化

**文件**：[backend/app/main.py:59-65](../backend/app/main.py)

```python
# 修改前
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 修改后
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)
```

同时在 `config.py` 给 `CORS_ORIGINS` 加一条生产环境校验：如果 `APP_ENV=="production"` 且列表里出现 `"*"`，直接拒绝启动（防止误配置成通配符 + `allow_credentials=True` 的经典组合漏洞）。

```python
@model_validator(mode="after")
def _validate_cors(self) -> "Settings":
    if self.APP_ENV == "production" and "*" in self.CORS_ORIGINS:
        raise ValueError("生产环境禁止 CORS_ORIGINS 使用通配符 '*'。")
    return self
```

**验证**：单测覆盖 `APP_ENV=production` + `CORS_ORIGINS=["*"]` 时启动失败。

**验收标准**：前端实际跨域请求（如有）功能不受影响（需要在真实浏览器里跑一次登录+查询流程回归）。

**落地状态（2026-07-04）**：已完成。`CORSMiddleware` 已将 `allow_methods` 显式收敛为 `GET/POST/PUT/PATCH/DELETE/OPTIONS`，`allow_headers` 显式收敛为 `Authorization/Content-Type/X-Requested-With`；`Settings` 在生产环境会拒绝 `CORS_ORIGINS=["*"]`。新增单测覆盖生产 CORS 通配符拒绝和 FastAPI CORS 中间件配置，`README.md` 与 `docs/operations_guide.md` 已同步生产配置提示。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_config.py tests/unit/test_cors_middleware.py -q`（9 passed，保留默认 SECRET_KEY warning）。

---

### P1-4｜前端 Token 存储于 localStorage（安全加固，评估后实施）

**文件**：[frontend/src/store/auth.ts:75](../frontend/src/store/auth.ts)

这一项改动面较大（涉及后端登录/刷新接口配合 Set-Cookie，以及 CSRF 防护），不建议在 P1 里直接推全量重构，按两步走：

**Step A（快速加固，成本低）**：
1. 审计所有富文本/用户可控内容渲染点是否统一走 `dompurify`：
   ```bash
   grep -rn "dangerouslySetInnerHTML" frontend/src/
   ```
   逐一确认渲染前是否过了 `DOMPurify.sanitize()`。
2. 给 CSP（Content-Security-Policy）加固，在 `deploy/nginx.conf` 增加 `Content-Security-Policy` 响应头，限制脚本来源，降低即使有 XSS 也无法外带 Token 的概率：
   ```nginx
   add_header Content-Security-Policy "default-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none';" always;
   ```

**Step B（架构级方案，需要单独立项）**：
- 后端登录/刷新接口改为通过 `Set-Cookie: access_token=...; HttpOnly; Secure; SameSite=Strict` 下发，前端不再手动持有 Token；
- 需要同步引入 CSRF Token（双提交 Cookie 或自定义 Header 校验），因为 Cookie 方案会让浏览器自动带上认证信息，容易受 CSRF 影响；
- 涉及 `backend/app/routers/auth.py`、`frontend/src/api/client.ts`、`frontend/src/store/auth.ts` 的联动改造，工作量与回归测试成本较高，建议单开一个迭代，不要和本次 P0/P1 混在一起做。

**验收标准（Step A 范围内）**：CSP 头在生产响应中生效（`curl -I` 可见）；`dangerouslySetInnerHTML` 全部有 `DOMPurify.sanitize()` 包裹或已确认无用户可控输入。

**落地状态（2026-07-04）**：Step A 已完成。`deploy/nginx.conf` 已增加生产 CSP 响应头，脚本只允许同源加载，保留同源 API、WebSocket、字体和 data 图片等现有前端运行所需来源，并禁止第三方 frame 嵌入与 object 加载；由于 Nginx `add_header` 在 location 中存在继承限制，`/assets/`、`/index.html` 和 SPA `/` 路由均已显式重声明 CSP。`rg -n "dangerouslySetInnerHTML|DOMPurify|dompurify" frontend/src frontend/package.json frontend/package-lock.json` 结果显示 `frontend/src` 当前没有 `dangerouslySetInnerHTML` 渲染点，`dompurify` 依赖仍保留备用。新增 `backend/tests/unit/test_nginx_security_headers.py` 覆盖 CSP 指令和 location 重声明要求。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_nginx_security_headers.py -q`（2 passed，保留默认 SECRET_KEY warning）、`cd frontend && npm run build`。

**最终落地状态（2026-07-04）**：Step B 已完成。后端新增可配置 Cookie 登录态：`AUTH_COOKIE_SECURE`、`AUTH_COOKIE_SAMESITE`、`AUTH_COOKIE_DOMAIN`，登录、LDAP、短信、2FA、OAuth exchange 和 refresh 均会下发 `access_token` / `refresh_token` HttpOnly Cookie，同时下发可读 `csrf_token`；`current_user` 保持 Bearer 兼容，缺少 Authorization 时可使用 Cookie 登录态。写操作在请求带认证 Cookie 时必须提供匹配的 `X-CSRF-Token`，refresh 可继续兼容 body refresh token，也可只使用 refresh Cookie。前端 `apiClient` 已启用 `withCredentials`，停止把 token 写入 localStorage / Authorization header，并在写操作中自动从 `csrf_token` Cookie 注入 CSRF Header；旧 localStorage token 会通过 Zustand persist migration 清空。生产 HTTPS 环境需显式设置 `AUTH_COOKIE_SECURE=true`，HTTP ECS 源码测试环境可保留 `false`。验证命令：`cd backend && .venv/bin/pytest tests/unit/test_auth.py tests/unit/test_auth_cookies.py tests/unit/test_cors_middleware.py -q`（37 passed）、`npm --prefix frontend test -- src/api/client.test.ts`（3 passed）、`npm --prefix frontend test`（37 passed）、`npm --prefix frontend run build`。

---

## 阶段 P2：测试与类型债务

### P2-1｜补强高风险模块的测试边界，逐步提升覆盖率门槛

> **修正说明**：初版手册把这三个模块写成"缺专项测试"是不准确的——`backend/tests/unit/` 下已经存在 `test_query_guard.py`、`test_masking.py`、`test_archive_cancel.py`（以及 `test_archive_doris.py`、`test_archive_starrocks.py`），不是从零开始。真正的任务是**核对现有用例是否覆盖了高风险边界，补齐薄弱点**，而不是新建测试文件。另外覆盖率门槛实际配置在 [README.md:147](../README.md) 和 [.github/workflows/ci.yml:172](../.github/workflows/ci.yml)（`pytest` 命令行参数），**不在** `backend/pyproject.toml` 里，调整时两处都要改，保持一致；当前已从 `--cov-fail-under=51` 提升到 `--cov-fail-under=55`。

**建议节奏**：
1. 先读一遍现有 `test_query_guard.py`，列出已覆盖 vs 未覆盖的规则分支，重点确认这几类是否有用例：
   - 无 WHERE 的 UPDATE/DELETE 拦截
   - 高风险 DDL（DROP/TRUNCATE）拦截
   - `SELECT *`、`INSERT ... SELECT` 的规则提示
   - 多语句执行顺序校验
   把清单里缺失的分支补上，而不是重写整个测试文件。
2. 同样方式核对 `test_masking.py`：内置脱敏类型和自定义正则的匹配/替换结果是否都有正例+反例（防止规则误伤或漏伤）。
3. 核对 `test_archive_cancel.py` 等：是否覆盖了"暂停/继续/取消"状态机的所有合法状态迁移路径，以及非法迁移（如已完成批次再次取消）是否被正确拒绝。
4. 每补齐一批边界用例后，评估实际覆盖率数字，再把 `--cov-fail-under=55` 继续小步上调（例如模块补齐后再提到 60%+），而不是一次性大幅调高导致 CI 长期红。

**文件**：`README.md:147`、`.github/workflows/ci.yml:172`（覆盖率门槛，两处需同步改）；`backend/tests/unit/test_query_guard.py`、`test_masking.py`、`test_archive_cancel.py` 等（补充用例，非新建）。

**验收标准**：每提升一次门槛，CI（`.github/workflows/ci.yml`）必须绿；上述现有测试文件针对本节列出的边界场景，缺失的分支补齐后不应再有遗漏。

**落地状态（2026-07-04）**：进行中。已完成 `test_masking.py` 自定义正则脱敏边界补强：新增正则替换正例，并覆盖 `hide_group` 指向未匹配可选分组时不应抛 `TypeError` 的反例。`DataMaskingService._apply_rule()` 已改为仅在目标分组实际匹配时替换为星号，未匹配可选分组保持为空，避免脱敏规则因可选分组缺失导致查询结果处理失败。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_masking.py -q`（23 passed，保留默认 SECRET_KEY warning）。

**增量落地状态（2026-07-04）**：本轮完成 `test_query_guard.py` 查询治理边界补强：新增无 `WHERE` 的 `UPDATE` / `DELETE` 精确拒绝原因，以及 `INSERT ... SELECT` 写入型语句的规则提示断言。`SqlQueryGuard` 保持 fail-closed，只将写操作拒绝原因细化为更可审计的高风险场景说明。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_query_guard.py -q`（326 passed，保留默认 SECRET_KEY warning）；`cd backend && uv run --with pytest --with pytest-asyncio --with pytest-cov pytest tests/unit/ -v --cov=app --cov-fail-under=51`（939 passed，Total coverage 52.30%）。由于距离 55% 仍有明显缺口，本轮暂不把 `README.md` 和 `.github/workflows/ci.yml` 的覆盖率门槛从 51% 上调。`P2-1` 剩余工作：继续核对 `test_archive_cancel.py` 的归档暂停/继续/取消状态迁移，完成后再评估覆盖率门槛是否可小步上调。

**增量落地状态（2026-07-04）**：本轮完成 `test_archive_cancel.py` 归档状态机边界补强：新增合法暂停（`queued`/`running` -> `pausing`）、合法继续（`paused` -> `queued`）、可直接取消状态（`approved`/`scheduled`/`queued`/`paused` -> `canceled` 并同步工单 `abort`）、运行中取消（`running`/`pausing` -> `canceling`）、以及终态/非法状态（`success`/`failed`/`canceled`/`canceling` 等）拒绝迁移的测试矩阵。状态机现有实现通过新增用例，无需修改生产代码。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_archive_cancel.py -q`（22 passed，保留默认 SECRET_KEY warning）；`cd backend && uv run --with pytest --with pytest-asyncio --with pytest-cov pytest tests/unit/ -v --cov=app --cov-fail-under=51`（954 passed，Total coverage 52.43%）。由于距离 55% 仍有明显缺口，本轮暂不把 `README.md` 和 `.github/workflows/ci.yml` 的覆盖率门槛从 51% 上调。`P2-1` 剩余工作：可继续补 archive 执行分支覆盖，或在下一轮进入 `P2-2` mypy baseline 消解。

**增量落地状态（2026-07-04）**：本轮完成 `test_archive_cancel.py` 归档执行暂停边界补强：新增 `execute_job()` 中执行子流程把作业置为 `paused` 后不应把 workflow 误同步为 `exception`、不应写失败执行结果、不应发送 `execution_failed` 通知的回归测试。`ArchiveService.execute_job()` 收尾逻辑已改为只对 `success`/`failed`/`canceled` 终态同步 workflow 终态和发送完成/失败通知，`paused` 等非终态只提交当前作业状态并保留 workflow `executing`。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_archive_cancel.py -q`（23 passed，保留默认 SECRET_KEY warning）；`cd backend && uv run --with pytest --with pytest-asyncio --with pytest-cov pytest tests/unit/ -v --cov=app --cov-fail-under=51`（955 passed，Total coverage 52.45%）。由于距离 55% 仍有缺口，本轮暂不把覆盖率门槛从 51% 上调。`P2-1` 剩余工作：继续评估 archive dest/mongo 执行分支覆盖，或在覆盖率仍不足 55% 时进入 `P2-2` mypy baseline 消解。

**增量落地状态（2026-07-04）**：本轮完成 `test_archive_cancel.py` MongoDB `dest` 归档执行分支补强：新增目标库已插入但源集合删除数量不足时必须拒绝继续、记录 `FAILED` 批次并提示人工核对的回归测试。`ArchiveService._execute_dest_mongo()` 已在 `insert_many()` 后校验 `delete_many()` 删除数量必须等于本批已插入文档数，避免目标已写入而源数据未完整删除时被误记为成功批次。验证命令：`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_archive_cancel.py tests/unit/test_archive_doris.py tests/unit/test_archive_starrocks.py tests/unit/test_archive_task.py -q`（36 passed，保留默认 SECRET_KEY warning）；`cd backend && uv run --with pytest --with pytest-asyncio --with pytest-cov pytest tests/unit/ -v --cov=app --cov-fail-under=51`（956 passed，Total coverage 52.52%）。由于距离 55% 仍有缺口，本轮暂不把覆盖率门槛从 51% 上调。`P2-1` 剩余工作：归档核心执行风险边界已继续收敛，下一轮可进入 `P2-2` mypy baseline 消解。

**增量落地状态（2026-07-04）**：本轮随 P1-4 Step B 完成认证传输安全边界补强：新增 `backend/tests/unit/test_auth_cookies.py` 覆盖 HttpOnly auth Cookie、可读 CSRF Cookie、Cookie 清理、CSRF 豁免/拒绝/通过路径；更新 `backend/tests/unit/test_auth.py` 覆盖 OAuth 登录码交换落 Cookie；更新 `backend/tests/unit/test_cors_middleware.py` 覆盖 `X-CSRF-Token` CORS 允许头；新增 `frontend/src/api/client.test.ts` 覆盖 `withCredentials`、写操作 CSRF Header 注入、以及不再把持久化 token 镜像进 Authorization Header。验证命令：`cd backend && .venv/bin/pytest tests/unit/ -q --cov=app --cov-report=term-missing --cov-fail-under=51`（961 passed，Total coverage 52.64%）、`npm --prefix frontend test`（37 passed）。由于距离 55% 仍有缺口，本轮继续不把 `README.md` 和 `.github/workflows/ci.yml` 的覆盖率门槛从 51% 上调；P2-1 仍属于持续迭代项，下一步应继续补 `archive` / `dashboard` / DB 引擎中更高收益的真实业务分支，而不是为了数字调整覆盖统计口径。

**落地状态（2026-07-05）**：已完成本轮手册目标。新增 `backend/tests/unit/test_sms_auth.py` 覆盖短信验证码开关、限流、每日上限、验证码一次性验证、阿里云/腾讯云/自定义 provider 分支；新增 `backend/tests/unit/test_dashboard_scope.py` 覆盖 dashboard 实例、查询、归档概览的作用域和聚合组装；新增 `backend/tests/unit/test_engine_protocol.py`、`test_common_schemas.py` 覆盖引擎协议默认能力与公共分页响应模型；新增 `backend/tests/unit/test_deps.py` 并扩展 `test_auth.py` 覆盖认证依赖、refresh、logout、2FA 与 SMS 登录链路。`README.md` 与 `.github/workflows/ci.yml` 覆盖率门槛已同步提升为 `--cov-fail-under=55`。验证命令：`cd backend && .venv/bin/pytest tests/unit/ -q --cov=app --cov-report=term-missing --cov-fail-under=55`（1013 passed，Total coverage 55.03%）。

---

### P2-2｜mypy baseline 消解计划

**文件**：`backend/mypy-baseline.txt`（56 个豁免文件）

**建议**：不追求一次清零，按优先级分批：
1. 优先消解 `app/services/` 下的豁免（业务逻辑，类型错误容易掩盖真实 bug）；
2. 其次是 `app/tasks/`（Celery 类型注解复杂，可延后）；
3. 每次 PR 顺带消解 1-2 个文件，从 baseline 里移除对应文件名，README 已提到"新增或拆分出的低风险 helper 模块应优先纳入 baseline"，这条规则本身没问题，只是需要一个"退出"机制配套（比如季度复查一次 baseline 文件数是否在下降）。

**验收标准**：baseline 文件数量按季度呈下降趋势，而不是只增不减。

**增量落地状态（2026-07-04）**：本轮按当前 CI/README 的真实语义修正执行口径：`backend/mypy-baseline.txt` 是"已清洁文件硬门禁清单"，不是豁免清单；已清洁的 `app/services/*` 继续保留在门禁内，不做删除降级。本轮完成 `app/tasks/notify.py` 的类型基线消解，补齐 Celery task 装饰器静态类型边界、payload 泛型类型与 async sessionmaker 类型用法，并将 `app/tasks/notify.py` 纳入 `backend/mypy-baseline.txt`。验证命令：`cd backend && uv run --with mypy mypy --follow-imports=silent app/tasks/notify.py`、`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_notify_task.py -q`。下一轮可继续按同一策略消解 `app/tasks/license.py` 或其他任务模块。

**增量落地状态（2026-07-04）**：本轮完成 `app/tasks/license.py` 的类型基线消解，复用 Celery task 装饰器静态类型边界，补齐 `_run_with_session()` handler 泛型、License 刷新结果类型与 task 返回类型，并改用 `async_sessionmaker` 适配 SQLAlchemy 2 async 类型签名。`app/tasks/license.py` 已纳入 `backend/mypy-baseline.txt`。验证命令：`cd backend && uv run --with mypy mypy --follow-imports=silent app/tasks/license.py`、`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_license_task.py -q`。下一轮可继续按同一策略消解 `app/tasks/monitor.py` 或其他任务模块。

**增量落地状态（2026-07-04）**：本轮完成 `app/tasks/monitor.py` 的类型基线消解，复用 Celery task 装饰器静态类型边界，补齐监控采集任务返回值泛型、collector 协程类型与 `async_sessionmaker` 类型签名。`app/tasks/monitor.py` 已纳入 `backend/mypy-baseline.txt`。验证命令：`cd backend && uv run --with mypy mypy --follow-imports=silent app/tasks/monitor.py`、`cd backend && while IFS= read -r target; do uv run --with mypy mypy --follow-imports=silent "$target"; done < mypy-baseline.txt`、`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_notify_task.py tests/unit/test_monitor_native.py -q`。下一轮可继续按同一策略消解其他低风险 task module，或在任务模块阶段足够收敛后进入 P3。

**增量落地状态（2026-07-04）**：本轮完成 `app/tasks/archive.py` 的类型基线消解，复用 Celery task 装饰器静态类型边界，补齐归档任务 wrapper 返回类型，并将本地 async engine 会话工厂从 `sessionmaker(..., class_=AsyncSession)` 调整为 SQLAlchemy 2 async 类型友好的 `async_sessionmaker`。`app/tasks/archive.py` 已纳入 `backend/mypy-baseline.txt`，相关 dispose 回归测试同步 patch 到新的会话工厂导入点。验证命令：`cd backend && uv run --with mypy mypy --follow-imports=silent app/tasks/archive.py`、`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_archive_task.py -q`。下一轮可继续按同一策略消解 `app/tasks/execute_sql.py`。

**增量落地状态（2026-07-04）**：本轮完成 `app/tasks/execute_sql.py` 的类型基线消解，复用 Celery task 装饰器静态类型边界，补齐 SQL 执行任务 wrapper 返回类型，并将任务内本地 async engine 会话工厂从 `sessionmaker(..., class_=AsyncSession)` 调整为 SQLAlchemy 2 async 类型友好的 `async_sessionmaker`。`app/tasks/execute_sql.py` 已纳入 `backend/mypy-baseline.txt`，相关 dispose 回归测试同步 patch 到新的会话工厂导入点。验证命令：`cd backend && uv run --with mypy mypy --follow-imports=silent app/tasks/execute_sql.py`、`cd backend && uv run --with pytest --with pytest-asyncio pytest tests/unit/test_execute_sql_task.py -q`、`cd backend && while IFS= read -r target; do uv run --with mypy mypy --follow-imports=silent "$target"; done < mypy-baseline.txt`。下一轮可进入 P3 或继续评估其他低风险 task/helper 模块是否适合纳入 baseline。

**增量落地状态（2026-07-04）**：本轮随 P1-4 Step B 新增 `app/core/auth_cookies.py`，该 helper 模块已通过严格 mypy 检查并纳入 `backend/mypy-baseline.txt`；`app/core/deps.py` 与 `app/routers/auth.py` 仍存在存量 `no-untyped-def` / 泛型注解问题，本轮未将其硬塞进 baseline。验证命令：`cd backend && .venv/bin/mypy --follow-imports=silent app/core/auth_cookies.py`、`cd backend && while read -r target; do [ -z "$target" ] && continue; .venv/bin/mypy --follow-imports=silent "$target"; done < mypy-baseline.txt`（全部通过）。下一轮可继续拆分认证路由 helper 或治理 `deps.py` 的类型注解，再扩大 baseline 门禁面。

**落地状态（2026-07-05）**：已完成本轮手册点名的认证类型基线收口。`app/core/deps.py` 补齐 `CurrentUser` 类型别名、`current_user`/`current_superuser`/`require_perm` 返回类型与依赖工厂签名；`app/routers/auth.py` 补齐认证 helper、登录/刷新/logout、2FA、短信、OAuth 端点的参数与返回类型，并对 `disable_2fa()` 的 `totp_secret` 空值边界做显式保护。两个模块已通过严格 mypy 并纳入 `backend/mypy-baseline.txt`。验证命令：`cd backend && .venv/bin/mypy --follow-imports=silent app/core/deps.py app/routers/auth.py`、`cd backend && while read -r target; do [ -z "$target" ] && continue; .venv/bin/mypy --follow-imports=silent "$target"; done < mypy-baseline.txt`。

---

## 阶段 P3：仓库与交付卫生

### P3-1｜`dist-commercial/` 不应长期提交进源码仓库版本控制

**现状**：`dist-commercial/` 目录下 249 个文件（含多版本 zip、sha256）已被 git 跟踪，累计约 26MB，且随着版本增多会持续膨胀 `.git` 体积（当前 61MB）。

**处理方式**：
```bash
git rm -r --cached dist-commercial
echo "dist-commercial/" >> .gitignore
git add .gitignore
git commit -m "移除已跟踪的商业构建产物目录，改为仅本地/CI 产物"
```
> 注意：这只是不再新增跟踪，历史 blob 仍留在 `.git` 里；如果要彻底瘦身仓库体积需要用 `git filter-repo` 之类工具重写历史，属于高风险操作，需要单独评估、通知协作者、并在低峰期执行，不建议和本次改动放在一起做。先执行"停止继续跟踪"这一步即可，历史清理作为可选的后续项。

**验收标准**：新的构建产物不再出现在 `git status` 里；`docs/public_commercial_delivery.md` 中"私有源码仓库 / 公开交付仓库分离"的原则和实际仓库内容保持一致。

**落地状态（2026-07-04）**：已完成。`dist-commercial/` 下 249 个既有商业构建产物已通过 `git rm -r --cached dist-commercial` 停止版本控制跟踪，本地生成目录保留但新增 `.gitignore` 规则避免后续商业包、SBOM 和 zip/sha256 产物再次进入源码提交。`docs/public_commercial_delivery.md` 已同步说明 `dist-commercial/` 仅作为本地或 CI 输出目录，发布资产以 workflow、Release 下载资产和公开交付仓库为准。验证命令：`git ls-files dist-commercial | wc -l`（0）、`git status --ignored --short dist-commercial | head`（目录显示为 ignored）、`git diff --check`。

---

### P3-2｜用户手册截图与当前品牌规范不一致

**现状**：[docs/screenshots/user-manual/01-login.png](../docs/screenshots/user-manual/01-login.png) 等截图展示旧品牌 `SagittaDB`/`v2.2.0`，与当前 `Sagitta Control`/`v2.3.5` 品牌规范不符。

**处理方式**：在下一次功能发布或专门安排的文档维护窗口，重新用最新版本跑一遍 `docs/screenshots/user-manual/` 里列出的全部 26 张截图（登录、Dashboard、工单、查询、监控×3、归档、字典、用户/角色/组管理、审批流、系统配置、脱敏规则、商业交付、审计日志；`ls docs/screenshots/user-manual/ | wc -l` 实测为 26，注意监控相关截图有 `12-monitor.png`/`12-monitor-sql-analysis.png`/`12-monitor-sql-insight.png` 三张同前缀文件），保持文件名不变，直接覆盖。

**验收标准**：截图里的品牌文案、版本号与当前 README/AGENT.md 定义的品牌规范一致。

**增量落地状态（2026-07-04）**：Step A 已完成。`frontend/scripts/capture-user-manual-screenshots.mjs` 的截图清单已从旧版 20 张对齐到当前 `docs/screenshots/user-manual/` 的 26 张文件名，覆盖 4 个 Dashboard 分页、工单模板、查询历史、监控 SQL 分析/洞察、实例管理、用户组、交付与支持和审计日志等当前手册截图；旧的 `20-license.png` 不再作为公开用户手册截图捕获目标。新增 `frontend/scripts/check-user-manual-screenshot-manifest.mjs` 并接入 `npm run screenshots:user-manual`，防止捕获脚本和截图目录再次漂移。验证命令：`node frontend/scripts/check-user-manual-screenshot-manifest.mjs`。

**增量落地状态（2026-07-04）**：Step B 已完成。`frontend/scripts/capture-user-manual-screenshots.mjs` 已在非 smoke 覆盖截图模式下要求同时提供 `E2E_USERNAME` 和 `E2E_PASSWORD`，并在动态加载 Playwright 前 fail-closed，避免缺少登录态时把 26 张认证页面误覆盖为登录页或先被缺失浏览器依赖错误掩盖。新增 `frontend/scripts/capture-user-manual-screenshots.config.mjs` 与 `frontend/scripts/capture-user-manual-screenshots.config.test.mjs` 覆盖缺凭据拒绝、smoke 模式放行、完整凭据放行和依赖加载前报错顺序，并纳入前端 Vitest 门禁。验证命令：`cd frontend && npm test`、`node frontend/scripts/check-user-manual-screenshot-manifest.mjs`、`cd frontend && node scripts/capture-user-manual-screenshots.mjs`（预期因未提供 `E2E_USERNAME/E2E_PASSWORD` 非零退出并提示凭据门禁）、`cd frontend && npm run build`。剩余截图刷新工作需要可登录且有演示数据的最新环境，改为人工或专项文档维护窗口处理；当前自动化不再因缺少演示账号、代表性数据或 `E2E_USERNAME` / `E2E_PASSWORD` 阻塞在 P3-2。

**调度决策（2026-07-04）**：按用户指令，P3-2 中可由自动化本地完成的截图清单对齐和凭据门禁已完成；真实登录环境重新生成 26 张截图改为人工跟进项，不再作为 SagittaDB optimization handbook dispatcher 的阻塞项。后续自动任务应视 P3-2 自动化部分完成，并继续推进 `P3-3｜Docker Compose / Helm 默认弱密码的运行时门禁需要补全覆盖面，而非从零建立`。

**最终落地状态（2026-07-04）**：已完成。用户提供云 ECS 测试环境登录凭据后，已用 `E2E_BASE_URL=http://47.102.146.147` 执行 `npm --prefix frontend run screenshots:user-manual`，重新覆盖 `docs/screenshots/user-manual/` 下全部 26 张截图；截图已确认不是登录页重定向或空白页误覆盖，登录页品牌为 `Sagitta Control` / `v2.3.5`。真实运行还暴露并修复了截图脚本主登录按钮定位过宽的问题：`frontend/scripts/capture-user-manual-screenshots.mjs` 改为点击 `.sagitta-auth-form button[type="submit"]`，避免误匹配第三方登录按钮。验证命令：`node frontend/scripts/check-user-manual-screenshot-manifest.mjs`、`E2E_BASE_URL=http://47.102.146.147 E2E_USERNAME=... E2E_PASSWORD=... npm --prefix frontend run screenshots:user-manual`、`find docs/screenshots/user-manual -maxdepth 1 -name '*.png' -print | wc -l`（26），并抽样查看登录页与审计日志截图。

---

### P3-3｜Docker Compose / Helm 默认弱密码的运行时门禁需要补全覆盖面，而非从零建立

> **修正说明**：[deploy/preflight-check.sh:145-147](../deploy/preflight-check.sh) 已经存在 `check_env_secret SECRET_KEY CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS`、`check_env_secret POSTGRES_PASSWORD sagitta123`、`check_env_secret REDIS_PASSWORD redis123` 三条检查，并非"只在文档层面提醒、完全没有运行时门禁"。需要做的是**核对 `check_env_secret` 函数本身的检查条件（是否只在 `APP_ENV=production` 时才生效、匹配是否精确）、并补齐遗漏的弱密码项（如 `changeme` 对应的 Grafana OAuth Secret）**，而不是新建一套机制。

**现状核对步骤**：
1. 先读 `deploy/preflight-check.sh` 里 `check_env_secret` 函数的完整实现，确认它的失败条件、是否区分 `APP_ENV`、是否会被跳过。
2. 确认 Helm values（`deploy/helm/sagitta-control/values.yaml`）里的 `sagitta123`/`redis123`/`CHANGE_ME_USE_RANDOM_32_CHARS_IN_PRODUCTION` 是否也有等价的门禁（`preflight-check.sh` 只覆盖 Docker Compose 场景，Helm 场景可能需要单独的校验，比如 `helm template` 后 grep 弱密码字符串，或者在 `values.schema.json` 里标记 `required` 字段）。

**建议补充的检查项（在现有 `check_env_secret` 调用序列后追加）**：

```bash
# deploy/preflight-check.sh 现有 145-147 行之后追加
check_env_secret GRAFANA_CLIENT_SECRET changeme
```

**验收标准**：`APP_ENV=production` 时，`.env` 中残留任一已知默认弱密码（含新补充的 Grafana OAuth Secret）会导致 `preflight-check.sh` 非零退出；Helm 部署路径确认是否需要等价门禁并给出结论（即使结论是"当前 Helm 场景暂不需要，因为客户走 `go-live-check.sh`"，也要在运维文档里写清楚，不要留空白）。

**落地状态（2026-07-04）**：已完成。`deploy/preflight-check.sh` 在既有 `SECRET_KEY`、`POSTGRES_PASSWORD`、`REDIS_PASSWORD` 检查基础上，新增实际 Compose 输入变量 `GRAFANA_CLIENT_SECRET=changeme` 拦截，避免 Grafana OAuth Secret 继续使用默认弱值。Helm 路径新增 `deploy/helm/sagitta-control/values.schema.json`，当 `app.env=production` 时拒绝默认 `SECRET_KEY`、内置 PostgreSQL/Redis 弱密码，以及外部 PostgreSQL/Redis 的 `CHANGE_ME` 占位密码；`docs/operations_guide.md` 与客户安装文档已写清 Helm schema 和 Compose preflight 的门禁边界。验证命令：`uv run --with pytest pytest tests/scripts/test_preflight_secret_gates.py -q`、`uv run --with pytest pytest tests/scripts/test_quality_gates.py::test_helm_chart_rejects_known_production_default_secrets -q`、`bash -n deploy/preflight-check.sh deploy/customer/go-live-check.sh`、`python3 -m json.tool deploy/helm/sagitta-control/values.schema.json >/dev/null`、`uv run --with jsonschema --with pyyaml python ...` 验证默认 Helm values 与 prod overlay 均会因生产弱默认值失败。

---

## 实施顺序建议（甘特式排期参考）

```text
第 1 天      P0-1、P0-2（SQL 转义修复，改动小、风险低，优先落地）
第 2 天      P0-3（diagnostic.py 资源组校验，直接复用 instance.py 现成逻辑，无需产品对齐）、P0-4（SECRET_KEY/CORS 校验）
第 3 天      P0-3/P0-4 集成测试与回归
第 4-6 天    P1-1（Celery engine 泄露重构）、P1-2（真实任务名接入 autoretry_for）、P1-3
第 7-8 天    P1-4 Step A（CSP + dompurify 审计），Step B 单独立项排期
持续迭代     P2-1（补强已有测试边界）、P2-2（每个 Sprint 排 1-2 个模块）
半天         P3-1、P3-2、P3-3（穿插在任意空闲时间执行）
```

## 每项修复的通用收尾动作（对齐 AGENT.md「新功能完成规则」）

修完每一项 P0/P1 后，按仓库既有约定收尾：
1. 更新受影响的文档（如涉及安全策略变化，同步 `docs/operations_guide.md` 第 10 节"安全运维检查表"）。
2. 跑对应验证命令：后端 `pytest tests/unit/ -v --cov=app --cov-fail-under=55`、`ruff check .`、`mypy` baseline 校验；前端如涉及改动跑 `npm run build`。
3. `git status --short` 确认改动范围与本项任务一致。
4. 按 AGENT.md 约定推送 `origin` 和 `gitee`，检查 GitHub Actions 状态。
