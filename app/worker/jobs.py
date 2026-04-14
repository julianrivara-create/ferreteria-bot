
from app.db.session import SessionLocal
from app.db.models import Order, OrderStatus, IdempotencyKey, Product, InventoryEvent
from app.core.config import get_settings
from app.services.stock_sheet_sync import StockSheetSync
from datetime import datetime, timedelta, timezone
import structlog

logger = structlog.get_logger()
settings = get_settings()

def expire_holds_job():
    session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        expired_holds = session.query(Order).filter(
            Order.status == OrderStatus.HOLD,
            Order.expires_at.isnot(None),
            Order.expires_at <= now,
        ).all()
        
        for order in expired_holds:
            for item in order.items:
                product = session.query(Product).filter(
                    Product.tenant_id == order.tenant_id,
                    Product.sku == item.sku,
                ).with_for_update().first()
                if product and product.reserved_qty >= item.quantity:
                    product.reserved_qty -= item.quantity
                    session.add(InventoryEvent(
                        tenant_id=order.tenant_id,
                        sku=item.sku,
                        delta_on_hand=0,
                        delta_reserved=-item.quantity,
                        reason="hold_expired",
                        source="expire_holds_job",
                    ))
            order.status = OrderStatus.EXPIRED
            order.updated_at = now
            logger.info("hold_expired", order_id=str(order.id))
        
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("job_error", job="expire_holds", error=str(e))
    finally:
        session.close()

def cleanup_idempotency_keys_job():
    session = SessionLocal()
    try:
        # Delete keys older than 30 days
        threshold = datetime.now(timezone.utc) - timedelta(days=30)
        session.query(IdempotencyKey).filter(IdempotencyKey.created_at < threshold).delete()
        session.commit()
    except Exception as e:
        session.rollback()
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
    if not settings.DEFAULT_TENANT_ID:
        logger.info("stock_sync_skipped", reason="missing_default_tenant_id")
        return

    session = SessionLocal()
    try:
        syncer = StockSheetSync(
            spreadsheet_id=spreadsheet_id,
            service_account_json=settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON,
            service_account_path=settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_PATH,
            tenant_id=settings.DEFAULT_TENANT_ID,
        )
        result = syncer.sync_to_database(session, tenant_id=settings.DEFAULT_TENANT_ID)
        logger.info("stock_sync_job_result", result=result)
    except Exception as e:
        session.rollback()
        logger.error("job_error", job="stock_sync", error=str(e))
    finally:
        session.close()
