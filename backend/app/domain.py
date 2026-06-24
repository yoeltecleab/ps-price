"""Domain models used throughout the PS Price backend.

**What is a "domain model"?**

These are plain Python objects that represent *business concepts* — a game
price snapshot, a search result — separate from:

- **HTTP/API layer** (``schemas.py`` — Pydantic models for JSON)
- **Database layer** (SQLite rows as dicts)
- **Scraping layer** (``ps_store.py`` / ``ps_graphql.py``)

**Why ``@dataclass(frozen=True)``?**

- ``@dataclass`` auto-generates ``__init__``, ``__repr__``, etc.
- ``frozen=True`` makes instances **immutable** — once built, fields cannot
  change accidentally.  Immutable objects are safer to pass between async
  tasks and easier to reason about.

**Data flow example**

::

    PlayStationStoreClient.fetch_product()
        → ProductSnapshot
        → PriceService saves to SQLite
        → API returns GameOut (Pydantic) to the browser

Typical usage:
  - PlayStationStoreClient.parse_product_page(...) -> ProductSnapshot
  - Service.search(...) -> list[SearchResult]

The dataclasses intentionally store both machine-friendly fields (cents,
timestamps) and human-friendly formatted strings to avoid repeated
formatting in the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProductSnapshot:
    """An immutable snapshot of a product's state at a specific time.

    Think of this as a **photograph** of a store listing: name, price, image,
    discount text, etc. at the moment we scraped it.

    **Why both cents and formatted strings?**

    - ``current_price_cents`` — for math (comparisons, discount %, DB storage).
    - ``current_price_formatted`` — for display exactly as the store showed it.

    **Change detection**

    ``raw_source_hash`` is a fingerprint of the underlying HTML/JSON.  If the
    hash changes on the next fetch, we know the store page content changed
    even before comparing individual fields.

    Attributes:
        product_id: The PS Store product identifier (e.g. "UP0001-CUSA00001_00-EXAMPLEID").
        locale: Store locale string (e.g. "en-us").
        name: Product title shown in the store.
        category: Optional category or genre for the product.
        image_url: Best-effort URL to a product image or poster.
        store_url: Canonical URL for the product on the PlayStation Store.
        currency: ISO currency code (e.g. "USD").
        current_price_cents: Current price in integer cents (None if free/unavailable).
        current_price_formatted: Human-friendly formatted price (localized string).
        original_price_cents: Original (pre-discount) price in cents.
        original_price_formatted: Formatted original price string.
        discount_text: Optional discount label ("-50%", "PS Plus", etc.).
        availability: Availability string (e.g. "available", "preorder", "unavailable").
        fetched_at: Datetime when the snapshot was taken.
        raw_source_hash: Hash of the raw HTML/JSON used to detect changes.
        price_source: Short identifier of which parsing source provided the price (e.g. "jsonld", "component").
        sale_end_at: Optional datetime when the sale ends.

    These snapshots are stored in the database (price_history) and used by
    the business logic to evaluate watches and to populate API responses.
    """

    product_id: str
    locale: str
    name: str
    category: str | None
    image_url: str | None
    store_url: str
    currency: str | None
    current_price_cents: int | None
    current_price_formatted: str | None
    original_price_cents: int | None
    original_price_formatted: str | None
    discount_text: str | None
    availability: str
    fetched_at: datetime
    raw_source_hash: str
    price_source: str
    sale_end_at: datetime | None = None
    description_short: str | None = None
    description_long: str | None = None
    publisher: str | None = None
    release_date: str | None = None
    genres: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    rating_average: float | None = None
    rating_count: int | None = None
    content_rating: str | None = None
    screenshots: tuple[str, ...] = ()
    edition: str | None = None
    popularity_rank: int | None = None


@dataclass(frozen=True)
class SearchResult:
    """Lightweight representation of a product in search results.

    Smaller than ``ProductSnapshot`` — used when listing many games (search,
    deals feed, GraphQL catalog sync).  Missing fields like ``availability``
    or ``fetched_at`` are filled in later when a game is fully tracked.

    ``platforms`` is a **list** (mutable type) but the dataclass itself is
    frozen — you cannot reassign ``result.platforms``, though the list's
    contents could theoretically be mutated; callers treat it as read-only.

    Attributes:
        product_id: PS Store product identifier.
        locale: Store locale string.
        name: Product title shown in search results.
        store_url: Product page URL.
        image_url: Optional thumbnail URL.
        platforms: List of supported platforms (e.g. ["PS5", "PS4"]).
        currency: ISO currency code or None.
        current_price_cents: Price in cents or None when not applicable.
        current_price_formatted: Formatted price string.
        original_price_cents: Original price in cents when discounted.
        original_price_formatted: Formatted original price string.
        discount_text: Optional discount label.
    """

    product_id: str
    locale: str
    name: str
    store_url: str
    image_url: str | None
    platforms: list[str]
    currency: str | None
    current_price_cents: int | None
    current_price_formatted: str | None
    original_price_cents: int | None
    original_price_formatted: str | None
    discount_text: str | None
    category: str | None = None
    description_short: str | None = None
    description_long: str | None = None
    publisher: str | None = None
    release_date: str | None = None
    genres: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    rating_average: float | None = None
    rating_count: int | None = None
    content_rating: str | None = None
    screenshots: tuple[str, ...] = ()
    edition: str | None = None
    popularity_rank: int | None = None
