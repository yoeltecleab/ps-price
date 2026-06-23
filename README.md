# PS Price — PlayStation Store Price Tracker

Track PlayStation Store game prices, view price history, and get email alerts when games drop or hit your target. Includes a Python/FastAPI backend and a Next.js web UI, deployable with a single `docker compose up`.

## Key Features

- **Live deals homepage** — PS Store sale listings synced to your local catalog
- **Deep filtering** — sort by discount, price, name; filter by platform, min discount, max price
- **Autocomplete search** — instant suggestions from your synced game database
- **Price tracking** — add any deal to your library with one click
- **Price history & charts** — full snapshot history per tracked game
- **Email alerts** — target price and any-drop notifications
- **18 visual themes** — dark, balanced, and light palettes (Settings → gear icon)
- **Background sync** — deals and tracked games refresh on a schedule

## Quick Start

### Docker (recommended)

```bash
docker compose up --build
```

- **Web app:** http://127.0.0.1:3000
- **API / docs:** http://127.0.0.1:8000/docs

### Local development

**Backend** (Python 3.14+, `.venv/`):

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

**Frontend** (Node 22+):

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:3000 — API requests are proxied to the backend via Next.js rewrites.


## 📧 Email Notifications (Optional)

By default, notifications are logged without sending. To enable email:

1. Copy `.env.example` to `.env`
2. Configure SMTP credentials:
   ```env
   PS_PRICE_SMTP_HOST=smtp.gmail.com
   PS_PRICE_SMTP_PORT=587
   PS_PRICE_SMTP_USERNAME=your-email@gmail.com
   PS_PRICE_SMTP_PASSWORD=your-app-password
   PS_PRICE_NOTIFICATION_FROM_EMAIL=your-email@gmail.com
   PS_PRICE_SMTP_USE_TLS=true
   ```
3. Restart the service

