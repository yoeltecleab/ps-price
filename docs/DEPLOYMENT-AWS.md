# Deploy PS Price on AWS EC2 — From Scratch

This guide takes you from zero AWS knowledge to a running PS Price deployment on a **single EC2 instance** using your existing `docker-compose.yml` plus a small AWS overlay — the same pattern as a typical capstone Docker deployment.

**Repository:** https://github.com/yoeltecleab/ps-price

---

## Table of Contents

1. [What you are building](#1-what-you-are-building)
2. [Cost estimate](#2-cost-estimate)
3. [Prerequisites](#3-prerequisites)
4. [Create an AWS account and secure it](#4-create-an-aws-account-and-secure-it)
5. [Launch an EC2 instance](#5-launch-an-ec2-instance)
6. [Open firewall ports (Security Group)](#6-open-firewall-ports-security-group)
7. [Assign a permanent IP (Elastic IP)](#7-assign-a-permanent-ip-elastic-ip)
8. [Connect via SSH](#8-connect-via-ssh)
9. [Install Docker](#9-install-docker)
10. [Add swap space (t2.micro only)](#10-add-swap-space-t2micro-only)
11. [Clone the repository](#11-clone-the-repository)
12. [Configure environment variables (.env)](#12-configure-environment-variables-env)
13. [Configure Caddy (HTTPS reverse proxy)](#13-configure-caddy-https-reverse-proxy)
14. [Deploy with Docker Compose](#14-deploy-with-docker-compose)
15. [Verify the deployment](#15-verify-the-deployment)
16. [Auto-start on reboot](#16-auto-start-on-reboot)
17. [Point a domain at your server (optional)](#17-point-a-domain-at-your-server-optional)
18. [Email alerts with AWS SES (optional)](#18-email-alerts-with-aws-ses-optional)
19. [Updating the app](#19-updating-the-app)
20. [Backups](#20-backups)
21. [Security checklist](#21-security-checklist)
22. [Troubleshooting](#22-troubleshooting)

---

## 1. What you are building

```
                Internet
                    │
          ┌─── port 80/443 ───┐
          │                   │
      ┌───▼───────────────────────────────────┐
      │           EC2 Instance                │
      │   ┌───────────────────────────────┐   │
      │   │  Caddy (reverse proxy)        │   │
      │   │  • Terminates HTTPS           │   │
      │   │  • Routes → frontend:3000     │   │
      │   └────────────┬──────────────────┘   │
      │                │ internal Docker net  │
      │   ┌────────────▼──────────────────┐   │
      │   │  frontend (Next.js, :3000)    │   │
      │   │  • Serves UI                  │   │
      │   │  • Proxies /api/* → backend   │   │
      │   └────────────┬──────────────────┘   │
      │                │                      │
      │   ┌────────────▼──────────────────┐   │
      │   │  backend (FastAPI, :8000)     │   │
      │   │  • REST API + scheduler       │   │
      │   │  • PlayStation catalog sync   │   │
      │   └────────────┬──────────────────┘   │
      │                │                      │
      │   ┌────────────▼──────────────────┐   │
      │   │  SQLite on Docker volume      │   │
      │   │  /data/ps_price.sqlite3       │   │
      │   └───────────────────────────────┘   │
      │                                       │
      │   Elastic IP: 3.x.x.x (static)        │
      └───────────────────────────────────────┘
```

**Why this layout?**

- **One EC2** — simple and cheap. No load balancer required.
- **Caddy** — automatic free HTTPS from Let's Encrypt when you have a domain.
- **Ports 3000 and 8000 are not public** — only Caddy on 80/443 faces the internet.
- **SQLite** lives on a Docker volume (`ps-price-data`). Run **one** backend instance only.

| AWS term | Plain English |
|----------|---------------|
| **EC2** | A virtual server you control remotely |
| **Elastic IP** | A static public IP that survives reboots |
| **Security Group** | Virtual firewall on your instance |
| **EBS** | The disk attached to your EC2 |

---

## 2. Cost estimate

| Resource | Free tier (12 months) | After free tier |
|----------|----------------------|-----------------|
| EC2 `t2.micro` | 750 hrs/month free | ~$8.50/month |
| EC2 `t3.small` | Not free tier | ~$15/month |
| EBS 30 GB | Free tier included | ~$2.40/month |
| Elastic IP (attached) | Free | Free while running |
| **Total (t2.micro)** | **~$0/month** | **~$11/month** |
| **Total (t3.small)** | **~$17/month** | **~$17/month** |

> **Recommendation:** Use **`t3.small`** if you can afford it — the first PlayStation catalog sync (~4,000 deals) is CPU- and memory-heavy. Use **`t2.micro`** + swap (Step 10) for free tier.

Set a **billing alert** in Step 4 so you never get a surprise bill.

---

## 3. Prerequisites

- [ ] Credit/debit card for AWS (free tier still requires one)
- [ ] GitHub access to https://github.com/yoeltecleab/ps-price
- [ ] Terminal (Mac/Linux) or Windows Terminal + SSH
- [ ] (Optional) A domain name for HTTPS — e.g. Cloudflare, Namecheap

---

## 4. Create an AWS account and secure it

### 4a. Create the account

1. Go to [aws.amazon.com](https://aws.amazon.com) → **Create an AWS Account**.
2. Choose the **Free** support plan.
3. Verify with your credit card.

### 4b. Billing alert

1. AWS Console → your account name → **Billing and Cost Management**.
2. **Budgets** → **Create budget** → **Zero spend budget**.

### 4c. IAM user (optional but recommended)

Create an IAM user with console access instead of using the root account daily.

---

## 5. Launch an EC2 instance

1. AWS Console → search **EC2** → **Launch instance**.

2. **Name:** `ps-price-prod`

3. **AMI:** **Ubuntu Server 24.04 LTS** (64-bit x86)

4. **Instance type:**
   - Free tier: **`t2.micro`** (add swap in Step 10)
   - Recommended: **`t3.small`**

5. **Key pair:** Create new → name `ps-price-key` → download `.pem` → store in `~/.ssh/ps-price-key.pem`

6. **Network:** Allow **SSH from My IP**.

7. **Storage:** **30 GiB gp3** (default is fine — SQLite database lives on Docker volume on root disk).

8. **Launch instance**.

---

## 6. Open firewall ports (Security Group)

1. EC2 → **Instances** → `ps-price-prod` → **Security** tab → click the Security Group.
2. **Edit inbound rules:**

| Type | Port | Source | Why |
|------|------|--------|-----|
| SSH | 22 | My IP | Admin access |
| HTTP | 80 | Anywhere-IPv4 | Caddy (redirects to HTTPS) |
| HTTPS | 443 | Anywhere-IPv4 | Caddy HTTPS |

> **Do NOT open ports 3000 or 8000.** Caddy is the only public entry point.

3. **Save rules**.

---

## 7. Assign a permanent IP (Elastic IP)

1. EC2 → **Elastic IPs** → **Allocate** → **Allocate**.
2. Select it → **Actions** → **Associate Elastic IP address** → choose `ps-price-prod`.
3. Note your IP (e.g. `54.123.45.67`).

---

## 8. Connect via SSH

```bash
chmod 400 ~/.ssh/ps-price-key.pem
ssh -i ~/.ssh/ps-price-key.pem ubuntu@54.123.45.67
```

Replace `54.123.45.67` with your Elastic IP.

---

## 9. Install Docker

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker ubuntu
newgrp docker

docker --version
docker compose version
```

---

## 10. Add swap space (t2.micro only)

> Skip if using `t3.small` or larger.

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

---

## 11. Clone the repository

```bash
git clone https://github.com/yoeltecleab/ps-price.git
cd ps-price
```

---

## 12. Configure environment variables (.env)

```bash
cp .env.example .env
nano .env
```

**Production values** (adjust for your Elastic IP or domain):

```env
PS_PRICE_DATABASE_PATH=/data/ps_price.sqlite3
PS_PRICE_STORE_LOCALE=en-us

PS_PRICE_SCHEDULER_ENABLED=true
PS_PRICE_CHECK_INTERVAL_MINUTES=360
PS_PRICE_FEED_SYNC_INTERVAL_MINUTES=60

PS_PRICE_CACHE_TTL_SECONDS=1800
PS_PRICE_REQUEST_MIN_INTERVAL_SECONDS=3

# Must match your public URL exactly (scheme + host, no trailing slash)
# HTTP only (no domain):
PS_PRICE_CORS_ORIGINS=http://54.123.45.67
# OR with HTTPS domain:
# PS_PRICE_CORS_ORIGINS=https://psprice.yourdomain.com

# Optional — AWS SES (see Step 18)
# PS_PRICE_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
# PS_PRICE_SMTP_PORT=587
# PS_PRICE_SMTP_USERNAME=...
# PS_PRICE_SMTP_PASSWORD=...
# PS_PRICE_SMTP_USE_TLS=true
# PS_PRICE_NOTIFICATION_FROM_EMAIL=alerts@yourdomain.com
```

Lock down permissions:

```bash
chmod 600 .env
```

---

## 13. Configure Caddy (HTTPS reverse proxy)

```bash
cp deploy/Caddyfile.example deploy/Caddyfile
nano deploy/Caddyfile
```

### Option A: Domain (HTTPS — recommended)

Your domain's **A record** must point at your Elastic IP first.

```
psprice.yourdomain.com {
    reverse_proxy frontend:3000
}
```

### Option B: IP only (HTTP demo)

```
:80 {
    reverse_proxy frontend:3000
}
```

Save (`Ctrl+X`, `Y`, `Enter`).

---

## 14. Deploy with Docker Compose

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml up -d --build
```

**What happens:**

1. Docker builds the FastAPI backend and Next.js frontend images.
2. Three containers start: `backend`, `frontend`, `caddy`.
3. Backend scheduler syncs the full PlayStation catalog on container start (10,000+ titles).
4. Caddy obtains a TLS certificate automatically if you used Option A.

> **First build takes 5–15 minutes** on a small instance.

**Watch logs:**

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml logs -f
```

**Check status:**

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml ps
```

Expected:

```
NAME                STATUS
ps-price-backend    Up (healthy)
ps-price-frontend   Up
ps-price-caddy      Up
```

---

## 15. Verify the deployment

### Browser

- **HTTP (Option B):** `http://54.123.45.67`
- **HTTPS (Option A):** `https://psprice.yourdomain.com`

### Server health checks

```bash
# Through Caddy → frontend → backend proxy
curl -s http://localhost/healthz | python3 -m json.tool

# Sync status (catalog bootstrap)
curl -s http://localhost/api/sync-status | python3 -m json.tool
```

Wait until `catalog_total` is above 1000 (first full-catalog sync may take 5–15 minutes):

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml logs -f backend
```

### Smoke test

1. Open the app URL — deals homepage should load.
2. Click **Sync PlayStation feed** if the catalog is still empty.
3. Search for a game (local catalog only).
4. Add a game to library → open game detail → deploy a watch (optional).

---

## 16. Auto-start on reboot

```bash
sudo systemctl enable docker
```

`docker-compose.aws.yml` sets `restart: unless-stopped` on all services.

**Test:**

```bash
sudo reboot
# wait ~60s, reconnect via SSH
cd ~/ps-price
docker compose -f docker-compose.yml -f docker-compose.aws.yml ps
```

---

## 17. Point a domain at your server (optional)

1. At your registrar, add an **A record**:
   - Host: `psprice` (or `@`)
   - Value: your Elastic IP
   - TTL: `300`
2. Wait 5–30 minutes → `nslookup psprice.yourdomain.com`
3. Update `deploy/Caddyfile` to Option A (Step 13).
4. Update `.env`:
   ```env
   PS_PRICE_CORS_ORIGINS=https://psprice.yourdomain.com
   ```
5. Redeploy:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.aws.yml up -d
   docker compose -f docker-compose.yml -f docker-compose.aws.yml exec caddy \
     caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
   ```

---

## 18. Email alerts with AWS SES (optional)

1. AWS Console → **SES** → verify your domain or sender email.
2. Request **production access** if still in sandbox.
3. SES → **SMTP settings** → create SMTP credentials.
4. Add to `.env` (see Step 12) and restart backend:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.aws.yml restart backend
   ```
5. Create a watch in the UI → **Test** email.

---

## 19. Updating the app

```bash
cd ~/ps-price
git pull origin master
docker compose -f docker-compose.yml -f docker-compose.aws.yml up -d --build
```

---

## 20. Backups

SQLite database lives in the Docker volume `ps-price_ps-price-data`.

```bash
# Logical backup
docker compose -f docker-compose.yml -f docker-compose.aws.yml exec backend \
  sqlite3 /data/ps_price.sqlite3 ".backup /data/backup.sqlite3"

# Copy to home directory
docker cp ps-price-backend:/data/backup.sqlite3 ~/ps-price-backup-$(date +%Y%m%d).sqlite3

# Download to your laptop
# scp -i ~/.ssh/ps-price-key.pem ubuntu@54.123.45.67:~/ps-price-backup-*.sqlite3 ./
```

> **Never run** `docker compose down -v` in production — `-v` deletes the database volume.

---

## 21. Security checklist

### Infrastructure

- [ ] `.env` permissions: `chmod 600 .env`
- [ ] `PS_PRICE_CORS_ORIGINS` matches your real public URL (HTTPS, no trailing slash)
- [ ] Ports **3000** and **8000** are **not** in the Security Group
- [ ] SSH restricted to **My IP** (not `0.0.0.0/0`)
- [ ] Billing alert configured
- [ ] UFW enabled (optional):
  ```bash
  sudo ufw allow OpenSSH
  sudo ufw allow 80
  sudo ufw allow 443
  sudo ufw enable
  ```

### Application (required for production)

Set these in `.env` on the server:

```env
PS_PRICE_PRODUCTION_MODE=true
PS_PRICE_COOKIE_SECURE=true
PS_PRICE_FRONTEND_URL=https://your-domain.com
PS_PRICE_WEBAUTHN_RP_ID=your-domain.com
PS_PRICE_WEBAUTHN_ORIGIN=https://your-domain.com
PS_PRICE_ADMIN_EMAILS=you@your-domain.com
PS_PRICE_JWT_SECRET=replace-with-openssl-rand-hex-32-or-longer-random-string
PS_PRICE_JWT_ACCESS_TTL_MINUTES=30
PS_PRICE_JWT_REFRESH_TTL_DAYS=30
PS_PRICE_REQUIRE_EMAIL_VERIFICATION=true
PS_PRICE_CORS_ORIGINS=https://your-domain.com
```

- [ ] `PS_PRICE_PRODUCTION_MODE=true` — enforces secure cookies, HTTPS frontend URL, WebAuthn RP ID, and at least one admin email at startup
- [ ] `PS_PRICE_COOKIE_SECURE=true` — JWT cookies only sent over HTTPS
- [ ] `PS_PRICE_JWT_SECRET` — random string ≥32 chars (`openssl rand -hex 32`)
- [ ] `PS_PRICE_ADMIN_EMAILS` — comma-separated verified account emails allowed to run manual catalog sync (`POST /api/sync-deals`) and scheduler refresh
- [ ] `PS_PRICE_WEBAUTHN_RP_ID` matches your public hostname (no port, no scheme)
- [ ] `PS_PRICE_WEBAUTHN_ORIGIN` matches the browser origin users sign in from
- [ ] SMTP configured for account verification, password reset, and price alerts
- [ ] Manual sync from the UI is **admin-only**; regular users rely on the backend scheduler

### Auth & abuse controls (built in)

- Argon2 password hashing
- JWT auth: short-lived access token + refresh token in HttpOnly cookies (`SameSite=lax`)
- Optional `Authorization: Bearer` header for API clients
- Rate limits on register, login, forgot-password, resend-verification, and notification-email verification
- Open-redirect protection on auth `next` parameters
- Security headers (`X-Frame-Options`, `HSTS` when production mode is on)
- `GET /healthz` returns minimal public status (no internal paths)

---

## 22. Troubleshooting

### View logs

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml logs
docker compose -f docker-compose.yml -f docker-compose.aws.yml logs backend
docker compose -f docker-compose.yml -f docker-compose.aws.yml logs frontend
docker compose -f docker-compose.yml -f docker-compose.aws.yml logs caddy
```

### Common problems

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Build killed / OOM | `t2.micro` out of RAM | Add swap (Step 10) or use `t3.small` |
| Connection refused on 80/443 | Security Group | Revisit Step 6 |
| 502 from Caddy | Frontend not ready | Wait; check `frontend` and `backend` logs |
| CORS errors in browser | Wrong `PS_PRICE_CORS_ORIGINS` | Match exact public URL in `.env`, restart backend |
| Empty deals / search | Catalog not synced | Wait for scheduler, or as admin: `curl -X POST -b cookies.txt http://localhost/api/sync-deals` |
| Caddy TLS failure | DNS not pointing at server | Fix A record; wait for propagation |
| Emails `skipped` | SMTP not configured | Set SES vars in `.env` |
| Data lost | Used `docker compose down -v` | Restore from backup; never use `-v` |

### Useful commands

```bash
df -h
free -h
docker stats --no-stream
curl -s http://localhost/api/sync-status | python3 -m json.tool
```

---

## Files for AWS deployment

| File | Purpose |
|------|---------|
| `docker-compose.aws.yml` | Overlay: Caddy + hide backend/frontend ports |
| `deploy/Caddyfile.example` | Template — copy to `deploy/Caddyfile` on the server |
| `.env.example` | All `PS_PRICE_*` environment variables |

---

## Related docs

- [DEPLOYMENT.md](../DEPLOYMENT.md) — local Docker, config reference, advanced AWS (ALB)
- [README.md](../README.md) — project overview
