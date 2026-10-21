# Architecture

This document describes how the code is actually organised in `v0.1.0`. It is meant for
people who need to change the engine or the ingestion pipeline, not as a product overview —
see [`../../README.en.md`](../../README.en.md) for that.

Chinese counterpart: [`../docker-deployment.md`](../docker-deployment.md) covers deployment
only; engine internals are currently documented here.

## 1. Scope and design constraints

The system has three responsibilities and one boundary:

1. **Decide eligibility** for a given person against a catalog of products (deterministic).
2. **Rank and bundle** eligible products under a budget (deterministic, auditable).
3. **Explain** the result, optionally, with a language model (advisory, replaceable).

The boundary: nothing in the system may produce a binding quote, an underwriting decision, or
a purchase flow. Every response carries a disclaimer and, where relevant, a premium-basis
note.

Two constraints drive most of the design:

- **The engine must work without a model.** LLM availability is treated as an enhancement.
  Any failure path returns a complete rule-based response.
- **Every recommendation must be reproducible.** Engine, rule matrix and scoring-weight
  versions are recorded in the response `meta`, so a past result can be re-derived from the
  product version chain.

## 2. Repository layout

```
backend/
  main.py                     FastAPI app factory, lifespan, middleware, routers
  app/
    api/                      HTTP layer (thin): recommend, products, auth, admin, ingestion
    engine/                   Pure recommendation logic (no HTTP, no FastAPI imports)
      rule_engine.py          Age/type matrix, hard filters, budget admission
      scoring.py              Eight-dimension scoring, type weights, price percentile
      budget.py               Budget split and sum-insured recommendations
      combo_builder.py        Greedy portfolio construction and coverage gaps
      ai_engine.py            Whitelisted LLM rerank, structured response model
      fallback.py             Fixed narrative used when the LLM path degrades
      health.py               Health-notice matching and warnings
      occupation.py           Free-text occupation → risk class
      llm_safety.py           Prompt-injection hardening
      models.py               Engine-internal dataclasses (UserProfile, ScoredProduct, …)
    crawler/                  Playwright scraper, LLM extractor, APScheduler wiring
    data_ingestion/           Discovery, fetch, extract, validate, review, publish, verify
    models/                   SQLAlchemy ORM (23 tables)
    schemas/                  Pydantic request/response models
    services/                 Auth, crypto, product queries
    middleware/               Redis rate limiter
    config.py                 Settings, YAML loading, version constants
    database.py               Engine/session, schema integrity gate
  config/                     scoring_weights.yaml, budget_rules.yaml, occupations.yaml
  alembic/                    Migration chain
  tests/                      pytest suite
frontend/
  src/pages/                  HomePage, ResultPage, LoginPage, RegisterPage, AccountPage, AdminPage
  src/components/             ProductCard, CompareTable, ScoreRadar, BudgetPreview, …
  src/api/                    Axios client with cookie credentials
  tests/e2e/                  Playwright specs + backend launcher
docs/                         Chinese operational docs (deployment, reviews)
docs/en/                      This document plus development and deployment guides
```

The dependency direction is one-way: `api → engine → models`. The engine never imports
`fastapi`, and the only place the API layer touches engine internals is orchestration in
`api/recommend.py`. One known inversion is documented in code: `api/recommend.py` imports
`COMPANY_URLS` from `backend/scripts/seed.py` to classify a product's source type; the correct
fix is to move that constant into `config` or `models`, but it was left in place to keep this
release free of refactors.

## 3. Runtime topology

| Component | Dev | Compose |
| --- | --- | --- |
| Frontend | Vite dev server on `:3000`, proxies `/api` | Nginx on `:80`, published as `127.0.0.1:${FRONTEND_PORT}` |
| Backend | `uvicorn` on `:8000` | `uvicorn` on `:8000`, not published |
| Database | SQLite file under `data/` | PostgreSQL 16 |
| Cache | Optional local Redis | Redis 7 with AOF |
| Scheduler | Disabled in tests via `DISABLE_SCHEDULER_IN_TESTS` | One replica only |

