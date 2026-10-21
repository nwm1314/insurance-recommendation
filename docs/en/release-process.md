# Maintenance and Release Process

The process below is sized for a single maintainer with occasional contributors. It uses
GitHub's native features only — no release bot, no changelog generator, no deployment
automation. Every step is executable by hand in a few minutes.

## 1. Branch model

`master` is the trunk, the default branch, and the branch releases are cut from.

```
issue → branch (fix/… or feat/…) → pull request → review → merge to master → tag → release
```

- `develop` still exists in the repository but is fully merged into `master` and is not used
  for new work. Do not branch from it.
- Feature branches are short-lived and deleted after merge.
- `master` must stay releasable: a merge that breaks the test suites is reverted rather than
  left red while the next change lands.

## 2. Versioning

[Semantic Versioning 2.0.0](https://semver.org/) with the standard pre-1.0 caveat:

| Change | Version bump | Example |
| --- | --- | --- |
| Incompatible API, schema, or response-shape change | minor while `0.x` | `0.1.0 → 0.2.0` |
| Backward-compatible feature | minor while `0.x` | `0.1.0 → 0.2.0` |
| Backward-compatible fix, docs, dependency patch | patch | `0.1.0 → 0.1.1` |
| Security fix | patch, plus a GitHub Security Advisory | `0.1.0 → 0.1.1` |

While the major version is `0`, minor versions may include breaking changes; the release notes
must say so explicitly under **Breaking changes**. Once `1.0.0` is reached, the usual SemVer
rules apply.

Engine-internal versions are **independent** of the release version and must not be confused
with it:

- `ENGINE_VERSION` in `backend/app/config.py` — response shape / engine semantics
- `RULE_VERSION` in `backend/app/engine/rule_engine.py` — the age/type matrix
- `version` in `backend/config/scoring_weights.yaml` — scoring weights

A release usually leaves these alone. A change to them is a compatibility signal for stored
recommendation results, not a marketing version.

## 3. What a release touches

1. `CHANGELOG.md` — a new section for the version, Keep a Changelog format.
2. `frontend/package.json` and `frontend/package-lock.json` — the `version` field (the package
   is private, so this is only for traceability).
3. `backend/main.py` — the FastAPI `version` string and the root response.
4. An annotated Git tag `vX.Y.Z`.
5. A GitHub Release with English notes.

`README.md` / `README.en.md` are updated only when the release changes documented behaviour.

## 4. Release gates

Run these before tagging. Record the result of each; a skipped gate is `BLOCKED`, not `PASS`.

```bash
# 1. Backend suite
./backend/venv/Scripts/python.exe -m pytest backend/tests -q     # Windows
backend/venv/bin/python -m pytest backend/tests -q               # macOS / Linux

# 2. Frontend type check and build
cd frontend && npm run build

# 3. End-to-end (ports must be free; offset them if not)
cd frontend && npx playwright test

# 4. Migration parity
cd backend && alembic heads          # exactly one head
```

Additional pre-tag checks:

- [ ] Working tree clean; nothing untracked that belongs in the release
- [ ] Version strings agree (`package.json`, `package-lock.json`, FastAPI `version`, changelog)
- [ ] `CHANGELOG.md` describes only what is actually in the tree — no planned features
- [ ] Links added in this release resolve (README, `docs/en/*`, `CONTRIBUTING.md`,
      `SECURITY.md`, templates)
- [ ] No workflow triggers a deployment on tag or release (verify
      `.github/workflows/*.yml` has no `deploy`, `release`, or registry push step)
- [ ] CI on `master` is green, or every failure is pre-existing, explained, and unrelated
- [ ] The private vulnerability reporting channel is enabled and reachable

If a gate fails for reasons unrelated to the release, say so in the release notes and in the
PR/issue trail. Do not describe an unrun test as passing.

## 5. Cutting a release

```bash
# from a clean master that matches origin
git checkout master
git pull origin master

# bump versions and changelog, then commit
git add CHANGELOG.md frontend/package.json frontend/package-lock.json backend/main.py
git commit -m "chore(release): v0.2.0"

# annotated tag on the release commit
git tag -a v0.2.0 -m "v0.2.0"
git push origin master
git push origin v0.2.0
```

Publish the GitHub Release with English notes:

```bash
gh release create v0.2.0 \
  --title "v0.2.0" \
  --notes-file v0.2.0-notes.md \
  --verify-tag
```

Release notes structure:

```markdown
## Highlights
## Added
## Changed
## Fixed
## Security
## Breaking changes
## Known limitations
## Verification
## Upgrade notes
```

`## Verification` lists the commands that were run and their outcomes. `## Upgrade notes`
mentions migrations, new required environment variables and anything an operator must do.

## 6. Post-release verification

- The tag points at the release commit: `git rev-parse v0.2.0^{commit}` equals the commit the
  release page shows.
- The source archive from the release page builds: `docker compose build` succeeds from a
  clean clone of that tag.
- `CHANGELOG.md` on `master` matches the published notes.
- No deployment happened as a side effect. Publishing a release is not a deployment; production
  upgrade remains a manual, documented operation
  ([deployment.md](deployment.md)).

## 7. Hotfixes

For a defect in a released version:

1. Branch from the tag: `git checkout -b fix/short-name v0.2.0`.
2. Fix, add a regression test, run the gates from section 4.
3. Merge to `master` (fast-forward or merge commit), then tag the patch on the merge commit.
4. Release notes: state the affected versions and the fix.

There is no long-term support branch. Only the latest release line receives fixes.

## 8. Security releases

Follow [SECURITY.md](../../SECURITY.md):

1. Triage in the private advisory.
2. Fix on a private fork or a local branch that is not pushed to a public remote.
3. Validate with the same gates plus a targeted check.
4. Tag the patch, publish the release, then publish the advisory with credit and mitigation.
5. If operators must act (rotate a key, change configuration), put that in the release notes
   and the advisory, not only in the changelog.

## 9. Issue and PR hygiene

- One issue per problem. Labels: `bug`, `enhancement`, `documentation`, `question`,
  `good first issue`, `help wanted`.
- A PR that changes behaviour without a test is sent back.
- A PR that changes eligibility, weights or the AI boundary needs a stated reason and a version
  bump for the relevant engine constant.
- Stale issues are closed with a reason, not silently. Reopening is fine.
- Merged branches are deleted; history on `master` is not rewritten.

## 10. Deliberately not automated (yet)

- No semantic-release or changelog generator: with a handful of releases per year, hand-written
  notes are clearer and cannot misclassify a breaking change.
- No release workflow: building multi-arch images requires a registry decision and credentials
  that do not belong in a public repo by default.
- No automatic deployment: production upgrades stay manual and gated, per
  [deployment.md](deployment.md).
- No dependency-update bot policy yet; dependency bumps are handled as normal PRs.

Revisit these when release frequency or contributor count makes the manual path a bottleneck.
