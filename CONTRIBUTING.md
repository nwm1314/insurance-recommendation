# Contributing

Thanks for considering a contribution. This is a small, single-maintainer project, so the
process is deliberately light: one issue, one focused branch, one reviewable pull request.

Chinese-language issues and pull requests are welcome. You can write in Chinese or English;
maintainers will reply in the language you used.

## Ways to contribute

| Contribution | Where to start |
| --- | --- |
| Bug report | [Open a bug report](https://github.com/nwm1314/insurance-recommendation/issues/new?template=bug_report.yml) |
| Feature idea | [Open a feature request](https://github.com/nwm1314/insurance-recommendation/issues/new?template=feature_request.yml) |
| Documentation fix | Small PRs are fine without a prior issue |
| Test coverage | Add a failing case first, then fix or document the behaviour |
| Insurance product rules | Read "Contributing product data" below before adding rules |
| Security issue | **Never a public issue** — see [SECURITY.md](SECURITY.md) |

Before opening an issue, search the existing ones. Duplicates are closed with a link, which is
not a judgement on the report.

For anything larger than a bug fix — a new scoring dimension, a new pipeline stage, a schema
change — open an issue first and describe the approach. It is much easier to agree on a design
before writing code than to rework a large PR.

## Reporting a bug

Use the bug report template. A useful report has:

- what you expected to happen and what happened instead;
- exact reproduction steps, including the questionnaire answers or API payload;
- environment: OS, Python and Node versions, whether you run Compose or manually, whether AI
  mode was enabled;
- relevant log lines **with secrets removed** (no API keys, cookies, tokens or health data);
- the command you ran for tests, if the bug appeared in a test run.

Screenshots help for UI issues. Redact personal data first.

## Requesting a feature

Describe the problem before the solution: who is affected, what decision the current behaviour
makes wrong, and what would be different if it were fixed. If you can, say whether the change
belongs in the rule engine, the scorer, the ingestion pipeline or the UI — the layers are
separated on purpose and a change in the wrong layer will be sent back.

## Development setup

Full instructions, including troubleshooting, are in [`docs/en/development.md`](docs/en/development.md).
The short version:

```bash
# backend
cd backend
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
mkdir -p ../data
alembic upgrade head
python scripts/seed.py
python -m uvicorn backend.main:app --reload --port 8000

# frontend
cd frontend
npm install
npm run dev
```

## Branches and commits

- Branch from `master`. Name the branch after the intent:
  `fix/empty-pool-crash`, `feat/scoring-region`, `docs/en-architecture`.
- One logical change per branch. Unrelated cleanups belong in their own PR.
- Commit messages follow `type(scope): summary` where `type` is one of `feat`, `fix`, `docs`,
  `test`, `refactor`, `chore`. Keep the summary in the imperative mood and under ~72 characters.
- Reference the issue in the body (`Closes #123`).
- Do not rewrite published history on `master`.

## Pull requests

A pull request should answer four questions in its description:

1. **What changed and why** — link the issue if there is one.
2. **How it was tested** — the commands you actually ran, with their results.
3. **What could break** — the affected behaviour, any migration, any configuration change.
4. **How to roll it back** — usually "revert the commit", but say so explicitly for migrations.

Checklist before requesting review:

- [ ] `pytest backend/tests -q` passes (or the failures are explained and pre-existing)
- [ ] `cd frontend && npm run build` passes when frontend code changed
- [ ] `cd frontend && npx playwright test` passes when a user-visible flow changed
- [ ] New behaviour has a test; a bug fix has a test that fails without the fix
- [ ] No secrets, keys, tokens, personal data or real user records in the diff
- [ ] No unrelated formatting churn or drive-by refactors
- [ ] Documentation updated when behaviour, configuration or commands changed
- [ ] If `TYPE_MATRIX` or scoring weights changed: the corresponding version was bumped

Draft pull requests are welcome for early feedback — mark them as draft and say what is
missing.

## Code style and tests

There is no configured linter or formatter. Match the file you are editing:

- Python: 4-space indentation, type hints where the surrounding module uses them, docstrings
  that explain *why* a guard exists (the existing backend modules do this in Chinese — follow
  the local convention rather than translating them).
- TypeScript/React: function components, hooks, explicit prop types, Ant Design components.
- Keep the engine free of FastAPI imports; keep the API layer free of scoring logic.

Tests live in `backend/tests/` and `frontend/tests/e2e/`. Backend tests must not depend on a
running Redis (the shared fixtures install an in-process fake) and must not write to
`data/insurance.db` (each module points `DATABASE_URL` at a temporary file before importing the
app). If your test needs a database fixture, follow the pattern in the file you are extending.

## Contributing documentation

Documentation is part of the product, not an afterthought:

- `README.md` (Chinese) and `README.en.md` (English) must stay in sync on facts: commands,
  features, limitations and configuration names. If you change one, change the other or say in
  the PR why the change is language-specific.
- `docs/` holds Chinese operational runbooks; `docs/en/` holds the English equivalents.
  Behaviour must never be described differently between them.
- Commands in documentation must be executed before being committed. A command that has not
  been run does not go in a guide.
- Use placeholders (`<your-key>`, `example.com`) in configuration examples, never real values.

## Contributing product data and rules

This is the area with the highest risk of causing harm, so the rules are stricter:

- **Only public sources.** Product facts must come from the insurer's official site or a public
  aggregator page that permits crawling under its `robots.txt`.
- **Never bypass the pipeline by hand.** Adding products directly to the database in a
  deployment skips validation, evidence capture and review. Contribute the source page instead,
  or use the admin console so a version record is written.
- **Rules need a source.** A change to `rule_engine.py`'s `TYPE_MATRIX` or to budget tiers must
  cite the policy or product term that justifies it. "It seems reasonable" is not a source.
- **Do not invent numbers.** Premium ranges, sum-insured limits, waiting periods and health
  notice counts must be traceable to a page you can link.
- **Bump versions.** `RULE_VERSION` for matrix semantics, `scoring_weights.yaml`'s `version`
  for weights, `ENGINE_VERSION` when response shape changes. Historical results depend on these
  values.
- **Demo data is not product data.** The seed catalog exists for local demos and E2E only; do
  not present it as a verified product pool.

## Review and merge

What a maintainer checks, in order:

1. Does it do what the description says, in the right layer?
2. Is the behaviour covered by a test, and does the existing suite still pass?
3. Does it change eligibility, pricing display, or the AI boundary? Those need explicit
   justification and a version bump.
4. Are secrets, personal data and unrelated changes absent?
5. Is the documentation consistent in both languages?

Expect review comments on scope, not only on correctness. A PR may be asked to split. Once
approved, the maintainer merges with a merge commit (not squash) so that individual commits and
their reasoning stay reviewable; the branch is deleted afterwards.

No response-time guarantee is offered. If a PR sits without a response for more than two weeks,
a polite ping on the PR is appropriate.

## Release process

Versions, changelog entries, tags and releases are described in
[`docs/en/release-process.md`](docs/en/release-process.md). Contributors do not need to bump the
version or edit `CHANGELOG.md`; the maintainer does that at release time, using merged PR titles
as input.

## License

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE),
the same terms as the project. Do not contribute code you cannot license this way, and do not
copy code from projects with incompatible licenses.
