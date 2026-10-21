# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the major version
is `0`, minor releases may contain breaking changes; they are called out explicitly.

## [Unreleased]

Nothing yet.

## [0.1.0] - 2026-10-21

First public release. The project had no tags or GitHub Releases before this version, so this
entry describes the initial state of the codebase rather than a diff against a previous
release.

### Added

**Recommendation engine**

- Seven-dimension user profile with social-insurance status, free-text occupation resolution
  (risk class 1–6) and declared existing policies.
- Hard eligibility filtering ("one-vote veto") on product status, age range, occupation class,
  the age/type policy matrix and per-type budget admission. Hard rules run before any model and
  cannot be overridden.
- Eight-dimension, insurance-type-specific scoring (coverage, price, flexibility, waiting
  period, waiver, sum-insured adequacy, brand, service) driven by
  `backend/config/scoring_weights.yaml`, with premium scored as a within-type rank percentile
  and undisclosed premiums scored neutrally.
- Budget-aware portfolio construction: three packages at 0.5/0.8/1.0 budget multipliers,
  layered into basic/core/supplementary, with one substitution when a required type is missing
  and per-type coverage-gap output in CNY.
- Constrained AI layer: the LLM re-ranks a closed per-type candidate list, returns product IDs
  validated against that list, and its selection is re-materialised through the budget checks.
  Hard rules and the budget ceiling are never delegated to the model.
- Deterministic degradation: missing key, provider error, timeout, invalid response or
  exhausted daily quota all return a complete rule-based answer with `engine_mode: "degraded"`.
- Reproducibility metadata in every response (`engine_version`, `rule_version`,
  `scoring_version`, `scoring_weights_hash`).
- Explainability: per-product score breakdown, recommendation reasons, rejection summary with
  reason codes, and hard-rule summary.

**Product data pipeline**

- Aggregator-first discovery and crawling, with `robots.txt` checks, per-platform rate limits,
  and SSRF protection (private/loopback blocking with DNS re-validation).
- LLM extraction with field-level evidence, Pydantic whitelist validation, an exact-match gate,
  and confidence/completeness-gated auto-publish that writes an audit entry.
- Human review queue, product version chain with rollback, and provenance per field.
- Official-site cross-verification and third-party review matching, recorded as annotations
  only.
- Freshness tracking (`last_verified_at`, stale flag after 90 days by default) and automatic
  off-shelf detection.

**Platform**

- FastAPI backend with routers for recommendations, catalog, comparison, auth, self-service
  profiles/history, admin and ingestion.
- React 18 + TypeScript + Ant Design frontend: questionnaire, result page with comparison,
  account page, and admin console for products, crawling, review tasks and audit logs;
  responsive down to 320 px.
- Email/password authentication with httpOnly cookies, access/refresh tokens and permission-
  based RBAC (`user`, `admin`). First admin bootstrapped from environment variables,
  idempotently, with an audit record.
- Redis-backed fixed-window rate limiting (atomic Lua), AI daily quota and narrative cache, all
  failing open with a warning.
- Docker Compose stack (PostgreSQL 16, Redis 7, backend, Nginx frontend) with the frontend
  published on loopback only; Alembic migration chain with a fail-closed startup schema gate.

**Security**

- Fernet encryption of saved recommendation records (profile/result, including health
  disclosures) when `RECORD_ENCRYPTION_KEY` is set; explicit plaintext warning when it is not,
  escalated to an error under `APP_ENV=production`.
- Login brute-force protection, explicit CORS allowlist (wildcards rejected with credentials),
  security response headers, HSTS in production, trusted-proxy handling for
  `X-Forwarded-For`, and prompt-injection hardening on both LLM surfaces.
- Redaction of credentials from LLM endpoint logging.

**Documentation and community**

- `README.en.md`: full English documentation covering architecture, pipeline, configuration,
  testing, security, limitations and roadmap, cross-linked with the Chinese README.
- `docs/en/architecture.md`, `docs/en/development.md`, `docs/en/deployment.md`,
  `docs/en/release-process.md`.
- `CONTRIBUTING.md`, `SECURITY.md` (with GitHub private vulnerability reporting enabled),
  `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), issue forms for bugs and feature requests,
  and a pull request template.

**Tests**

- 300+ backend tests covering eligibility boundaries, persona scenarios, scoring and money-unit
  consistency, AI whitelist and fallback, prompt-injection hardening, SSRF and robots handling,
  review workflow and versioning, freshness, auth/RBAC, rate limiting, record encryption,
  schema-migration parity and Compose policy.
- 37 Playwright end-to-end tests over a real backend and Vite dev server, including mobile
  viewports at 320 px and 375 px.

### Changed

- Package names for the three portfolios are neutral and functional
  (low premium first / balanced / high coverage first) instead of implying that a higher
  premium is better.
- Version strings aligned to `0.1.0` in `backend/main.py`, `frontend/package.json` and the
  lockfile. `ENGINE_VERSION` (1.1.0), `RULE_VERSION` (2) and the scoring-weights version (2)
  remain independent engine-level identifiers.
- README seed command corrected to `python backend/scripts/seed.py`, which matches the
  container working directory (`/srv`).
- `docs/docker-deployment.md` no longer references a non-existent `v0.3.0` tag, and the staging
  branch advice now matches the repository (trunk is `master`; `develop` is fully merged).

### Fixed

- SQLite databases now create their parent directory before the engine connects, so
  `alembic upgrade head` and `scripts/seed.py` work on a fresh clone, where `data/` does not
  exist because it is git-ignored. This was also the cause of the failing E2E workflow on CI,
  which runs from a clean checkout.

### Security

- No published advisories at the time of release. Private vulnerability reporting is enabled
  at <https://github.com/nwm1314/insurance-recommendation/security/advisories/new>.

### Known limitations

- Premiums are the lower bound of a quoted range; no binding quote, real-time underwriting or
  purchase flow is provided.
- No regional (province/city) eligibility dimension.
- Chinese mainland product catalog and Chinese-language UI; no i18n layer.
- AI mode depends on an external OpenAI-compatible endpoint; quota and latency apply.
- Demo catalog is for local/E2E use only; production pools must be built from reviewed crawl
  data, so a fresh production deployment starts with an empty pool.
- `RECORD_RETENTION_DAYS` is reserved; no retention job runs.
- Backend must run as a single replica unless non-primary replicas set
  `SCHEDULER_DISABLED=true`.
- No linter or formatter is configured.
- `COMPANY_URLS` is imported from the seed script by the recommendation API — a known layering
  inversion left in place for this release.

### Verification

Executed on the release commit before tagging:

| Gate | Command | Result |
| --- | --- | --- |
| Backend tests | `pytest backend/tests -q` | 309 passed, 1 skipped |
| Frontend build + type check | `npm run build` | pass |
| End-to-end | `npx playwright test` (ports 3200/8200) | 37 passed |
| Migration heads | `alembic heads` | single head `20260914_0002` |
| Compose deployment | not executed in this environment | BLOCKED — no Docker daemon available |

[Unreleased]: https://github.com/nwm1314/insurance-recommendation/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nwm1314/insurance-recommendation/releases/tag/v0.1.0
