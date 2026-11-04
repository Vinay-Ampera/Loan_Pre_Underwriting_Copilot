"""Application settings. The only place that reads `.env`; never log these values."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: SecretStr | None = None
    report_database_url: SecretStr | None = None  # read-only monitoring login (report_ro)

    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    nvidia_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None

    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_enabled: bool = True  # False = never send traces (tests set this)
    otel_exporter_otlp_endpoint: str = ""  # Tempo (OTLP gRPC); empty = no span export

    app_env: str = "dev"
    jwt_secret: SecretStr = SecretStr("change-me-to-a-long-random-string")
    upload_dir: Path = Path("./data/uploads")
    max_upload_mb: int = 10  # per file
    max_case_upload_mb: int = 60  # per case

    # API (Stage 6)
    llm_enabled: bool = True  # False = no model calls; code writes the report text (browser tests)
    access_token_minutes: int = 15  # renewed in the background while the user is active
    idle_timeout_minutes: int = 30  # no activity for this long = signed out
    session_max_hours: int = 12  # hard limit from sign-in, however active
    idle_warning_minutes: int = 2  # the browser warns this long before the idle sign-out
    refresh_grace_seconds: int = 10  # a second tab may present the token a moment after rotation
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    cors_origins: str = ""  # comma separated; empty = same origin (dev server proxies /api)

    # Customer messages (Stage 9): v1 delivers to the backend terminal only
    notification_sender: str = "console"
    branch_contact_email: str = ""  # optional extra contact lines in customer messages
    branch_contact_phone: str = ""

    def report_sqlalchemy_url(self) -> str | None:
        """REPORT_DATABASE_URL for the auditor's group charts, or None to use DATABASE_URL."""
        if self.report_database_url is None:
            return None
        url = self.report_database_url.get_secret_value()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    def sqlalchemy_url(self) -> str:
        """DATABASE_URL rewritten for SQLAlchemy's psycopg (v3) driver."""
        if self.database_url is None:
            raise RuntimeError("DATABASE_URL is not set in .env")
        url = self.database_url.get_secret_value()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
