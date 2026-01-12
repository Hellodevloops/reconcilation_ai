"""
Celery Configuration for Async Task Processing
Enables background processing for OCR and reconciliation tasks
"""

from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

# Redis configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
celery_app = Celery(
    'reconcile_app',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['tasks.ocr_tasks', 'tasks.reconciliation_tasks']
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

if __name__ == '__main__':
    celery_app.start()

