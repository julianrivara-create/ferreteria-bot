import logging
import os
from logging.handlers import RotatingFileHandler
from .paths import logs_dir_path

def setup_logging(level=None):
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
    
    # Ensure persistent log directory exists
    log_dir = logs_dir_path()
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger("maintenance")
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger
    
    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console Handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File Handler (Rolling)
    fh = RotatingFileHandler(
        os.path.join(log_dir, "maintenance.log"),
        maxBytes=5*1024*1024,  # 5MB
        backupCount=5
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    return logger

logger = setup_logging()
