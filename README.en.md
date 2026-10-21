# Insurance Recommendation

[简体中文](README.md) | **English**

An open-source decision-support tool for personal insurance planning. A deterministic rule
engine decides which products a user is allowed to buy, an eight-dimension scorer ranks them,
a budget-aware planner assembles three portfolios, and an optional LLM layer explains the
result without ever being able to override the rules.

The project targets the Chinese mainland insurance market: the product catalog, the
questionnaire and the UI copy are Chinese-language. Everything else — code, configuration and
these documents — is in English so that the logic can be reviewed and reused elsewhere.

- **Status:** early public release, `v0.1.0`
- **License:** MIT
- **Not affiliated with** any insurer, broker or comparison site

---

## 1. Project Overview

Given a short profile (age, life stage, income, occupation risk class, health status, family
burden, existing coverage), the system answers one question: *which combination of insurance
products is both admissible and affordable for this person, and why?*

It does that in four deterministic stages and one optional AI stage:

```
profile → hard eligibility rules → 8-dimension scoring → budget-aware bundling → optional LLM explanation
```

The rule stages are pure SQL/Python and always run. The AI stage can only re-rank and
explain products that already survived the rules; it cannot add a product, drop a hard
constraint, or exceed the budget. When the model is unavailable, slow, rate-limited or out of
quota, the request still returns a complete rule-based answer.

The product catalog is not scraped from proprietary APIs. It is built by crawling public
product pages, extracting structured fields with an LLM, validating them against a schema and
a source whitelist, and routing uncertain extractions to human review. Every published
product keeps its source URL and a last-verified timestamp.

## 2. Motivation & Problems Solved

Insurance comparison sites optimise for conversion. Their rankings are opaque, their "best"
label is commercial, and the same product can appear with different premiums depending on the
entry point. Meanwhile, most open-source insurance projects stop at a calculator: they compute
a number but do not model eligibility, underwriting boundaries or portfolio construction.

This project takes the opposite position:

| Problem | Approach taken here |
| --- | --- |
| Rankings that cannot be audited | Every score is decomposed into eight named dimensions with type-specific weights stored in versioned YAML |
| Recommendations that ignore eligibility | Age, occupation class, product status and age/type policy rules are hard filters applied before anything else |
| "Just buy the most expensive plan" | Three portfolios differ only in budget tier and completeness, and are named neutrally (`low premium first` / `balanced` / `high coverage first`) |
| LLMs inventing products | The model receives a closed candidate whitelist and returns product IDs; unknown IDs are discarded |
| Stale or unverifiable product data | Crawled products carry `source_url`, extraction evidence, a version chain and a `last_verified_at` freshness flag |
| Tools that look like they sell insurance | The result page states the boundary explicitly: no real-time underwriting, no binding quote, no lead capture |

This is a **decision-support** project. It is not a brokerage, it does not issue quotes, and
it does not replace reading a policy contract.

## 3. Key Features

**Recommendation engine**

- Seven-dimension user profile, plus social-insurance status, free-text occupation
  resolution and existing policy details that feed a coverage-gap analysis
- Hard rule tree ("one-vote veto"): out-of-range age, occupation class above the product
  limit, off-shelf products, age/type policy matrix (e.g. no term life under 18), and
  per-type budget admission are all applied before scoring
- Eight-dimension, type-weighted scoring: coverage breadth, premium competitiveness,
  underwriting flexibility, waiting period, waiver clauses, sum-insured adequacy, brand
  tier, value-added services
- Budget-aware portfolio construction: greedy selection under an absolute budget tier,
  organised into basic / core / supplementary layers, with one swap when a required type is
  missing and per-type coverage-gap output
- Dual engine routing: rule-only mode returns synchronously in under a second; AI mode
  re-ranks within a per-type candidate pool and returns a structured explanation
- Deterministic fallback on LLM error, timeout, missing key or exhausted daily quota
- Explainability: per-product score breakdown, recommendation reasons, rejection summary
  with reason codes, hard-rule summary, and engine/rule/scoring version metadata for
  reproducing a historical result

