## What changed

<!-- One or two sentences. Link the issue if there is one: Closes #123 -->

## Why

<!-- The problem this solves. For rule or scoring changes, cite the product term or policy that justifies it. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Rule / scoring / budget change
- [ ] Ingestion or catalog change
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Tests or CI
- [ ] Deployment or configuration

## How it was tested

<!-- Paste the commands you actually ran and their results. Do not claim a pass you did not observe. -->

```bash
# backend
pytest backend/tests -q

# frontend
cd frontend && npm run build

# end-to-end (only when a user-visible flow changed)
cd frontend && npx playwright test
```

## Risk

<!-- What could break, for whom. Mention migrations, configuration changes, and anything that changes eligibility or displayed prices. -->

- Affected behaviour:
- Migration required: yes / no
- Configuration change: yes / no
- Engine/rule/scoring version bumped: yes / no / not applicable

## Rollback

<!-- Usually "revert this commit". Say so explicitly for migrations or data changes. -->

## Checklist

- [ ] The change is limited to one logical concern
- [ ] New behaviour has a test; a bug fix has a test that fails without it
- [ ] `pytest backend/tests -q` passes, or the failures are pre-existing and explained above
- [ ] `npm run build` passes when frontend code changed
- [ ] `npx playwright test` passes when a user-visible flow changed
- [ ] No secrets, credentials, tokens, personal data or real user records in the diff
- [ ] Documentation updated (both `README.md` and `README.en.md` when facts changed)
- [ ] Version constants bumped when rules, weights or response shape changed
