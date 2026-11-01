"""`uvicorn app.main:app` entry point (the app itself is built in `app.api.main`)."""

from app.api.main import create_app

app = create_app()
