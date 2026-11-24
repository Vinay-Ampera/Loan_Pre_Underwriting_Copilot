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
    max_files_per_upload: int = 60  # files in one bulk upload, zip contents included (Stage 10)

    # API (Stage 6)
    llm_enabled: bool = True  # False = no model calls; code writes the report text (browser tests)
    access_token_minutes: int = 15  # renewed in the background while the user is active
    idle_timeout_minutes: int = 30  # no activity for this long = signed out
    session_max_hours: int = 12  # hard limit from sign-in, however active
    idle_warning_minutes: int = 2  # the browser warns this long before the idle sign-out
    refresh_grace_seconds: int = 10  # a second tab may present the token a moment after rotation
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    # 2-step verification (SECURITY.md 4h): roles that must give an authenticator code after the
    # password, comma separated. An account that has 2-step set up is always asked for it.
    mfa_roles: str = "admin,auditor"
    mfa_token_minutes: int = 5  # from a correct password to the code
    cors_origins: str = ""  # comma separated; empty = same origin (dev server proxies /api)

    # Several documents in one PDF (Stage 10, Part D). Off = a multi-page PDF is one document, as
    # before. The limits are the bundle's own: more pages and a larger file than a single document.
    bundle_split_enabled: bool = True
    bundle_max_pages: int = 120
    bundle_max_mb: int = 25

    # Applicant upload link (Stage 10, Part C)
    upload_link_days: int = 7  # how long a new link stays open; an officer can extend it
    public_base_url: str = "http://localhost:5173"  # where the applicant page is served
    link_max_files: int = 80  # files one link may add in total
    link_rate_per_minute: int = 30  # requests per link per minute (public routes)
    address_rate_per_minute: int = 90  # requests per client address per minute (public routes)

    # Customer messages (Stage 9) and email (Notifications Part 2). console = print in the
    # terminal; smtp = really send, only to EMAIL_ALLOWLIST (or redirected to EMAIL_REDIRECT_TO)
    notification_sender: str = "console"
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_security: str = "ssl"  # ssl | starttls | none
    smtp_username: str = ""
    smtp_password: SecretStr | None = None  # the Resend API key with Resend; never logged
    smtp_timeout_seconds: int = 15
    email_from: str = "Pramaan <onboarding@resend.dev>"
    email_allowlist: str = ""  # exact addresses, comma separated
    email_redirect_to: str = ""  # demo: other addresses are sent here instead
    staff_emails_default: bool = True  # new accounts start with notice emails on
    email_worker_seconds: int = 15  # how often queued staff emails are sent; 0 = never (tests)
    notice_email_gap_minutes: int = 30  # at most one notice email per person in this time
    retention_hours: int = 24  # how often the retention job runs in the app; 0 = never (tests)
    bureau_retention_months: int = 6  # bureau-derived data is kept this long (SECURITY.md 7)
    email_retention_days: int = 90  # sent, held or failed staff email rows are kept this long
    branch_contact_email: str = ""  # optional extra contact lines in customer messages
    branch_contact_phone: str = ""

    def mfa_role_set(self) -> set[str]:
        return {r.strip() for r in self.mfa_roles.split(",") if r.strip()}

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
