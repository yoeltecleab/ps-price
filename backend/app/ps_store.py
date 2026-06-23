"""PlayStation Store scraping client and HTML/JSON parsing helpers.

This module contains a compact async HTTP client tailored to scrape
product pages and search results from the PlayStation Store. It
implements lightweight caching, rate limiting (minimum interval
between requests), retry/backoff semantics, and multiple parsing
strategies to extract price and metadata.

The parsing functions are defensive: they attempt to read structured
JSON-LD and Next.js/Apollo state from the page before falling back to
simpler HTML heuristics.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx

from backend.app.config import Settings
from backend.app.domain import ProductSnapshot, SearchResult
from backend.app.money import currency_for_locale, format_cents, money_to_cents


PRODUCT_RE = re.compile(r"^[A-Z0-9_-]{12,}$")
LOCALE_RE = re.compile(r"^[a-z]{2}-[a-z]{2}$")
ENV_SCRIPT_RE = re.compile(
    r'<script id="(env:[^\"]+)" type="application/json">(.*?)</script>', re.S
)
JSONLD_RE = re.compile(
    r'<script id="mfe-jsonld-tags" type="application/ld\+json">(.*?)</script>', re.S
)
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
PRODUCT_LINK_RE = re.compile(r"/(?P<locale>[a-z]{2}-[a-z]{2})/product/(?P<product>[A-Z0-9_-]+)")


class StoreClientError(RuntimeError):
    """Base exception for PlayStationStoreClient errors."""


class ProductNotFound(StoreClientError):
    """Raised when the PlayStation Store returns a 404 for a product URL."""


class ProductParseError(StoreClientError):
    """Raised when the client cannot extract required product fields."""


@dataclass
class _CacheEntry:
    fetched_at: datetime
    value: object


class PlayStationStoreClient:
    """Async HTTP client and parser for PlayStation Store pages.

    The client implements a per-instance in-memory cache (TTL controlled
    via settings), basic rate limiting (minimum seconds between
    requests) and retry logic for 429/5xx responses. It exposes two main
    async methods: `fetch_product(...)` and `search(...)`.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._cache: dict[str, _CacheEntry] = {}

    async def close(self) -> None:
        """Close the underlying HTTPX client gracefully."""
        await self._client.aclose()

    async def fetch_product(
        self, product_ref: str, locale: str | None = None, force: bool = False
    ) -> ProductSnapshot:
        """Fetch and parse a product page returning a ProductSnapshot.

        `product_ref` may be a raw product id or a full product URL. If
        `force` is True the cache will be ignored.
        """
        product_id, detected_locale = extract_product_ref(product_ref)
        active_locale = normalize_locale(locale or detected_locale or self.settings.store_locale)
        url = product_url(self.settings.store_origin, active_locale, product_id)
        cache_key = f"product:{url}"
        cached = self._get_cached(cache_key, force)
        if isinstance(cached, ProductSnapshot):
            return cached

        page = await self._get_text(url)
        snapshot = parse_product_page(page, product_id, active_locale, url)
        self._cache[cache_key] = _CacheEntry(datetime.now(UTC), snapshot)
        return snapshot

    async def search(
        self, query: str, locale: str | None = None, limit: int = 10, force: bool = False
    ) -> list[SearchResult]:
        """Search the PlayStation Store and return a list of SearchResult.

        The method normalizes the query, enforces a configured `max_search_limit`
        and caches recent responses to reduce traffic against the store.
        """
        active_locale = normalize_locale(locale or self.settings.store_locale)
        clean_query = " ".join(query.split())
        if not clean_query:
            return []
        bounded_limit = max(1, min(limit, self.settings.max_search_limit))
        url = f"{self.settings.store_origin}/{active_locale}/search/{quote(clean_query)}"
        cache_key = f"search:{url}:{bounded_limit}"
        cached = self._get_cached(cache_key, force)
        if isinstance(cached, list):
            return cached[:bounded_limit]

        page = await self._get_text(
            url, min_interval=self.settings.search_min_interval_seconds
        )
        results = parse_search_page(page, active_locale, self.settings.store_origin)
        results = results[:bounded_limit]
        self._cache[cache_key] = _CacheEntry(datetime.now(UTC), results)
        return results

    async def fetch_deals(
        self, locale: str | None = None, force: bool = False
    ) -> list[SearchResult]:
        """Fetch the full PlayStation Store catalog (all games + deal pricing)."""
        from backend.app.ps_graphql import fetch_store_catalog

        active_locale = normalize_locale(locale or self.settings.store_locale)
        cache_key = f"catalog-full:{active_locale}"
        cached = self._get_cached(cache_key, force)
        if isinstance(cached, list):
            return cached

        results = await fetch_store_catalog(
            self._client,
            locale=active_locale,
            origin=self.settings.store_origin,
            shards=self.settings.catalog_sync_shard_list or ["all"],
            page_size=self.settings.graphql_page_size,
            max_pages=self.settings.catalog_sync_max_pages,
            min_interval=self.settings.graphql_min_interval_seconds,
            deals_category_id=self.settings.deals_category_id,
        )
        self._cache[cache_key] = _CacheEntry(datetime.now(UTC), results)
        return results

    def _get_cached(self, key: str, force: bool) -> object | None:
        """Return a cached value if present and not expired.

        The `force` parameter allows callers to bypass the cache and fetch
        fresh data.
        """
        if force:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        age = (datetime.now(UTC) - entry.fetched_at).total_seconds()
        if age > self.settings.cache_ttl_seconds:
            self._cache.pop(key, None)
            return None
        return entry.value

    async def _get_text(self, url: str, *, min_interval: float | None = None) -> str:
        """Fetch a URL with retries, backoff and basic 429 handling.

        The method uses `_wait_for_slot()` to enforce a minimum time
        between requests and raises `StoreClientError` on repeated
        failures.
        """
        interval = (
            self.settings.request_min_interval_seconds
            if min_interval is None
            else min_interval
        )
        for attempt in range(self.settings.request_retries):
            await self._wait_for_slot(interval)
            response = await self._client.get(url)
            if response.status_code == 404:
                raise ProductNotFound(f"PlayStation Store returned 404 for {url}")
            if response.status_code == 429:
                await asyncio.sleep(_retry_after_seconds(response) or (2**attempt * 5))
                continue
            if 500 <= response.status_code < 600:
                await asyncio.sleep(2**attempt)
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise StoreClientError(str(exc)) from exc
            return response.text
        raise StoreClientError(f"PlayStation Store did not return a usable response for {url}")

    async def _wait_for_slot(self, min_interval: float | None = None) -> None:
        """Enforce a minimum interval between requests using an asyncio lock."""
        interval = (
            min_interval
            if min_interval is not None
            else self.settings.request_min_interval_seconds
        )
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait_for = interval - (now - self._last_request_at)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_request_at = loop.time()


