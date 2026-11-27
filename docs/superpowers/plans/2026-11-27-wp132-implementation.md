# WP-132 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for shared implementation and superpowers:dispatching-parallel-agents for independent focused tasks.

**Goal:** Implement experimental employee-side Arbeitsrecht 0.2.0.
**Architecture:** Extend existing corpus/deadline contracts as approved in D-074. Keep employment rules in module data and SDK calculators.
**Tech Stack:** Python/FastAPI, YAML, PostgreSQL 16/pgvector, existing development environment.
**Spec:** [approved proposal](2026-11-27-wp132-proposal.md).

## Global constraints

No new dependency/service/frontend, no live inference or deployment ingestion,
no commit/push. Preserve AGENTS.md. Keep draft/proposed review metadata and
explicit session scope. Core 3.7.0/module API 3.5, module 0.2.0.

## Review focus

- Missing receipt/knowledge must not borrow dates from another fact.
- Special dismissal consent/unknown qualifications must not yield reassuring results.
- Date thresholds, holiday rollover and incomplete years require boundary tests.
- Expired/future parameters and unsupported regimes must refuse arithmetic.
- Draft placeholders, critical warnings and source identity must survive rendering.

## Task 1: Source evidence and shared extensions

Files: app/fristen/{specs,evaluator}.py, app/dossier/deadlines.py,
app/services/{corpus,retrieval}.py, app/db/models.py, alembic/versions/018_employment_sources.py,
tests/unit/test_employment_deadlines.py, tests/unit/test_arbeitsrecht_corpus.py.
Interface: FristInput.kenntnis_datum and chronology facts accept explicit ISO knowledge dates;
kenntnis specs use the qualified explicit-event path. Existing paths unchanged.
- [x] Write/run failing tests for knowledge-date isolation and corpus identities/storage.
- [x] Enable knowledge trigger and six new statute sources, existing KSchG/BUrlG adapters.
- [x] Verify focused tests and dated official source evidence.

## Task 2: Deterministic employment calculators

