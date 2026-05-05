"""
AI 路由：Text2SQL 端点。
业务逻辑全部委托给 services/text2sql.py，此处只处理请求解析和响应映射。
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user
from app.services.text2sql import generate_sql

logger = logging.getLogger(__name__)
router = APIRouter()


class Text2SQLRequest(BaseModel):
    question: str
    instance_id: int | None = None
    db_name: str | None = None
    dialect_hint: str | None = None  # 可选：手动指定方言


@router.post("/text2sql/", summary="自然语言转 SQL（AI Text2SQL）")
async def text2sql(
    data: Text2SQLRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not data.question.strip():
        raise HTTPException(400, "问题描述不能为空")

    try:
        result = await generate_sql(
            db=db,
            question=data.question,
            instance_id=data.instance_id,
            db_name=data.db_name,
            dialect_hint=data.dialect_hint,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except httpx.TimeoutException as e:
        raise HTTPException(504, "AI API 请求超时，请重试") from e
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e
    except Exception as e:
        logger.error("text2sql_error: user=%s error=%s", user.get("username"), str(e))
        raise HTTPException(500, f"AI 生成失败：{str(e)}") from e

    return {
        "status": 0,
        "sql": result.sql,
        "db_type": result.db_type,
        "model": result.model,
    }
