"""Pydantic request/response schemas for the API.

These models are used by the FastAPI endpoints to validate input and
format responses. They deliberately mirror database column names so
they can be constructed directly from repository rows.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GameCreate(BaseModel):
    """Schema for creating or refreshing a tracked game via the API."""
    product_ref: str = Field(..., min_length=1)
    locale: str | None = Field(default=None, examples=["en-us"])


class GameOut(BaseModel):
    """Representation of a tracked game returned by the API."""
    id: int
    product_id: str
    locale: str
    name: str
    category: str | None = None
    image_url: str | None = None
    store_url: str
    currency: str | None = None
    current_price_cents: int | None = None
    current_price_formatted: str | None = None
    original_price_cents: int | None = None
    original_price_formatted: str | None = None
    discount_text: str | None = None
    availability: str
    price_source: str | None = None
    sale_end_at: str | None = None
    last_checked_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    platforms: list[str] = []
    discount_percent: int | None = None
    is_tracked: bool = False
    catalog_synced_at: str | None = None
    description_short: str | None = None
    description_long: str | None = None
    publisher: str | None = None
    release_date: str | None = None
    genres: list[str] = []
    features: list[str] = []
    rating_average: float | None = None
    rating_count: int | None = None
    content_rating: str | None = None
    screenshots: list[str] = []
    edition: str | None = None
    popularity_rank: int | None = None
    savings_cents: int | None = None
    created_at: str
    updated_at: str


class GameDetail(GameOut):
    """GameOut extended with recent price history."""
    history: list[dict]


class SearchOut(BaseModel):
    """A unified search result from catalog and/or PlayStation Store."""
    product_id: str
    locale: str
    name: str
    store_url: str
    image_url: str | None = None
    platforms: list[str] = []
    currency: str | None = None
    current_price_cents: int | None = None
    current_price_formatted: str | None = None
    original_price_cents: int | None = None
    original_price_formatted: str | None = None
    discount_text: str | None = None
    id: int | None = None
    source: str = "store"
    discount_percent: int | None = None
    is_tracked: bool = False


class SuggestOut(BaseModel):
    """Autocomplete suggestion from the local catalog."""
    id: int
    name: str
    product_id: str
    image_url: str | None = None
    current_price_formatted: str | None = None
    discount_percent: int | None = None
    is_tracked: bool = False


class DealsPageOut(BaseModel):
    """Paginated deals listing."""
    items: list[GameOut]
    total: int
    limit: int
    offset: int
    last_sync: str | None = None


class WatchCreate(BaseModel):
    """Request body for creating a new price watch."""
    game_id: int
    email: str
    target_price_cents: int | None = Field(default=None, ge=0)
    notify_on_any_drop: bool = True
    enabled: bool = True
    theme_id: str | None = None


class BulkTrackRequest(BaseModel):
    game_ids: list[int] = Field(..., min_length=1)


class BulkWatchCreate(BaseModel):
    game_ids: list[int] = Field(..., min_length=1)
    email: str
    target_price_cents: int | None = Field(default=None, ge=0)
    notify_on_any_drop: bool = True
    enabled: bool = True
    theme_id: str | None = None


class BulkDeleteNotifications(BaseModel):
    ids: list[int] = Field(..., min_length=1)


class WatchPatch(BaseModel):
    """Patch/schema for updating an existing watch."""
    target_price_cents: int | None = Field(default=None, ge=0)
    notify_on_any_drop: bool | None = None
    enabled: bool | None = None


class WatchOut(BaseModel):
    """Representation of a stored watch returned by the API."""
    id: int
    game_id: int
    email: str
    target_price_cents: int | None = None
    notify_on_any_drop: int
    enabled: int
    theme_id: str | None = None
    last_notified_price_cents: int | None = None
    last_notified_at: str | None = None
    created_at: str
    updated_at: str


class NotificationOut(BaseModel):
    """Representation of a notification log entry returned by the API."""
    id: int
    watch_id: int | None = None
    game_id: int | None = None
    email: str
    subject: str
    body: str
    status: str
    reason: str | None = None
    error: str | None = None
    created_at: str
    sent_at: str | None = None
    game_name: str | None = None
