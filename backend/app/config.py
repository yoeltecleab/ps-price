"""Application configuration via Pydantic Settings.

This module exposes a single `Settings` model which reads configuration
from environment variables (prefixed with PS_PRICE_) and an optional
.env file. It centralizes defaults used across the application (database
path, HTTP client behaviour, scheduler and SMTP settings).

Use `get_settings()` to obtain a cached Settings instance that can be
passed to other components (repository, service, notifier).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# en-us "All Deals" category (cat.gma.AllDeals) — ~4k+ sale products via GraphQL
ALL_DEALS_CATEGORY_ID = "3f772501-f6f8-49b7-abac-874a88ca4897"
# Full store browse grid — ~10k concepts per shard (games with and without discounts)
STORE_CATALOG_GRID_ID = "28c9c2b2-cecc-415c-9a08-482a605cb104"


class Settings(BaseSettings):
    """Configuration values for the PS Price application.

    Settings are loaded from environment variables with the prefix
    `PS_PRICE_` by default. Reasonable defaults are provided so the app
    can run locally without additional configuration.

    Important properties:
      - `database_path`: Path to the SQLite database file.
      - `store_origin` / `store_locale`: Base URL and default locale for the PlayStation Store client.
      - `request_*`: HTTP client timeouts, retries and rate limiting.
      - `smtp_*`: SMTP configuration used by `notifier.EmailNotifier`.
    """

    model_config = SettingsConfigDict(env_prefix="PS_PRICE_", env_file=".env", extra="ignore")

    app_name: str = "PS Price"
    database_path: str = "backend/data/ps_price.sqlite3"
    store_origin: str = "https://store.playstation.com"
    store_locale: str = "en-us"
    user_agent: str = (
        "Mozilla/5.0 (compatible; PSPriceTracker/0.1; "
        "+https://github.com/local/ps-price)"
    )
    request_timeout_seconds: float = 20.0
    request_min_interval_seconds: float = 3.0
    search_min_interval_seconds: float = 0.4
    cache_ttl_seconds: int = 1800
    request_retries: int = 3
    check_interval_minutes: int = 360
    feed_sync_interval_minutes: int = 60
    scheduler_enabled: bool = True
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: float = 15.0
    notification_from_email: str = "ps-price@example.com"

    max_search_limit: int = Field(default=24, ge=1, le=48)
    deals_category_id: str = ALL_DEALS_CATEGORY_ID
    catalog_category_id: str = STORE_CATALOG_GRID_ID
    catalog_sync_shards: str = "all,PS5,PS4"
    graphql_page_size: int = Field(default=100, ge=10, le=200)
    graphql_min_interval_seconds: float = 1.0
    catalog_sync_max_pages: int | None = None
    deals_sync_max_pages: int | None = None

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