The backend container's entrypoint runs `alembic upgrade head` before `uvicorn`. Application
startup then verifies the schema (`verify_schema_integrity`): an empty database is created and
stamped at head, while a database at the wrong revision, without a version row, or with
missing tables/columns refuses to start. The gate is deliberately fail-closed; silent
`create_all()` drift is treated as an error.

Because the scheduler runs inside the backend process, **the backend must run as a single
replica** unless every non-primary replica sets `SCHEDULER_DISABLED=true`.

## 4. HTTP layer

Routers are registered in `main.py` after middleware:

| Prefix | Module | Responsibility |
| --- | --- | --- |
| `/api/recommend` | `api/recommend.py` | Profile → packages, dual-engine routing, persistence |
| `/api/products`, `/api/compare` | `api/products.py` | Catalog reads, admin create/update/delete, comparison |
| `/api/auth`, `/api/my/*` | `api/auth.py` | Register/login/refresh/logout, saved profiles, history, role grant |
| `/api/admin` | `api/admin.py` | Health, manual crawl trigger, crawl logs |
| `/api/admin/ingestion` | `api/ingestion.py` | Platforms, source pages, jobs, review tasks, versions, provenance |

Middleware is registered in `main.py` and executes outermost-first in the reverse of the
`add_middleware` order:

1. Security headers — `nosniff`, `X-Frame-Options: DENY`, referrer policy, a restrictive CSP,
   and HSTS only in production when enabled.
2. `RateLimiterMiddleware` — Redis Lua fixed-window counters (IP / user / day). Resolves the
   caller identity from `Authorization: Bearer`, then the `access_token` cookie, then the
   direct peer address (or `X-Forwarded-For` when the peer is a trusted proxy). Redis
   unavailability fails open with a warning.
3. CORS — explicit allowlist with credentials; a wildcard origin is rejected at import time,
   before the middleware is registered.

Authorization is permission-based: routers depend on `require_permission("crawl:read")` and
similar, never on a role name. Roles map to permission sets in `services/auth_service.py`
(`user` → self-service read/save; `admin` → the full set including `admin:grant`).

## 5. Recommendation engine

### 5.1 Inputs

`api/recommend.py` converts the request schema into the engine's `UserProfile`. Two
resolutions happen at this boundary and are easy to get wrong:

- `social_insurance` is inferred as `employee` when it is `none` but `existing_coverage`
  contains `social` — this keeps older clients behaving as before.
- `job_class` is taken explicitly, or resolved from `occupation_name`; if neither yields a
  value the request fails with `422`. Occupation class feeds a hard filter, so guessing a
  default would silently change eligibility.

### 5.2 Rule engine

`filter_candidate_pool_with_profile` issues a single joined query (`joinedload` on rules and
benefits) and evaluates, per product:

- status must be on-shelf;
- `min_age <= age <= max_age`;
- `job_class <= job_class_limit`;
- the age/type matrix in `TYPE_MATRIX` (required / optional / discouraged / forbidden);
- per-type budget admission based on the product's premium floor.

Rejections are returned with a reason code, aggregated into `not_recommended_summary` and
truncated detail (30 items) for the UI. The matrix version is `RULE_VERSION`
(`rule_engine.py`), currently `2`.

### 5.3 Scoring

`score_product` produces eight sub-scores and a total. Weights come from
`config/scoring_weights.yaml`:

- global `weights` (coverage .20, price .18, flexibility .15, waiting .10, waiver .10,
  adequacy .10, brand .10, service .07) plus a small company-preference bonus;
- per-type overrides in `type_weights` for medical, critical illness, accident, term life and
  cancer insurance.

