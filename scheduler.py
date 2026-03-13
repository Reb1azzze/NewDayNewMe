# scheduler.py
import logging
from datetime import time as dt_time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

def create_scheduled_job(
    scheduler: AsyncIOScheduler,
    send_digest_func,
    chat_id: int,
    send_time_str: str
):
    """Создаёт задачу в APScheduler"""
    h, m = map(int, send_time_str.split(":"))
    send_time = dt_time(hour=h, minute=m)

    job_id = f"digest_{chat_id}"
    scheduler.add_job(
        send_digest_func,
        trigger=CronTrigger(hour=send_time.hour, minute=send_time.minute, timezone="Europe/Moscow"),
        args=[chat_id],
        id=job_id,
        replace_existing=True,
        name=job_id,
    )
    logger.info(f"📅 Scheduled job {job_id} for {send_time_str}")


def remove_scheduled_job(scheduler: AsyncIOScheduler, chat_id: int):
    """Удаляет задачу из APScheduler"""
    job_id = f"digest_{chat_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"🗑️ Removed job {job_id}")