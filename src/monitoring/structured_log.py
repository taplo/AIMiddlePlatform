import json
import logging
import sys
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            entry.update(record.extra_fields)
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_json_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and isinstance(handler.formatter, JSONFormatter):
            return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_with_fields(logger: logging.Logger, level: int, message: str, **fields) -> None:
    if logger.isEnabledFor(level):
        record = logger.makeRecord(
            logger.name, level, "", 0, message, (), None
        )
        record.extra_fields = fields
        logger.handle(record)
