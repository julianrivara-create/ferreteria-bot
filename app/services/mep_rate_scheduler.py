import atexit
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except Exception:  # pragma: no cover - optional scheduler dependency
    BackgroundScheduler = None
    CronTrigger = None
import structlog

from app.services.catalog_service import CatalogService

logger = structlog.get_logger()

SCHEDULE_HOURS = (11, 14, 17)
_scheduler: BackgroundScheduler | None = None
_scheduler_started = False
_scheduler_lock_fp = None
_scheduler_lock_file = os.getenv("MEP_SCHEDULER_LOCK_FILE", "/tmp/mep_rate_scheduler.lock")

try:
    import fcntl
except ImportError:  # pragma: no cover - fcntl is unavailable on Windows.
    fcntl = None


def _try_acquire_scheduler_lock():
    if fcntl is None:
        return None
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


def _run_scheduled_mep_refresh() -> None:
    try:
        service = CatalogService(auth_sheets=False)
        rate = service.refresh_mep_rate(force=True, use_lock=True)
        logger.info("scheduled_mep_refresh_completed", rate=rate)
    except Exception as e:
        logger.error("scheduled_mep_refresh_failed", error=str(e))


def _shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
    _release_scheduler_lock()


def start_mep_rate_scheduler() -> None:
    global _scheduler, _scheduler_started, _scheduler_lock_fp

    if _scheduler_started:
        return
    _scheduler_started = True

    if BackgroundScheduler is None or CronTrigger is None:
        logger.warning("mep_rate_scheduler_dependency_missing", dependency="apscheduler")
        return

    enabled = os.getenv("MEP_SCHEDULE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
    if not enabled:
        logger.info("mep_rate_scheduler_disabled")
        return

    _scheduler_lock_fp = _try_acquire_scheduler_lock()
    if fcntl is not None and _scheduler_lock_fp is None:
        logger.info("mep_rate_scheduler_skipped_lock_held", lock_file=_scheduler_lock_file)
        return

    timezone_name = os.getenv("MEP_SCHEDULE_TIMEZONE", "America/Argentina/Buenos_Aires").strip()
    if not timezone_name:
        timezone_name = "America/Argentina/Buenos_Aires"

    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning("invalid_mep_schedule_timezone_fallback_to_utc", timezone=timezone_name)
        timezone_name = "UTC"
        timezone = ZoneInfo("UTC")

    scheduler = BackgroundScheduler(timezone=timezone)
    for hour in SCHEDULE_HOURS:
        scheduler.add_job(
            _run_scheduled_mep_refresh,
            trigger=CronTrigger(hour=hour, minute=0, timezone=timezone),
            id=f"mep_refresh_{hour:02d}00",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=1800,
        )

    scheduler.start()
    _scheduler = scheduler
    atexit.register(_shutdown_scheduler)
    logger.info(
        "mep_rate_scheduler_started",
        timezone=timezone_name,
        times=[f"{hour:02d}:00" for hour in SCHEDULE_HOURS],
    )
