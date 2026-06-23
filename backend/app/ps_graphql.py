"""PlayStation Store GraphQL client for catalog and deal listings.

The public GraphQL API at web.np.playstation.com exposes paginated
category grids with thousands of products — far more than SSR HTML pages
surface (typically ~12–24 items).
"""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from backend.app.domain import SearchResult
from backend.app.money import currency_for_locale, money_to_cents
from backend.app.ps_store import _select_image, product_url

GRAPHQL_URL = "https://web.np.playstation.com/api/graphql/v1/op"
CATEGORY_GRID_HASH = "9845afc0dbaab4965f6563fffc703f588c8e76792000e8610843b8d3ee9c4c09"

# en-us "All Deals" category (cat.gma.AllDeals) — ~4k+ products
ALL_DEALS_CATEGORY_ID = "3f772501-f6f8-49b7-abac-874a88ca4897"

LOCALE_ACCEPT_LANGUAGE = {
    "en-us": "en-US,en;q=0.9",
    "en-gb": "en-GB,en;q=0.9",
    "de-de": "de-DE,de;q=0.9",
    "fr-fr": "fr-FR,fr;q=0.9",
}


class GraphQLClientError(RuntimeError):
    """Raised when the PlayStation GraphQL API returns errors."""


def locale_accept_language(locale: str) -> str:
    return LOCALE_ACCEPT_LANGUAGE.get(locale.lower(), "en-US,en;q=0.9")


def parse_graphql_product(
    product: dict[str, Any],
    locale: str,
    origin: str,
    *,
    popularity_rank: int | None = None,
) -> SearchResult | None:
    """Convert a GraphQL Product node into a SearchResult."""
    product_id = product.get("id")
    name = product.get("name")
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


async def fetch_category_products(
    client: httpx.AsyncClient,
    *,
    category_id: str,
    locale: str,
    origin: str,
    page_size: int = 100,
    max_pages: int | None = None,
    min_interval: float = 1.0,
    on_page: Callable[[dict[str, Any]], None] | None = None,
) -> list[SearchResult]:
    """Paginate a categoryGridRetrieve query until all products are fetched."""
    import asyncio

    results: list[SearchResult] = []
    seen: set[str] = set()
    offset = 0
    page_index = 0

    while True:
        if max_pages is not None and page_index >= max_pages:
            break

        variables = {
            "id": category_id,
            "pageArgs": {"size": page_size, "offset": offset},
            "sortBy": {"name": "sales30", "isAscending": False},
            "filterBy": [],
            "facetOptions": [],
        }
        params = {
            "operationName": "categoryGridRetrieve",
            "variables": json.dumps(variables, separators=(",", ":")),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": CATEGORY_GRID_HASH,
                    }
                },
                separators=(",", ":"),
            ),
        }
        url = f"{GRAPHQL_URL}?{urlencode(params)}"
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

        if page_info.get("isLast") or not products:
            break

        offset += page_size
        page_index += 1
        if min_interval > 0:
            await asyncio.sleep(min_interval)

    return results


def _first_str(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None