def extract_product_ref(product_ref: str) -> tuple[str, str | None]:
    """Parse a product reference which may be an id or a product URL.

    Returns a tuple (product_id, locale_or_None).
    """
    candidate = product_ref.strip()
    if not candidate:
        raise ValueError("product_ref is required")
    parsed = urlparse(candidate)
    if parsed.scheme and parsed.netloc:
        decoded_path = unquote(parsed.path)
        match = PRODUCT_LINK_RE.search(decoded_path)
        if not match:
            raise ValueError("PlayStation Store product URL must contain /{locale}/product/{id}")
        return match.group("product"), match.group("locale")
    if not PRODUCT_RE.match(candidate):
        raise ValueError("product_ref must be a PlayStation product ID or product URL")
    return candidate, None


def normalize_locale(locale: str) -> str:
    """Normalize a locale string into the canonical form like 'en-us'."""
    cleaned = locale.strip().replace("_", "-").lower()
    if not LOCALE_RE.match(cleaned):
        raise ValueError("locale must look like en-us")
    return cleaned


def product_url(origin: str, locale: str, product_id: str) -> str:
    """Build the canonical product page URL for a product id and locale."""
    return f"{origin.rstrip('/')}/{locale}/product/{product_id}"


def parse_product_page(
    page_html: str, product_id: str, locale: str, store_url: str
) -> ProductSnapshot:
    """Parse a product HTML page and return a ProductSnapshot.

    The parser tries several sources of truth (component cache, JSON-LD)
    and normalizes prices and timestamps into the ProductSnapshot
    structure. It raises ProductParseError when a required field
    (product name) cannot be found.
    """
    now = datetime.now(UTC)
    jsonld = _extract_jsonld(page_html)
    product_data, price_data = _extract_product_component_data(page_html, product_id)

    name = _first_text(
        product_data.get("name") if product_data else None,
        jsonld.get("name") if jsonld else None,
    )
    if not name:
        raise ProductParseError(f"Could not find product name for {product_id}")

    image_url = _first_text(
        _select_image(product_data.get("media") if product_data else None),
        jsonld.get("image") if jsonld else None,
    )
    category = _first_text(jsonld.get("category") if jsonld else None)
    offer = _first_offer(jsonld.get("offers") if jsonld else None)
    product_price = product_data.get("price") if isinstance(product_data.get("price"), dict) else {}

    currency = _first_text(
        price_data.get("currencyCode") if price_data else None,
        offer.get("priceCurrency") if offer else None,
        currency_for_locale(locale),
    )

    current_formatted = _first_text(
        price_data.get("discountedPrice") if price_data else None,
        price_data.get("discountPriceFormatted") if price_data else None,
        product_price.get("discountedPrice"),
    )
    current_cents = _first_int(
        price_data.get("discountedValue") if price_data else None,
        price_data.get("discountPriceValue") if price_data else None,
        money_to_cents(current_formatted),
        money_to_cents(offer.get("price") if offer else None),
    )
    original_formatted = _first_text(
        price_data.get("basePrice") if price_data else None,
        price_data.get("originalPriceFormatted") if price_data else None,
        product_price.get("basePrice"),
    )
    original_cents = _first_int(
        price_data.get("basePriceValue") if price_data else None,
        price_data.get("originalPriceValue") if price_data else None,
        money_to_cents(original_formatted),
    )

    if current_formatted is None:
        current_formatted = format_cents(current_cents, currency)
    if original_formatted is None:
        original_formatted = format_cents(original_cents, currency)

    discount_text = _first_text(
        price_data.get("savingTag") if price_data else None,
        price_data.get("discountBadgeText") if price_data else None,
        price_data.get("discountText") if price_data else None,
        product_price.get("discountText"),
    )
    availability = "unavailable"
    if current_cents == 0:
        availability = "free"
    elif current_cents is not None:
        availability = "available"

    sale_end_at = _parse_millis_timestamp(price_data.get("endTime") if price_data else None)
    raw_hash = hashlib.sha256(_relevant_source(page_html, product_id).encode()).hexdigest()
    metadata = extract_product_metadata(page_html, product_id)
    return ProductSnapshot(
        product_id=product_id,
        locale=locale,
        name=name,
        category=_first_text(metadata.get("category"), category),
        image_url=image_url,
        store_url=store_url,
        currency=currency,
        current_price_cents=current_cents,
        current_price_formatted=current_formatted,
        original_price_cents=original_cents,
        original_price_formatted=original_formatted,
        discount_text=discount_text,
        availability=availability,
        fetched_at=now,
        raw_source_hash=raw_hash,
        price_source="component-cache" if price_data else "json-ld",
        sale_end_at=sale_end_at,
        description_short=metadata.get("description_short"),
        description_long=metadata.get("description_long"),
        publisher=metadata.get("publisher"),
        release_date=metadata.get("release_date"),
        genres=metadata.get("genres", ()),
        features=metadata.get("features", ()),
        rating_average=metadata.get("rating_average"),
        rating_count=metadata.get("rating_count"),
        content_rating=metadata.get("content_rating"),
        screenshots=metadata.get("screenshots", ()),
        edition=metadata.get("edition"),
    )


