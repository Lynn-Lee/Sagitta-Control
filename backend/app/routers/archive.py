"""Data archive routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.services.archive import ARCHIVE_SUPPORT, ArchiveService

router = APIRouter()


class ArchiveRequest(BaseModel):
    source_instance_id: int
    source_db: str
    source_table: str
    condition: str = Field(..., description="WHERE 条件（MongoDB 需为 JSON 格式）")
    archive_mode: str = Field(default="purge", description="purge=直接删除 dest=归档到目标")
    dest_instance_id: int | None = None
    dest_db: str | None = None
    dest_table: str | None = None
    batch_size: int = Field(default=1000, ge=1, le=10000)
    sleep_ms: int = Field(default=100, ge=0, le=10000)
    dry_run: bool = Field(default=True, description="兼容旧字段；run 接口不再同步执行")
    apply_reason: str = Field(default="", max_length=500)
    flow_id: int | None = Field(default=None, description="审批流模板 ID")


@router.get("/support/", summary="查询数据库归档支持情况")
async def get_archive_support(_user=Depends(current_user)):
    return {
        "support": {
            db_type: {
                "purge": cfg.get("purge", False),
                "dest": cfg.get("dest", False),
                "reason": cfg.get("reason", ""),
                "verified": cfg.get("verified", False),
            }
            for db_type, cfg in ARCHIVE_SUPPORT.items()
        }
    }


@router.post("/estimate/", summary="估算归档影响行数（不执行）")
async def estimate_archive(
    data: ArchiveRequest,
    _user=Depends(require_perm("archive_apply")),
    db: AsyncSession = Depends(get_db),
):
    return await ArchiveService.estimate_rows(
        db, data.source_instance_id, data.source_db, data.source_table, data.condition
    )


@router.post("/run/", summary="提交归档作业并进入审批")
async def submit_archive_job(
    data: ArchiveRequest,
    user=Depends(require_perm("archive_apply")),
    db: AsyncSession = Depends(get_db),
):
    job = await ArchiveService.submit_job(db, data, user)
    return {
        "success": True,
        "msg": "归档作业已提交审批",
        "job_id": job.id,
        "workflow_id": job.workflow_id,
        "status": job.status,
        "estimated_rows": job.estimated_rows,
    }


@router.get("/jobs/", summary="归档作业列表")
async def list_archive_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, items = await ArchiveService.list_jobs(db, user, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/jobs/{job_id}/", summary="归档作业详情")
async def get_archive_job(
    job_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ArchiveService.get_job(db, job_id, user)


@router.get("/jobs/{job_id}/status/", summary="归档作业状态")
async def get_archive_job_status(
    job_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await ArchiveService.get_job(db, job_id, user)
    return {
        "job_id": job["id"],
        "workflow_id": job["workflow_id"],
        "status": job["status"],
        "estimated_rows": job["estimated_rows"],
        "processed_rows": job["processed_rows"],
        "current_batch": job["current_batch"],
        "error_message": job["error_message"],
    }


@router.post("/jobs/{job_id}/start/", summary="启动已审批归档作业")
async def start_archive_job(
    job_id: int,
    user=Depends(require_perm("archive_apply")),
    db: AsyncSession = Depends(get_db),
):
    job = await ArchiveService.start_job(db, job_id, user)
    return {"success": True, "msg": "归档作业已加入后台队列", "job_id": job.id, "status": job.status}


@router.post("/jobs/{job_id}/pause/", summary="暂停归档作业")
async def pause_archive_job(
    job_id: int,
    user=Depends(require_perm("archive_apply")),
    db: AsyncSession = Depends(get_db),
):
    job = await ArchiveService.set_job_control_state(db, job_id, "pause", user)
    return {"success": True, "msg": "暂停请求已提交，将在当前批次完成后生效", "job_id": job.id, "status": job.status}


@router.post("/jobs/{job_id}/resume/", summary="继续归档作业")
async def resume_archive_job(
    job_id: int,
    user=Depends(require_perm("archive_apply")),
    db: AsyncSession = Depends(get_db),
):
    job = await ArchiveService.set_job_control_state(db, job_id, "resume", user)
    job = await ArchiveService.start_job(db, job.id, user)
    return {"success": True, "msg": "归档作业已继续执行", "job_id": job.id, "status": job.status}


@router.post("/jobs/{job_id}/cancel/", summary="取消归档作业")
async def cancel_archive_job(
    job_id: int,
    user=Depends(require_perm("archive_apply")),
    db: AsyncSession = Depends(get_db),
):
    job = await ArchiveService.set_job_control_state(db, job_id, "cancel", user)
    return {"success": True, "msg": "取消请求已提交；执行中作业将在当前批次完成后停止", "job_id": job.id, "status": job.status}
