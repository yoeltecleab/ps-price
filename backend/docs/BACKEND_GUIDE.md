# PS Price Backend — Beginner's Guide

This document explains how the Python backend works, written for developers who are new to Python or FastAPI. Read it top-to-bottom once, then use it as a reference.

---

## What does this backend do?

PS Price is a **PlayStation Store price tracker**. The backend:

1. **Syncs thousands of deals** from the PlayStation Store into a local SQLite database
2. **Tracks games** you care about and records price history over time
3. **Sends email alerts** when prices drop
4. **Exposes a REST API** that the Next.js frontend calls

Think of it as three layers:

```
┌─────────────────────────────────────────┐
│  HTTP API (FastAPI)     main.py         │  ← What the browser calls
├─────────────────────────────────────────┤
│  Business logic         service.py      │  ← Rules: search, sync, alerts
├─────────────────────────────────────────┤
│  Data access            repository.py   │  ← SQL queries
├─────────────────────────────────────────┤
│  SQLite database        database.py     │  ← Files on disk
└─────────────────────────────────────────┘
         ↑                          ↑
   ps_store.py              ps_graphql.py
   (scrape product pages)   (fetch 4000+ deals)
```

---

## Project layout

```
backend/
├── app/
│   ├── main.py          # FastAPI app + HTTP routes
│   ├── service.py       # Business logic (PriceService)
│   ├── repository.py    # Database queries (Repository)
│   ├── database.py      # SQLite setup + schema migrations
│   ├── schemas.py       # Pydantic models for API request/response JSON
│   ├── domain.py        # Plain Python dataclasses (ProductSnapshot, SearchResult)
│   ├── config.py        # Settings from environment variables
│   ├── ps_store.py      # HTTP client + HTML parser for PlayStation Store
│   ├── ps_graphql.py    # GraphQL client for full deals catalog (~4400 games)
│   ├── scheduler.py     # Background timer for periodic price checks
│   ├── notifier.py      # Email sending (SMTP)
│   ├── money.py         # Price parsing helpers ($29.99 → 2999 cents)
│   └── cli.py           # Command-line tool for manual store queries
├── docs/
│   ├── BACKEND_GUIDE.md # This file
│   └── API.md           # HTTP endpoint reference
├── tests/               # Pytest suite
├── Dockerfile
└── requirements.txt
```

---

## Core concepts

### 1. Settings (`config.py`)

All configuration comes from **environment variables** prefixed with `PS_PRICE_`.

```python
from backend.app.config import get_settings

settings = get_settings()
print(settings.database_path)   # default: backend/data/ps_price.sqlite3
print(settings.store_locale)      # default: en-us
```

Important settings:

| Variable | Default | Meaning |
|----------|---------|---------|
| `PS_PRICE_DATABASE_PATH` | `backend/data/ps_price.sqlite3` | Where SQLite file lives |
| `PS_PRICE_STORE_LOCALE` | `en-us` | PlayStation Store region |
| `PS_PRICE_SCHEDULER_ENABLED` | `true` | Background price checks |
| `PS_PRICE_CHECK_INTERVAL_MINUTES` | `360` | How often to re-check tracked games |
| `PS_PRICE_SMTP_HOST` | (empty) | SMTP server for email alerts |

`get_settings()` is cached — call it anywhere; you always get the same object.

### 2. Database (`database.py` + `app/db/`)

**Docker / production** uses **PostgreSQL** via `PS_PRICE_DATABASE_URL`. **Local pytest** defaults to **SQLite** (`PS_PRICE_DATABASE_PATH`) when no URL is set.

```python
from backend.app.database import create_database, Database
from backend.app.config import get_settings

db = create_database(get_settings())  # picks Postgres or SQLite from settings
db.migrate()

with db.connect() as conn:
    rows = conn.execute("SELECT * FROM games LIMIT 5").fetchall()
```

| Setting | When |
|---------|------|
| `PS_PRICE_DATABASE_URL` | Docker Compose, production (required when `PRODUCTION_MODE=true`) |
| `PS_PRICE_DATABASE_PATH` | Local tests / CLI without Postgres |

**Tables:**

| Table | Purpose |
|-------|---------|
| `games` | Every product we know about (deals catalog + tracked games) |
| `price_history` | Timestamped price snapshots per game |
| `watches` | User email alert rules |
| `notifications` | Log of emails sent (or failed) |
| `catalog_meta` | Key/value store (last sync time, counts) |

The `games` table has two modes:

- **`is_tracked = 0`** — synced deal in the catalog (from GraphQL)
- **`is_tracked = 1`** — game you explicitly added to your library

### 3. Repository (`repository.py`)

