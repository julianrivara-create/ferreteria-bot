
from app.db.session import SessionLocal
from app.db.models import Order, OrderStatus, IdempotencyKey, Product
from app.core.config import get_settings
from app.services.stock_sheet_sync import StockSheetSync
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()
settings = get_settings()

def expire_holds_job():
    session = SessionLocal()
    try:
        # 15 min expiration
        expiry_threshold = datetime.utcnow() - timedelta(minutes=15)
        expired_holds = session.query(Order).filter(
            Order.status == OrderStatus.HOLD,
            Order.updated_at < expiry_threshold
        ).all()
        
        for order in expired_holds:
            order.status = OrderStatus.EXPIRED
            # Release stock logic if reserved (simplified here)
            # In V2 we reserve at Hold? No, usually at confirmation. 
            # If we reserved at Hold, we would release here.
            # Assuming Hold is just soft hold for now.
            logger.info("hold_expired", order_id=str(order.id))
        
        session.commit()
    except Exception as e:
        logger.error("job_error", job="expire_holds", error=str(e))
    finally:
        session.close()

def cleanup_idempotency_keys_job():
    session = SessionLocal()
    try:
        # Delete keys older than 30 days
        threshold = datetime.utcnow() - timedelta(days=30)
        session.query(IdempotencyKey).filter(IdempotencyKey.created_at < threshold).delete()
        session.commit()
    except Exception as e:
        logger.error("job_error", job="cleanup_idempotency", error=str(e))
    finally:
        session.close()

def stock_sync_job():
    """
    Sync stock from Google Sheets to DB.
    Skips safely when Sheets credentials are not configured yet.
    """
    spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
    if not spreadsheet_id:
        logger.info("stock_sync_skipped", reason="missing_spreadsheet_id")
        return

    session = SessionLocal()
    try:
        syncer = StockSheetSync(
            spreadsheet_id=spreadsheet_id,
            service_account_json=settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON,
            service_account_path=settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_PATH,
        )
        result = syncer.sync_to_database(session)
        logger.info("stock_sync_job_result", result=result)
    except Exception as e:
        logger.error("job_error", job="stock_sync", error=str(e))
    finally:
        session.close()
