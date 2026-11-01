"""`uvicorn app.main:app` entry point (the app itself is built in `app.api.main`)."""

from app.api.main import create_app
from app.observability.logs import configure_logging

configure_logging()
app = create_app()
