# Architecture

## System Overview

PS Price is a backend service that scrapes the PlayStation Store and tracks game prices over time. Users can set up "watches" to receive email notifications when prices drop or reach target levels.

```
┌─────────────────┐
│   Frontend      │  Next.js
│   (React)       │
└────────┬────────┘
         │ HTTP/JSON
         ▼
┌────────────────────────────────────────────────┐
│         FastAPI Backend (Python)               │
│                                                 │
│  ┌─────────────────────────────────────────┐  │
│  │        HTTP Endpoints (/api/*)          │  │
│  │  - Search, Games, Watches, Notifications│  │
│  └──────────────┬──────────────────────────┘  │
│                 │                              │
│  ┌──────────────▼──────────────────────────┐  │
│  │    PriceService (Business Logic)        │  │
│  │  - add_or_refresh_game()                │  │
│  │  - evaluate_watches()                   │  │
│  │  - create_watch()                       │  │
│  └──────────────┬──────────────────────────┘  │
│                 │                              │
│     ┌───────────┼───────────┐                  │
│     │           │           │                  │
│     ▼           ▼           ▼                  │
│ ┌────────┐ ┌───────────┐ ┌──────────┐         │
│ │Repo    │ │PS Store   │ │Email     │         │
│ │(Data   │ │Client     │ │Notifier  │         │
│ │Access) │ │(HTTP+Parse)│ │(SMTP)    │         │
│ └───┬────┘ └─┬─────────┘ └────────┬─┘         │
│     │        │                    │            │
│     └────────┼────────┬───────────┘            │
│              │        │                        │
└──────────────┼────────┼────────────────────────┘
               │        │
        ┌──────▼──┐  ┌──▼──────┐
        │PostgreSQL│ │PlayStation
        │ (SQLAlchemy)│ Store API
        │         │  │
        └─────────┘  └─────────┘
```

## Component Details

### 1. **FastAPI Application** (`main.py`)
- Entry point for the REST API
- Manages application lifecycle (startup/shutdown)
- Initializes all services and wires dependencies
- Exposes 15+ HTTP endpoints for games, watches, searches, notifications

**Endpoints:**
- `GET /healthz` - Health check with service status
- `GET /api/search` - Search PlayStation Store
- `POST /api/games` - Add or refresh tracked game
- `GET /api/games` - List all tracked games
- `GET /api/games/{id}` - Get game + price history
- `POST /api/games/{id}/refresh` - Force refresh
- `DELETE /api/games/{id}` - Delete tracked game
- `POST /api/watches` - Create a price watch
- `GET /api/watches` - List watches (with optional game filter)
- `PATCH /api/watches/{id}` - Update watch settings
- `DELETE /api/watches/{id}` - Delete watch
- `POST /api/watches/{id}/test` - Send test email
- `GET /api/notifications` - List notification log
- `POST /api/refresh-due` - Trigger scheduler refresh

### 2. **PriceService** (`service.py`)
Core business logic orchestrating the other layers:
- **add_or_refresh_game()** - Fetches from store, saves snapshot, evaluates watches
- **refresh_due_games()** - Batch refresh all games past check interval
- **search()** - Query PlayStation Store search
- **create_watch()** - Validate email + create watch + notify if target met
- **update_watch()** - Patch watch properties
- **test_watch()** - Send test email
- **_evaluate_watches()** (private) - Check if any watches should trigger
- **_target_met()** (private) - Check if watch target price is reached

### 3. **PlayStationStoreClient** (`ps_store.py`)
Async HTTP client for PlayStation Store scraping:
- **fetch_product()** - Get one product page, parse, return ProductSnapshot
- **search()** - Search store, parse results, return SearchResult list
- **_get_cached()** - Per-process in-memory cache with TTL
- **_get_text()** - HTTP GET with retry/backoff for 429 and 5xx
- **_wait_for_slot()** - Rate limiting (minimum seconds between requests)

**Parsing Strategy (defensive, multiple sources):**
1. JSON-LD structured data (`<script id="mfe-jsonld-tags" type="application/ld+json">`)
2. React component cache (`<script id="env:..." type="application/json">`)
3. Next.js Apollo state (`<script id="__NEXT_DATA__" type="application/json">`)
4. Fallback: extract product links from HTML

### 4. **Repository** (`repository.py`)
Data access layer - all SQL and database operations:
- **upsert_game_snapshot()** - Insert or update game + append price history
- **mark_game_error()** - Record fetch failure
- **list_games()** / **get_game()** - Query games
- **delete_game()** - Remove game (cascades to watches, history)
- **get_history()** - Get price history for one game (default 50 entries)
- **due_games()** - Query games past refresh interval
- **create_watch()** / **update_watch()** / **get_watch()** / **list_watches()** / **delete_watch()** - Watch CRUD
- **mark_watch_notified()** - Update last notification price
- **log_notification()** - Record notification attempt
- **list_notifications()** - Query notification log

### 5. **Database** (`app/db/` + Alembic)
PostgreSQL via SQLAlchemy 2.0 ORM and Alembic migrations:
- **Database.session()** — Context manager for SQLAlchemy sessions
- **Database.migrate()** — Run `alembic upgrade head` on startup

**Core tables** (see `app/db/models.py` for full schema): `games`, `price_history`, `watches`, `notifications`, `users`, `sessions`, `passkey_credentials`, and related auth/catalog tables.

