import json
import os
import time
import fcntl
from datetime import datetime, timezone
from .logging_config import logger
from .paths import state_file_path

STATE_FILE = state_file_path()


def _state_file() -> str:
    configured = (globals().get("STATE_FILE") or "").strip()
    if configured:
        return configured
    return state_file_path()

def get_empty_state():
    return {
        "last_run_ts": None,
        "last_success_ts": None,
        "last_ok_ts": None,
        "last_digest_ts": None,
        "last_status": "UNKNOWN",
        "last_run_duration_ms": 0,
        "cost_counters": {
            "log_pulls_today": 0,
            "log_bytes_today": 0,
            "log_last_reset_date": datetime.now(timezone.utc).date().isoformat()
        }
    }

def read_state():
    """Reads state with shared lock."""
    state_file = _state_file()
    if not os.path.exists(state_file):
        return get_empty_state()
    
    try:
        with open(state_file, "r") as f:
            try:
                # Shared lock (LOCK_SH)
                fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
                data = json.load(f)
                fcntl.flock(f, fcntl.LOCK_UN)
                return data
            except (IOError, json.JSONDecodeError):
                # Fallback if locked or corrupt
                logger.warning("Could not acquire lock or state corrupt, reading without lock")
                f.seek(0)
                return json.load(f)
    except Exception as e:
        logger.error(f"Error reading state: {e}")
        return get_empty_state()

def write_state(data):
    """Writes state with exclusive lock and atomic rename."""
    state_file = _state_file()
    state_dir = os.path.dirname(state_file) or "."
    os.makedirs(state_dir, exist_ok=True)
    temp_file = f"{state_file}.tmp"
    
    try:
        # Atomic write pattern
        with open(temp_file, "w") as f:
            # Exclusive lock (LOCK_EX)
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
                fcntl.flock(f, fcntl.LOCK_UN)
            except IOError:
                logger.warning("Could not acquire exclusive lock for state write, retrying once")
                time.sleep(0.5)
                json.dump(data, f, indent=2)
        
        os.replace(temp_file, state_file)
    except Exception as e:
        logger.error(f"Error writing state: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

def update_counters(pulls=0, bytes_val=0):
    """Updates global cost counters in state.json."""
    state = read_state()
    today = datetime.now(timezone.utc).date().isoformat()
    
    if state["cost_counters"]["log_last_reset_date"] != today:
        logger.info(f"New day detected ({today}). Resetting cost counters.")
        state["cost_counters"] = {
            "log_pulls_today": pulls,
            "log_bytes_today": bytes_val,
            "log_last_reset_date": today
        }
    else:
        state["cost_counters"]["log_pulls_today"] += pulls
        state["cost_counters"]["log_bytes_today"] += bytes_val
        
    write_state(state)
