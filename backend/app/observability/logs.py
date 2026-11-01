"""JSON log lines for Loki. One object per line: time, level, logger, event, plus `extra` fields.

Messages are written by our code from ids and counts. Document text and prompts are never logged
(see SECURITY.md); this formatter adds nothing but the standard fields and explicit `extra`.
"""

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_STANDARD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        out.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD})
        if record.exc_info:
            out["exception"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(out, default=str)


def configure_logging(log_dir: Path | None = Path("logs"), level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return  # already set up (reload, repeated imports)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_dir / "app.log", maxBytes=5_000_000, backupCount=3))
    for h in handlers:
        h.setFormatter(JsonFormatter())
        root.addHandler(h)
    root.setLevel(level)
