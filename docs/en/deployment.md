# Deployment Guide

Operational notes for running this project with Docker Compose behind your own reverse proxy.
The full step-by-step runbook, including the Chinese checklists used for staging and
production, is [`../docker-deployment.md`](../docker-deployment.md). This document is the
English summary: required configuration, the two hard gates, and the parts that are easy to get
wrong.

Nothing here provisions a server, a domain or TLS certificates for you, and no workflow in this
repository deploys anywhere. A release tag changes source code only.

## 1. Topology

```
host nginx / caddy  :80/:443
  └── 127.0.0.1:${FRONTEND_PORT}      frontend container (nginx, static build)
        └── /api/  →  backend:8000     FastAPI (not published to the host)
              ├── postgres:5432        PostgreSQL 16
              └── redis:6379           Redis 7 (rate limits, AI quota and cache)
```

Only the frontend publishes a port, and it is bound to loopback on purpose:
`127.0.0.1:${FRONTEND_PORT}:80`. PostgreSQL, Redis and the backend are reachable only on the
Compose network. That is why the host proxy is mandatory rather than optional.

Two instances on one host need distinct directories, `.env` files, `COMPOSE_PROJECT_NAME` and
`FRONTEND_PORT` values (for example `18080` for staging, `18081` for production).

## 2. Required configuration

`docker-compose.yml` uses `:?` for four values, so Compose refuses to start when they are
missing:

| Variable | Why it is mandatory |
| --- | --- |
| `LLM_API_KEY` | Prevents a silent deployment where AI mode is permanently degraded |
| `JWT_SECRET_KEY` | Session tokens must not be signed with the default placeholder |
| `POSTGRES_PASSWORD` | No default database password |
| `DATABASE_URL` | Must point at the Compose `postgres` service |

A production `.env` should also set:

```env
COMPOSE_PROJECT_NAME=insurance_prod
FRONTEND_PORT=18081
APP_ENV=production
COOKIE_SECURE=true                 # required when APP_ENV=production
COOKIE_SAMESITE=lax
CORS_ALLOW_ORIGINS=https://insurance.example.com
TRUST_PROXY_HEADERS=true
TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12
SECURITY_HEADERS=true
HSTS_ENABLED=true
SCORING_WEIGHTS_FAIL_FAST=true
RECORD_ENCRYPTION_KEY=<random string>
SEED_DEMO_PRODUCTS=false
FIRST_ADMIN_EMAIL=admin@example.com
FIRST_ADMIN_PASSWORD=<temporary password, clear after first boot>
```

`CORS_ALLOW_ORIGINS` must be the exact browser origin of the frontend. Wildcards are rejected
in production, and a wildcard can never be combined with credentials in any environment.

`TRUSTED_PROXIES` must cover every hop that appends to `X-Forwarded-For`: the host proxy
(typically `127.0.0.1`) and the frontend container subnet (`172.16.0.0/12` for the default
Compose network). Getting this wrong does not break requests, it makes rate limiting count the
proxy instead of the client.

## 3. First deployment

```bash
git clone https://github.com/nwm1314/insurance-recommendation.git /opt/insurance-prod
cd /opt/insurance-prod
git fetch --tags
git checkout v0.1.0
cp .env.example .env
# edit .env per section 2
```

```bash
docker compose build
docker compose up -d postgres redis
docker compose run --rm backend sh -c "cd /srv/backend && alembic upgrade head"
docker compose up -d --build
docker compose ps
```

The backend image runs `alembic upgrade head` from its entrypoint before starting Uvicorn, so
the explicit migration step is preflight visibility rather than the only migration path. A
migration failure still prevents the container from becoming healthy.

Verify:

```bash
curl -fsS http://127.0.0.1:18081/healthz          # frontend nginx
curl -fsS http://127.0.0.1:18081/api/products | head -c 200
docker compose logs --tail=100 backend
```

`/healthz` is served by the frontend container. The backend exposes `/` and
`/api/admin/health`; neither is published to the host.

### Product pool after first boot

`SEED_DEMO_PRODUCTS=false` is the production default, so the pool starts empty and stays empty
until ingestion publishes reviewed products. Recommendations return an empty package set in
that state — that is expected, not a bug. To populate a demo environment:

```bash
docker compose exec backend python backend/scripts/seed.py
```

Do not run that against production: the demo catalog is not real product data and would mix
with crawled records.

## 4. Hard gate 1 — schema

The application verifies the schema at startup and refuses to serve traffic when:

- the database has tables but no Alembic version row;
- the version is not the head of the migration chain;
- a model table or column is missing.

This is deliberate. Recovering with `Base.metadata.create_all()` would hide drift, so the app
fails instead. The fix is always `alembic upgrade head`, preceded by a backup.

## 5. Hard gate 2 — recommendation record encryption

Saved recommendation records contain the profile and the result, including `health_status` and
declared health issues. That is sensitive personal information.

With `RECORD_ENCRYPTION_KEY` set, those fields are encrypted with Fernet (any non-empty string
is accepted and derived into a key). With it empty, records are stored in plaintext and the
application logs a warning — an error when `APP_ENV=production` — but still starts. The
degradation is explicit rather than silent, and the deployment checklist is what makes it
mandatory:

