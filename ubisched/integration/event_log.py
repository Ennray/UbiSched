"""Console + UTF-8 rotating text/JSONL logs. Logging never changes task state."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import threading
import time

LOG = logging.getLogger("ubisched")
LOG.addHandler(logging.NullHandler())
_limits = {}
_limit_lock = threading.Lock()


class EventFormatter(logging.Formatter):
    def format(self, record):
        stamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        values = getattr(record, "fields", {})
        details = " ".join(f"{k}={json.dumps(v, ensure_ascii=False, default=str)}" for k, v in values.items())
        return f"{stamp}.{int(record.msecs):03d} {record.levelname} [{record.name}] [{getattr(record, 'event', 'message')}] {record.getMessage()} {details}".rstrip()


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"time": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
                           "timestamp": record.created, "level": record.levelname,
                           "logger": record.name, "pid": record.process, "thread": record.threadName,
                           "event": getattr(record, "event", "message"), "message": record.getMessage(),
                           **getattr(record, "fields", {})}, ensure_ascii=False, default=str)


def configure_logging(directory=None, role="server"):
    directory = Path(directory or os.environ.get("UBISCHED_LOG_DIR", "logs/ubisched")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    role = re.sub(r"[^\w.-]", "_", role)
    text_path, json_path = directory/f"{role}.log", directory/f"{role}.jsonl"
    handlers = []
    try:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(EventFormatter())
        handlers.append(console)
        for path, formatter in ((text_path, EventFormatter()), (json_path, JsonFormatter())):
            handler = RotatingFileHandler(path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
            handler.setFormatter(formatter)
            handlers.append(handler)
    except Exception:
        for handler in handlers:
            handler.close()
        raise
    for handler in list(LOG.handlers):
        LOG.removeHandler(handler)
        handler.close()
    LOG.setLevel(logging.INFO)
    LOG.propagate = False
    for handler in handlers:
        LOG.addHandler(handler)
    event(LOG, "logging_ready", "日志已启用", text_file=str(text_path), jsonl_file=str(json_path))
    return text_path, json_path


def event(logger, event_name, message, *, level=logging.INFO, **fields):
    logger.log(level, message, extra={"event": event_name, "fields": fields})


def limited_event(logger, event_name, message, *, key=None, interval=30, level=logging.INFO, **fields):
    now = time.monotonic()
    token = (logger.name, event_name, str(key))
    with _limit_lock:
        if now - _limits.get(token, float("-inf")) < interval:
            return
        if len(_limits) > 2048:
            _limits.clear()
        _limits[token] = now
    event(logger, event_name, message, level=level, **fields)