Files: modules/arbeitsrecht/calculators.py, parameters/*.yaml,
tests/unit/test_arbeitsrecht_calculators.py.
Interface: process_extraction(extraction, param_overrides) produces existing calculation entries;
load_parameters(extraction, source) returns rows and a legal snapshot; CALCULATORS exports SDK tuple.
Types: notice, severance, leave, leave_compensation, minimum_wage; money in integer cents.
- [x] Write/run failing tests for notice thresholds, severance rounding, leave fractions,
  compensation, minimum wage validity and missing qualifications.
- [x] Implement pure parameter-backed calculations with provisional/unavailable statuses.
- [x] Run focused tests including unsupported regimes and invalid types.

## Task 3: Module content and synthetic acceptance fixtures

Files: modules/arbeitsrecht/{module,intake-schema,fristen,dossier,corpus}.yaml,
copy/{de,en,de-LS}/plain.yaml, prompts/profile.yaml, documents/templates.yaml,
DISCLAIMER_ADDENDUM.md, compliance/deny-phrases.json, goldset/*, README.md, CHANGELOG.md.
Interface: critical receipt rule ar_kuendigungsschutz; knowledge rule ar_arbeitsuchend_kurz;
backwards event rule ar_arbeitsuchend_lang. Explicit qualifications select branches.
- [x] Supply guarded drafts, intake/dossier, translated static copy and >=15 synthetic cases.
- [x] Verify module validation, critical banner, draft guards and dossier/plain reports.

## Task 4: Integration, versions and final verification

Files: API_DOCUMENTATION.md, docs/MODULE-AUTHORING.md, docs/module-catalog.md,
TODO.md, docs/roadmap-v3.0.0.md, DISCLAIMER_{DE,EN}.md, app/plain/core/*.yaml,
app/core/config.py, app/services/prompts.py, app/modules/sdk.py, pyproject.toml, test pins.
- [x] Align core/API, disclaimer and prompt versions with delivered behavior.
- [x] Run ruff lint/format, mypy, purpose drift, all-module validation, offline evaluations,
  full unit/integration tests and relevant offline tests using disposable PostgreSQL.
- [x] Review full diff, correct material findings and repeat invalidated checks.
- [x] Record results/limitations and inspect Git; leave changes uncommitted.

## Execution record

Baseline 1aaf606; owner AGENTS.md modification preserved. Approved proposal is binding.
No separate approval round: owner explicitly instructed execution after approving scope.


### Findings and supporting corrections

- Failing tests first demonstrated missing knowledge support, unsupported source
  types/storage and absent calculators. Canonical short statute names were also
  pinned after a failing test showed official long HTML titles would break lookup.
- Independent review found inclusive employment periods were completed a day early
  when calendar months clamp. Added literal regressions for Jan31/Feb27,
  Mar31/Sep29, Aug31/Feb28 and leap-day residual years; corrected waiting periods,
  severance thresholds and the last probation day. All affected calculator tests
  passed after the correction.
- Registration reminders must survive a dismissal/contract/agreement document
  label. Confirmed qualification gates may replace a single-document selector;
  unqualified selector-free rules remain rejected. Combined-dismissal regression
  verifies both the action deadline and the separate knowledge-based reminder.
- Legacy profile-less/stub test inputs now use the still-profile-less
  `vertragsrecht` peer. Historical WP-93 comparisons project out only the new
  employment keywords, source scope and BGB tagging while retaining other pins;
  dedicated tests cover those new surfaces. Four offline fixtures still assumed
  Mietrecht had no profile after WP-131; their profile-less test input was stale,
  so it was changed to the same remaining peer. No production preparation/privacy
  behavior was relaxed to pass tests.
- Refreshed existing editable package metadata without dependencies or network;
  source-tree egg-info had shadowed installed 3.7.0 metadata with 3.6.0. Final
  saved reports identify effective core 3.7.0 and include the real draft annex.
- Independent final-delta review reported no remaining important defects after
  these changes (inspection only, not an additional test run).


### Final verification and handoff

Tested on Python 3.12 with the existing development environment and disposable
PostgreSQL 16/pgvector, based on `1aaf606` plus the uncommitted WP-132 working tree.
No production database, real documents, live inference or embedding calls used.

- `pytest tests/unit/ tests/integration/ tests/offline/ -q`: **1,835 passed,
  4 skipped**, 21 warnings, 80.65 seconds. Skips: removed CORS-setting test,
  pre-existing unknown-intake error-route test and two unavailable German spaCy
  NER-model controls. Existing testcontainers/lxml deprecations and two async
  cancellation warnings remain; no test failure remains.
- Final official-source inspection identified the MuSchG directory as
  `muschg_2018` while retaining runtime key `muschg`. Watched its corrected
  literal mapping test fail before the change, then reran all affected corpus,
  citation/MCP and corpus integration checks: **42 passed**, one deprecation
  warning. This is the only production delta after the complete suite above.
- Ruff `app/` lint and format pass; new module calculator/test lint also passes.
  `mypy app/ --python-version 3.12` passes (113 source files). Python 3.11 was
  not separately executed here. Compile checks cover calculator and migration.
- All nine modules validate with no errors; proposed-parameter and pre-existing
  stub-content warnings remain. Purpose drift passes (32 files, 94 deny phrases).
- Arbeitsrecht dossier **18/18**, all four aggregate metrics **1.0**, real draft
  annex included; plain **21/21** in DE/EN/de-LS. Saved core-3.7.0 reports are
  under `modules/arbeitsrecht/goldset/reports/`. Their Git SHA identifies the
  base commit; these reports test the uncommitted implementation, not that base
  commit alone. They are deterministic/content evidence, not live quality scores.
- Sozialrecht dossier/plain and Mietrecht dossier/plain regression gates pass.
  Sozialrecht dossier checklist/chronology metrics remain 0.979/0.935 and exceed
  their existing gates; no perfect-content claim is made for those fixtures.
- Independent review identified the corrected employment-period boundary defect;
  follow-up inspection found no further important defects. Human legal/language
  review and promotion remain deferred under D-071, never marked complete.

Implemented module 0.2.0, core 3.7.0/module API 3.5, disclaimer v3.4.0 and prompt
set 3.5.0. Deployment still needs migration/parameter seeding and explicit source
selection/ingestion using separately configured embeddings. No deployment,
publication or live-inference quality claim. §38 qualified planning limitations,
contractual/tariff exclusion clauses, special regimes and minimum-wage coverage
are documented in module content and source evidence.

Branch: `codex/wp-132-arbeitsrecht`, based on fetched merged main `1aaf606`.
Relevant changes: employment module and tests, deadline/corpus contracts,
migration 018, version/notices and API/authoring/roadmap records. Owner's
pre-existing `AGENTS.md` edit is unchanged. No commit or push performed.
