"""Small CLI utility for ad-hoc fetching and searching of the PlayStation Store.

Run from the project root (with dependencies installed)::

    python -m backend.app.cli fetch UP0001-CUSA00001_00-EXAMPLEID
    python -m backend.app.cli search "god of war" --limit 5

This bypasses the web API and database — useful when debugging parsers in
``ps_store.py`` without starting FastAPI or the frontend.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, is_dataclass

from backend.app.config import get_settings
from backend.app.ps_store import PlayStationStoreClient


def _json_default(value):
    """Teach ``json.dumps`` how to serialize dataclasses and datetimes."""
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def _run() -> None:
    """Parse command-line arguments and run fetch or search."""
    parser = argparse.ArgumentParser(description="PlayStation Store live data helper")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Download one product by ID or URL")
    fetch.add_argument("product_ref", help="Product ID or store URL")
    fetch.add_argument("--locale", default=None, help="e.g. en-us")

    search = sub.add_parser("search", help="Search the store by keyword")
    search.add_argument("query")
    search.add_argument("--locale", default=None)
    search.add_argument("--limit", type=int, default=5)

    args = parser.parse_args()

    client = PlayStationStoreClient(get_settings())
    try:
        if args.command == "fetch":
            result = await client.fetch_product(args.product_ref, args.locale, force=True)
        else:
            result = await client.search(args.query, args.locale, args.limit, force=True)
        print(json.dumps(result, default=_json_default, indent=2, ensure_ascii=False))
    finally:
        await client.close()


def main() -> None:
    """Synchronous entry point — ``asyncio.run`` starts the async event loop."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
