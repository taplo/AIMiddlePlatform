import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

_buffer: deque[dict[str, Any]] | None = None
_lock = threading.Lock()
_maxlen = 1000


class LogBuffer(logging.Handler):
    def __init__(self, maxlen: int = 1000, level: int = logging.INFO):
        super().__init__(level=level)
        self.maxlen = maxlen
        self.buffer = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatter.formatException(record.exc_info) if self.formatter else ""
        self.buffer.append(entry)

    def get_all(self) -> list[dict[str, Any]]:
        return list(self.buffer)

    def _log(self, level: int, msg: str, *args: Any) -> None:
        if level < self.level:
            return
        record = logging.LogRecord(
            name="LogBuffer",
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=args,
            exc_info=None,
        )
        self.emit(record)

    def debug(self, msg: str, *args: Any) -> None:
        self._log(logging.DEBUG, msg, *args)

    def info(self, msg: str, *args: Any) -> None:
        self._log(logging.INFO, msg, *args)

    def warning(self, msg: str, *args: Any) -> None:
        self._log(logging.WARNING, msg, *args)

    def error(self, msg: str, *args: Any) -> None:
        self._log(logging.ERROR, msg, *args)


def init_log_buffer(maxlen: int = 1000, level: int = logging.INFO) -> None:
    global _buffer, _maxlen
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, LogBuffer):
            root.removeHandler(h)
    handler = LogBuffer(maxlen=maxlen, level=level)
    handler.setFormatter(logging.Formatter())
    root.addHandler(handler)
    root.setLevel(level)
    _maxlen = maxlen
    _buffer = handler.buffer


def get_logs(
    level: str | None = None,
    module: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    global _buffer
    if _buffer is None:
        return {"logs": [], "total": 0}
    with _lock:
        entries = list(_buffer)
    if level:
        entries = [e for e in entries if e["level"] == level.upper()]
    if module:
        entries = [e for e in entries if module.lower() in e["logger"].lower()]
    if q:
        ql = q.lower()
        entries = [e for e in entries if ql in e["message"].lower()]
    entries.reverse()
    total = len(entries)
    sliced = entries[offset : offset + limit]
    return {"logs": sliced, "total": total}


def clear_logs() -> None:
    global _buffer
    with _lock:
        if _buffer is not None:
            _buffer.clear()
