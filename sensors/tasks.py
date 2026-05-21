import logging
from celery import shared_task
from .services import fetch_and_filter_hotspots

logger = logging.getLogger(__name__)

@shared_task(name="your_fire_app.tasks.update_malaysia_hotspots")
def update_malaysia_hotspots():
    logger.info("⏰ [Celery] Triggering scheduled 2-hour NASA FIRMS hotspot synchronization...")
    try:
        result = fetch_and_filter_hotspots()
        logger.info(f"✅ [Celery] Synchronization result: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ [Celery] Critical failure in background sync task: {str(e)}")
        return f"Failed due to error: {str(e)}"