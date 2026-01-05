import logging
import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from config import config

class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)

def setup_logging():
    """Setup structured logging with JSON formatting and rotation."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO if not config.FLASK_DEBUG else logging.DEBUG)
    
    # Console Handler (Human-friendly)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(console_handler)
    
    # JSON File Handler (Rotation: 5MB per file, kept 5 backups)
    log_file = config.LOGS_DIR / f"app_{datetime.now():%Y%m%d}.json"
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)
    
    return logger

# Initialize logging when imported
logger = setup_logging()