The **Repository** is the only place that runs SQL. The rest of the app never writes raw SQL.

```python
from backend.app.repository import Repository

repo = Repository(db)

# List filtered deals
items, total = repo.list_deals(
    q="god of war",
    platform="PS5",
    min_discount=20,
    sort="discount",
    limit=48,
    offset=0,
)

# Upsert a price snapshot (used when refreshing a tracked game)
game, previous_price = repo.upsert_game_snapshot(snapshot)
```

**Key methods:**

| Method | What it does |
|--------|--------------|
| `list_deals()` | Filtered/sorted catalog with pagination |
| `search_catalog()` | Local text search by name or product ID |
| `upsert_catalog_entries()` | Bulk insert/update from deals sync |
| `upsert_game_snapshot()` | Update one game + append price history |
| `get_game()` / `get_game_by_product()` | Fetch single game rows |
| `set_catalog_meta()` / `get_catalog_meta()` | Sync timestamps and stats |

### 4. Domain models (`domain.py`)

These are **frozen dataclasses** — immutable snapshots of data moving between components:

```python
@dataclass(frozen=True)
class ProductSnapshot:
    product_id: str       # e.g. "UP9000-CUSA07408_00-00000000GODOFWAR"
    locale: str           # e.g. "en-us"
    name: str
    current_price_cents: int | None
    current_price_formatted: str | None
    # ... more fields
```

- **`ProductSnapshot`** — full product state when refreshing a tracked game
- **`SearchResult`** — lightweight row for search results and catalog sync

### 5. PlayStation Store clients

We talk to PlayStation two ways:

#### HTML scraper (`ps_store.py`)

```python
client = PlayStationStoreClient(settings)

# Fetch and parse a product page
snapshot = await client.fetch_product("UP9000-...", "en-us")

# Search the store (parses search results HTML)
results = await client.search("007", "en-us", limit=12)
```