```bash
# generate a key and append it to .env
python -c "import secrets; print('RECORD_ENCRYPTION_KEY=' + secrets.token_urlsafe(48))" >> .env

# prove Compose actually injects it (a key in .env without the environment: entry does nothing)
docker compose config | grep -A1 RECORD_ENCRYPTION_KEY

# after startup: any PLAINTEXT warning means the gate failed
if docker compose logs backend | grep -qi "RECORD_ENCRYPTION_KEY"; then
  echo "FAIL: recommendation records are stored in plaintext"
  exit 1
fi
echo "OK: no plaintext warning"
```

Check the log, not the `.env` file: Compose only injects variables listed in the service's
`environment:` block. That forwarding line is locked by
`backend/tests/test_compose_policy.py::test_backend_forwards_record_encryption_key`.

Changing the key later makes existing ciphertext unreadable. Set it before the first real user
and back it up with the database.

Note the limits: encryption covers recommendation records only. Database dumps, volume
snapshots and backups remain sensitive and need their own protection. `RECORD_RETENTION_DAYS`
is reserved configuration; no cleanup job runs in `v0.1.0`.

## 6. Reverse proxy and TLS

The host proxy terminates TLS and forwards to the loopback-published frontend port:

```nginx
server {
    listen 443 ssl;
    server_name insurance.example.com;

    location / {
        proxy_pass http://127.0.0.1:18081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

`COOKIE_SECURE=true` requires HTTPS end to end. If you terminate TLS at the host proxy, the
browser sees HTTPS and the cookie is accepted; the inner hop stays HTTP on loopback, which is
fine because the cookie's `Secure` flag is a browser-side rule.

A Content-Security-Policy for the HTML application should be added at the proxy or CDN. The
backend's CSP header applies to API responses only (`default-src 'none'`).

## 7. Single replica and the scheduler

The backend embeds APScheduler for product-pool maintenance. Running two replicas without
care means two crawlers and duplicated jobs. Either keep the backend at one replica, or set
`SCHEDULER_DISABLED=true` on every replica except the primary.

There is no distributed lock, no leader election and no queue. Horizontal scaling of the
backend is therefore a design change, not a configuration change.

## 8. Backup, upgrade, rollback

**Backup before every upgrade:**

```bash
docker compose exec postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql
```

**Upgrade to a newer tag:**

```bash
cd /opt/insurance-prod
git fetch --tags
git checkout v0.x.y
docker compose build
docker compose run --rm backend sh -c "cd /srv/backend && alembic upgrade head"
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend
```

Then re-run the encryption gate from section 5 — a rebuilt container that lost the variable
would fall back to plaintext.

**Rollback:** check out the previous tag, rebuild, and restore the database backup if the
migration was not backward compatible. `alembic downgrade -1` reverts the revision record and
is best-effort for data; treat a full restore as the reliable path.

**Stop:** `docker compose down`. Never run `docker compose down -v` in production — it deletes
the database volume.

## 9. Staging vs. production

| Concern | Staging | Production |
| --- | --- | --- |
| `APP_ENV` | `staging` | `production` |
| Cookies | `COOKIE_SECURE=true` only with HTTPS | Must be `true`; startup fails otherwise |
| HSTS | Usually off | `HSTS_ENABLED=true` |
| `CORS_ALLOW_ORIGINS` | Staging origin | Exact production origin |
| `RECORD_ENCRYPTION_KEY` | Required (real testers) | Required |
| `SEED_DEMO_PRODUCTS` | Allowed | Must stay `false` |
| Branch / ref | `develop` | Release tag |

Both environments run the same image build; only configuration differs. There is no
staging-only code path.

## 10. What this project does not provide

Stated so that expectations are correct:

- No HA, autoscaling, or multi-region deployment; the scheduler assumes a single replica.
- No object storage, queue, or background worker pool; crawling runs inside the API process.
- No WAF, DDoS protection or bot management — put those in front if you expose the service.
- No audit export, SIEM integration, or metrics endpoint. Logs go to the container's stdout.
- No automatic data-retention deletion.
- No legal compliance certification. If you handle real health data, you are responsible for
  the applicable regulatory obligations in your jurisdiction.

## 11. Security checklist

Before exposing an instance to real users:

- [ ] `APP_ENV=production`, `COOKIE_SECURE=true`, HSTS enabled, HTTPS terminating at the proxy
- [ ] `JWT_SECRET_KEY` and `POSTGRES_PASSWORD` replaced with random values, stored outside git
- [ ] `RECORD_ENCRYPTION_KEY` set, forwarded by Compose, and the log gate passes
- [ ] `CORS_ALLOW_ORIGINS` lists exact origins, no wildcard
- [ ] `TRUSTED_PROXIES` covers exactly the proxies in the request path
- [ ] `SEED_DEMO_PRODUCTS=false`
- [ ] Backups scheduled and a restore has been tested
- [ ] `FIRST_ADMIN_PASSWORD` cleared after the first admin exists
- [ ] Rate limits reviewed for your expected traffic
