import logging
import json
from datetime import datetime
from typing import Any, Dict


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Create console handler if none exists
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _format_log(self, level: str, message: str, **kwargs) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            **kwargs
        }
        return json.dumps(log_data, cls=DateTimeEncoder)

    def info(self, message: str, **kwargs: Any) -> None:
        self.logger.info(self._format_log("INFO", message, **kwargs))

    def error(self, message: str, **kwargs: Any) -> None:
        self.logger.error(self._format_log("ERROR", message, **kwargs))

    def warning(self, message: str, **kwargs: Any) -> None:
        self.logger.warning(self._format_log("WARNING", message, **kwargs))

    def debug(self, message: str, **kwargs: Any) -> None:
        self.logger.debug(self._format_log("DEBUG", message, **kwargs))

    def exception(self, message: str, **kwargs: Any) -> None:
        self.logger.exception(self._format_log("EXCEPTION", message, **kwargs))

# Create logger instances for different components
auth_logger = StructuredLogger("auth")
job_logger = StructuredLogger("jobs")
payment_logger = StructuredLogger("payments")
message_logger = StructuredLogger("messages")
security_logger = StructuredLogger("security")
task_logger = StructuredLogger("tasks")
app_logger = StructuredLogger("app")
