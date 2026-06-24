"""PS Price backend package.

This folder is the Python backend for the PS Price app. A "backend" is the
server-side code that runs on your machine (or in the cloud) and talks to:

  - The database (PostgreSQL) where games, prices, and user data live
  - The PlayStation Store (to fetch prices)
  - The frontend (Next.js) over HTTP JSON APIs

The real application code lives in the ``backend.app`` sub-package. Start
reading there — ``main.py`` is the front door (HTTP routes), then follow
imports to see how data flows.

Suggested reading order for beginners:

  1. ``app/config.py``       — settings from environment variables
  2. ``app/database.py``     — database facade and session layer
  3. ``app/db/models.py``    — SQLAlchemy ORM models
  4. ``app/main.py``         — HTTP API endpoints (FastAPI)
  5. ``app/repository.py``   — SQL queries for games/watches
  6. ``app/service.py``      — business rules (when to sync, notify, etc.)
  7. ``app/auth_*.py``       — login, sessions, passkeys
"""
