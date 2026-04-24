"""
Celery 应用配置。
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "sagittadb",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.execute_sql",
        "app.tasks.notify",
        "app.tasks.archive",
        "app.tasks.monitor",
    ],
)

celery_app.conf.update(
    # 序列化
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # 时区
    timezone="Asia/Shanghai",
    enable_utc=True,
    # 任务超时（防止 1.x 的 timeout=-1 永不超时问题）
    task_soft_time_limit=3600,   # 1小时软超时（发送 SoftTimeLimitExceeded）
    task_time_limit=3900,        # 1小时5分钟硬超时（强制 Kill）
    # 结果过期
    result_expires=86400,        # 24小时
    # 队列配置
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "execute":  {"exchange": "execute",  "routing_key": "execute"},   # SQL 执行（高优先级）
        "notify":   {"exchange": "notify",   "routing_key": "notify"},    # 通知（低优先级）
        "archive":  {"exchange": "archive",  "routing_key": "archive"},   # 数据归档
        "monitor":  {"exchange": "monitor",  "routing_key": "monitor"},   # 监控采集
    },
    task_default_queue="default",
    # Worker 并发
    worker_prefetch_multiplier=1,  # execute 队列逐条处理，防止堆积
    # Beat 定时任务（Sprint 5 添加监控采集调度）
    beat_schedule={
        "dispatch-scheduled-workflows-every-minute": {
            "task": "dispatch_scheduled_workflows",
            "schedule": crontab(minute="*"),
            "options": {"queue": "execute"},
        },
        "collect-session-snapshots-every-minute": {
            "task": "collect_session_snapshots",
            "schedule": crontab(minute="*"),
            "options": {"queue": "monitor"},
        },
        "collect-slow-queries-every-five-minutes": {
            "task": "collect_slow_queries",
            "schedule": crontab(minute="*/5"),
            "options": {"queue": "monitor"},
        },
    },
)
