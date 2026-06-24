"""Pydantic request/response schemas for the API.

**What is Pydantic?**

FastAPI uses **Pydantic** models to:

1. **Validate** incoming JSON (wrong types → automatic 422 error).
2. **Document** the API (OpenAPI / Swagger UI reads these classes).
3. **Serialize** Python objects back to JSON for responses.

**Schemas vs domain models**

- ``domain.py`` — internal Python dataclasses used between backend modules.
- ``schemas.py`` — **wire format** matching what the frontend expects.

Field names intentionally mirror SQLite column names so repository rows map
cleanly: ``GameOut(**row)``.

**Common patterns here**

- ``Field(..., min_length=1)`` — required string, cannot be empty.
- ``Field(default=None, ge=0)`` — optional integer, must be >= 0 if provided.
- Inheritance (``GameDetail(GameOut)``) — reuse fields and add more.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GameCreate(BaseModel):
    """Schema for creating or refreshing a tracked game via the API.

    ``product_ref`` accepts either a bare PS product ID or a full store URL.
    ``locale`` overrides the default store region (e.g. ``en-gb``).
    """
    product_ref: str = Field(..., min_length=1)
    locale: str | None = Field(default=None, examples=["en-us"])


class GameOut(BaseModel):
    """Representation of a tracked game returned by the API.

    One row from the ``games`` table plus derived fields like
    ``discount_percent`` and ``savings_cents`` computed in the service layer.
    """
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
    """GameOut extended with recent price history.

    ``history`` is a list of dicts (price check rows) for charting on the
    game detail page.
    """
    history: list[dict]


class SearchOut(BaseModel):
    """A unified search result from catalog and/or PlayStation Store.

    ``source`` tells the UI whether the hit came from the local database
    (``catalog``) or a live store search (``store``).
    """
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
    """Autocomplete suggestion from the local catalog.

    Smaller than ``SearchOut`` — only the fields needed for a typeahead dropdown.
    """
    id: int
    name: str
    product_id: str
    image_url: str | None = None
    current_price_formatted: str | None = None
    discount_percent: int | None = None
    is_tracked: bool = False


class DealsPageOut(BaseModel):
    """Paginated deals listing.

    ``items`` + ``total`` + ``limit`` + ``offset`` is the standard pagination
    pattern: clients request a slice and know how many rows exist overall.
    """
    items: list[GameOut]
    total: int
    limit: int
    offset: int
    last_sync: str | None = None


class WatchCreate(BaseModel):
    """Request body for creating a new price watch.

    A **watch** stores rules like "email me when price drops below $20" or
    "notify on any price decrease".
    """
    game_id: int
    notification_email_id: int | None = None
    target_price_cents: int | None = Field(default=None, ge=0)
    notify_on_any_drop: bool = True
    enabled: bool = True
    theme_id: str | None = None


class BulkTrackRequest(BaseModel):
    """Track multiple games at once (add to user's library / tracking list)."""
    game_ids: list[int] = Field(..., min_length=1)


class BulkWatchCreate(BaseModel):
    """Create identical watches for several games in one API call."""
    game_ids: list[int] = Field(..., min_length=1)
    notification_email_id: int | None = None
    target_price_cents: int | None = Field(default=None, ge=0)
    notify_on_any_drop: bool = True
    enabled: bool = True
    theme_id: str | None = None


class BulkDeleteNotifications(BaseModel):
    """Delete multiple notification log entries by ID."""
    ids: list[int] = Field(..., min_length=1)


class WatchPatch(BaseModel):
    """Patch/schema for updating an existing watch.

    All fields are optional — only provided keys are updated (partial update).
    """
    target_price_cents: int | None = Field(default=None, ge=0)
    notify_on_any_drop: bool | None = None
    enabled: bool | None = None


class WatchOut(BaseModel):
    """Representation of a stored watch returned by the API.

    Note: ``enabled`` and ``notify_on_any_drop`` are stored as integers (0/1)
    in SQLite but exposed here as ints for JSON compatibility.
    """
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
    """Representation of a notification log entry returned by the API.

    ``status`` is one of ``sent``, ``failed``, or ``skipped``.  ``game_name``
    may be joined from the games table for display in the notifications UI.
    """
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
