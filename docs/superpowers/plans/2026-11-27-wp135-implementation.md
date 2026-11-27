# WP-135 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task by task.

**Goal:** Implement the approved experimental Familienrecht backend.
**Architecture:** Existing module data/SDK calculators, additive federal source mappings and a narrow FamFG calendar entry. No new service or workflow.
**Tech Stack:** Python/FastAPI, YAML, PostgreSQL 16/pgvector, Alembic.
**Spec:** [approved proposal](2026-11-27-wp135-proposal.md).

## Global Constraints

Experimental, proposed/draft review; no live inference or deployment ingestion.
Preserve AGENTS.md, existing APIs and unrelated module behavior. No commit/push.
Approved by owner: “approved. proceed.” (2026-11-27).

## Review Focus

- Unknown/urgent family procedures must not receive ordinary complaint dates.
- Birth-month transitions must not silently use today's age for past maintenance.
- Full child benefit for UVG differs from half-credit for qualified minor maintenance.
- Missing eligibility or income qualifications must not become entitlement findings.
- Third-party identifiers and child-welfare narratives must remain minimised.

### Task 1: Sources and calendar

Files: corpus/retrieval/citation mappings, models, migration 021, rollover/evaluator,
SDK/schema versions, source and integration tests, API documentation.
Interface: source keys `famfg`, `uvg`, `minuhv`; rollover `famfg_16`.
- [x] Verify dated primary statutes and publisher reuse terms; record coverage.
- [x] Write source identity, migration and calendar tests; observe missing support.
- [x] Extend existing mappings and chain; run focused tests including real PG writes.

### Task 2: Qualified maintenance arithmetic

Files: familienrecht calculators.py, parameters/maintenance.yaml, calculator tests.
Interface: SDK Calculator `family_checks`; types `minimum_maintenance`, `uvg_amount`,
`retroactive_maintenance`; `as_of` selects dated parameters; deterministic_result projection.
- [x] Test literal 2026 age bands: 48600/55800/65300 cents, half-credit12950;
  UVG full-credit25900, payment/orphan deductions, zero floor, strict refusals.
- [x] Test §1613 qualified event month, missing evidence, future/unsupported periods.
- [x] Implement pure parameter-backed arithmetic; run all targeted regressions.

### Task 3: Module and preparation content

Files: module manifest, deadline, intake schema, prompt profile, dossier, drafts,
plain copy, goldsets/reports, disclaimer pins and module changelog.
Interfaces: established module manifests, explicit service/fact/calendar contracts.
- [x] Test ordinary complaint qualification and refused urgent/unknown proceedings;
  expected month-end/weekend/local holiday dates and absent service facts.
- [x] Add guarded information-request, response-outline and UVG-preparation drafts.
- [x] Add DE/EN/de-LS copy, ≥15 synthetic cases, deterministic dossier/plain goldsets.
- [x] Run content contracts, all-module validator, offline evaluation and purpose drift.

### Task 4: Verification and handoff

Files: D-077, roadmap, catalog, TODO, authoring guide and this execution record.
- [x] Run Ruff lint/format, mypy, unit/integration suites with disposable PG16.
- [x] Fresh whole-change review; address material findings with regression tests.
- [x] Inspect final Git state; record exact checks, limits and unverified areas.

## Execution ledger

- Baseline: main/origin main db57937; branch codex/wp-135-familienrecht.
  Owner AGENTS.md edit preserved. Implementation approval covers the proposal.
- Ruling: execute inline under the user's proceed direction; no further design
  approval round or commits. Source identifier MinUhV/minuhv verified officially.

### Task results and rulings

- Task 1: observed 10 failing new source/calendar/migration regressions, then
  13 passing source/calendar and real PostgreSQL integration tests. Eight
  official snapshots fetched and operative provisions inspected; three new
  federal sources parsed locally with expected sections/amounts. No embeddings
  or deployment ingestion. Hashes and OQ-7 evidence are in the source record.
- Task 2: observed 41 failing calculator regressions before implementation,
  then 41 passes. Tests cover literal statutory age bands/credit, UVG deductions
  and zero floor, period/age/eligibility refusals, conditional §1613 month start
  and parameter-loader provenance. No live inference.
- Task 3: observed 23 failing content regressions before implementation; focused
  module/content/API/disclosure checks subsequently passed except three
  intentionally changed inherited-profile hashes. Those specific historical
  pins were retired with dedicated replacement assertions, without regenerating
  the historical baseline. Restored all original deny phrases and appended
  three family-specific phrases; no existing drift control removed.
- Offline dossier 20/20, with actual draft annexes and all aggregate metrics 1.0;
  plain 25/25 covering DE/EN/de-LS. Reports in the module identify core 3.10.0 and
  module 0.3.0. Draft/proposed review metadata remains intact.
