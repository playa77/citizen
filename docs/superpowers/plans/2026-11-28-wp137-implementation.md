# WP-137 Implementation Plan

> Execute the approved proposal task by task with test-first checks. Independent
> calculator and procedural work may proceed in parallel; integrate and review
> the whole delivered state before completion.

**Goal:** Experimental own-matter Steuerrecht backend, roadmap .1–.9.
**Architecture:** Existing SDK, corpus, procedural engine, static copy and drafts.
**Tech stack:** Python/FastAPI, YAML, Decimal, PostgreSQL 16/pgvector.
**Spec:** [approved proposal](2026-11-28-wp137-proposal.md).

## Global constraints

Preserve AGENTS.md edit; no commits/pushes/publication, live inference, new
dependencies or frontend. No AGPL embedding. Human review remains deferred,
parameters proposed and copy draft. Exact years and supported regimes documented.
No additional architectural changes without specific approval.

## Review focus

- Missing dispatch must never use issue date; early receipt cannot shorten a presumption.
- Disputed/late receipt and electronic/foreign service must not receive ordinary dates.
- Unsupported tax years, tariff special regimes and missing parameters yield unavailable.
- LLM assertions cannot establish calculator confirmations or leak financial identifiers.
- Catalog metadata documents own-matter support without claiming authenticated enforcement.

## Task 1: Sources, AO procedural contracts and corpus

Files: `app/fristen/{fictions,rollover,evaluator}.py`, `app/dossier/deadlines.py`,
`app/services/{corpus,retrieval}.py`, `app/citations/`, `app/db/`, migration 023,
`modules/steuerrecht/fristen.yaml`, source records, focused tests.
Interfaces: existing FristInput/DeadlineSpec, corpus source maps and single chain.
- [x] Verify dated official AO/EStG/StBerG and source identities under paced budget.
- [x] Write/run failing tests for tax fiction, receipt safeguards, AO rollover,
  dossier facts and source identities.
- [x] Implement approved entries and guarded migration; preserve other modules.
- [x] Run focused tests and record results.

## Task 2: Pure tax calculations and parameters

Files: `modules/steuerrecht/{calculators.py,parameters/tax.yaml,intake-schema.yaml}`,
`tests/unit/test_steuerrecht_calculators.py`.
Interfaces: Calculator SDK, parameter source, explicit `CITIZEN_TAX_FACTS:` block.
- [x] Write/run failing tests for 2026 tariff boundaries/rounding, allowances,
  assessment difference, unsupported years and input provenance.
- [x] Implement source-backed pure arithmetic, bounded proposed parameters and
  allowlisted explicit confirmation extraction. No gross-to-taxable inference.
- [x] Run focused calculator tests; publish coverage and limits.

## Task 3: Module content and additive metadata

Files: remaining `modules/steuerrecht/` content, schema/catalog/validator,
static notices/disclaimer pins, API docs and content tests.
Interfaces: existing manifests, intake, dossier, drafts and static-copy schemas.
- [x] Write/run failing own-matter metadata and content contract tests.
- [x] Add optional assistance metadata, enforce tax false, populate experimental
  module, guarded drafts and minimised own-matter preparation content.
- [x] Add >=15 synthetic cases and DE/EN/de-LS copy/evaluation cases including
  actual guarded drafts; verify deterministic results without live inference.

## Task 4: Integration, records and delivery

- [x] Record D-079 accepted architecture and supporting source/coverage records.
- [x] Update capability/package versions, changelogs, roadmap and authoring docs.
- [x] Run focused and full pytest, Ruff lint/format, mypy, all-module validator,
  purpose drift and offline dossier/plain gates. Record failures/limits honestly.
- [x] Obtain fresh whole-change review; reproduce/fix material findings with tests.
- [x] Inspect final Git state; report branch, changes, verification, no commit/push.

## Execution ledger

Baseline `598f68d`; owner's AGENTS.md edit preserved. Dedicated branch
`codex/wp-137-steuerrecht`. Owner approved proposal and instructed proceeding;
no additional plan approval round is necessary. Existing environment `.venv` reused.
Source verification: one in-flight request per publisher, >=2 seconds pacing,
<=3 attempts/resource, <=10 minutes/publisher, no embeddings or ingestion.

### Implementation rulings and review

- Independent work used disjoint calculator/procedural/corpus files under the
  parallel-agents skill; root integrated module content and records. No commits.
