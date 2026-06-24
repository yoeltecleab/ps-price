"""Application configuration via Pydantic Settings.

This module is the **control panel** for the whole backend. Instead of hard-
coding paths, URLs, and secrets in many files, we read them once from:

  1. Environment variables starting with ``PS_PRICE_`` (e.g. ``PS_PRICE_DATABASE_URL``)
  2. An optional ``.env`` file in the project root (for local development)

Pydantic's ``BaseSettings`` validates types automatically — if you set
``PS_PRICE_SMTP_PORT=abc``, the app fails at startup with a clear error.

Typical usage::

    from backend.app.config import get_settings
    settings = get_settings()
    print(settings.database_url)

``get_settings()`` is cached (``@lru_cache``) so we only parse the environment once.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# PlayStation Store GraphQL category IDs (Sony-internal identifiers)
# ---------------------------------------------------------------------------
# "All Deals" feed — roughly 4k+ products currently on sale.
ALL_DEALS_CATEGORY_ID = "3f772501-f6f8-49b7-abac-874a88ca4897"
# Full browse grid — ~10k games per shard (with and without discounts).
STORE_CATALOG_GRID_ID = "28c9c2b2-cecc-415c-9a08-482a605cb104"


class Settings(BaseSettings):
    """All configurable values for PS Price.

    Each attribute below can be overridden via ``PS_PRICE_<NAME>`` in the
    environment. Defaults let you run locally without editing code.
    """

    # Tell Pydantic to load PS_PRICE_* vars and ignore unknown extra vars.
    model_config = SettingsConfigDict(env_prefix="PS_PRICE_", env_file=".env", extra="ignore")

    # --- General app ---
    app_name: str = "PS Price"
    database_url: str = "postgresql+psycopg://psprice:psprice@localhost:5432/psprice"

    # --- PlayStation Store HTTP client ---
    store_origin: str = "https://store.playstation.com"
    store_locale: str = "en-us"
    user_agent: str = (
        "Mozilla/5.0 (compatible; PSPriceTracker/0.1; "
        "+https://github.com/local/ps-price)"
    )
    request_timeout_seconds: float = 20.0
    request_min_interval_seconds: float = 3.0  # polite delay between store requests
    search_min_interval_seconds: float = 0.4
    cache_ttl_seconds: int = 1800  # how long to reuse fetched HTML/JSON
    request_retries: int = 3

    # --- Background scheduler (see scheduler.py) ---
    check_interval_minutes: int = 360  # re-check tracked game prices
    feed_sync_interval_minutes: int = 60  # re-download catalog/deals feeds
    scheduler_enabled: bool = True
    sync_on_startup: bool = True  # pull catalog when the API process starts (deploy)

    # --- HTTP API security ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- SMTP email (optional — alerts are logged as "skipped" if unset) ---
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: float = 15.0
    notification_from_email: str = "ps-price@example.com"
    notification_from_name: str = "PS Prices"

    # --- Catalog / deals sync tuning ---
    max_search_limit: int = Field(default=48, ge=1, le=100)
    catalog_refresh_cooldown_seconds: int = Field(default=60, ge=0, le=3600)
    deals_category_id: str = ALL_DEALS_CATEGORY_ID
    catalog_category_id: str = STORE_CATALOG_GRID_ID
    catalog_sync_shards: str = "all,PS5,PS4"  # comma-separated browse shards
    graphql_page_size: int = Field(default=100, ge=10, le=200)
    graphql_min_interval_seconds: float = 0.4
    catalog_sync_max_pages: int | None = None  # None = no artificial cap
    deals_sync_max_pages: int | None = None

    # --- Authentication & JWT ---
    jwt_secret: str = "dev-only-change-me-use-ps-price-jwt-secret-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    jwt_refresh_ttl_days: int = Field(default=30, ge=1, le=365)
    session_ttl_days: int = Field(default=30, ge=1, le=365)  # legacy alias; prefer jwt_refresh_ttl_days
    frontend_url: str = "http://localhost:3000"  # used in verification email links
    webauthn_rp_id: str = "localhost"  # passkey "relying party" hostname
    webauthn_rp_name: str = "PS Price"
    webauthn_origin: str = "http://localhost:3000"  # must match browser origin
    require_email_verification: bool = True
    cookie_secure: bool = False  # set True in production (HTTPS only cookies)
    production_mode: bool = False  # enables strict startup checks
    admin_emails: str = ""  # comma-separated emails allowed to run manual sync
    internal_api_key: str = ""  # when set, require X-PS-Price-Internal header

    @property
    def admin_email_list(self) -> set[str]:
        """Parse ``admin_emails`` string into a lowercase set for fast lookup."""
        return {
            email.strip().lower()
            for email in self.admin_emails.split(",")
            if email.strip()
        }

    def validate_production_settings(self) -> None:
        """Fail fast at startup when production mode is on but settings are unsafe.

        Called from ``main.lifespan`` before the server accepts traffic.
        Raises ``RuntimeError`` with a message telling you which env var to fix.
        """
        if not self.production_mode:
            return
        if not self.database_url or not self.database_url.strip():
            raise RuntimeError("PS_PRICE_DATABASE_URL must be set when PS_PRICE_PRODUCTION_MODE=true")
        if not self.cookie_secure:
            raise RuntimeError("PS_PRICE_COOKIE_SECURE must be true when PS_PRICE_PRODUCTION_MODE=true")
        if self.frontend_url.startswith("http://"):
            raise RuntimeError("PS_PRICE_FRONTEND_URL must use https in production mode")
        if self.webauthn_rp_id in {"", "localhost"}:
            raise RuntimeError("PS_PRICE_WEBAUTHN_RP_ID must be set to your domain in production mode")
        if "localhost" in self.webauthn_origin:
            raise RuntimeError("PS_PRICE_WEBAUTHN_ORIGIN must not use localhost in production mode")
        if not self.admin_email_list:
            raise RuntimeError("PS_PRICE_ADMIN_EMAILS must list at least one admin email in production mode")
        if (
            not self.jwt_secret
            or self.jwt_secret == "dev-only-change-me-use-ps-price-jwt-secret-in-prod"
            or len(self.jwt_secret) < 32
        ):
            raise RuntimeError(
                "PS_PRICE_JWT_SECRET must be set to a random string of at least 32 characters in production mode"
            )
        if not self.internal_api_key or len(self.internal_api_key) < 32:
            raise RuntimeError(
                "PS_PRICE_INTERNAL_API_KEY must be set to a random string of at least 32 characters in production mode"
            )
        if self.internal_api_key == "ps-price-local-proxy-key":
            raise RuntimeError(
                "PS_PRICE_INTERNAL_API_KEY must not use the default development value in production mode"
            )
        if "*" in self.cors_origins:
            raise RuntimeError("PS_PRICE_CORS_ORIGINS must not use wildcard (*) in production mode")
        for origin in self.cors_origin_list:
            if not origin.startswith("https://"):
                raise RuntimeError(
                    f"PS_PRICE_CORS_ORIGINS must list HTTPS origins only in production mode (got {origin!r})"
                )

    @property
    def webauthn_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.webauthn_origin.split(",") if origin.strip()]

    @property
    def catalog_sync_shard_list(self) -> list[str]:
        shards = [part.strip() for part in self.catalog_sync_shards.split(",")]
        return [shard for shard in shards if shard]

    @property
    def cors_origin_list(self) -> list[str]:
        """Return the configured CORS origins as a cleaned list.

        The `cors_origins` setting is stored as a comma separated string to
        make environment configuration simple; this property returns a list
        suitable for FastAPI CORS middleware.
        """
        values = [origin.strip() for origin in self.cors_origins.split(",")]
        return [origin for origin in values if origin]

    @property
    def smtp_configured(self) -> bool:
        """Return True when sufficient SMTP configuration is present.

        This is a simple check used by EmailNotifier to decide whether to
        attempt real sends or operate in a test/log-only mode.
        """
        return bool(self.smtp_host and self.notification_from_email)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Using lru_cache ensures the expensive environment parsing happens
    only once and the same Settings object is reused across the app.
    """
    return Settings()
