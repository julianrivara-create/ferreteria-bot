
import time
import schedule
from app.worker.jobs import expire_holds_job, cleanup_idempotency_keys_job, stock_sync_job
from app.core.logging import configure_logging
from app.core.config import get_settings
import structlog

configure_logging()
logger = structlog.get_logger()
settings = get_settings()

def run_scheduler():
    logger.info("scheduler_started", 
               google_sheets_enabled=settings.GOOGLE_SHEETS_ENABLED)
    
    # Expire holds every 60 seconds
    schedule.every(60).seconds.do(expire_holds_job)
    
    # Cleanup idempotency keys daily at 3 AM
    schedule.every().day.at("03:00").do(cleanup_idempotency_keys_job)
    
    # Stock Sync: Twice daily at 12:00 PM and 8:00 PM (Buenos Aires time)
    # Note: Railway runs in UTC, so adjust if needed
    # 12:00 PM ART = 15:00 UTC (UTC-3)
    # 8:00 PM ART = 23:00 UTC
    schedule.every().day.at("15:00").do(stock_sync_job)  # 12:00 PM ART
    schedule.every().day.at("23:00").do(stock_sync_job)  # 8:00 PM ART
    logger.info("stock_sync_scheduled", times=["15:00 UTC (12:00 PM ART)", "23:00 UTC (8:00 PM ART)"])
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    run_scheduler()
