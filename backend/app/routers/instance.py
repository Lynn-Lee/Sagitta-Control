"""实例管理路由。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.schemas.instance import (
    InstanceCreate,
    InstanceUpdate,
    TunnelCreate,
)
from app.services.instance import InstanceService, TunnelService
from app.services.instance_database import InstanceDatabaseService
from app.services.query_priv import QueryPrivService

router = APIRouter()


async def _ensure_data_dict_access(
    db: AsyncSession,
    user: dict,
    instance_id: int,
    db_name: str = "",
    tb_name: str = "",
):
    inst = await _ensure_instance_access(db, user, instance_id)
    allowed, reason = await QueryPrivService.check_data_dict_access(
        db=db,
        user=user,
        instance=inst,
        db_name=db_name,
        table_name=tb_name,
    )
    if not allowed:
        raise HTTPException(403, "暂无数据字典访问权限，请先申请对应范围的查询权限")
    return inst


def _validate_resource_group_scope(user: dict, resource_group_ids: list[int] | None) -> None:
    if not resource_group_ids:
        return
    if user.get("is_superuser") or "query_all_instances" in user.get("permissions", []):
        return
    allowed_rg_ids = set(user.get("resource_groups", []))
    requested_rg_ids = set(resource_group_ids)
    if not requested_rg_ids.issubset(allowed_rg_ids):
        raise HTTPException(403, "不能操作资源组外的实例")


# ─── 实例 CRUD ────────────────────────────────────────────────


@router.get("/", summary="实例列表")
async def list_instances(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db_type: str | None = None,
    search: str | None = None,
    resource_group_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    total, items = await InstanceService.list_instances(
        db,
        page=page,
        page_size=page_size,
        db_type=db_type,
        search=search,
        resource_group_id=resource_group_id,
        user=user,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [InstanceService.to_response(i) for i in items],
    }


async def _ensure_instance_access(db: AsyncSession, user: dict, instance_id: int):
    from fastapi import HTTPException

    inst = await InstanceService.get_by_id(db, instance_id)
    if user.get("is_superuser") or "query_all_instances" in user.get("permissions", []):
        return inst

    user_rg_ids = set(user.get("resource_groups", []))
    instance_rg_ids = {rg.id for rg in inst.resource_groups}
    if user_rg_ids & instance_rg_ids:
        return inst
    raise HTTPException(403, "实例不在你的资源组内")


@router.post("/", summary="新建实例", dependencies=[Depends(require_perm("instance_manage"))])
async def create_instance(
    data: InstanceCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    _validate_resource_group_scope(user, data.resource_group_ids)
    inst = await InstanceService.create(db, data)
    return {"status": 0, "msg": "实例创建成功", "data": InstanceService.to_response(inst)}


@router.get("/{instance_id}/", summary="实例详情")
async def get_instance(
    instance_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    inst = await _ensure_instance_access(db, user, instance_id)
    return InstanceService.to_response(inst)


@router.put(
    "/{instance_id}/", summary="修改实例", dependencies=[Depends(require_perm("instance_manage"))]
)
async def update_instance(
    instance_id: int,
    data: InstanceUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    await _ensure_instance_access(db, user, instance_id)
    _validate_resource_group_scope(user, data.resource_group_ids)
    inst = await InstanceService.update(db, instance_id, data)
    return {"status": 0, "msg": "实例已更新", "data": InstanceService.to_response(inst)}


@router.delete(
    "/{instance_id}/",
    summary="删除实例",
    dependencies=[Depends(require_perm("instance_manage"))],
)
async def delete_instance(
    instance_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    await _ensure_instance_access(db, user, instance_id)
    await InstanceService.delete(db, instance_id)
    return {"status": 0, "msg": "实例已删除"}


@router.post("/{instance_id}/test/", summary="测试连接")
async def test_connection(
    instance_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    await _ensure_instance_access(db, user, instance_id)
    result = await InstanceService.test_connection(db, instance_id)
    return result


@router.get("/{instance_id}/databases/", summary="获取数据库列表")
async def get_databases(
    instance_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    inst = await _ensure_data_dict_access(db, user, instance_id)
    registered = await InstanceDatabaseService.list_databases(
        db, instance_id, include_inactive=True
    )
    if user.get("is_superuser", False):
        return {"databases": registered}

    allowed_database_names = await QueryPrivService.list_data_dict_databases(
        db=db,
        user=user,
        instance=inst,
        database_names=[item["db_name"] for item in registered],
    )
    allowed_set = set(allowed_database_names)
    return {
        "databases": [item for item in registered if item["db_name"] in allowed_set]
    }


@router.get("/{instance_id}/tables/", summary="获取表列表")
async def get_tables(
    instance_id: int,
    db_name: str = Query(..., description="数据库名"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    inst = await _ensure_data_dict_access(db, user, instance_id, db_name=db_name)
    tables = await InstanceService.get_tables(db, instance_id, db_name)
    tables = await QueryPrivService.list_data_dict_tables(
        db=db,
        user=user,
        instance=inst,
        db_name=db_name,
        table_names=tables,
    )
    return {"tables": tables}


@router.get("/{instance_id}/columns/", summary="获取列信息")
async def get_columns(
    instance_id: int,
    db_name: str = Query(...),
    tb_name: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    await _ensure_data_dict_access(db, user, instance_id, db_name=db_name, tb_name=tb_name)
    columns = await InstanceService.get_columns(db, instance_id, db_name, tb_name)
    return {"columns": columns}


@router.get("/{instance_id}/constraints/", summary="获取表约束信息")
async def get_constraints(
    instance_id: int,
    db_name: str = Query(...),
    tb_name: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    await _ensure_data_dict_access(db, user, instance_id, db_name=db_name, tb_name=tb_name)
    constraints = await InstanceService.get_constraints(db, instance_id, db_name, tb_name)
    return {"constraints": constraints}


@router.get("/{instance_id}/indexes/", summary="获取表索引信息")
async def get_indexes(
    instance_id: int,
    db_name: str = Query(...),
    tb_name: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    await _ensure_data_dict_access(db, user, instance_id, db_name=db_name, tb_name=tb_name)
    indexes = await InstanceService.get_indexes(db, instance_id, db_name, tb_name)
    return {"indexes": indexes}


@router.get("/{instance_id}/params/", summary="实例参数列表")
async def get_params(
    instance_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(current_user),
):
    await _ensure_instance_access(db, user, instance_id)
    params = await InstanceService.get_variables(db, instance_id)
    return {"params": params}


# ─── SSH 隧道 ─────────────────────────────────────────────────

# ── 实例数据库管理（Pack C2）────────────────────────────────


@router.get("/{instance_id}/db-list/", summary="已注册数据库列表")
async def list_registered_databases(
    instance_id: int,
    include_inactive: bool = False,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_instance_access(db, user, instance_id)
    show_inactive = user.get("is_superuser", False) or include_inactive
    items = await InstanceDatabaseService.list_databases(db, instance_id, show_inactive)
    return {"items": items, "total": len(items)}


@router.post(
    "/{instance_id}/db-list/",
    summary="手动添加数据库",
    dependencies=[Depends(require_perm("instance_manage"))],
)
async def add_database(
    instance_id: int,
    data: dict,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_instance_access(db, user, instance_id)
    db_name = data.get("db_name", "").strip()
    remark = data.get("remark", "")
    if not db_name:
        raise HTTPException(400, "db_name 不能为空")
    idb = await InstanceDatabaseService.add_database(db, instance_id, db_name, remark)
    return {"status": 0, "msg": f"数据库 '{db_name}' 添加成功", "data": {"id": idb.id}}


@router.put(
    "/{instance_id}/db-list/{idb_id}/",
    summary="更新数据库备注/状态",
    dependencies=[Depends(require_perm("instance_manage"))],
)
async def update_database(
    instance_id: int,
    idb_id: int,
    data: dict,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_instance_access(db, user, instance_id)
    idb = await InstanceDatabaseService.update_database(
        db,
        idb_id,
        remark=data.get("remark"),
        is_active=data.get("is_active"),
    )
    return {"status": 0, "msg": "已更新", "data": {"id": idb.id}}


@router.delete(
    "/{instance_id}/db-list/{idb_id}/",
    summary="删除数据库注册",
    dependencies=[Depends(require_perm("instance_manage"))],
)
async def delete_database(
    instance_id: int,
    idb_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_instance_access(db, user, instance_id)
    await InstanceDatabaseService.delete_database(db, idb_id)
    return {"status": 0, "msg": "已删除"}


@router.post("/{instance_id}/db-list/sync/", summary="从引擎自动同步数据库列表")
async def sync_databases(
    instance_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_instance_access(db, user, instance_id)
    result = await InstanceDatabaseService.sync_from_engine(db, instance_id)
    return result


@router.get("/tunnels/", summary="SSH 隧道列表")
async def list_tunnels(
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_user),
):
    tunnels = await TunnelService.list_tunnels(db)
    return {
        "tunnels": [
            {
                "id": t.id,
                "tunnel_name": t.tunnel_name,
                "host": t.host,
                "port": t.port,
                "user": t.user,
            }
            for t in tunnels
        ]
    }


@router.post(
    "/tunnels/", summary="新建 SSH 隧道", dependencies=[Depends(require_perm("instance_manage"))]
)
async def create_tunnel(
    data: TunnelCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_user),
):
    tunnel = await TunnelService.create(db, data)
    return {
        "status": 0,
        "msg": "SSH 隧道已创建",
        "data": {"id": tunnel.id, "tunnel_name": tunnel.tunnel_name},
    }


@router.delete(
    "/tunnels/{tunnel_id}/",
    summary="删除 SSH 隧道",
    dependencies=[Depends(require_perm("instance_manage"))],
)
async def delete_tunnel(
    tunnel_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_user),
):
    await TunnelService.delete(db, tunnel_id)
    return {"status": 0, "msg": "SSH 隧道已删除"}