Each dimension contributes `weight × 100` points, so a product's total is at most 100. Because
weights are type-specific, the per-dimension maxima shift per insurance type; the UI displays
the global-weight maxima (20/18/15/10/10/10/10/7). Price is the exception: the first pass
records raw premium, and `apply_price_scoring` later converts it into a within-type rank
percentile. Products without a disclosed premium receive a neutral price score and are
excluded from the ranking, so an unknown premium is never rewarded as if it were the cheapest.
Company preference does not enter `score_product` (the parameter is retained for call-site
compatibility); the only place it takes effect is a small tier bonus in
`combo_builder.tier_adjusted_score`.

`validate_scoring_weights_on_startup` warns (or fails, with `SCORING_WEIGHTS_FAIL_FAST=true`)
when the YAML is missing dimensions or does not sum to the expected total.

### 5.4 Budget and portfolios

`budget.py` computes the annual budget from income and budget ratio, then splits it across
types using the absolute tiers in `config/budget_rules.yaml`. Tiers, not the ratio alone,
decide which types are admissible. `calculate_sum_insured` derives a recommended sum insured
per type; `calculate_coverage_gaps` compares that against declared existing policies.

`combo_builder.py` defines three packages:

| Tag | Label | Budget multiplier | Strategy |
| --- | --- | --- | --- |
| `budget` | Low premium first | 0.5 | cheapest |
| `star` | Balanced | 0.8 | best score |
| `premium` | High coverage first | 1.0 | best score |

Each package fills layers in order — basic (medical, accident), core (critical illness, term
life), supplementary (cancer, annuity) — under the package budget, skipping types the matrix
forbids. Packages 2 and 3 attempt one substitution when a required type is missing, and keep
it only if the completeness score improves. Output per package: products, total premium
(min and max), budget utilisation, completeness, coverage-gap notes and per-type gaps in CNY.

### 5.5 AI layer

`ai_engine.ai_rerank_sync` builds the whitelist by taking the top
`AI_CANDIDATE_POOL_SIZE` products per type from the already-scored pool, then asks the model
for a narrative plus a structured object containing selected product IDs. The response model
is validated by `instructor`/Pydantic; IDs outside the whitelist invalidate the response. The
selected IDs are re-materialised through `build_ai_pick_package`, which re-applies the budget,
so a hallucinated or over-budget selection cannot reach the user.

Caching and quota live in `api/recommend.py`, not in the engine: the cache key is
`sha256(canonical request JSON + ENGINE_VERSION)`, quota is an atomic `INCR` keyed by user ID
or IP with a one-day expiry. Both are skipped when Redis is unreachable.

Degradation is explicit and observable: `engine_mode` is one of `rule`, `ai` or `degraded`,
and a degraded response always carries a fixed narrative plus a warning log line containing
the model and the sanitised base URL — never the API key.

## 6. Data model

23 tables, grouped by concern:

- **Catalog** — `products`, `rules`, `benefits`. `products` holds the searchable facts
  (company, type, premium range, sum-insured range, status, source URL, verification flags,
  `last_verified_at`); `rules` holds the eligibility envelope (age, job class, waiting period,
  health-notice count); `benefits` holds itemised coverage lines.
- **Ingestion** — `source_platforms`, `source_pages`, `crawl_jobs`, `crawl_runs`,
  `raw_documents`, `extraction_runs`, `product_drafts`, `product_versions`,
  `product_review_tasks`, `product_field_evidence`, `page_logs`. This is an append-only trail:
  a draft records what the extractor believed, a review task records the human decision, and a
  version records what was published and why.
- **Identity** — `users`, `roles`, `permissions`, `user_roles`, `role_permissions`,
  `refresh_tokens`, `audit_logs`.
- **User data** — `saved_profiles`, `recommendation_records`. Both are scoped to the owning
  user; recommendation records are encrypted at the field level when a key is configured.

Units are enforced by convention and tests: `sum_insured_*` is in ten-thousands of CNY (万),
while `premium_*` and `deductible` are in CNY. `test_money_unit_consistency.py` and
`test_fix_sum_insured_units.py` lock this down.

## 7. Ingestion pipeline

