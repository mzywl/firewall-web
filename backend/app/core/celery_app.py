from celery import Celery
import os

# Redis 配置
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# 创建 Celery 实例
celery_app = Celery(
    "firewall_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1小时超时
    worker_prefetch_multiplier=1,
)

# 自动发现任务
celery_app.autodiscover_tasks(["app.tasks"])
