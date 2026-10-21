# Development Guide

How to build, run and test this project locally. For deployment see
[`deployment.md`](deployment.md); for internals see [`architecture.md`](architecture.md).

## 1. Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.12+ | The backend image uses 3.12; the Backend Tests workflow uses 3.11 and passes |
| Node.js | 22+ recommended | The E2E workflow uses Node 20; both work |
| npm | Bundled with Node | `npm ci` needs the committed lockfile |
| Docker + Compose | Recent | Optional; required only for the Compose path |
| Redis | 7.x | Optional locally — the app fails open without it |

Playwright needs a Chromium build. On first run:

```bash
cd frontend && npx playwright install --with-deps chromium
```

## 2. First-time setup

```bash
git clone https://github.com/nwm1314/insurance-recommendation.git
cd insurance-recommendation

cp .env.example .env       # optional; defaults are development-safe
```

Edit `.env` only if you need AI mode (`LLM_API_KEY`) or a non-default database. Never commit
`.env` — it is git-ignored, and `.env.example` must keep placeholders only.

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate                  # Windows: venv\Scripts\activate
pip install -r requirements.txt
mkdir -p ../data                          # git-ignored; the app also creates it on boot
alembic upgrade head
python scripts/seed.py                    # optional demo catalog
python -m uvicorn backend.main:app --reload --port 8000
```

`mkdir -p ../data` is only needed on a fresh clone: the default SQLite URL is
`sqlite:///data/insurance.db`, and SQLite will not create the directory itself. The app
creates it at startup, but `alembic` and `seed.py` run before that.

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000, proxies /api to http://localhost:8000
```

The Vite dev proxy forwards `/api` to `http://localhost:${E2E_BACKEND_PORT}` (default `8000`),
so the same variable that moves the E2E backend also moves the proxy target.

## 3. Database and migrations

The app refuses to start when the schema does not match the Alembic head. That is intentional:
a mismatched schema is treated as an error, not silently repaired.

```bash
cd backend

alembic upgrade head          # apply all migrations
alembic current               # show the revision the database is on
alembic downgrade -1          # step back one revision (data is preserved where possible)
alembic history               # full chain
```

Chain in `v0.1.0` (all six revisions are on the path to head):

```
20260706_0001 (auth/rbac)
  → 20260706_0002 (data ingestion + catalog)
  → 20260811_0001 (align models)
  → 20260816_0001 (verification fields)
  → 20260914_0001 (last_verified_at)
  → 20260914_0002 (admin-edit versions)   ← head
```

Adding a migration:

```bash
cd backend
alembic revision -m "describe the change"
```

Then update the migration by hand. `backend/tests/test_schema_migration.py` asserts that a
freshly migrated database matches the ORM metadata; run it after any model change.

**Common error**

```
Database schema is at migration 'x' but the current Alembic head is 'y'
```

The local database is behind. Run `alembic upgrade head` from `backend/`. `data/insurance.db`
is the default development database and is git-ignored — deleting it is safe if you do not need
the local data, but re-run `seed.py` afterwards.

## 4. Test suites

All commands below assume the repository root as the working directory. They are independent
of each other.

### Backend

```bash
./backend/venv/Scripts/python.exe -m pytest backend/tests -q     # Windows
backend/venv/bin/python -m pytest backend/tests -q               # macOS / Linux
```

Runtime is roughly 70–90 seconds. Each test module points `DATABASE_URL` at its own temporary
SQLite file *before* importing the app, so no module writes to `data/insurance.db`.
`backend/tests/conftest.py` replaces `redis.from_url` with an in-process fake and flushes it
between tests, so the suite does not need a running Redis and cannot accumulate rate-limit or
cache state across runs.

What each file guards:

| File | Focus |
| --- | --- |
| `test_eligibility_boundaries.py` | Age/type matrix, hard-filter boundaries |
| `test_persona_scenarios.py` | End-to-end recommendations for nine personas |
| `test_stage3_recommendation.py` | Scoring, budget, combos, AI whitelist and degradation |
| `test_premium_range_budget.py` | Premium ranges and per-type budget admission |
| `test_ai_pick.py` | AI selection materialisation and budget re-checks |
| `test_llm_safety.py` | Prompt-injection hardening on both prompt surfaces |
| `test_ssrf_protection.py` | URL/DNS blocking for private ranges |
| `test_product_pool_pipeline.py` | Discovery → fetch → extract → publish gates |
| `test_product_freshness.py` | `last_verified_at` and stale labelling |
| `test_product_catalog.py` | Catalog reads, admin writes, off-shelf behaviour |
| `test_ingestion_review_workflow.py` | Review tasks, approve/reject, versioning |
| `test_auth_ingestion_api.py` | Auth flows, RBAC, ingestion endpoints |
| `test_ops002_security.py` | Login brute force, record encryption, cookie flags |
| `test_rate_limiter.py` | Redis fixed-window counters and fail-open |
| `test_profile_history_api.py` | Saved profiles and recommendation history |
| `test_recommendation_persistence.py` | Record storage, encryption round-trip |
| `test_schema_migration.py` | Migration chain vs. ORM metadata |
| `test_money_unit_consistency.py` | 万 vs. CNY unit conventions |
| `test_compose_policy.py` | Compose forwards the variables the docs promise |
| `test_cors_validation.py` | Origin allowlist and wildcard rejection |
| `test_sqlite_path_bootstrap.py` | SQLite parent-directory creation on a fresh clone |
| `test_e2e_port_consistency.py` | E2E port offset wiring |
| `test_redis_test_isolation.py` | The fake Redis cannot leak to the dev database |
| `test_seed_urls.py` | Demo catalog source URLs |
| `test_verification_evidence.py` | Official verification and evidence capture |
| `test_admin_bootstrap.py` | First-admin bootstrap and audit entry |
| `test_fix_sum_insured_units.py` | Sum-insured unit regressions |
| `test_product_draft_schema.py` | Draft schema validation |

