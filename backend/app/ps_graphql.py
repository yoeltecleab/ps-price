"""PlayStation Store GraphQL client for catalog and deal listings.

**What is GraphQL?**

REST APIs often have many URLs (``/games``, ``/games/123``, …).  **GraphQL**
uses a single endpoint and lets the client describe *exactly* what data
shape it wants in one request.  The PlayStation Store web app uses GraphQL
behind the scenes to load big product grids.

**Why we use GraphQL here**

A normal HTML search/deals page only shows ~12–24 items (server-side
rendered).  Sony's public GraphQL API at ``web.np.playstation.com`` can
return **thousands** of products when we paginate with ``offset`` and
``page_size``.

**Persisted queries**

Instead of sending the full GraphQL query text every time, the client sends
a **SHA-256 hash** of a known query (``graphql_hash``).  The server already
has the query on file — this saves bandwidth and is a common production
pattern.

**Pagination loop**

``fetch_category_products`` repeats until ``pageInfo.isLast`` is true:

1. Build URL query params: ``operationName``, ``variables`` (JSON),
   ``extensions`` (hash).
2. ``GET`` the GraphQL endpoint (yes — this API uses HTTP GET).
3. Parse ``products`` or ``concepts`` arrays from the JSON response.
4. Increase ``offset`` by ``page_size`` and sleep ``min_interval`` seconds
   between pages to be polite.

**Concept vs Product nodes**

Browse grids return **Concepts** (a game idea) that may contain nested
**Products** (specific SKUs/editions).  ``parse_graphql_concept`` picks the
first valid product ID and merges concept-level media/price when needed.
"""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from backend.app.domain import SearchResult
from backend.app.money import currency_for_locale, money_to_cents
from backend.app.ps_store import _select_image, product_url

# Base URL for all GraphQL operations (GET requests with query params).
GRAPHQL_URL = "https://web.np.playstation.com/api/graphql/v1/op"

# --- Persisted query hashes (fingerprints of pre-registered GraphQL queries) ---
# Deals grid — flat `products` array (~4.5k sale items en-us)
DEALS_GRID_HASH = "9845afc0dbaab4965f6563fffc703f588c8e76792000e8610843b8d3ee9c4c09"
ALL_DEALS_CATEGORY_ID = "3f772501-f6f8-49b7-abac-874a88ca4897"

# Full store browse grid — `concepts` array (games with and without discounts)
STORE_CATALOG_GRID_ID = "28c9c2b2-cecc-415c-9a08-482a605cb104"
STORE_CATALOG_GRID_HASH = "4e41660b6732f35c99fc5541926b7502a09557924e8c2cfebd1beb1a5c8c8f81"
# Facets tell the API which filter metadata to include alongside results.
STORE_CATALOG_FACETS = [
    "targetPlatforms",
    "productGenres",
    "webBasePrice",
    "productReleaseDate",
    "storeDisplayClassification",
]

LOCALE_ACCEPT_LANGUAGE = {
    "en-us": "en-US,en;q=0.9",
    "en-gb": "en-GB,en;q=0.9",
    "de-de": "de-DE,de;q=0.9",
    "fr-fr": "fr-FR,fr;q=0.9",
}


class GraphQLClientError(RuntimeError):
    """Raised when the PlayStation GraphQL API returns errors.

    GraphQL responses can be HTTP 200 OK but still contain an ``errors``
    array in the JSON body — we treat that as a hard failure.
    """


def locale_accept_language(locale: str) -> str:
    """Map a store locale to an HTTP ``Accept-Language`` header value.

    Servers may return localized price strings based on this header.
    """
    return LOCALE_ACCEPT_LANGUAGE.get(locale.lower(), "en-US,en;q=0.9")


def shard_filter_by(shard: str) -> list[str]:
    """Map a browse shard label to GraphQL filterBy tokens."""
    label = (shard or "").strip()
    if not label or label.lower() in {"all", "base", "default"}:
        return []
    return [f"targetPlatforms:{label.upper()}"]