def extract_product_metadata(page_html: str, product_id: str) -> dict[str, object]:
    """Extract rich product metadata from embedded Apollo cache blocks."""
    product = _merged_product_cache(page_html, product_id)
    if not product:
        return {}

    descriptions = product.get("descriptions") if isinstance(product.get("descriptions"), list) else []
    description_short = None
    description_long = None
    for item in descriptions:
        if not isinstance(item, dict):
            continue
        text = _strip_html(_first_text(item.get("value")))
        if item.get("type") == "SHORT":
            description_short = text
        elif item.get("type") == "LONG":
            description_long = text

    genres: list[str] = []
    for genre in product.get("localizedGenres") or []:
        if isinstance(genre, dict):
            value = _first_text(genre.get("value"))
            if value:
                genres.append(value)

    features: list[str] = []
    edition = product.get("edition") if isinstance(product.get("edition"), dict) else {}
    edition_name = _first_text(edition.get("name"))
    accessibility = product.get("accessibilityNoticesByPlatform")
    if isinstance(accessibility, dict):
        for notices in accessibility.values():
            if not isinstance(notices, list):
                continue
            for notice in notices:
                if not isinstance(notice, dict):
                    continue
                if notice.get("value") in {"TRUE", "BASIC"}:
                    label = str(notice.get("type", "")).replace("_", " ").title()
                    if label and label not in features:
                        features.append(label)

    price = product.get("price") if isinstance(product.get("price"), dict) else {}
    for branding in price.get("serviceBranding") or []:
        if isinstance(branding, str) and branding not in {"NONE"}:
            label = branding.replace("_", " ")
            if label not in features:
                features.append(label)

    screenshots: list[str] = []
    media = product.get("media")
    if isinstance(media, list):
        for item in media:
            if (
                isinstance(item, dict)
                and item.get("type") == "IMAGE"
                and item.get("role") == "SCREENSHOT"
                and item.get("url")
            ):
                screenshots.append(str(item["url"]))

    star = product.get("starRating") if isinstance(product.get("starRating"), dict) else {}
    content = (
        product.get("contentRating")
        if isinstance(product.get("contentRating"), dict)
        else {}
    )

    return {
        "category": _first_text(
            product.get("localizedStoreDisplayClassification"),
            product.get("storeDisplayClassification"),
        ),
        "description_short": description_short,
        "description_long": description_long,
        "publisher": _first_text(product.get("publisherName")),
        "release_date": _first_text(product.get("releaseDate")),
        "genres": tuple(genres),
        "features": tuple(features[:12]),
        "rating_average": star.get("averageRating")
        if isinstance(star.get("averageRating"), (int, float))
        else None,
        "rating_count": star.get("totalRatingsCount")
        if isinstance(star.get("totalRatingsCount"), int)
        else None,
        "content_rating": _first_text(content.get("name")),
        "screenshots": tuple(screenshots[:8]),
        "edition": edition_name,
    }


