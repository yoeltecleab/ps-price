# Security — PS Price

This document defines how PS Price is secured and what every contributor (human or AI) must preserve.

**Reality check:** Perfect security does not exist. We use **defense in depth** so that a single mistake does not compromise the whole system. Agents must read this file before touching auth, APIs, Docker, or deployment.

---

## Threat model (what we protect against)

| Threat | Mitigation |
|--------|------------|
| Direct backend access from the internet | Backend not published on host; `InternalAPIKeyMiddleware` + shared secret |
| Stolen session cookies (XSS) | HttpOnly JWT cookies; CSP on frontend |
| CSRF | SameSite=Lax cookies; same-site frontend proxy |
| Credential stuffing / brute force | Rate limits on login, register, verify |
| Open redirect after login | `safe_redirect_path()` |
| Admin abuse | Verified user + `PS_PRICE_ADMIN_EMAILS` allow-list |
| SQL injection | Parameterized queries only in repositories |
| Oversized payloads | 1 MiB body limit on API |
| Information disclosure | No scheduler details on public healthz; generic 500s in production |
| Weak production config | `validate_production_settings()` fails startup |

---

## Network layout (production)

```
Internet → :443 Caddy → frontend:3000 → backend:8000 (Docker network only)
```

- Security group: **only** 22 (SSH, your IP), 80, 443.
- Ports **3000** and **8000** must **not** be public.

---

## Internal API key

The backend is **not** reachable on the public internet. Only the Next.js server talks to it on the Docker network.

Two headers must be present on every `/api/*` request the backend accepts:

| Header | Set by | Purpose |
|--------|--------|---------|
| `X-PS-Price-Internal` | Next.js proxy (server-side only) | Shared secret; never exposed to the browser |
| `X-PS-Price-Client: 1` | Next.js proxy on upstream; browser sends `1` to the proxy first | Blocks address-bar `/api/...` visits and direct backend calls |

The browser `fetch()` in `frontend/src/lib/api.ts` sends `X-PS-Price-Client`. The production proxy rejects requests without it (and blocks `Sec-Fetch-Mode: navigate`).

| Variable | Where |
|----------|--------|
| `PS_PRICE_INTERNAL_API_KEY` | Backend `.env` |
| `INTERNAL_API_KEY` | Frontend container env (same value) |
| `ALLOWED_API_ORIGINS` | Frontend container — usually same as `PS_PRICE_CORS_ORIGINS` |

**Production requirements** (`PS_PRICE_PRODUCTION_MODE=true`):

- At least **32** random characters
- Must **not** be `ps-price-local-proxy-key`
- Must be set on **both** frontend and backend

Generate:

```bash
openssl rand -base64 48
```

---

## Authentication

- **Access JWT** — short-lived, `ps_price_access` HttpOnly cookie (or `Authorization: Bearer`)
- **Refresh JWT** — `ps_price_refresh` HttpOnly cookie, rotation via `/api/auth/refresh`
- **Passkeys** — WebAuthn with configured `PS_PRICE_WEBAUTHN_RP_ID` / `ORIGIN`
- **Passwords** — bcrypt hashes only in `users.password_hash`

Production also requires:

- `PS_PRICE_COOKIE_SECURE=true`
- `PS_PRICE_JWT_SECRET` — 32+ random chars, not the dev default
- HTTPS `PS_PRICE_FRONTEND_URL`
- `PS_PRICE_CORS_ORIGINS` — HTTPS origins only, no `*`

---

## HTTP security headers

**Backend (JSON API):** `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `CSP`, `HSTS` (production), `Cache-Control: no-store`.

**Frontend (Next.js):** CSP, frame denial, nosniff — see `frontend/next.config.ts`.

---

## Rate limiting (in-memory)

Applied on: register, login, resend verification, catalog refresh, admin sync, watch test emails.

> **Limitation:** Per-process only. If you run multiple backend replicas, use a shared store (Redis) or stay single-instance.

---

## Admin & ops

- Admin dashboard: `/admin` (frontend) → `/api/admin/*` (backend)
- Legacy `POST /api/sync-deals` — admin-only + rate limited
- `GET /healthz?scheduler=true` — **requires internal API key** (no public scheduler leak)

---

## Secrets & git

- `.env` is gitignored — never commit it
- Rotate `JWT_SECRET` and `INTERNAL_API_KEY` if leaked
- Use `chmod 600 .env` on the server

---

## Production checklist

Before going live, verify:

- [ ] `PS_PRICE_PRODUCTION_MODE=true`
- [ ] Strong `PS_PRICE_JWT_SECRET` and `PS_PRICE_INTERNAL_API_KEY`
- [ ] `PS_PRICE_COOKIE_SECURE=true`
- [ ] `PS_PRICE_CORS_ORIGINS` = your HTTPS site only
- [ ] `PS_PRICE_ADMIN_EMAILS` set
- [ ] WebAuthn RP ID / origin match your domain
- [ ] Backend port not in security group
- [ ] SSH restricted to your IP
- [ ] SMTP configured for real alerts (optional but recommended)
- [ ] Backups documented in `docs/DEPLOYMENT-AWS.md`

---

## For AI agents

Mandatory rules live in:

- [`AGENTS.md`](../AGENTS.md) (repo root)
- [`.cursor/rules/security-mandatory.mdc`](../.cursor/rules/security-mandatory.mdc)

**Do not** remove or bypass these controls without explicit user approval and a documented reason.