def parse_graphql_product(
    product: dict[str, Any],
    locale: str,
    origin: str,
    *,
    popularity_rank: int | None = None,
    name_override: str | None = None,
) -> SearchResult | None:
    """Convert a GraphQL Product node into a SearchResult.

    Returns ``None`` (instead of raising) when required fields are missing —
    a single bad row should not abort an entire catalog sync.
    """
    product_id = product.get("id")
    name = name_override or product.get("name")
    if not isinstance(product_id, str) or not product_id or not isinstance(name, str) or not name:
        return None

    price = product.get("price") if isinstance(product.get("price"), dict) else {}
    currency = currency_for_locale(locale)
    current_formatted = _first_str(price.get("discountedPrice"), price.get("basePrice"))
    original_formatted = _first_str(price.get("basePrice"))
    current_cents = money_to_cents(current_formatted)
    original_cents = money_to_cents(original_formatted)

    platforms = [str(p) for p in product.get("platforms", []) if p]

    return SearchResult(
        product_id=product_id,
        locale=locale,
        name=name,
        store_url=product_url(origin, locale, product_id),
        image_url=_select_image(product.get("media")),
        platforms=platforms,
        currency=currency,
        current_price_cents=current_cents,
        current_price_formatted=current_formatted,
        original_price_cents=original_cents,
        original_price_formatted=original_formatted,
        discount_text=_first_str(price.get("discountText"), price.get("upsellText")),
        category=_first_str(product.get("localizedStoreDisplayClassification")),
        popularity_rank=popularity_rank,
    )


def parse_graphql_concept(
    concept: dict[str, Any],
    locale: str,
    origin: str,
    *,
    popularity_rank: int | None = None,
) -> SearchResult | None:
    """Convert a browse-grid Concept node into a SearchResult.

    A **Concept** is the marketing wrapper (title, artwork).  It contains one
    or more **Product** entries (Standard Edition, Deluxe, etc.).  We pick the
    first product with a valid ``id`` and merge concept-level fields when the
    product object is incomplete.
    """
    name = concept.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    products = concept.get("products") or []
    product: dict[str, Any] | None = None
    product_id: str | None = None
    for candidate in products:
        if isinstance(candidate, dict) and isinstance(candidate.get("id"), str) and candidate["id"]:
            product = candidate
            product_id = candidate["id"]
            break
    if not product_id:
        return None

    merged = dict(product)
    if not merged.get("media") and concept.get("media"):
        merged["media"] = concept.get("media")
    if not isinstance(merged.get("price"), dict) and isinstance(concept.get("price"), dict):
        merged["price"] = concept.get("price")
    if not merged.get("platforms") and concept.get("platforms"):
        merged["platforms"] = concept.get("platforms")

    return parse_graphql_product(
        merged,
        locale,
        origin,
        popularity_rank=popularity_rank,
        name_override=name.strip(),
    )


