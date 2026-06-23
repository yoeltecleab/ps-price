"""Domain models used throughout the PS Price backend.

This module defines small, immutable data structures that represent a
single scraped snapshot of a PlayStation Store product and a lightweight
search result used for listing or search endpoints. These are plain
dataclasses (frozen) so they are hashable and safe to pass between
components (service, repository, notifier) without accidental mutation.

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

    SearchResult contains only the information necessary to list products in
    search endpoints or selection UIs. It intentionally mirrors a subset of
    ProductSnapshot for convenience.

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
