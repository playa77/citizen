# Citizen Deployment Guide

**Version: 1.0.0 | 2026-07-13**

Production deployment of the Citizen legal reasoning engine on VPS.

---

## Target Infrastructure

| Item | Value |
|---|---|
| **Host** | 37.60.240.152 |
| **OS** | Ubuntu 24.04 |
| **User** | opencode (sudo) |
| **Domain** | workbench.gronowski.cc |
| **DNS** | Cloudflare proxy → VPS |
| **TLS** | Let's Encrypt via certbot --nginx |
| **Disk** | 96 GB |
| **RAM** | 11 GB |

---

## Architecture

```
Internet → Cloudflare (HTTPS) → VPS nginx :443
                                  ├─ /health → proxy_pass http://127.0.0.1:8001
                                  ├─ /api/*  → proxy_pass http://127.0.0.1:8001
                                  ├─ /api/v1/analyze → SSE (no buffering, 180s timeout)
                                  └─ /static/* → proxy_pass http://127.0.0.1:8001

Docker Compose:
  ┌─ citizen-db-1 (pgvector/pgvector:pg16)
  │  └─ port 5432, bound to 127.0.0.1
  │  └─ data volume: citizen_pgdata
  └─ citizen-citizen-app-1 (Dockerfile build)
     └─ port 8000 → host 8001 (127.0.0.1 only)
     └─ env_file: .env
```

---

## Deployment Procedure

### 1. Transfer project files

```bash
rsync -avz --exclude='.venv' --exclude='.git' --exclude='logs' \
  --exclude='uploads' --exclude='node_modules' --exclude='test.db' \
  --exclude='.env' /path/to/citizen/ opencode@37.60.240.152:/home/opencode/citizen/
```

### 2. Create production .env

Copy `.env.example` and fill in all values. Critical variables:

```bash
DATABASE_URL=postgresql+asyncpg://citizen_user:<PASSWORD>@db:5432/citizen_db
OPENROUTER_API_KEY=sk-or-v1-...
SECRET_KEY=<random 64-char string>
```

### 3. Create docker-compose.override.yml

Overrides for production — DB credentials, named volume, restart policy:

```yaml
services:
  db:
    environment:
      POSTGRES_USER: citizen_user
      POSTGRES_PASSWORD: <PASSWORD>
      POSTGRES_DB: citizen_db
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"

  citizen-app:
    ports:
      - "127.0.0.1:8001:8000"
    restart: unless-stopped

volumes:
  pgdata:
```

### 4. Configure nginx

```nginx
# /etc/nginx/sites-available/workbench.gronowski.cc
server {
    listen 80;
    server_name workbench.gronowski.cc;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE streaming for /api/v1/analyze (main analysis)
    location /api/v1/analyze {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # SSE streaming for /api/v1/goldset (Prüfstand demo analysis)
    location /api/v1/goldset {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

Enable the site and disable default:

```bash
sudo ln -sf /etc/nginx/sites-available/workbench.gronowski.cc /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 5. Get Let's Encrypt certificate

```bash
sudo certbot --nginx -d workbench.gronowski.cc
```

Auto-renewal is configured by certbot automatically.

### 6. Build and start

```bash
cd /home/opencode/citizen
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build
```

### 7. Verify

```bash
# Health check
curl https://workbench.gronowski.cc/health
# → {"status":"ok","version":"v1.0.0"}

# Verify DB tables
docker exec citizen-db-1 psql -U citizen_user -d citizen_db -c "\dt"
# → 15 tables (alembic_version, cache_entry, case_run, case_run_area, ...)

# Check disclaimer version
curl https://workbench.gronowski.cc/api/v1/meta/disclaimer/version
# → {"version":"v0.1.0"}

# Check active profile
curl https://workbench.gronowski.cc/api/v1/meta/active-profile
# → {"profile":"eu-avv","label":"EU-AVV (Default — NGO Build)",...}
```

---

## Operations

### Restart

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml restart citizen-app
```

### View logs

```bash
docker logs -f citizen-citizen-app-1
```

### Database access

```bash
docker exec -it citizen-db-1 psql -U citizen_user -d citizen_db
```

### Rebuild after code changes

```bash
cd /home/opencode/citizen
# Sync updated files first, then:
docker compose -f docker-compose.yml -f docker-compose.override.yml down
docker compose -f docker-compose.yml -f docker-compose.override.yml build --no-cache citizen-app
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

### SSL renewal check

```bash
sudo certbot renew --dry-run
```

---

## Known Issues & Fixes Applied

### D-001: Missing asyncpg dependency
`asyncpg>=0.29.0` added to `pyproject.toml` dependencies.

### D-002: Missing pgvector Python package
`pgvector>=0.3.0` added to `pyproject.toml` dependencies.

### D-003: Docker port conflict (8000)
Resolved by mapping container port 8000 to host port 8001 in the override file, and updating nginx proxy_pass.

### D-004: Migration DAG with multiple heads
The alembic migration tree has two branches from `<base>`:
- PostgreSQL: 001 → 002 → 003 → 004 → 005 → 006
- SQLite: 007 → 008 → 009 → 010

`alembic upgrade head` (singular) fails with "Multiple head revisions are present."
Fixed in `app/main.py` — the auto-migration targets `006_add_intake_and_legal_areas`
for PostgreSQL and `heads` for SQLite.

### D-005: Missing schema columns (regime, notes, pii_mapping)
Migrations 008–010 (on the SQLite branch) add columns to `legal_parameter` and
`case_run` that the PostgreSQL branch (001→006) does not include. Applied manually
via `ALTER TABLE` DDL on the production database. A proper migration 011 is pending.

### D-006: alembic upgrade deadlock during startup
`alembic_command.upgrade()` called via `asyncio.to_thread()` from inside uvicorn's
lifespan handler causes an event-loop deadlock (asyncpg + greenlet conflict across
threads). Fixed by running alembic in a subprocess instead (`asyncio.create_subprocess_exec`).

### D-007: Docker HEALTHCHECK interval
The Docker HEALTHCHECK runs `curl http://localhost:8000/health` every 30 seconds.
During initial startup (before lifespan completes), the /health endpoint may not
respond, causing the container to be marked unhealthy. The lifespan now completes
in ~2 seconds, so this is not an issue in practice.

---

## Upgrade Path

When deploying a new version:

1. Sync code to VPS
2. Rebuild the Docker image
3. If database schema changed, the auto-migration handles it on startup
4. Verify health endpoint and key API routes

---

## Backup

The PostgreSQL data lives in the named Docker volume `citizen_pgdata`. To back up:

```bash
docker exec citizen-db-1 pg_dump -U citizen_user citizen_db | gzip > citizen_db_$(date +%Y%m%d).sql.gz
```

