"""JSON log lines for Loki. One object per line: time, level, logger, event, plus `extra` fields.

Messages are written by our code from ids and counts. Document text and prompts are never logged
(see SECURITY.md); this formatter adds nothing but the standard fields and explicit `extra`.

Two guards (Stage 11 security pass): libraries that write document text or model prompts and
replies in their DEBUG lines (the PDF parser, LiteLLM, HTTP clients, OCR) are held at WARNING
whatever the root level, and every text field of a line has identifier patterns (PAN, Aadhaar,
GSTIN, email, phone, account number) replaced by their kind before it is written.
"""

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import REPO_ROOT
from app.intake.masker import redact

_STANDARD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}

# Their DEBUG and INFO lines can carry raw document text (pdfminer prints every text operator),
# prompts or replies (LiteLLM), or request bodies (HTTP clients).
CONTENT_LOGGERS = ("pdfminer", "pdfplumber", "fitz", "PIL", "LiteLLM", "LiteLLM Router",
                   "LiteLLM Proxy", "litellm", "httpx", "httpcore", "openai", "urllib3",
                   "RapidOCR", "ppocr", "paddleocr", "pytesseract")  # fmt: skip


def quiet_content_loggers() -> None:
    for name in CONTENT_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _clean(value: object) -> object:
    return redact(value) if isinstance(value, str) else value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": redact(record.getMessage()),
        }
        out.update({k: _clean(v) for k, v in record.__dict__.items() if k not in _STANDARD})
        if record.exc_info:
            out["exception"] = redact(self.formatException(record.exc_info).splitlines()[-1])
        return json.dumps(out, default=str)


def configure_logging(log_dir: Path | None = REPO_ROOT / "logs", level: int = logging.INFO) -> None:
    """JSON lines to stdout and to `logs/app.log` at the repository root (where Promtail reads
    them, whatever directory the server was started from)."""
    quiet_content_loggers()
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


quiet_content_loggers()  # also when only the formatter is imported (tests, command line)
