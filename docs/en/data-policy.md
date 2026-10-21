# Product Data Policy

This document explains where the product catalog comes from, what the project stores, how the
source is attributed, and how to request a correction or removal. It exists because the
catalog is built from public web pages, not from a licensed data feed — that distinction
carries obligations for both maintainers and operators.

Chinese version: [`../data-policy.md`](../data-policy.md).

## 1. Principles

1. **Public pages only.** Product facts are collected from pages that are reachable without
   logging in and that the site's `robots.txt` permits fetching.
2. **No personal data.** The crawler targets product pages. It does not collect applicant,
   customer or agent information, and it does not visit account, quote or application flows.
3. **Attribute, don't republish.** Every product row keeps the URL it came from. The project
   does not republish whole pages, and it does not present third-party text as its own.
4. **Uncertain data does not ship.** Extractions below the confidence and completeness gates
   wait for human review; heuristic or fuzzy matches never auto-publish.
5. **Corrections beat arguments.** If a source says the data is wrong or should be removed,
   the default is to correct or remove it, not to defend the extraction.

## 2. What is collected

Per product, the structured fields the recommender actually needs:

- product name, insurer, insurance type;
- premium range (lower/upper bound where the page states one), sum-insured range, deductible;
- eligibility envelope: minimum and maximum age, occupation-class limit, waiting period,
  health-notice item count;
- benefit lines (name, amount, payment limit);
- the source URL, whether it is the insurer's own site or an aggregator page, and when it was
  last verified;
- optional annotations from official-site existence checks and third-party review matching.

Not collected: applicant or customer data, agent contact details, page media files, anything
behind a login, and anything a `robots.txt` disallows.

## 3. Where it comes from

Source platforms are registered in `source_platforms` and seeded by
`backend/app/data_ingestion/pipeline.py`. Each row carries its `robots_url` and a
`rate_limit_seconds` value, and the fetcher enforces both.

| Source | Role | Notes |
| --- | --- | --- |
| 慧择网 (huize.com) | Primary aggregator | Product detail pages; 10 s between requests |
| 开心保 (kaixinbao.com) | Primary aggregator | Product detail pages; 10 s between requests |
| 深蓝保 (shenlanbao.com) | Review annotation | Used to attach a third-party review link; not a product source |
| 中国平安, 中国人寿, 众安保险, 泰康在线 official sites | Cross-verification | Existence check and field comparison; 30 s (65 s for 众安, per its `Crawl-delay`) |
| 中民保险网 (zhongmin.cn) | Retired | `robots.txt` disallows crawling (`Disallow: /`); the platform row is kept but deactivated and never fetched |

The fetcher refuses a request when `robots.txt` disallows the path, and treats an unreachable
`robots.txt` as unknown rather than as permission. SSRF protection blocks loopback, private and
link-local addresses, including after redirects.

## 4. Storage and exposure

- `raw_documents` keeps the fetched HTML/text snapshot and its MD5 hash. Snapshots exist so a
  review task can show *why* an extraction produced a value, and so an unchanged page is not
  re-extracted. They are internal: no API endpoint serves them.
- Only structured fields are exposed by `/api/products`, `/api/products/{id}` and
  `/api/compare`. There is no bulk export endpoint and no full-text search over page bodies.
- Recommendation responses include `source_url`, `source_type`, `last_verified_at` and
  `data_stale`, so a user can always reach the page the facts came from.
- Raw snapshots are third-party content. No automated retention job deletes them; an operator
  who keeps them for a long time should decide their own retention period.

## 5. Attribution and freshness

- `source_type` is `official` when the URL host matches the insurer's registered homepage, and
  `aggregator` otherwise. The UI labels these differently ("官网" vs "产品页").
- `last_verified_at` records the last successful verification. Products older than
  `DATA_STALE_DAYS` (default 90) are flagged `data_stale` and shown as stale; they are not
  silently presented as current.
- When a page resolves to a discontinued or non-purchasable state, the product is taken
  off-shelf. Publishing never reactivates an off-shelf product.

## 6. Accuracy and liability

The catalog is a best-effort snapshot of public information. It can be incomplete, out of date,
or wrong — pages change, regional variants exist, and extraction is not infallible. Premiums
are the lower bound of a quoted range, not an offer. Nothing in the catalog is a quote, an
underwriting decision, or a statement by the insurer.

Always verify against the insurer's current product terms, health notice and official channels
before relying on any figure.

## 7. Correction and removal requests

If you are an insurer, a platform operator, or a user and you believe a record is inaccurate,
mis-attributed, or should not be published:

1. Open a **Data correction or takedown** issue using the repository's issue form. Include the
   product name, the affected field, and the URL of the authoritative source.
2. Do not include personal data, credentials, or confidential material in the issue.
3. A takedown request does not need to justify itself with legal argument. The maintainer will
   take the product off-shelf or delete the record while the claim is checked.

If the request itself is sensitive, use the private reporting form referenced in
[`../../SECURITY.md`](../../SECURITY.md) and state that it concerns product data.

## 8. Operator responsibilities

Running this software does not transfer any rights to third-party content. If you deploy it:

- you decide which sources are enabled, and you are responsible for complying with each
  source's terms of use in your jurisdiction;
- keep `robots.txt` enforcement and rate limits enabled — do not patch them out;
- do not republish raw snapshots or build a competing product database from them without
  permission;
- handle correction and takedown requests addressed to *your* deployment yourself; the
  upstream project cannot do it for you;
- treat product data as advisory and keep the disclaimer visible in your UI.

## 9. Licensing

The repository's MIT license covers the **code and documentation**. It does not grant rights to
third-party product descriptions, trademarks or page content that the crawler retrieves, and it
does not make the catalog a licensed data product. Insurer and platform names are used for
identification only.

## 10. How the policy is enforced

| Control | Where |
| --- | --- |
| `robots.txt` check before fetch | `data_ingestion/fetchers/page_fetcher.py` |
| Per-platform rate limit | same, using `source_platforms.rate_limit_seconds` |
| SSRF / private-network blocking | `crawler/scraper.py` |
| Schema whitelist and completeness gate | `data_ingestion/validators/` |
| Confidence + exact-match gate before auto-publish | `data_ingestion/auto_publish.py` |
| Human review for everything else | `data_ingestion/review.py`, `/api/admin/ingestion/review-tasks` |
| Off-shelf detection and version chain | `data_ingestion/pipeline.py`, `product_versions` |
| Freshness labelling | `api/recommend.py`, `products.last_verified_at` |
| Retired-source handling | `ensure_seed_sources` (`中民保险网` kept inactive) |

Changes to these controls are reviewed like any other behaviour change; see
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).
