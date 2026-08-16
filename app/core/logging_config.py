import contextvars
import json
import logging
import time
from typing import Any

# Global contextvar to hold the correlation ID for the current request context
correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")

class StructuredJSONFormatter(logging.Formatter):
    """
    JSON formatter that structures logs as JSON objects.
    Automatically injects the correlation ID from contextvars.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt or "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_ctx.get(),
            "module": record.module,
            "line": record.lineno,
        }
        
        # Inject traceback details if exception occurred
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        # Include extra attributes passed via logger.info("msg", extra={"key": "val"})
        for key, val in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName"
            }:
                log_record[key] = val
                
        return json.dumps(log_record)

def setup_logging(level: str = "INFO") -> None:
    """
    Configure the root logger to output structured JSON to stdout.
    """
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    formatter = StructuredJSONFormatter()
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Mute third party libraries to prevent clutter
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