> **Note:** Gmail users should use an [App Password](https://support.google.com/accounts/answer/185833), not your account password.

## 🧪 Testing

Run all tests (27 tests):
```bash
source .venv/bin/activate
pytest tests/ -v
```

Run specific test file:
```bash
pytest tests/test_integration.py -v
```

## 📡 API Examples

### Health Check
```bash
curl http://127.0.0.1:8000/healthz
```

### Search PlayStation Store
```bash
curl "http://127.0.0.1:8000/api/search?q=god+of+war&locale=en-us&limit=10"
```

### Add Game to Track
```bash
curl -X POST http://127.0.0.1:8000/api/games \
  -H "Content-Type: application/json" \
  -d '{
    "product_ref": "UP9000-PPSA08329_00-GOWRAGNAROK00000",
    "locale": "en-us"
  }'
```

### List Tracked Games
```bash
curl http://127.0.0.1:8000/api/games
```

### Create Price Watch
```bash
curl -X POST http://127.0.0.1:8000/api/watches \
  -H "Content-Type: application/json" \
  -d '{
    "game_id": 1,
    "email": "you@example.com",
    "target_price_cents": 2999,
    "notify_on_any_drop": true
  }'
```

### List Watches
```bash
curl http://127.0.0.1:8000/api/watches
```

### Update Watch
```bash
curl -X PATCH http://127.0.0.1:8000/api/watches/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### Send Test Email
```bash
curl -X POST http://127.0.0.1:8000/api/watches/1/test
```

### View Notification Log
```bash
curl "http://127.0.0.1:8000/api/notifications?limit=50"
```

### Force Refresh All Due Games
```bash
curl -X POST http://127.0.0.1:8000/api/refresh-due
```

## 📚 Documentation

- **[API.md](docs/API.md)** - Complete endpoint reference
- **[BACKEND_GUIDE.md](backend/BACKEND_GUIDE.md)** - Beginner-friendly backend walkthrough
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design, data flow, rate limiting strategy

## 🔧 Configuration

All settings use environment variables with prefix `PS_PRICE_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `/data/ps_price.sqlite3` | SQLite database location |
| `STORE_LOCALE` | `en-us` | Default PlayStation Store locale |
| `SCHEDULER_ENABLED` | `true` | Enable background refresh |
| `CHECK_INTERVAL_MINUTES` | `360` | Minutes between game refreshes (0 = check every refresh) |
| `CACHE_TTL_SECONDS` | `1800` | Seconds to cache store responses |
| `REQUEST_MIN_INTERVAL_SECONDS` | `3` | Minimum seconds between PS Store requests |
| `CORS_ORIGINS` | `http://localhost:3000` | CORS allowed origins |
| `SMTP_HOST` | (empty) | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | (empty) | SMTP username |
| `SMTP_PASSWORD` | (empty) | SMTP password |
| `SMTP_USE_TLS` | `true` | Use STARTTLS |
| `SMTP_USE_SSL` | `false` | Use SSL/TLS connection |
| `NOTIFICATION_FROM_EMAIL` | (empty) | From address for emails |

See `.env.example` for full reference.

## 🛡️ Anti-Blocking Features

The implementation is designed to avoid IP blocking:

1. **Request Spacing** - Enforces minimum interval between PlayStation Store requests
2. **HTTP Caching** - Per-process cache prevents duplicate requests
3. **Retry/Backoff** - Exponential backoff for 429 and server errors
4. **Conservative Polling** - Default 6-hour refresh interval (configurable)
5. **Visible Errors** - Each game tracks error state without aggressive retries

## 🏗️ Project Structure

```
backend/
├── app/
│   ├── main.py           # FastAPI app + endpoints
│   ├── service.py        # Business logic
│   ├── repository.py     # Data access layer
│   ├── database.py       # SQLite schema + connection
│   ├── ps_store.py       # PlayStation Store client + parsing
│   ├── notifier.py       # Email notifications
│   ├── scheduler.py      # Background task scheduler
│   ├── config.py         # Settings from environment
│   ├── domain.py         # Data models (ProductSnapshot, SearchResult)
│   ├── schemas.py        # Pydantic request/response models
│   ├── money.py          # Price parsing/formatting
│   └── cli.py            # CLI utility
tests/
├── test_integration.py   # API endpoint tests
├── test_money.py         # Money conversion tests
├── test_ps_store_parser.py   # HTML parsing tests
└── test_repository.py    # Database tests
docs/
├── API.md                # API reference
ARCHITECTURE.md           # System design documentation
```

## 🐳 Docker Deployment

**Build:**
```bash
docker compose build
```

**Run:**
```bash
docker compose up -d
```

**Logs:**
```bash
docker compose logs -f backend
```

**Stop:**
```bash
docker compose down
```

**Data Persistence:**
- Database stored in Docker volume `ps-price-data`
- Survives container restart/rebuild

## 🔍 Monitoring

**Check Service Status:**
```bash
curl http://127.0.0.1:8000/healthz?scheduler=true
```

Response includes:
- Service status
- Email configuration
- Scheduler running/enabled status
- Database path

**View Recent Errors:**
```bash
curl "http://127.0.0.1:8000/api/notifications?limit=100" | grep -i error
```

**Check Game Status:**
```bash
curl http://127.0.0.1:8000/api/games | jq '.[] | {name, last_checked_at, last_error}'
```

## 📝 Development

**Run Tests:**
```bash
pytest tests/ -v
```

**Check Code Quality:**
```bash
python -m pytest tests/ --tb=short -q
```

**CLI Utility (manual testing):**
```bash
python -m backend.app.cli fetch UP9000-PPSA08329_00-GOWRAGNAROK00000
python -m backend.app.cli search "god of war" --limit 5
```

## Project Structure

```
backend/app/          # FastAPI service (API, scheduler, PS Store client)
frontend/src/         # Next.js web UI
tests/                # Backend test suite
docs/API.md           # API reference
docker-compose.yml    # Full stack deployment
PRODUCT.md            # Product context (Impeccable design)
DESIGN.md             # Visual design system
```

## Future work

- Additional PlayStation Store locales
- Request authentication for multi-user deployments
- Prometheus metrics

## 📄 License

All code is provided as-is for personal use.

## ✅ Verification Checklist

- [x] Backend 100% functional with all endpoints working
- [x] 27 tests passing (integration + unit tests)
- [x] Database schema created and tested
- [x] Rate limiting + caching implemented
- [x] Email notifications (with fallback logging)
- [x] Docker setup with persistent volumes
- [x] Comprehensive API documentation
- [x] Architecture documentation
- [x] Environment configuration via .env
- [x] Health check + monitoring endpoints