Stages, in execution order, with the gate that stops bad data:

1. **Discovery** (`discovery.py`) — read aggregator listing pages, extract product detail URLs,
   register crawl jobs with a per-source cap.
2. **Fetch** (`fetchers/page_fetcher.py`) — `robots.txt` check per platform (unreachable
   robots is treated as unknown, not as a block), rate-limit delay, then fetch. URL and DNS
   are validated against private/loopback ranges (`crawler/scraper.py::validate_url_for_ssrf`),
   including after redirects.
3. **Change detection** — content hash (MD5) compared with the previous document; unchanged
   pages stop here.
4. **Extraction** (`crawler/llm_extractor.py`) — LLM extraction into a draft schema, with
   field-level evidence captured for review.
5. **Validation** (`validators/`) — Pydantic whitelist validation, completeness rules, and an
   exact-match gate. Heuristic extraction results are never eligible for auto-publish.
6. **Publish** (`auto_publish.py` / `review.py`) — drafts clearing
   `AUTO_PUBLISH_CONFIDENCE`, completeness and exact-match gates publish automatically and
   write an audit entry; everything else becomes a `pending_review` task. Publishing writes
   product, rule, benefit and version rows in one transaction.
7. **Verification** (`official_verification.py`) — optional official-site existence check and
   third-party review matching. Results are annotations only; they never change availability.
8. **Lifecycle** — pages that resolve to "discontinued" take the product off-shelf; edits made
   in the admin console create a version snapshot instead of mutating history.

Scheduling (`crawler/scheduler.py`) runs discovery plus all enabled jobs every
`CRAWL_INTERVAL_MINUTES`, guarded by a process-level singleton.

## 8. Security-relevant components

| Concern | Where | Behaviour |
| --- | --- | --- |
| Password storage | `services/auth_service.py` | bcrypt |
| Session | `api/auth.py` | httpOnly cookies, access + refresh, refresh tokens hashed at rest |
| CSRF | `main.py`, `config.py` | `SameSite=Lax` + explicit CORS allowlist; no token by design |
| Rate limits | `middleware/rate_limiter.py` | Redis Lua `INCR`+`EXPIRE`, fail-open |
| Login brute force | `api/auth.py` | Attempt counters keyed by account and IP |
| SSRF | `crawler/scraper.py` | Scheme/host validation, private-range blocking, DNS re-check |
| Prompt injection | `engine/llm_safety.py` | Delimiting, instruction stripping, output schema enforcement |
| Encryption at rest | `services/crypto.py` | Fernet over profile/result JSON in recommendation records |
| Sensitive logging | `config.safe_llm_base_url` | Credentials and query strings stripped before logging |

## 9. Extending the system

- **Add a scoring dimension** — requires a new field in `ScoreDetail`, a weight in
  `scoring_weights.yaml` (global and every `type_weights` block), an update to the UI maximum
  table, and a version bump. `validate_scoring_weights_on_startup` and
  `test_stage3_recommendation.py` will catch partial changes.
- **Change eligibility policy** — edit `TYPE_MATRIX` and bump `RULE_VERSION`; historical
  results stay reproducible via `meta.rule_version`.
- **Add a crawl source** — register a `source_platform` with its robots URL and rate limit,
  then add a fetcher configuration; the SSRF and robots checks apply automatically.
- **Swap the LLM provider** — any OpenAI-compatible endpoint works via `LLM_BASE_URL`; the
  structured-output contract lives in `ai_engine.py`.

## 10. Known architectural debt

Recorded honestly, because it affects contributors:

- The `COMPANY_URLS` import inversion described in §2.
- `RECORD_RETENTION_DAYS` is configuration-only; no cleanup task exists.
- Saved-profile and recommendation-record APIs share `api/auth.py`, which has grown beyond
  authentication concerns.
- The UI has no i18n layer; Chinese strings are inline in components.
- No linter or formatter is configured for either backend or frontend; style is held by review
  and by `tsc`.
