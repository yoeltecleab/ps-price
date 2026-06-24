# Instructions for AI agents (Cursor, Copilot, etc.)

**Every agent working on this repository must follow these rules.**

## 1. Read before you code

| Area | Required reading |
|------|------------------|
| **Security** | [`docs/SECURITY.md`](docs/SECURITY.md) |
| **Backend** | [`backend/docs/BACKEND_GUIDE.md`](backend/docs/BACKEND_GUIDE.md) |
| **API** | [`backend/docs/API.md`](backend/docs/API.md) |
| **Deploy / prod** | [`docs/DEPLOYMENT-AWS.md`](docs/DEPLOYMENT-AWS.md) |
| **Frontend (Next.js 16)** | [`frontend/AGENTS.md`](frontend/AGENTS.md) |

Cursor rules in `.cursor/rules/` reinforce this (especially `security-mandatory.mdc`).

## 2. Security is not optional

- Treat security regressions as **blockers**.
- Do not expose port `8000` publicly or bypass the internal API key in production.
- Do not commit secrets or weaken `validate_production_settings()`.
- See `docs/SECURITY.md` for the full threat model and checklist.

> **Honest expectation:** No application can be "100% unhackable." We use layered controls, least privilege, and fail-closed defaults. Your job is to **strengthen**, never weaken, those layers.

## 3. Architecture constraints

```
Browser → Next.js (public) → /api/* proxy → FastAPI (internal only)
                                    ↑
                          X-PS-Price-Internal header
```

- SQLite lives on a Docker volume; single backend instance only.
- Admin = verified user + email in `PS_PRICE_ADMIN_EMAILS`.

## 4. When finishing work

- Run relevant tests (`pytest backend/tests/`).
- Update `.env.example` if you add settings.
- Update `docs/SECURITY.md` or deployment docs if behavior changes.