- Initial tests failed for absent module/implementations before changes. Normal
  pytest required approved Docker access; pure focused checks also used
  `--confcutdir=tests/unit` while the manifest was being assembled. Integrated
  tests subsequently ran with the normal PostgreSQL conftest.
- Filing date uses a narrow versioned precomputed 2026 statutory date with
  explicit state/local-calendar and regime confirmations. This avoids inventing
  a new calendar SDK or duplicate calendar. EGAO transition coverage was checked
  separately; historical/advised/voluntary/special regimes remain unavailable.
- First full application run: 2,247 passed, four skipped, ten failures in
  intentionally changed module/catalog/intake/disclaimer expectations. Updated
  explicit module pins and projected only the new tax area out of the historical
  v2 golden comparison, preserving its original baseline bytes. Follow-up full
  application/database run: 2,267 passed, four skipped.
- Review found no material defects; minor observation: plain cases 16–20 reuse
  deadline fixtures. They test static rendering, while dedicated calculator
  tests carry arithmetic coverage. No live-pipeline quality claim is made.
- A later integration regression exposed that assessment differences did not
  reach the existing overall summary. Observed two failures (positive/negative
  differences), then propagated discrepancy count, absolute EUR amount and
  direction through the existing SDK fields. Equal values retain no discrepancy.
  All 47 calculator tests passed; independent review of this narrow delta found
  no material issue. This is arithmetic comparison, not illegality adjudication.
- Editable installation metadata was stale: offline no-dependency editable
  reinstall updated dist-info; a pre-existing project egg-info still shadowed it.
  Regenerated egg-info through setuptools; `get_app_version()` now reports 3.12.0.
  No dependency/runtime configuration was changed. Earlier 3.11-labelled reports
  remain only in ignored eval output; delivered reports both identify 3.12.0.

### Check limitations

- Default-target `mypy app/` stops at installed NumPy stub syntax requiring
  Python 3.12. CI's supported `--python-version 3.12` target passes all 113 app
  files. No configuration workaround was introduced.
- Bare `pytest -q` also collects pre-existing third-party package-cache tests
  beneath ignored `tmp/verification-setup/uv-cache`, producing 148 collection
  errors. The comprehensive project test command is `pytest tests/ -q -rs`;
  this includes unit, integration and offline tests without modifying discovery
  configuration or deleting user caches.
- No live inference, deployed corpus population, legal/language review or
  promotion. The PostgreSQL upgrade through 023 and store/cite/exact-retrieve
  checks are exercised; stored-row downgrade refusal has a mocked operation test,
  not a destructive database downgrade exercise.

### Final verification and handoff

`pytest tests/ -q -rs` against disposable PostgreSQL 16/pgvector through 023:
**2,292 passed, four skipped, 25 warnings**, 89.86 seconds. Includes offline,
unit and integration suites. Four existing skips: obsolete CORS field,
pre-existing GET intake exception-handling gap, two spaCy pseudonymization
checks without `de_core_news_lg`. Existing testcontainers/pytest-asyncio/bs4
deprecations and asyncpg cancellation-coroutine warnings remain; one warning
surfaces during the new module-detail test as well. No runtime changes or model
installation to suppress warnings/skips.

Ruff `check app/` and `format --check app/` passed; additional tax calculator
and test lint/format passed. `mypy app/ --python-version 3.12` passed all 113
app files. All twelve modules validate (proposed-parameter warnings expected),
purpose drift passes 67 files / 116 deny phrases, and `git diff --check` passes.

Delivered offline reports in `modules/steuerrecht/goldset/reports/` identify
core 3.12.0/module 0.1.0: dossier 20/20, actual draft annex included and all
metrics 1.0; plain 24/24 covering DE/EN/de-LS, all draft review metadata retained.
These cover deterministic preparation/rendering, not live pipeline quality.

Branch `codex/wp-137-steuerrecht`, HEAD/base `598f68d` (merged WP-136), no new
commits or pushes. Relevant files: tax module, migration 023, shared AO/corpus/
manifest/catalog additions, notices/version pins, tests and linked records.
Owner's pre-existing AGENTS.md edit is unchanged. No publication, release,
deployment, live inference or human promotion performed.

### PR publication follow-up

The owner subsequently requested: “prepare and open a pr with this session's
work.” D-079 records authorization to commit the verified WP-137 changes,
push their dedicated branch and open a PR against main, excluding the owner's
pre-existing AGENTS.md edit. Executable state and verification results are
unchanged; this follow-up adds publication authority only. Merge, release,
deployment, live inference and promotion remain unauthorized.