def _merged_product_cache(page_html: str, product_id: str) -> dict[str, Any]:
    """Merge all Apollo cache fragments for a product id."""
    merged: dict[str, Any] = {}
    for data in _iter_env_json(page_html):
        cache = data.get("cache")
        if not isinstance(cache, dict):
            continue
        block = cache.get(f"Product:{product_id}")
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if value is None or value == [] or value == {}:
                continue
            if key not in merged or merged[key] is None:
                merged[key] = value
    return merged


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", value)
    cleaned = re.sub(r"\s+", " ", html.unescape(cleaned)).strip()
    return cleaned or None


def parse_search_page(page_html: str, locale: str, origin: str) -> list[SearchResult]:
    """Extract a list of SearchResult from a search page HTML.

    The parser prefers Next.js/Apollo state but falls back to extracting
    simple product links when structured data is not present.
    """
    products = _extract_next_products(page_html)
    if not products:
        products = _extract_product_links(page_html)
    results: list[SearchResult] = []
    seen: set[str] = set()
    for product in products:
        product_id = product.get("id")
        name = product.get("name")
        if not isinstance(product_id, str) or not product_id or product_id in seen:
            continue
        if not isinstance(name, str) or not name:
            name = product_id
        seen.add(product_id)
        price = product.get("price") if isinstance(product.get("price"), dict) else {}
        currency = currency_for_locale(locale)
        current_formatted = _first_text(price.get("discountedPrice"), price.get("priceOrText"))
        original_formatted = _first_text(price.get("basePrice"))
        results.append(
            SearchResult(
                product_id=product_id,
                locale=locale,
                name=name,
                store_url=product_url(origin, locale, product_id),
                image_url=_select_image(product.get("media")),
                platforms=[str(value) for value in product.get("platforms", [])],
                currency=currency,
                current_price_cents=money_to_cents(current_formatted),
                current_price_formatted=current_formatted,
                original_price_cents=money_to_cents(original_formatted),
                original_price_formatted=original_formatted,
                discount_text=_first_text(price.get("discountText"), price.get("savingTag")),
            )
        )
    return results