### 6. **EmailNotifier** (`notifier.py`)
SMTP email sending with fallback logging:
- **send_price_notification()** - Async send via asyncio.to_thread
- **_send_sync()** - Synchronous SMTP (run in thread)
- **_subject()** / **_body()** - Format email
- Always logs notification to database (status: sent, failed, or skipped)

### 7. **PriceScheduler** (`scheduler.py`)
Background async task:
- **start()** - Launch background refresh task
- **stop()** - Graceful shutdown
- **_run()** - Main loop calling refresh_due_games at configured interval

### 8. **Configuration** (`config.py`)
Pydantic settings from environment variables (prefix `PS_PRICE_`):
- Database URL (`PS_PRICE_DATABASE_URL`)
- Store origin + locale + user agent
- Request timeout, min interval (rate limit), cache TTL, retry count
- Check interval (scheduler polling period)
- SMTP settings (host, port, auth, TLS/SSL)
- CORS origins
- Max search limit

### 9. **Domain Models** (`domain.py`)
Immutable dataclasses for type safety:
- **ProductSnapshot** - One product scrape result (frozen)
- **SearchResult** - Search result item (frozen)

### 10. **Money Utilities** (`money.py`)
Price parsing and formatting:
- **money_to_cents()** - Convert localized price strings → integer cents
- **format_cents()** - Format cents → display string with currency prefix
- **currency_for_locale()** - Infer currency from locale (11 mappings)

### 11. **Pydantic Schemas** (`schemas.py`)
Request/response validation:
- **GameCreate** - POST /api/games
- **GameOut** - GET /api/games
- **GameDetail** - GET /api/games/{id} (includes history)
- **SearchOut** - GET /api/search result item
- **WatchCreate** - POST /api/watches
- **WatchPatch** - PATCH /api/watches/{id}
- **WatchOut** - Watch response
- **NotificationOut** - Notification log item

## Data Flow

### Adding a Game
1. User calls `POST /api/games` with product reference (URL or ID)
2. **main.py** endpoint validates + calls **PriceService.add_or_refresh_game()**
3. **PriceService** calls **PlayStationStoreClient.fetch_product()**
4. **Client** HTTP GETs store page, caches result
5. **Client** parses HTML via multiple strategies → **ProductSnapshot**
6. **PriceService** calls **Repository.upsert_game_snapshot()**
7. **Repository** UPSERTs row in `games` table + INSERTs in `price_history`
8. **PriceService** calls **_evaluate_watches()** to check if any watches trigger
9. Response returned to user

### Scheduled Refresh
1. **PriceScheduler** wakes up (every N minutes)
2. Calls **PriceService.refresh_due_games()**
3. **Repository.due_games()** queries games past check_interval
4. For each game, call **refresh_game()** (same flow as above)
5. Watch evaluation happens after each game update
6. **EmailNotifier** sends emails for triggered watches
7. **Repository.log_notification()** records outcome (sent/failed/skipped)
8. **Repository.mark_watch_notified()** prevents duplicate sends at same price

### Watch Evaluation
When a game is refreshed, **_evaluate_watches()** checks enabled watches:
1. Get current price from refreshed game
2. If no current price, skip (product unavailable)
3. For each enabled watch on that game:
   - **Target met?** → Schedule notification with reason="target_met"
   - **Price dropped?** (current < previous AND notify_on_any_drop) → Schedule notification
   - **Already notified at this price?** → Skip to avoid duplicates
4. Call **EmailNotifier.send_price_notification()** for each triggered watch
5. On success, **mark_watch_notified()** updates last_notified_price_cents + timestamp

## Rate Limiting & Anti-Blocking

The implementation employs conservative strategies to avoid IP blocking:

1. **Per-Request Spacing** - Minimum `request_min_interval_seconds` (default 3s) between PS Store requests
2. **In-Process Cache** - Per-request cached results with TTL (`cache_ttl_seconds`, default 30min)
3. **HTTP Retries with Backoff** - Up to N retries with exponential backoff for 429 and 5xx
4. **429 (Too Many Requests) Handling** - Parses Retry-After header, sleeps accordingly
5. **Conservative Check Interval** - Defaults to 360 minutes (6 hours) between full game checks
6. **Visible Failure State** - Each game stores `last_error` to surface issues without retrying aggressively

## Testing

- **Unit Tests** — Money conversion, HTML parsing, repository operations
- **Integration Tests** — API endpoints, service layer, database initialization
- **Total Coverage** — 56+ tests verifying major paths

## Deployment

**Docker:**
```bash
docker compose up --build
```

**Environment Variables:**
- See `.env.example` for all configuration
- Only `PS_PRICE_SMTP_*` and `PS_PRICE_NOTIFICATION_FROM_EMAIL` are optional
- PostgreSQL data is persisted in Docker volume `ps-price-pg`

**Local Development:**
```bash
# Start Postgres (Docker or local install), then:
source .venv/bin/activate
cd backend && alembic upgrade head
uvicorn backend.app.main:app --reload --port 8000
```

## Frontend

The Next.js frontend:
1. Call `/api/search` to find games
2. Call `POST /api/games` to track games
3. Call `POST /api/watches` to create price watches
4. Display game list + price history chart
5. Manage watches (edit, delete, test)
6. Show notification log