Features:
- Rate limiting (waits between requests so we don't hammer Sony)
- In-memory cache (30 min TTL by default)
- Retries on 429/5xx errors
- Parses embedded JSON from PlayStation's Next.js pages

#### GraphQL client (`ps_graphql.py`)

The deals page HTML only shows ~12 games. The full catalog uses Sony's public GraphQL browse grid (`concepts`, ~10k per shard) plus an overlay pass from the All Deals category for accurate sale pricing:

```python
from backend.app.ps_graphql import fetch_store_catalog

rows = await fetch_store_catalog(
    client,
    locale="en-us",
    origin="https://store.playstation.com",
    shards=["all", "PS5", "PS4"],
    page_size=100,
)
```

Configure shards with `PS_PRICE_CATALOG_SYNC_SHARDS` (default `all,PS5,PS4`). A full sync can take several minutes because each page is rate-limited.

### 6. Service layer (`service.py`)

`PriceService` is the **brain** — it coordinates repository, store client, and email notifier.

```python
service = PriceService(settings, repo, store_client, notifier)

# Sync full catalog into local database
result = await service.sync_deals()
# → {"synced": 12000, "fetched": 12000, "locale": "en-us", "catalog_total": 12000}

# Search local catalog only (DB)
hits = await service.search_unified("007", "en-us", limit=12)

# Add or refresh a tracked game
game = await service.add_or_refresh_game("UP9000-CUSA07408_00-00000000GODOFWAR", "en-us")
```

**Search flow** (`search_unified`):

1. Query local SQLite catalog by name or product ID
2. Results include games with and without active discounts once a catalog sync has run

### 7. API layer (`main.py`)

FastAPI maps HTTP routes to service methods:

```python
@app.get("/api/deals")
def list_deals(...):
    return service.list_deals(...)

@app.get("/api/search")
async def search_games(q: str, ...):
    return await service.search(q, locale, limit)
```

**Startup (`lifespan`):**

1. Create database, run migrations
2. Wire up repository, store client, notifier, service, scheduler
3. Start background scheduler (runs a full catalog sync immediately on deploy, then on `PS_PRICE_FEED_SYNC_INTERVAL_MINUTES`)

**Important endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/deals` | Paginated filtered deals |
| GET | `/api/search?q=` | Local catalog search |
| GET | `/api/suggest?q=` | Autocomplete from local DB |
| POST | `/api/sync-deals` | Trigger full deals sync |
| GET | `/api/sync-status` | Catalog size, last sync time |
| POST | `/api/games` | Add game to library by product ID |
| GET | `/api/games/{id}` | Game detail + price history |
| POST | `/api/games/{id}/refresh` | Re-fetch price from store |
| POST | `/api/watches` | Create price alert |
| GET | `/healthz` | Health check |

Interactive docs: **http://localhost:8000/docs**

### 8. Schemas (`schemas.py`)

Pydantic models validate API input and shape JSON output:

```python
class GameOut(BaseModel):
    id: int
    name: str
    current_price_cents: int | None
    discount_percent: int | None
    platforms: list[str] = []
    # ...
```

FastAPI uses these automatically — invalid requests get HTTP 422 with clear errors.

### 9. Scheduler (`scheduler.py`)

Runs periodic tasks in the background:

- **Deals sync** — refresh the full catalog
- **Price checks** — re-fetch all tracked games due for update

Controlled by `PS_PRICE_SCHEDULER_ENABLED` and `PS_PRICE_CHECK_INTERVAL_MINUTES`.

### 10. Email notifier (`notifier.py`)

When a watch triggers (price dropped or hit target), `EmailNotifier` sends SMTP email and logs the result to the `notifications` table.

If SMTP isn't configured, it logs what it *would* send (useful for development).

---

## Data flow examples

### Example A: User searches for "007"

```
Browser  →  GET /api/search?q=007
              ↓
           main.py  →  service.search_unified()
              ↓                    ↓
         store_client.search()   repo.search_catalog()
         (live PS Store)         (local SQLite)
              ↓                    ↓
           merge + dedupe by product_id
              ↓
           JSON list of SearchOut objects
```

### Example B: Startup deals sync

```
lifespan()  →  asyncio.create_task(service.sync_deals())
                    ↓
              store_client.fetch_deals()
                    ↓
              ps_graphql.fetch_category_products()  [~45 pages × 100 items]
                    ↓
              repo.upsert_catalog_entries()  [batch insert/update]
                    ↓
              catalog_meta: last_deals_sync, last_deals_count
```

### Example C: Price alert fires

```
scheduler  →  service.refresh_due_games()
                  ↓
             repo.upsert_game_snapshot()  [new price in price_history]
                  ↓
             compare vs watch rules (target price? any drop?)
                  ↓
             notifier.send()  →  SMTP email + notifications row
```

---

## Money handling (`money.py`)

PlayStation shows prices as strings like `"$29.99"`. We store **integer cents** internally:

```python
from backend.app.money import money_to_cents, format_cents, discount_percent

money_to_cents("$29.99")   # → 2999
format_cents(2999, "USD")   # → "$29.99"
discount_percent(2999, 5999)  # → 50
```

Always use cents for comparisons and math. Format only for display.

---

## Running and testing

### Start the server

```bash
source .venv/bin/activate
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

### Run tests

```bash
pytest
```

Tests use a temporary SQLite database and mock the PlayStation Store where needed.

### CLI (manual store queries)

```bash
python -m backend.app.cli search "god of war" --limit 5
python -m backend.app.cli fetch UP9000-CUSA07408_00-00000000GODOFWAR
```

### Trigger deals sync manually

```bash
curl -X POST http://localhost:8000/api/sync-deals
curl http://localhost:8000/api/sync-status
```

---

## Docker notes

In Docker Compose:

- Database persists in volume `ps-price-data` at `/data/ps_price.sqlite3`
- Backend listens on port `8000`
- Frontend proxies `/api/*` to `http://backend:8000`

First startup syncs ~4400 deals in the background (~45–60 seconds).

---

## Common tasks for developers

### Add a new API field to games

1. Add column in `database.py` → `_migrate_games_columns()`
2. Update `repository.py` upsert methods
3. Add field to `GameOut` in `schemas.py`
4. Update frontend `types.ts`

### Add a new sort option for deals

1. Add key to `order_map` in `repository.list_deals()`
2. Update regex pattern on `sort` query param in `main.py`
3. Add option in frontend `FilterPanel.tsx`

### Add a new data source

1. Create a client module (like `ps_graphql.py`)
2. Parse into `SearchResult` or `ProductSnapshot`
3. Call from `service.py`
4. Expose via `main.py` route

---

## Glossary

| Term | Meaning |
|------|---------|
| **product_id** | PlayStation's unique ID, e.g. `UP9000-CUSA07408_00-00000000GODOFWAR` |
| **locale** | Store region, e.g. `en-us`, `en-gb` |
| **catalog** | All deals synced locally (`is_tracked = 0`) |
| **tracked** | Games in your library (`is_tracked = 1`) |
| **watch** | Email alert rule for a tracked game |
| **snapshot** | One point-in-time price reading |

---

## Further reading

- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Pydantic documentation](https://docs.pydantic.dev/)
- [SQLite Python tutorial](https://docs.python.org/3/library/sqlite3.html)
- Project API reference: `backend/docs/API.md`
- Architecture overview: `docs/ARCHITECTURE.md`
- Deployment: `docs/DEPLOYMENT.md`
