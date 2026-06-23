"""Small CLI utility for ad-hoc fetching and searching of the PlayStation Store.

This script can be executed directly to inspect live store data without
running the full API. Output is JSON-encoded using a small helper that
converts dataclasses and datetimes into serializable forms.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, is_dataclass

from backend.app.config import get_settings
from backend.app.ps_store import PlayStationStoreClient


def _json_default(value):
    """JSON default serializer for dataclasses and datetimes."""
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def _run() -> None:
    """Parse CLI args and run the requested subcommand (fetch or search)."""
    parser = argparse.ArgumentParser(description="PlayStation Store live data helper")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("product_ref")
    fetch.add_argument("--locale", default=None)
    search = sub.add_parser("search")
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
    """Entry point for the CLI; runs the async runner."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
