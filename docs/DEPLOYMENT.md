# Deployment Guide

PS Price ships as three Docker services (PostgreSQL, FastAPI backend, Next.js frontend). The backend uses **SQLAlchemy 2.0 + Alembic** against PostgreSQL. This guide covers local Docker deployment, production hardening, and a complete **AWS** deployment path.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Local / Docker Deployment](#local--docker-deployment)
3. [AWS Deployment](#aws-deployment)
4. [Configuration Reference](#configuration-reference)
5. [Email (SMTP / AWS SES)](#email-smtp--aws-ses)
6. [Database Backup & Restore](#database-backup--restore)
7. [Monitoring & Health Checks](#monitoring--health-checks)
8. [Troubleshooting](#troubleshooting)
9. [Production Checklist](#production-checklist)

---

## Architecture

```
                    ┌─────────────────────────────────────┐
  Users ──HTTPS──►  │  Application Load Balancer (ALB)    │
                    │  • /        → frontend :3000        │
                    │  • /api/*   → backend  :8000      │
                    │  • /healthz → backend  :8000      │
                    └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │                                         │
     ┌────────▼────────┐                    ┌──────────▼─────────┐
     │  Frontend       │  INTERNAL_API_URL  │  Backend           │
     │  Next.js :3000  │ ─────────────────► │  FastAPI :8000     │
     │  (standalone)   │  (Docker network)  │  + scheduler       │
     └─────────────────┘                    └──────────┬─────────┘
                                                       │
                                              ┌────────▼─────────┐
                                              │  PostgreSQL 16   │
                                              │  volume ps-price-pg │
                                              └──────────────────┘
```

**Important:** Run **one backend instance** against **one PostgreSQL database**. Schema is managed by **Alembic** (`alembic upgrade head` on startup). Do not point multiple backends at the same DB without understanding connection pooling limits.

| Component | Port | Role |
|-----------|------|------|
| Frontend | 3000 | Web UI; proxies `/api/*` to backend |
| Backend | 8000 | REST API, catalog sync, scheduler, email notifications |
| PostgreSQL | 5432 | Primary data store (Docker volume `ps-price-pg`) |

---

## Local / Docker Deployment

### Prerequisites

- Docker 24+ and Docker Compose v2
- `.env` file (copy from `.env.example`)
- Optional: SMTP credentials for email alerts

### Quick Start

```bash
git clone https://github.com/yoeltecleab/ps-price.git
cd ps-price

cp .env.example .env
# Edit .env — at minimum set PS_PRICE_CORS_ORIGINS if not using localhost

docker compose up --build -d

# Verify (frontend proxies API; backend is internal-only in default compose)
curl http://127.0.0.1:3000/healthz
curl http://127.0.0.1:3000
```

| URL | Service |
|-----|---------|
| http://127.0.0.1:3000 | Web app |
| http://127.0.0.1:5432 | PostgreSQL (local IntelliJ / psql; optional) |

On first launch the backend scheduler syncs the full PlayStation catalog (10,000+ titles). This can take 5–15 minutes. Watch progress:

```bash
docker compose logs -f backend
curl http://127.0.0.1:3000/api/sync-status
```

### Management

```bash
# Logs
docker compose logs -f backend
docker compose logs -f frontend

# Restart
docker compose restart

# Stop
docker compose down

# Rebuild after code changes
docker compose up --build -d

# Reset database (destructive — wipes Postgres volume)
docker compose down -v
docker compose up -d
```

---

## AWS Deployment

### Recommended: single EC2 + Caddy (simple)

PS Price uses the **same deployment pattern** as a typical Docker capstone project:

- **One EC2 instance** (no load balancer)
- **Docker Compose** (`docker-compose.yml` + `docker-compose.aws.yml`)
- **Caddy** on ports 80/443 for HTTPS (automatic Let's Encrypt)
- **Frontend** proxies `/api/*` to the backend internally — Caddy only talks to port 3000

**Full step-by-step guide:** [docs/DEPLOYMENT-AWS.md](docs/DEPLOYMENT-AWS.md)

Quick deploy on a fresh Ubuntu EC2:

```bash
git clone https://github.com/yoeltecleab/ps-price.git
cd ps-price
cp .env.example .env          # edit PS_PRICE_CORS_ORIGINS for your IP/domain
cp deploy/Caddyfile.example deploy/Caddyfile  # edit with your domain or use :80 for IP-only
docker compose -f docker-compose.yml -f docker-compose.aws.yml up -d --build
```

**Estimated cost:** ~$0–17/month (`t2.micro` free tier or `t3.small` recommended for catalog sync).

---

### Advanced: EC2 + Application Load Balancer (optional)

The section below documents an **ALB + ACM + Route 53** setup for teams that need managed TLS at the load balancer or plan to scale beyond one instance. For most personal deployments, **use the single-EC2 guide above instead.**

**Estimated monthly cost (us-east-1, light traffic):** ~$25–45  
(t3.small EC2 + 20 GB gp3 EBS + ALB + minimal data transfer)

### AWS services used

| Service | Purpose |
|---------|---------|
| **EC2** | Runs Docker Compose (postgres + backend + frontend) |
| **EBS** | Optional host bind-mount for Postgres data (`/data/postgres`) |
| **ALB** | HTTPS termination, path-based routing |
| **ACM** | Free TLS certificate |
| **Route 53** | DNS A/alias record |
| **SES** | Transactional email for price alerts (optional) |
| **SSM Parameter Store** | Secure environment variables (optional) |
| **CloudWatch** | Logs and alarms |

### Step 1 — Prepare the repository

On your laptop (already done if you cloned from GitHub):

```bash
git clone https://github.com/yoeltecleab/ps-price.git
cd ps-price
```

### Step 2 — Request an ACM certificate

1. Open **AWS Certificate Manager** in the **same region** as your ALB (e.g. `us-east-1`).
2. Request a **public** certificate for `psprice.yourdomain.com` (and optionally `*.yourdomain.com`).
3. Validate via **DNS** (add the CNAME records ACM provides to Route 53 or your DNS host).
4. Wait until status is **Issued**.

> ACM certificates for CloudFront must be in `us-east-1`. For ALB-only deployments, create the cert in your ALB region.

### Step 3 — Create a security group

Create `ps-price-sg` with:

| Type | Port | Source | Notes |
|------|------|--------|-------|
| HTTPS | 443 | `0.0.0.0/0` | Public web traffic → ALB |
| HTTP | 80 | `0.0.0.0/0` | Redirect to HTTPS |
| SSH | 22 | `YOUR_IP/32` | Admin access only |
| Custom TCP | 3000 | `ps-price-alb-sg` | ALB → frontend |
| Custom TCP | 8000 | `ps-price-alb-sg` | ALB → backend API |

Create a separate `ps-price-alb-sg` allowing inbound 443/80 from the internet and outbound to `ps-price-sg` on ports 3000 and 8000.

### Step 4 — Launch an EC2 instance

1. **AMI:** Ubuntu 24.04 LTS (or Amazon Linux 2023)
2. **Instance type:** `t3.small` (2 vCPU, 2 GB RAM) — sufficient for catalog sync + web UI
3. **Storage:** 30 GB gp3 root volume; optionally add **20 GB gp3 EBS** for Postgres data (`/data/postgres`)
4. **Security group:** `ps-price-sg`
5. **IAM role:** attach a role with `AmazonSSMManagedInstanceCore` (for Session Manager, no SSH keys required)
6. **User data** (cloud-init) — install Docker (optional: mount EBS for Postgres):

```bash
#!/bin/bash
set -euxo pipefail

apt-get update
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin git

# Optional: persistent Postgres on host (adjust device if not /dev/xvdf)
DATA_DEV=/dev/xvdf
mkdir -p /data/postgres
if ! blkid "$DATA_DEV"; then mkfs.ext4 "$DATA_DEV"; fi
grep -q '/data/postgres ext4' /etc/fstab || echo "$DATA_DEV /data/postgres ext4 defaults,nofail 0 2" >> /etc/fstab
mount -a
chown -R 999:999 /data/postgres || true

cd /opt
git clone https://github.com/yoeltecleab/ps-price.git
cd ps-price
```

> **Device name:** On Nitro instances the data volume may appear as `/dev/nvme1n1`. Check with `lsblk` after launch.

To use the host Postgres directory, add to `docker-compose.yml` on the server:

```yaml
services:
  postgres:
    volumes:
      - /data/postgres:/var/lib/postgresql/data
```

### Step 5 — Configure production environment

SSH or SSM into the instance:

```bash
cd /opt/ps-price
cp .env.example .env
nano .env
```

**Production `.env` example:**

```env
# PostgreSQL — Docker Compose sets PS_PRICE_DATABASE_URL for the backend automatically.
# Change POSTGRES_* here; keep passwords strong in production.
POSTGRES_USER=psprice
POSTGRES_PASSWORD=CHANGE_ME_STRONG_PASSWORD
POSTGRES_DB=psprice

# PlayStation Store
PS_PRICE_STORE_LOCALE=en-us

# Scheduler
PS_PRICE_SCHEDULER_ENABLED=true
PS_PRICE_CHECK_INTERVAL_MINUTES=360
PS_PRICE_FEED_SYNC_INTERVAL_MINUTES=60

# HTTP client
PS_PRICE_CACHE_TTL_SECONDS=1800
PS_PRICE_REQUEST_MIN_INTERVAL_SECONDS=3

# CORS — your public site origin (no trailing slash)
PS_PRICE_CORS_ORIGINS=https://psprice.yourdomain.com

# Email via AWS SES SMTP
PS_PRICE_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
PS_PRICE_SMTP_PORT=587
PS_PRICE_SMTP_USERNAME=YOUR_SES_SMTP_USERNAME
PS_PRICE_SMTP_PASSWORD=YOUR_SES_SMTP_PASSWORD
PS_PRICE_SMTP_USE_TLS=true
PS_PRICE_SMTP_USE_SSL=false
PS_PRICE_NOTIFICATION_FROM_EMAIL=alerts@yourdomain.com
```

The frontend container needs the backend reachable on the Docker network (default `INTERNAL_API_URL=http://backend:8000` — already set in the frontend Dockerfile).

Start the stack:

```bash
docker compose up --build -d
docker compose ps
docker compose exec backend curl -s http://localhost:8000/healthz
```

The backend runs Alembic migrations on startup, then the scheduler syncs the full PlayStation catalog. Monitor progress:

```bash
curl -s http://localhost:3000/api/sync-status
```

To force a manual re-sync (from the host, via frontend proxy):

```bash
curl -X POST http://localhost:3000/api/sync-deals
```

### Step 6 — Create an Application Load Balancer

1. **Target type:** Instance
2. **Scheme:** Internet-facing
3. **Listeners:**
   - **HTTP :80** → redirect to HTTPS :443
   - **HTTPS :443** → forward to target groups (certificate from ACM)
4. **Target group `ps-price-frontend-tg`:**
   - Port **3000**, protocol HTTP, health check path `/`
   - Register your EC2 instance
5. **Target group `ps-price-backend-tg`:**
   - Port **8000**, protocol HTTP, health check path `/healthz`
   - Register your EC2 instance
6. **Listener rules (HTTPS :443):**

| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | Path is `/api/*` | Forward to `ps-price-backend-tg` |
| 2 | Path is `/healthz` | Forward to `ps-price-backend-tg` |
| 3 | Path is `/docs` or `/docs/*` | Forward to `ps-price-backend-tg` |
| 4 | Path is `/openapi.json` | Forward to `ps-price-backend-tg` |
| default | — | Forward to `ps-price-frontend-tg` |

> The Next.js frontend also proxies `/api/*` to the backend internally. Routing API traffic directly to the backend at the ALB is optional but reduces load on the frontend container.

### Step 7 — Route 53 DNS

1. Create a hosted zone for `yourdomain.com` (or use an existing one).
2. Create an **A record** (alias) `psprice.yourdomain.com` → your ALB.
3. Confirm HTTPS works: `curl -I https://psprice.yourdomain.com/healthz`

### Step 8 — AWS SES for email alerts

1. Open **Amazon SES** → verify your domain (`yourdomain.com`) or sender address.
2. If your account is in the **SES sandbox**, request production access or verify each recipient email for testing.
3. Create **SMTP credentials** (SES console → SMTP settings).
4. Add the SMTP values to `.env` (see Step 5).
5. Restart backend: `docker compose restart backend`
6. Test from the UI: create a watch → **Test email**, or:

```bash
curl -X POST https://psprice.yourdomain.com/api/watches/1/test
```

### Step 9 — Secrets with SSM Parameter Store (recommended)

Instead of storing SMTP passwords in plain `.env` on disk:

```bash
aws ssm put-parameter --name "/ps-price/smtp-password" --value "YOUR_PASSWORD" --type SecureString
aws ssm put-parameter --name "/ps-price/smtp-username" --value "YOUR_USERNAME" --type SecureString
```

Grant the EC2 IAM role `ssm:GetParameters` on `/ps-price/*`. Load at container start with a small wrapper script, or use [ECS secrets](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data-parameters.html) if you migrate to Fargate later.

### Step 10 — CloudWatch monitoring

**Log shipping** — install the CloudWatch agent or use `awslogs` Docker log driver:

```yaml
# docker-compose.yml snippet
services:
  backend:
    logging:
      driver: awslogs
      options:
        awslogs-group: /ps-price/backend
        awslogs-region: us-east-1
        awslogs-stream-prefix: backend
```

**Recommended alarms:**

| Alarm | Metric | Threshold |
|-------|--------|-------------|
| Instance status | `StatusCheckFailed` | ≥ 1 for 2 min |
| ALB unhealthy hosts | `UnHealthyHostCount` | ≥ 1 for 5 min |
| ALB 5xx | `HTTPCode_Target_5XX_Count` | > 10 in 5 min |
| Disk usage | Custom agent metric | > 80% on Postgres data volume |

### Step 11 — Backups on AWS

**Automated EBS snapshots** (if Postgres data is on a dedicated EBS volume):

```bash
aws ec2 create-snapshot \
  --volume-id vol-xxxxxxxx \
  --description "ps-price postgres daily $(date +%F)"
```

**Logical SQL dump** (portable, recommended):

```bash
docker compose exec -T postgres pg_dump -U psprice psprice | gzip > "psprice-$(date +%F).sql.gz"
aws s3 cp "psprice-$(date +%F).sql.gz" s3://your-backup-bucket/ps-price/
```

Retain 7 daily + 4 weekly snapshots or dumps.

### Step 12 — Deploying updates

```bash
cd /opt/ps-price
git pull origin master
docker compose build --no-cache
docker compose up -d
curl -s https://psprice.yourdomain.com/healthz
```

For zero-downtime on a single instance, use a blue/green second instance behind the ALB, or accept ~30 s downtime during `docker compose up`.

### Alternative: ECS Fargate (advanced)

For ECS, run **PostgreSQL on RDS** or as a single-container task with an **EBS volume** for `/var/lib/postgresql/data`. Do not use EFS for Postgres data files.

High-level steps:

1. Push images to **ECR** (`ps-price-backend`, `ps-price-frontend`).
2. Create an ECS cluster with services for postgres (or use RDS), backend, and frontend.
3. Set `PS_PRICE_DATABASE_URL` to the RDS or task Postgres endpoint.
4. Set `PS_PRICE_SCHEDULER_ENABLED=true` on exactly **one** backend task.
5. Point the ALB to the ECS service(s) with the same path rules as above.

This adds complexity without benefit for most personal deployments — **EC2 + Compose is simpler**.

### AWS troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| 502 from ALB | Container not listening / wrong port | Check `docker compose ps`, security groups |
| CORS errors in browser | `PS_PRICE_CORS_ORIGINS` mismatch | Set to exact `https://your-domain` |
| Catalog empty | Initial sync not finished | `POST /api/sync-deals`, watch logs |
| Emails `skipped` | SMTP not configured | Set SES SMTP vars, restart backend |
| Database connection errors | Wrong `POSTGRES_*` or URL | Check `docker compose logs postgres backend` |
| Sync slow / timeouts | Instance too small | Upgrade to `t3.medium` during first sync |

---

## Configuration Reference

Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `psprice` | Postgres role (Docker Compose) |
| `POSTGRES_PASSWORD` | `psprice` | Postgres password — **change in production** |
| `POSTGRES_DB` | `psprice` | Database name |
| `PS_PRICE_DATABASE_URL` | (set by Compose) | SQLAlchemy URL (`postgresql+psycopg://...`) — override for host-run backend |
| `PS_PRICE_STORE_LOCALE` | `en-us` | PlayStation Store locale |
| `PS_PRICE_SCHEDULER_ENABLED` | `true` | Background catalog sync scheduler |
| `PS_PRICE_CHECK_INTERVAL_MINUTES` | `360` | How often tracked library games are considered "due" |
| `PS_PRICE_FEED_SYNC_INTERVAL_MINUTES` | `60` | Scheduled full catalog sync interval |
| `PS_PRICE_CACHE_TTL_SECONDS` | `1800` | In-memory store response cache TTL |
| `PS_PRICE_REQUEST_MIN_INTERVAL_SECONDS` | `3` | Minimum seconds between PlayStation HTTP requests |
| `PS_PRICE_REQUEST_TIMEOUT_SECONDS` | `20` | HTTP timeout per store request |
| `PS_PRICE_REQUEST_RETRIES` | `3` | Retries on 429/5xx from store |
| `PS_PRICE_MAX_SEARCH_LIMIT` | `24` | Max search results per query |
| `PS_PRICE_CORS_ORIGINS` | `http://localhost:3000,...` | Comma-separated allowed browser origins |
| `PS_PRICE_SMTP_HOST` | — | SMTP server (SES, Gmail, SendGrid, etc.) |
| `PS_PRICE_SMTP_PORT` | `587` | SMTP port |
| `PS_PRICE_SMTP_USERNAME` | — | SMTP username |
| `PS_PRICE_SMTP_PASSWORD` | — | SMTP password |
| `PS_PRICE_SMTP_USE_TLS` | `true` | STARTTLS |
| `PS_PRICE_SMTP_USE_SSL` | `false` | Implicit SSL |
| `PS_PRICE_NOTIFICATION_FROM_EMAIL` | — | Sender address (must be verified in SES) |

Verify loaded config:

```bash
docker compose exec backend env | grep PS_PRICE
curl http://127.0.0.1:3000/healthz
docker compose exec backend curl -s "http://localhost:8000/healthz?scheduler=true" -H "x-ps-price-internal: YOUR_INTERNAL_KEY"
```

---

## Email (SMTP / AWS SES)

### AWS SES (production)

```env
PS_PRICE_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
PS_PRICE_SMTP_PORT=587
PS_PRICE_SMTP_USERNAME=AKIA..............................
PS_PRICE_SMTP_PASSWORD=....................................
PS_PRICE_SMTP_USE_TLS=true
PS_PRICE_NOTIFICATION_FROM_EMAIL=alerts@yourdomain.com
```

Replace the region in the SMTP host if not using `us-east-1`.

### Gmail (development / testing)

1. Enable 2-Step Verification on your Google account.
2. Create an [App Password](https://myaccount.google.com/apppasswords).
3. Configure:

```env
PS_PRICE_SMTP_HOST=smtp.gmail.com
PS_PRICE_SMTP_PORT=587
PS_PRICE_SMTP_USERNAME=your-email@gmail.com
PS_PRICE_SMTP_PASSWORD=your-16-char-app-password
PS_PRICE_NOTIFICATION_FROM_EMAIL=your-email@gmail.com
PS_PRICE_SMTP_USE_TLS=true
```

### SendGrid

```env
PS_PRICE_SMTP_HOST=smtp.sendgrid.net
PS_PRICE_SMTP_PORT=587
PS_PRICE_SMTP_USERNAME=apikey
PS_PRICE_SMTP_PASSWORD=SG.xxxxxxxxxxxxx
PS_PRICE_NOTIFICATION_FROM_EMAIL=alerts@yourdomain.com
```

---

## Database Backup & Restore

### Backup

```bash
# Compressed SQL dump (recommended)
docker compose exec -T postgres pg_dump -U psprice psprice | gzip > "psprice-$(date +%F).sql.gz"

# Plain SQL
docker compose exec -T postgres pg_dump -U psprice psprice > backup.sql
```

### Restore

```bash
docker compose down
docker compose up -d postgres
# Wait for postgres healthy, then:
gunzip -c psprice-2026-06-22.sql.gz | docker compose exec -T postgres psql -U psprice psprice
docker compose up -d
```

### Inspect

```bash
docker compose exec postgres psql -U psprice psprice -c "\dt"
docker compose exec postgres psql -U psprice psprice -c "SELECT COUNT(*) FROM games;"
docker compose exec postgres psql -U psprice psprice -c "SELECT COUNT(*) FROM games WHERE is_tracked = 1;"
```

### Schema migrations

Alembic runs automatically on backend startup. To run manually:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

---

## Monitoring & Health Checks

```bash
curl http://127.0.0.1:3000/healthz
docker compose exec backend curl -s "http://localhost:8000/healthz?scheduler=true" -H "x-ps-price-internal: YOUR_INTERNAL_KEY"
curl http://127.0.0.1:3000/api/sync-status
```

Example response:

```json
{
  "status": "ok"
}
```

With `?scheduler=true` and a valid internal key:

```json
{
  "status": "ok",
  "scheduler_running": true,
  "scheduler_enabled": true
}
```

Docker health check (included in `docker-compose.yml`):

```bash
docker ps   # STATUS should show "healthy"
```

---

## Troubleshooting

### Container won't start

```bash
docker compose logs -f backend
docker compose build --no-cache
docker compose up -d
```

### API unreachable

```bash
docker ps
curl -v http://127.0.0.1:3000/healthz
docker inspect ps-price-backend | grep -A 5 Health
```

### Emails not sending

```bash
docker compose exec backend env | grep SMTP
curl "http://127.0.0.1:3000/api/notifications?limit=10"
# Look for status: "skipped" (SMTP not configured) or "failed" (bad credentials)
```

### Performance tuning

```env
# Aggressive library refresh checks
PS_PRICE_CHECK_INTERVAL_MINUTES=60

# Hourly full catalog sync
PS_PRICE_FEED_SYNC_INTERVAL_MINUTES=60

# Conservative store rate limiting (safer against blocks)
PS_PRICE_REQUEST_MIN_INTERVAL_SECONDS=5
```

---

## Production Checklist

- [ ] `.env` configured with production values (no secrets in git)
- [ ] `POSTGRES_PASSWORD` and `PS_PRICE_JWT_SECRET` are strong, unique values
- [ ] `PS_PRICE_CORS_ORIGINS` matches your public HTTPS origin
- [ ] Postgres data on persistent storage (Docker volume or EBS bind-mount)
- [ ] **Single** backend instance with scheduler enabled
- [ ] ALB + ACM certificate active, HTTP → HTTPS redirect
- [ ] Route 53 DNS pointing to ALB
- [ ] Initial catalog sync completed (`catalog_total` > 1000)
- [ ] SES domain verified, production access granted
- [ ] Test watch email delivers successfully
- [ ] `pg_dump` or EBS snapshot backup schedule configured
- [ ] CloudWatch alarms for unhealthy targets and disk usage
- [ ] Security group: SSH restricted to your IP (or use SSM only)
- [ ] `git pull && docker compose up --build -d` update procedure documented for your team

---

## Support

- **Single-EC2 AWS guide:** [docs/DEPLOYMENT-AWS.md](docs/DEPLOYMENT-AWS.md)
- **API docs:** `/docs` on the backend (e.g. `https://psprice.yourdomain.com/docs` if routed via ALB)
- **Health:** `/healthz`
- **Sync status:** `/api/sync-status`
- **Repository:** https://github.com/yoeltecleab/ps-price