- Initial full run: 2055 passed, two failed, four skipped, 24 warnings. Failures:
  `test_issue_term_anchors_parse_as_norms` exposed missing statute names in new
  family prompt terms; added FamFG/UhVorschG anchors. `test_same_surface`
  exposed one-sided historical-key filtering; retired keys now removed from
  both compared surfaces. Focused rerun: 71 passed. These were integration
  corrections within approved scope, not new architecture.
- Ruling: installed editable metadata still reported 3.9.0 due to stale ignored
  root egg-info shadowing the new dist-info. Reinstalled locally with existing
  dependencies, offline/no build isolation, and regenerated setuptools egg-info;
  actual package version now 3.10.0. No dependency or runtime configuration
  change. Earlier scratch eval reports were not delivered.
- Independent fresh-context code/content review found no material actionable
  findings; bounded follow-up confirmed preserved drift controls, complete
  citation anchors and narrowly retired historical prompt pins.
- Ruff app/module/new-tests lint and format pass. Mypy app with Python 3.12
  target passes all 113 app files. Default 3.11-target mypy cannot parse the
  installed NumPy 3.12 stub (`numpy/__init__.pyi:737`), matching WP-134's
  documented environment limitation. No configuration was changed to hide it.
- All 10 modules validate; purpose drift passes across 47 files/104 phrases.
  Existing unverified-parameter/copy warnings remain honest under D-071.

- Second full run: 2055 passed, two addendum-copy checks failed, four skips.
  A later spacing cleanup in the module addendum had not been copied back
  verbatim into the two canonical notices. Resynchronised those exact bodies;
  no legal meaning or acknowledged version changed within this unpublished
  package. The observed failing verbatim tests cover this correction.

- Four pre-existing skips: removed CORS field check, unknown-intake404 check,
  and two `TestNerControls` checks requiring absent `de_core_news_lg`.
  The full runs also report existing async cancellation/resource, testcontainers,
  pytest-asyncio and dependency deprecation warnings; no NER installation or
  runtime/dependency change is made for this work.
- Targeted canonical addendum/plain-pin rerun:52 passed after synchronization.
  Goldset loader audit:20 cases, no warnings. Source reuse clearance, human
  parameter/language/legal review, deployed ingestion and live-inference
  quality remain outside the completed automated scope.

## Final delivery verification

- `.venv/bin/pytest tests/unit/ tests/integration/ -q`: **2057 passed,
  four existing skips, 24 warnings in 85.33s**, using disposable
  PostgreSQL 16/pgvector migrated through 021. Final output recorded at
  `/tmp/wp135-delivery-suite.log` during this session. No failed tests remain.
- `.venv/bin/ruff check app/ modules/familienrecht/` plus new tests: pass;
  format check across 118 affected/required files: pass.
- `.venv/bin/mypy app/ --python-version 3.12`: pass, 113 app files;
  default 3.11-target command has the documented installed NumPy stub limitation.
- All-module validator: 10 modules, zero errors; goldset loader audit 20 cases,
  no warnings; purpose drift 47 files/104 phrases passes; `git diff --check` passes.
- Saved dossier report: 20/20 schema-valid, all deadline/checklist/chronology
  metrics 1.0, actual draft annexes included. Saved plain report: 25/25, DE/EN/de-LS.
  Both delivered reports identify core 3.10.0 and family module 0.3.0; `git_sha`
  records baseline db57937, because these checks ran on the uncommitted WP-135
  working tree. They are deterministic gates, not live-quality evaluations.
- Fresh review and bounded integration-fix follow-up found no material
  actionable issues. The final notice synchronization was covered by observed
  failing-then-passing verbatim tests and the complete passing suite.
- Branch `codex/wp-135-familienrecht` is based on main/origin main db57937,
  fetched at task start. No new commit, upstream branch, push or publication.
  The owner's pre-existing AGENTS.md edit is preserved and excluded from WP-135.
- Completed scope: approved experimental backend package, including qualified
  refusals and recorded limitations. Human review/promotion, live inference,
  deployed corpus population, GUI/combined acceptance and OQ-7 reuse clearance
  remain explicitly unverified/outside this package. No additional work is
  needed to meet its bounded automated implementation acceptance.


## Publication follow-up

The owner requested opening a PR with this session's work, authorizing a
WP-135 commit, branch push and PR against main. D-077 records the scoped
supersession of the earlier implementation-only publication boundary.
Origin was refreshed before publication; main remains at db57937. The owner’s
pre-existing AGENTS.md edit is excluded. The tested implementation is unchanged;
only the matching publication authority/execution notes were added.
