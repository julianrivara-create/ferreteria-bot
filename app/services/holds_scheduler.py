"""
Scheduler that periodically cleans up expired product holds.

Runs every 5 minutes using APScheduler's BackgroundScheduler,
following the same pattern as mep_rate_scheduler.py.
"""

import atexit
import os

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
except Exception:  # pragma: no cover - optional dependency
    BackgroundScheduler = None
    IntervalTrigger = None

try:
    import fcntl
except ImportError:  # pragma: no cover - unavailable on Windows
    fcntl = None

import structlog

logger = structlog.get_logger()

_scheduler: "BackgroundScheduler | None" = None
_scheduler_started = False
_scheduler_lock_fp = None
_scheduler_lock_file = os.getenv("HOLDS_SCHEDULER_LOCK_FILE", "/tmp/holds_scheduler.lock")

CLEANUP_INTERVAL_MINUTES = int(os.getenv("HOLDS_CLEANUP_INTERVAL_MINUTES", "5"))


def _try_acquire_scheduler_lock():
    if fcntl is None:
        return None
    from pathlib import Path
    lock_path = Path(_scheduler_lock_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fp = lock_path.open("a+")
    try:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fp
    except BlockingIOError:
        lock_fp.close()
        return None
    except Exception:
        lock_fp.close()
        raise


def _release_scheduler_lock() -> None:
    global _scheduler_lock_fp
    if not _scheduler_lock_fp:
        return
    try:
        if fcntl is not None:
            fcntl.flock(_scheduler_lock_fp.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    finally:
        _scheduler_lock_fp.close()
        _scheduler_lock_fp = None


def _cleanup_expired_holds() -> None:
    """Delete expired holds across all active tenants."""
    try:
        from bot_sales.core.tenancy import tenant_manager
    except Exception as e:
        logger.error("holds_cleanup_import_failed", error=str(e))
        return

    for tenant_id, tenant in tenant_manager.tenants.items():
        try:
            db = tenant_manager.get_db(tenant_id)
            deleted = db.cleanup_holds()
            if deleted:
                logger.info(
                    "holds_cleanup_completed",
                    tenant_id=tenant_id,
                    deleted=deleted,
                )
        except Exception as e:
            logger.error(
                "holds_cleanup_failed",
                tenant_id=tenant_id,
                error=str(e),
            )


def _shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
    _release_scheduler_lock()


def start_holds_scheduler() -> None:
    """Start the background scheduler for expired-holds cleanup.

    Safe to call multiple times — only one scheduler will ever be started.
    Respects HOLDS_SCHEDULE_ENABLED=0/false/no to disable.
    """
    global _scheduler, _scheduler_started, _scheduler_lock_fp

    if _scheduler_started:
        return
    _scheduler_started = True

    if BackgroundScheduler is None or IntervalTrigger is None:
        logger.warning(
            "holds_scheduler_dependency_missing", dependency="apscheduler"
        )
        return

    enabled = (
        os.getenv("HOLDS_SCHEDULE_ENABLED", "1").strip().lower()
        not in {"0", "false", "no"}
    )
    if not enabled:
        logger.info("holds_scheduler_disabled")
        return

    _scheduler_lock_fp = _try_acquire_scheduler_lock()
    if fcntl is not None and _scheduler_lock_fp is None:
        logger.info(
            "holds_scheduler_skipped_lock_held", lock_file=_scheduler_lock_file
        )
        return

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _cleanup_expired_holds,
        trigger=IntervalTrigger(minutes=CLEANUP_INTERVAL_MINUTES),
        id="holds_cleanup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )

    scheduler.start()
    _scheduler = scheduler
    atexit.register(_shutdown_scheduler)
    logger.info(
        "holds_scheduler_started",
        interval_minutes=CLEANUP_INTERVAL_MINUTES,
    )