def _extract_jsonld(page_html: str) -> dict[str, Any]:
    """Extract and parse JSON-LD block from the page when present."""
    match = JSONLD_RE.search(page_html)
    if not match:
        return {}
    try:
        value = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _extract_product_component_data(
    page_html: str, product_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract product and price information from embedded env JSON caches.

    The PlayStation Store renders parts of the page into <script> blocks
    (env cache). This helper scans those blocks for cached Product and
    GameCTA objects and returns the best-available product and price
    dictionaries.
    """
    product: dict[str, Any] = {}
    best_price: dict[str, Any] = {}
    for data in _iter_env_json(page_html):
        cache = data.get("cache")
        if not isinstance(cache, dict):
            continue
        cached_product = cache.get(f"Product:{product_id}")
        if isinstance(cached_product, dict):
            product = {**product, **cached_product}
            direct_price = cached_product.get("price")
            if isinstance(direct_price, dict) and not best_price:
                best_price = direct_price
        for key, value in cache.items():
            if not key.startswith("GameCTA:") or product_id not in key:
                continue
            if isinstance(value, dict) and isinstance(value.get("price"), dict):
                price = value["price"]
                if price.get("applicability") in (None, "APPLICABLE") or not best_price:
                    best_price = price
    return product, best_price


def _iter_env_json(page_html: str) -> list[dict[str, Any]]:
    """Yield parsed JSON objects found in env:<name> script blocks."""
    values: list[dict[str, Any]] = []
    for _, body in ENV_SCRIPT_RE.findall(page_html):
        try:
            data = json.loads(html.unescape(body))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            values.append(data)
    return values


def _extract_next_products(page_html: str) -> list[dict[str, Any]]:
    """Extract Next.js `__NEXT_DATA__` Apollo product state when present."""
    match = NEXT_DATA_RE.search(page_html)
    if not match:
        return []
    try:
        next_data = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return []
    apollo = next_data.get("props", {}).get("apolloState", {})
    if not isinstance(apollo, dict):
        return []
    products = [value for key, value in apollo.items() if key.startswith("Product:")]
    return [value for value in products if isinstance(value, dict)]


def _extract_product_links(page_html: str) -> list[dict[str, Any]]:
    """Fallback: extract product ids from simple links in the HTML."""
    products: list[dict[str, Any]] = []
    for match in PRODUCT_LINK_RE.finditer(page_html):
        products.append({"id": match.group("product"), "name": match.group("product")})
    return products


def _first_offer(offers: object) -> dict[str, Any]:
    """Return the first offer object from offers which may be a dict or list."""
    if isinstance(offers, dict):
        return offers
    if isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict):
                return offer
    return {}


def _select_image(media: object) -> str | None:
    """Select the best image URL from a media structure.

    The function prefers specific roles (MASTER, GAMEHUB_COVER_ART, ...)
    to return the most suitable image for display.
    """
    if isinstance(media, str):
        return media
    if not isinstance(media, list):
        return None
    preferred_roles = [
        "MASTER",
        "GAMEHUB_COVER_ART",
        "EDITION_KEY_ART",
        "FOUR_BY_THREE_BANNER",
        "PORTRAIT_BANNER",
        "BACKGROUND",
    ]
    images = [
        item
        for item in media
        if isinstance(item, dict) and item.get("type") == "IMAGE" and item.get("url")
    ]
    for role in preferred_roles:
        for item in images:
            if item.get("role") == role:
                return str(item["url"])
    return str(images[0]["url"]) if images else None


def _first_text(*values: object) -> str | None:
    """Return the first non-empty string from the given arguments."""
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None


def _first_int(*values: object) -> int | None:
    """Return the first integer (not boolean) found in values, or None."""
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int):
            return value
    return None


def _parse_millis_timestamp(value: object) -> datetime | None:
    """Parse an integer millisecond timestamp to a UTC datetime or None."""
    if value in (None, ""):
        return None
    try:
        millis = int(str(value))
    except ValueError:
        return None
    return datetime.fromtimestamp(millis / 1000, UTC)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse the `Retry-After` header into seconds when present."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def _relevant_source(page_html: str, product_id: str) -> str:
    """Return a minimal concatenation of page fragments used to compute a source hash."""
    pieces = [product_id]
    jsonld = JSONLD_RE.search(page_html)
    if jsonld:
        pieces.append(jsonld.group(1))
    for data in _iter_env_json(page_html):
        cache = data.get("cache")
        if not isinstance(cache, dict):
            continue
        for key, value in cache.items():
            if product_id in key:
                pieces.append(json.dumps({key: value}, sort_keys=True, ensure_ascii=False))
    return "\n".join(pieces)