### Frontend

```bash
cd frontend
npm run build        # tsc -b (type check) then vite build
```

There is no separate `npm test` unit suite; component behaviour is covered by the Playwright
suite. `npm run build` is the type-checking gate and must pass before a PR is merged.

### End-to-end

```bash
cd frontend
npx playwright test
```

Playwright starts a real backend (`tests/e2e/start-backend.mjs`: `alembic upgrade head` against
`data/e2e-backend.db`, then `uvicorn`) and a Vite dev server, then runs 37 tests with two
workers. Ports default to 3000 (frontend) and 8000 (backend) with
`reuseExistingServer: false`; if either is taken, the run fails immediately.

```bash
# offset both ports instead of killing whatever holds 3000/8000
E2E_FRONTEND_PORT=3100 E2E_BACKEND_PORT=8100 npx playwright test
```

On Windows, find and stop the holder:

```powershell
Get-NetTCPConnection -LocalPort 3000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

If the busy port belongs to another project, prefer the offset.

Artifacts land in `frontend/playwright-report/` (HTML) and `frontend/test-results/` (traces,
screenshots, video on failure). Both are git-ignored.

## 5. Code style and review expectations

No linter or formatter is configured (no ESLint, Prettier, Ruff or Flake8 config in the
repository). Style is therefore held by three things:

1. `tsc -b` for the frontend and the import-time behaviour of the backend.
2. The test suite, which asserts behaviour rather than formatting.
3. Review: match the surrounding code, keep functions small, and prefer explicit names.

Conventions worth knowing before you change engine code:

- **Units.** `sum_insured_*` is in ten-thousands of CNY (万); `premium_*` and `deductible` are
  in CNY. Tests fail if these drift.
- **Versions.** Changing `TYPE_MATRIX` requires bumping `RULE_VERSION`; changing scoring
  weights or semantics requires bumping the `version` key in `scoring_weights.yaml` and
  `ENGINE_VERSION` when the response shape changes. Historical results are reproduced from
  those values.
- **Docstrings.** Backend modules use detailed Chinese docstrings to record why a guard exists
  and which review item it closes. Follow that pattern; do not strip those comments.
- **Language.** Code comments and UI copy are Chinese; README, `docs/en/*` and the community
  files are English.

## 6. Continuous integration

Two workflows run on pushes and pull requests targeting `main` or `master`:

| Workflow | Command | Notes |
| --- | --- | --- |
| `Backend Tests` | `python -m pytest` in `backend/` | Python 3.11, pip cache |
| `E2E Tests` | `E2E_PYTHON=python npm run test:e2e` | Chromium, uploads the Playwright report and test results as artifacts |

Neither workflow builds images, pushes to a registry, or deploys anywhere. A release tag does
not trigger a deployment.

## 7. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `unable to open database file` | Parent directory of the SQLite file is missing | `mkdir -p data` at the repository root (fixed for app/alembic/seed paths since `v0.1.0`) |
| `Database schema is at migration … head is …` | Local database is behind | `cd backend && alembic upgrade head` |
| Frontend starts but every API call fails | Backend not running on 8000, or CORS origin mismatch | Start the backend; add your dev origin to `CORS_ALLOW_ORIGINS` |
| `http://localhost:3000 is already used` | Orphaned dev server | Offset E2E ports or stop the process holding the port |
| Same message although nothing listens on the port | An `HTTP_PROXY`/`HTTPS_PROXY` in the environment answers for localhost, so Playwright thinks the server is already up | Run with `NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 npx playwright test` |
| AI responses show `engine_mode: "degraded"` | No `LLM_API_KEY`, provider error, timeout, or daily quota exhausted | Check the backend log line `AI mode degraded` (it includes model and sanitised base URL) |
| Recommendations are empty | Product pool is empty | `python scripts/seed.py` for a demo pool, or run ingestion and publish reviewed products |
| `RECORD_ENCRYPTION_KEY is not set … PLAINTEXT` | Encryption key missing | Set the key before exposing the app to real users; changing it later makes old records unreadable |
| Rate limiting seems not to work | Redis is unavailable (fail-open by design) | Start Redis or set `REDIS_URL`; check for the fail-open warning |

## 8. Where to start

- Product/eligibility behaviour: `backend/app/engine/rule_engine.py`
- Ranking: `backend/app/engine/scoring.py` and `backend/config/scoring_weights.yaml`
- Portfolio assembly: `backend/app/engine/combo_builder.py`
- AI contract: `backend/app/engine/ai_engine.py`
- Crawl and publish gates: `backend/app/data_ingestion/`
- HTTP surface: `backend/app/api/`
- UI flows: `frontend/src/pages/`
