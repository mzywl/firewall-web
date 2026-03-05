"""
Celery tasks initialization
"""
from .push_tasks import push_policies_task

__all__ = ["push_policies_task"]
