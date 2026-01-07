import logging
import json
import traceback
from datetime import datetime
from enum import Enum
from config import config

class ErrorSeverity(Enum):
    LOW = "INFO"
    MEDIUM = "WARNING"
    HIGH = "ERROR"
    CRITICAL = "CRITICAL"

class ErrorHandler:
    """Centralized error handling and structured reporting."""
    
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.error_log_path = config.LOGS_DIR / "critical_errors.json"

    def handle(self, error, context=None, severity=ErrorSeverity.MEDIUM):
        """Log error with context and severity."""
        error_type = type(error).__name__
        msg = f"[{error_type}] {str(error)}"

        # Determine logging level
        log_level = getattr(logging, severity.value)
        self.logger.log(log_level, msg, extra={"context": context} if context else None)

        # For High/Critical, store in a separate structured error log
        if severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self._save_to_error_log(error, context, severity)

    def log_error(self, message, severity=ErrorSeverity.MEDIUM, context=None):
        """Alias for handle() for backward compatibility with lock_manager."""
        # Create a dummy exception with the message
        class LoggedError(Exception):
            pass

        error = LoggedError(message)
        self.handle(error, context=context, severity=severity)

    def _save_to_error_log(self, error, context, severity):
        record = {
            "timestamp": datetime.now().isoformat(),
            "severity": severity.name,
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "context": context or {}
        }
        
        try:
            records = []
            if self.error_log_path.exists():
                with open(self.error_log_path, 'r', encoding='utf-8') as f:
                    try:
                        records = json.load(f)
                    except:
                        pass
            
            records.append(record)
            # Keep last 500 records
            records = records[-500:]
            
            with open(self.error_log_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save error record: {e}")

# Global handler
error_handler = ErrorHandler()
