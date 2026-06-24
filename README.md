# PS Price — PlayStation Store Price Tracker

Track PlayStation Store game prices, view price history, and get email alerts when games drop or hit your target. Python/FastAPI backend + Next.js frontend, deployable with `docker compose up`.

## Quick start

```bash
docker compose up --build
```

- **Web app:** http://127.0.0.1:3000  
- **API:** proxied at http://127.0.0.1:3000/api/* (backend is internal-only in Docker)

On first deploy the **backend scheduler** syncs the full PlayStation catalog automatically. The frontend only reads from the API — it does not trigger sync on page load.

## Local development

Requires **PostgreSQL 16** (e.g. `docker compose up -d postgres` or a local install).

**Backend** (Python 3.14+):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PS_PRICE_DATABASE_URL=postgresql+psycopg://psprice:psprice@localhost:5432/psprice
alembic upgrade head
cd .. && uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

**Frontend** (Node 22+):

```bash
cd frontend
npm install
npm run dev
```

**Tests:**

```bash
cd backend && pytest -q
```

## Configuration

Copy `.env.example` to `.env` at the repo root (used by Docker Compose). All settings use the `PS_PRICE_` prefix — see `.env.example` for the full list.

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Local Docker, config, troubleshooting |
| [docs/DEPLOYMENT-AWS.md](docs/DEPLOYMENT-AWS.md) | Single-EC2 AWS deployment (Caddy + TLS) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and data flow |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Product context |
| [docs/SECURITY.md](docs/SECURITY.md) | Security model and production checklist |
| [AGENTS.md](AGENTS.md) | **Required reading for AI agents** |
| [backend/docs/BACKEND_GUIDE.md](backend/docs/BACKEND_GUIDE.md) | Backend walkthrough |
| [backend/docs/API.md](backend/docs/API.md) | HTTP API reference |
| [frontend/DESIGN.md](frontend/DESIGN.md) | Visual design system |

## Project layout

```
backend/          # FastAPI service, tests, Dockerfile
frontend/         # Next.js web UI
docs/             # Cross-cutting documentation
deploy/           # Caddyfile template for AWS
docker-compose.yml
```

## License

Provided as-is for personal use.