async def fetch_category_products(
    client: httpx.AsyncClient,
    *,
    category_id: str,
    locale: str,
    origin: str,
    page_size: int = 100,
    max_pages: int | None = None,
    min_interval: float = 1.0,
    graphql_hash: str = DEALS_GRID_HASH,
    sort_by: dict[str, Any] | None | object = ...,
    filter_by: list[str] | None = None,
    facet_options: list[str] | None = None,
    on_page: Callable[[dict[str, Any]], None] | None = None,
) -> list[SearchResult]:
    """Paginate a categoryGridRetrieve query until all products are fetched.

    This is the core GraphQL pagination loop:

    - ``offset`` = how many items to skip (0, page_size, 2*page_size, …)
    - ``page_size`` = how many items per request (often 100)
    - ``max_pages`` = optional safety cap for testing/dev
    - ``on_page`` = optional callback so callers can log progress

    The ``sort_by is ...`` sentinel (Ellipsis) lets callers pass ``None``
    explicitly to disable sorting while still using the default otherwise.
    """
    import asyncio

    if sort_by is ...:
        sort_by = {"name": "sales30", "isAscending": False}

    results: list[SearchResult] = []
    seen: set[str] = set()  # dedupe by product_id across pages
    offset = 0
    page_index = 0

    while True:
        if max_pages is not None and page_index >= max_pages:
            break

        # GraphQL variables are serialized to compact JSON for the URL.
        variables: dict[str, Any] = {
            "id": category_id,
            "pageArgs": {"size": page_size, "offset": offset},
            "sortBy": sort_by,
            "filterBy": filter_by or [],
            "facetOptions": facet_options or [],
        }
        params = {
            "operationName": "categoryGridRetrieve",
            "variables": json.dumps(variables, separators=(",", ":")),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": graphql_hash,
                    }
                },
                separators=(",", ":"),
            ),
        }
        url = f"{GRAPHQL_URL}?{urlencode(params)}"
        # Reuse the httpx.AsyncClient passed in from PlayStationStoreClient.
        response = await client.get(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Language": locale_accept_language(locale),
                "x-apollo-operation-name": "categoryGridRetrieve",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise GraphQLClientError(str(payload["errors"]))

        grid = payload.get("data", {}).get("categoryGridRetrieve") or {}
        products = grid.get("products") or []
        concepts = grid.get("concepts") or []
        page_info = grid.get("pageInfo") or {}

        page_count = 0
        for product in products:
            if not isinstance(product, dict):
                continue
            parsed = parse_graphql_product(
                product,
                locale,
                origin,
                popularity_rank=len(results) + 1,
            )
            if parsed and parsed.product_id not in seen:
                seen.add(parsed.product_id)
                results.append(parsed)
                page_count += 1

        for concept in concepts:
            if not isinstance(concept, dict):
                continue
            parsed = parse_graphql_concept(
                concept,
                locale,
                origin,
                popularity_rank=len(results) + 1,
            )
            if parsed and parsed.product_id not in seen:
                seen.add(parsed.product_id)
                results.append(parsed)
                page_count += 1

        if on_page:
            on_page(
                {
                    "page": page_index + 1,
                    "offset": offset,
                    "page_count": page_count,
                    "total": len(results),
                    "reported_total": page_info.get("totalCount"),
                }
            )

        if page_info.get("isLast") or (not products and not concepts):
            break

        offset += page_size
        page_index += 1
        # Pause between pages — same politeness idea as ps_store rate limiting.
        if min_interval > 0:
            await asyncio.sleep(min_interval)

    return results


async def fetch_store_catalog(
    client: httpx.AsyncClient,
    *,
    locale: str,
    origin: str,
    shards: list[str],
    page_size: int = 100,
    max_pages: int | None = None,
    min_interval: float = 1.0,
    deals_category_id: str = ALL_DEALS_CATEGORY_ID,
) -> list[SearchResult]:
    """Fetch the full PS Store catalog (all games) plus deal pricing overlay.

    Strategy (two-pass merge):

    1. For each **shard** (e.g. PS5, PS4, or "all"), download the browse
       grid and store rows in a dict keyed by ``product_id``.
    2. Download the **deals** grid and overwrite matching IDs — deal rows
       carry fresher sale pricing.

    Using a dict means later rows automatically update earlier ones.
    """
    merged: dict[str, SearchResult] = {}

    for shard in shards:
        shard_rows = await fetch_category_products(
            client,
            category_id=STORE_CATALOG_GRID_ID,
            locale=locale,
            origin=origin,
            page_size=page_size,
            max_pages=max_pages,
            min_interval=min_interval,
            graphql_hash=STORE_CATALOG_GRID_HASH,
            sort_by=None,
            filter_by=shard_filter_by(shard),
            facet_options=STORE_CATALOG_FACETS,
        )
        for row in shard_rows:
            merged[row.product_id] = row

    deal_rows = await fetch_category_products(
        client,
        category_id=deals_category_id,
        locale=locale,
        origin=origin,
        page_size=page_size,
        max_pages=max_pages,
        min_interval=min_interval,
        graphql_hash=DEALS_GRID_HASH,
    )
    for row in deal_rows:
        merged[row.product_id] = row

    return list(merged.values())


def _first_str(*values: object) -> str | None:
    """Return the first non-empty string from ``values`` (helper for parsing)."""
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None
