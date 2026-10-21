# Security Policy

This project handles personal data — age, income, occupation, health declarations and saved
recommendation results. Security reports are treated seriously, and private disclosure is the
only acceptable first step.

## Supported versions

| Version | Supported |
| --- | --- |
| `0.1.x` | Yes — current public release line |
| anything else | No — pre-release snapshots and unreleased branches receive no fixes |

Only the latest patch of the current minor line is maintained. Security fixes are released as
a patch version and documented in [`CHANGELOG.md`](CHANGELOG.md).

## Reporting a vulnerability

**Do not open a public issue, pull request, or discussion for a suspected vulnerability.**

Use GitHub's private vulnerability reporting for this repository:

**<https://github.com/nwm1314/insurance-recommendation/security/advisories/new>**

That form opens a private advisory thread visible only to you and the repository maintainers.
If the form is unavailable to you, open a public issue that says only *"I would like to report a
security issue privately"* and contains no technical detail, no payload and no affected URL;
the maintainer will arrange a private channel before you share anything.

Please do not send reports to any address, account or form that is not listed in this file.

## What to include

A useful report contains:

- affected version, tag or commit SHA;
- the component (API, engine, ingestion, authentication, frontend, deployment config);
- a description of the issue and the security property it breaks (confidentiality, integrity,
  availability, authorization boundary);
- reproduction steps or a minimal proof of concept, if you have one;
- the impact you believe it has, and any preconditions (authentication required, specific
  configuration, network position);
- whether the issue is already public anywhere.

You do not need a working exploit to report a design flaw. A clear description of the
boundary that can be crossed is enough.

## What not to send

- **No real user data.** Do not attach production database dumps, recommendation records,
  saved profiles or health information. Use synthetic data.
- **No live credentials.** Redact API keys, `JWT_SECRET_KEY`, `RECORD_ENCRYPTION_KEY`, session
  cookies and database passwords from logs and screenshots.
- **No third-party data.** Do not include dumped content from insurer or aggregator sites.
- **No unsolicited access.** Do not test against instances you do not own. A local deployment
  built from this repository is the right target.
- **No public disclosure before coordination.** Give the maintainer a chance to ship a fix.

## Scope

In scope:

- the backend application (`backend/app/`), including the recommendation engine, ingestion
  pipeline, authentication and rate limiting;
- the frontend application (`frontend/src/`);
- default deployment configuration (`docker-compose.yml`, `backend/Dockerfile`,
  `frontend/nginx.conf`, `.env.example`);
- dependencies, where the vulnerability is reachable through this project's usage.

Out of scope:

- third-party insurer, broker or aggregator websites, including their availability, terms or
  data accuracy;
- the accuracy or completeness of crawled product data (report that as a data-quality issue,
  not a vulnerability);
- findings that require an already-compromised host, a modified image, or a debug configuration
  the documentation tells you not to use in production (for example `APP_ENV=development`
  exposed to the internet, or `CORS_ALLOW_ORIGINS=*` with credentials, which is rejected at
  startup anyway);
- missing hardening headers, TLS configuration or WAF rules at the reverse proxy, which is
  outside this repository;
- volumetric denial of service, spam, or social engineering;
- automated scanner output without a demonstrated, project-specific impact.

## How reports are handled

This is a single-maintainer project. The process is intentionally short, and no response-time
guarantee is offered:

1. **Acknowledge** the private report and ask for anything missing.
2. **Triage** — confirm the issue, decide severity, and agree with you on a disclosure window.
3. **Fix** on a private branch, with a regression test where the behaviour is testable.
4. **Validate** — run the backend suite, the frontend build and the end-to-end suite, plus a
   targeted check of the reported path.
5. **Release** a patch version, publish a GitHub Security Advisory, and credit you unless you
   ask not to be named.

If a report turns out not to be a vulnerability, you will get the reasoning rather than a
silent close.

## Disclosure principles

- Reporters get credit in the advisory by default; anonymity is respected on request.
- Details are published after a fix is available, not before.
- If a fix cannot be shipped quickly, the advisory may be published with mitigations first, so
  operators can protect their deployments.
- There is no bug bounty programme. This project cannot pay for reports, and nothing here
  should be read as an offer of compensation.
- This project holds no security certification (no SOC 2, ISO 27001, or similar). Do not
  describe it as certified.

## For operators

The security posture depends on configuration as much as on code. Before exposing an instance,
follow the checklist in [`docs/en/deployment.md`](docs/en/deployment.md), in particular:

- `APP_ENV=production`, `COOKIE_SECURE=true`, HTTPS at the proxy;
- a real `JWT_SECRET_KEY` and `POSTGRES_PASSWORD`;
- `RECORD_ENCRYPTION_KEY` set and proven present in the container environment;
- an exact `CORS_ALLOW_ORIGINS` allowlist;
- `TRUSTED_PROXIES` limited to the proxies actually in the request path.

Leaving `RECORD_ENCRYPTION_KEY` empty stores health declarations in plaintext. The application
logs a warning (an error in production) but does not refuse to start, so this is an operator
decision, not something the code can enforce for you.