**Product data pipeline**

- Aggregator-first discovery and crawling with `robots.txt` checks, per-platform rate limits
  and SSRF guards
- LLM extraction followed by Pydantic validation against a field whitelist and an exact-match
  gate, so heuristic or fuzzy extractions never auto-publish
- Confidence- and completeness-gated auto-publish with an audit trail; everything else goes
  to a human review queue
- Product / rule / benefit / version records with provenance and rollback
- Official-site cross-verification and third-party review matching as annotations only
- Freshness tracking (`last_verified_at`, stale flag after 90 days by default) and automatic
  off-shelf detection

**Platform**

- Email/password authentication with httpOnly cookies, access/refresh tokens and RBAC
  (`user`, `admin`) enforced per permission
- Redis-backed fixed-window rate limiting (atomic Lua), AI daily quota and short result cache,
  all fail-open with a logged warning
- Explicit CORS allowlist, security response headers, trusted-proxy handling for
  `X-Forwarded-For`
- Encryption at rest for saved recommendation records, which contain health disclosures
- Chinese-first React UI, responsive down to 320 px, with admin console for products,
  crawling, review tasks and audit logs
- A 300+ case backend suite, a TypeScript build gate and 37 Playwright end-to-end tests

## 4. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ Browser  React 18 + TypeScript + Ant Design 5 (Vite)                 │
│   /            questionnaire      /result     portfolios + compare   │
│   /account     saved profiles     /admin      catalog / crawl / review│
└───────────────────────────────┬──────────────────────────────────────┘
                                │  /api/*  (httpOnly cookie session)
┌───────────────────────────────▼──────────────────────────────────────┐
│ FastAPI application                                                  │
│  middleware   rate limiter (Redis Lua) · security headers · CORS      │
│  routers      /api/recommend · /api/products · /api/compare           │
│               /api/auth · /api/my/* · /api/admin/*                    │
│  engine       rule_engine → scoring → budget → combo_builder          │
│               ai_engine (whitelisted rerank) · fallback · health      │
│  ingestion    discovery · fetcher (robots/SSRF) · extractor · review   │
│               auto_publish · official_verification · versions         │
│  crawler      scraper · llm_extractor · APScheduler (single replica)   │
└──────────┬───────────────────────────────────┬───────────────────────┘
           │                                   │
    ┌──────▼──────┐                    ┌───────▼────────┐
    │ PostgreSQL  │  products, rules,  │ Redis          │  rate limits,
    │ (SQLite in  │  ingestion, auth,  │                │  AI quota/cache
    │  development)│  recommendation   └────────────────┘
    └─────────────┘  records
                                │
                     ┌──────────▼──────────┐
                     │ OpenAI-compatible   │  extraction + explanation
                     │ LLM endpoint        │  (optional; degrades)
                     └─────────────────────┘
```

Layering rules that the code actually enforces:

1. The API layer never scores anything itself; it orchestrates engine calls.
2. The rule engine is the only place allowed to remove a product from consideration.
3. The AI engine receives already-scored candidates and returns selections from that set
   only; its response model rejects unknown product IDs.
4. The product pool is the single source of truth for what can be recommended — a product
   that has not been reviewed or auto-published never reaches the engine.

See [`docs/en/architecture.md`](docs/en/architecture.md) for module-by-module detail, the data
model, and the request lifecycle.

## 5. Recommendation Pipeline

**Stage 0 — Profile.** The questionnaire produces age, gender, annual income, life stage,
family burden, health status, declared health issues, existing coverage, budget ratio,
occupation (class 1–6, resolved from a free-text name when not given explicitly) and optional
existing policies. If neither an explicit job class nor a resolvable occupation is provided,
the request is rejected with `422` rather than silently defaulting — occupation class is a
hard filter input.

**Stage 1 — Budget and sum insured.** An annual budget is derived from income and budget
ratio; recommended sum insured is computed per insurance type. The absolute budget tier, not
the ratio alone, determines which insurance types are admissible.

**Stage 2 — Hard eligibility ("one-vote veto").** Pure database filtering, no model involved:

- age outside `[min_age, max_age]` of the product → rejected
- occupation class above the product's `job_class_limit` → rejected
- product status off-shelf → rejected
- age/type policy matrix → term life is forbidden under 18; critical illness is discouraged
  (not forbidden) from 56, so a product that explicitly accepts the age can still enter the
  pool; cancer insurance is optional rather than forced
- premium floor above the per-type budget → rejected

The output is an admissible candidate pool plus a rejection list with reason codes.

**Stage 3 — Eight-dimension scoring.** Each surviving product is scored per insurance type
using weights from `backend/config/scoring_weights.yaml` (`type_weights`, currently version 2):

| Dimension | What it measures |
| --- | --- |
| `coverage` | Breadth of covered risks and benefit lines |
| `price` | Premium competitiveness as a within-type rank percentile |
| `flexibility` | Underwriting and enrollment looseness (age range, health notice count) |
| `waiting` | Waiting-period advantage, with per-type optima |
| `waiver` | Waiver-of-premium and similar clauses |
| `adequacy` | Sum insured relative to the recommended amount |
| `brand` | Company tier (T1/T2/T3) as a small tiebreaker; profile-based tier preference is applied later, during portfolio construction |
| `service` | Value-added services |

Products with no disclosed premium are scored neutrally and excluded from the price ranking,
so an unknown price is never treated as a cheap price.

**Stage 4 — Portfolio construction.** Candidates are matched against a required/optional type
matrix and selected greedily under the package budget. Three packages are produced with
budget multipliers `0.5 / 0.8 / 1.0` and different selection strategies (`cheapest` vs
`best_score`). Each package is organised into basic (medical + accident), core (critical
illness + term life) and supplementary (cancer, annuity) layers. Packages 2 and 3 perform one
substitution when a required type is missing, accepted only if completeness improves. Each
package reports budget utilisation, a completeness score and per-type coverage gaps in CNY.
The package names deliberately describe the trade-off instead of implying that a higher
premium is better.

**Stage 5 — Optional AI layer.** Only when `enable_llm_engine=true`:

- the top N products per type (default 5) form a closed whitelist, drawn from the already
  filtered and scored pool
- the model returns a narrative plus a structured selection of product IDs, validated by a
  Pydantic response model; IDs outside the whitelist are rejected
- the selected products are re-materialised through the same budget checks, so the AI cannot
  overspend
- results are cached in Redis for one hour keyed by a hash of the canonical profile plus the
  engine version; cached responses are labelled `ai_from_cache=true`
- each user (or anonymous IP) gets a daily AI quota (default 20); exceeding it degrades to
  rule mode instead of failing
- any exception, timeout, missing key or invalid response degrades to rule mode with an
  explicit `engine_mode: "degraded"` and a fixed fallback narrative

Hard rules and the budget ceiling are never delegated to the model. This is the core safety
property of the design.

## 6. Technology Stack

| Layer | Choice |
| --- | --- |
| Frontend | React 18, TypeScript 5.6, Ant Design 5, Vite 6, Axios, React Router 6 |
| Visualisation | Plain React/CSS score breakdown and budget allocation (no charting library) |
| Backend | FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2, APScheduler 3.11 |
| Auth | PyJWT access/refresh tokens in httpOnly cookies, bcrypt password hashing |
| Crawling | Playwright 1.49 (Chromium), BeautifulSoup 4, httpx |
| LLM | `openai` 1.58 + `instructor` 1.7 against any OpenAI-compatible endpoint |
| Storage | PostgreSQL 16 in Compose, SQLite for local development and tests |
| Cache / limits | Redis 7 (atomic Lua counters, AI cache) |
| Migrations | Alembic 1.14 with a startup schema gate |
| Tests | pytest 8, Playwright 1.62 |
| Packaging | Docker Compose (Postgres + Redis + backend + Nginx frontend) |

## 7. Quick Start

### Prerequisites

- Python 3.12+
- Node.js 22+ (CI also runs Node 20 for the E2E job)
- Docker and Docker Compose (optional but the fastest path)
- Redis is optional locally; without it, rate limiting and AI caching are skipped
  (fail-open) and a warning is logged

### Docker Compose

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```env
LLM_API_KEY=<your key>              # Compose refuses to start without it
JWT_SECRET_KEY=<random string>      # Compose refuses to start without it
POSTGRES_PASSWORD=<strong password>
DATABASE_URL=postgresql+psycopg2://insurance:<strong password>@postgres:5432/insurance
RECORD_ENCRYPTION_KEY=<random string>
```

Then:

```bash
docker compose up -d --build
docker compose exec backend python backend/scripts/seed.py   # optional demo catalog
```

- Frontend: <http://localhost:18080>
- API docs: <http://localhost:8000/docs> when running the backend outside Compose

`LLM_API_KEY`, `JWT_SECRET_KEY`, `POSTGRES_PASSWORD` and `DATABASE_URL` are hard requirements
in `docker-compose.yml`. If `LLM_API_KEY` is absent, Compose fails fast instead of silently
deploying without AI.

### Manual development

```bash
# 1. Backend
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
mkdir -p ../data                  # SQLite files live here; the directory is git-ignored
alembic upgrade head
python scripts/seed.py            # optional demo catalog
python -m uvicorn backend.main:app --reload --port 8000

# 2. Frontend (second terminal)
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

### First administrator

Public registration always creates a `user`. The first admin is bootstrapped from environment
variables, idempotently, and the action is written to the audit log:

```bash
FIRST_ADMIN_EMAIL=admin@example.com FIRST_ADMIN_PASSWORD='<strong password>' \
  python -m uvicorn backend.main:app --reload
```

Clear `FIRST_ADMIN_PASSWORD` afterwards. Later admins are granted by an existing admin via
`POST /api/admin/users/{user_id}/roles` with `{"roles": ["admin"]}` (requires `admin:grant`).

## 8. Configuration

All settings are read from environment variables (or `.env` at the repository root) through
`pydantic-settings`. Names are case-insensitive for the app, but **Compose only interpolates
uppercase names** — a lowercase-only `.env` will deploy with empty values.

### Application essentials

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///data/insurance.db` | SQLAlchemy URL; PostgreSQL in Compose |
| `REDIS_URL` | `redis://localhost:6379` | Rate limits, AI quota and cache |
| `LLM_API_KEY` | empty | Required for AI mode; empty ⇒ AI mode degrades |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | Any OpenAI-compatible endpoint |
| `LLM_MODEL` | `deepseek-v4-flash` | Model name passed to the provider |
| `LLM_MAX_TOKENS` | `2048` | Cap for structured responses |
| `LLM_CONNECT_TIMEOUT` / `LLM_READ_TIMEOUT` | `3.0` / `90.0` | Seconds |
| `AI_DAILY_LIMIT_PER_USER` | `20` | Per user, or per IP for anonymous callers |
| `AI_CACHE_TTL_SECONDS` | `3600` | Narrative cache TTL |
| `AI_CANDIDATE_POOL_SIZE` | `5` | Whitelist size per insurance type |
| `DATA_STALE_DAYS` | `90` | Age after which product data is flagged stale |

### Security and privacy

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `development\|test\|staging\|production` |
| `COOKIE_SECURE` | inferred | Forced `true` in production; explicit `false` there fails startup |
| `COOKIE_SAMESITE` | `lax` | Primary CSRF control; `none` requires `COOKIE_SECURE=true` |
| `CORS_ALLOW_ORIGINS` | localhost list | Explicit origins only; `*` is rejected with credentials |
| `TRUST_PROXY_HEADERS` | `false` | Parse `X-Forwarded-For` only from trusted peers |
| `TRUSTED_PROXIES` | empty | IPs or CIDRs; malformed values fail startup |
| `SECURITY_HEADERS` | `true` | nosniff, frame options, referrer policy, CSP |
| `HSTS_ENABLED` | `false` | Honoured only when `APP_ENV=production` |
| `RECORD_ENCRYPTION_KEY` | empty | Fernet key material for saved recommendation records |
| `RECORD_RETENTION_DAYS` | `0` | Reserved (0 = keep forever); cleanup is not implemented |
| `JWT_SECRET_KEY` | `change_me_before_deploy` | **Must** be replaced outside local development |

Leaving `RECORD_ENCRYPTION_KEY` empty stores recommendation records in plaintext and logs a
warning at startup (an error when `APP_ENV=production`). Because those records contain health
disclosures, any deployment reachable by real users must set it. Changing the key later makes
existing ciphertext unreadable — set it before the first real user.

### Product pool maintenance

| Variable | Default | Purpose |
| --- | --- | --- |
| `SEED_DEMO_PRODUCTS` | `false` | Inject the demo catalog into an empty database |
| `AUTO_PUBLISH_ENABLED` | `true` | Publish high-confidence drafts without human review |
| `AUTO_PUBLISH_CONFIDENCE` | `0.8` | Confidence threshold for auto-publish |
| `DISCOVERY_ENABLED` | `true` | Discover new product URLs from aggregator listings |
| `DISCOVERY_MAX_NEW_PER_SOURCE` | `20` | Cap per maintenance run |
| `CRAWL_INTERVAL_MINUTES` | `720` | Scheduler interval |
| `OFFICIAL_VERIFICATION_ENABLED` | `true` | Cross-check products against official sites |

The most common settings are documented in [`.env.example`](.env.example); the complete
schema lives in `backend/app/config.py`.

## 9. Testing

Run from the repository root. The three commands are independent.

```bash
# 1. Backend suite (isolated temporary SQLite per test file, fake Redis installed by conftest)
./backend/venv/Scripts/python.exe -m pytest backend/tests -q      # Windows
backend/venv/bin/python -m pytest backend/tests -q                # macOS / Linux

# 2. Frontend type check + production build
cd frontend && npm run build

# 3. End-to-end (real backend + Vite dev server, Playwright Chromium)
cd frontend && npx playwright test
```

E2E binds ports **3000** (frontend) and **8000** (backend) with
`reuseExistingServer: false`. If either is occupied, Playwright fails instead of reusing it.
Offset both ports when needed:

```bash
E2E_FRONTEND_PORT=3100 E2E_BACKEND_PORT=8100 npx playwright test
```

The offset is safe: the warm-up URL follows the resolved `baseURL` and the `/api` proxy target
follows `E2E_BACKEND_PORT`, a property locked by
`backend/tests/test_e2e_port_consistency.py`.

What the suites cover: eligibility boundaries and the age/type matrix, persona scenarios,
scoring and money-unit consistency, premium ranges, budget admission, AI whitelist and
fallback behaviour, prompt-injection hardening, SSRF and robots handling, review workflow and
versioning, freshness labelling, auth/RBAC boundaries, rate limiting, encryption of
recommendation records, schema-migration parity, and the Compose policy assertions.

CI runs `Backend Tests` and `E2E Tests` on pushes and pull requests to `main`/`master`. Neither
workflow deploys anything. See [`docs/en/development.md`](docs/en/development.md) for the full
test map and known environment constraints.

## 10. Security & Privacy

The system handles health information, so the defaults are conservative and the trade-offs are
documented rather than hidden.

- **Authentication.** Passwords are bcrypt-hashed. Access and refresh tokens are delivered as
  httpOnly cookies (`SameSite=Lax`, `Secure` in production) and hashed before storage.
- **Authorization.** Two roles (`user`, `admin`) mapped to explicit permission names such as
  `crawl:read`, `review:approve`, `admin:grant`. Admin-only routers depend on a permission
  check, not on a role string.
- **CSRF.** No CSRF token is issued: the API has no server-rendered forms, cookies are
  `SameSite=Lax`, and CORS is an explicit allowlist with credentials — a wildcard origin is
  rejected at startup. This is a documented design choice with known limits for non-browser
  clients.
- **Abuse.** Redis atomic counters enforce per-IP, per-user and per-day limits; login has
  brute-force protection. Redis outages fail open with a warning, by design, so availability
  does not depend on the cache.
- **AI surface.** Both LLM prompts are hardened against injection from crawled page content
  and user input. The model cannot introduce product IDs, and its output is schema-validated.
- **Crawling.** Targets must pass an SSRF check (no loopback, link-local or private
  addresses, with DNS re-resolution) and a `robots.txt` check before any fetch.
- **Data at rest.** Recommendation records are encrypted with Fernet when
  `RECORD_ENCRYPTION_KEY` is set. Saved profiles and recommendation history are scoped to the
  owning user.
- **No telemetry.** The project contains no analytics, tracking or outbound call-home code.

Vulnerability disclosure: see [`SECURITY.md`](SECURITY.md). Please do not open a public issue
for a suspected vulnerability.

## 11. Limitations & Disclaimer

Known limitations, stated plainly:

- **Premiums are indicative.** `premium` is the lower bound of a quoted range and
  `premium_basis_note` says so in every response. Actual pricing depends on underwriting,
  age, sum insured and payment term, and differs per product.
- **No real-time underwriting.** Health notices are matched heuristically to produce warnings;
  no insurer is contacted and no underwriting decision is simulated.
- **No regional dimension.** Province/city eligibility is neither collected nor modelled,
  because the product data does not carry it.
- **Chinese market only.** Product data, currency (CNY) and UI copy assume the Chinese
  mainland market. There is no UI internationalisation layer yet.
- **AI mode is advisory and optional.** It requires an external LLM endpoint; quota, latency
  and provider availability all affect it, and it degrades to rule mode.
- **Demo catalog vs. real pool.** `SEED_DEMO_PRODUCTS=true` injects a demonstration catalog
  for local use and E2E. Production deployments are expected to run with it disabled and build
  the pool from reviewed crawl data, which means an empty product pool on first boot.
- **Retention is not enforced.** `RECORD_RETENTION_DAYS` is reserved; no cleanup job runs.
- **Single-scheduler assumption.** The backend embeds APScheduler, so only one replica may run
  the scheduler; other replicas need `SCHEDULER_DISABLED=true`.
- **Not a licensed intermediary.** The project provides no application, purchase or lead
  capture flow.

> **Disclaimer.** This tool produces algorithm-generated suggestions for informational
> purposes only. It does not provide a binding quote, real-time underwriting, or any guarantee
> of coverage. Product terms, health notices and underwriting results from the insurer always
> prevail. Nothing here is financial, legal or medical advice.

## 12. Roadmap

The following items are **not implemented** in `v0.1.0` and are listed as intent, not delivery:

- Optional UI internationalisation (English locale) on top of the Chinese catalog
- Region/province eligibility once product data exposes it
- A scheduled retention job for saved health information
- Pluggable premium normalisation so quotes with different bases can be compared more fairly
- Additional crawl sources and a source-health dashboard
- Structured release automation (changelog draft, artifact build) once releases become frequent

Priorities may change; issues and discussion are the right place to influence them.

## 13. Contributing

Contributions are welcome — bug reports, documentation fixes, test coverage, and new product
rules. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md), which covers the local setup, branch
and commit conventions, test requirements, and how PRs are reviewed. Community expectations
are in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Security issues must follow
[`SECURITY.md`](SECURITY.md), not the public issue tracker.

Chinese-language issues and pull requests are welcome; maintainers will respond in Chinese or
English.

## 14. License

[MIT](LICENSE). You may use, modify and redistribute this project, including commercially,
provided the copyright notice and license text are retained. The software is provided "as is",
without warranty of any kind — see the license text for the full disclaimer.
