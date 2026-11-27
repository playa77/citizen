# WP-134 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement experimental Verkehrsrecht traffic-offence backend with qualified deterministic tools.
**Architecture:** Approved federal corpus additions and shared StPO rollover use existing libraries/storage. Legal applicability and content remain module-owned.
**Tech Stack:** Existing Python/FastAPI/YAML/PostgreSQL 16/pgvector environment.
**Spec:** [approved proposal](2026-11-27-wp134-proposal.md).

## Global Constraints

No new service/dependency/frontend, deployment ingestion, live inference or commit/push.
Preserve AGENTS.md. Draft/proposed review metadata; explicit module selection.
Core 3.9.0, module API 3.7, new module 0.1.0 on codex/wp-134-verkehrsrecht.
Owner specifically approved the proposal and instructed execution: no further plan approval round.
Existing feature branch provides separation from main; no overlapping implementation work is present.

## Review Focus

- Hearing/issue dates must never replace actual service for an objection.
- Missing limitation events/register records must not establish expiry or driving entitlement.
- Anniversary periods beginning on the event day differ from objection periods.
- Sanction lookups must disclose limited coverage and reject unsupported regimes.
- Witness duties and personal particulars differ from the affected person's right to silence.

## Task 1: Primary sources and shared procedures

Files: app/services/corpus.py, retrieval.py, app/citations/laws.py,
app/db/models.py, alembic/versions/020_traffic_sources.py, app/fristen/rollover.py,
tests/unit/test_verkehrsrecht_corpus.py and tests/integration/test_traffic_sources.py.
Interfaces: existing scrape_and_chunk(source_type, client=...); new keys
owig/stvg/stvo/bkatv/fev/stpo; get_rollover('stpo_43') -> (date, state) -> date.
- [x] Verify official sources: one in-flight request, >=2s spacing, one attempt per request, 20s timeout; no embeddings.
- [x] Write and run failing catalog/citation/annex-scope/migration/rollover tests.
- [x] Implement source catalog, mappings, guarded migration and StPO rollover with correct calendar.
- [x] Run focused tests, including actual migrated PostgreSQL storage and retrieval.

## Task 2: Qualified traffic calculators

Files: modules/verkehrsrecht/calculators.py, parameters/traffic.yaml,
tests/unit/test_verkehrsrecht_calculators.py.
Interfaces: SDK process_extraction(extraction, param_overrides), load_parameters(extraction, source), CALCULATORS.
Types: sanction_lookup, prosecution_limitation, driving_ban_start, register_retention.
- [x] Write/run failing literal boundary, refusal, validity and malformed-input tests.
- [x] Implement pure parameter-backed checks with explicit legal qualifications and no fallback values.
- [x] Test interrupted limitation and unknown records, offence-day periods, leap dates, finality and multi-ban exclusions.

## Task 3: Module content and offline acceptance

Files: modules/verkehrsrecht manifest/corpus/intake/intake-schema/fristen/dossier,
documents/prompts/copy/compliance/sources/goldset/reports; tests/unit/test_verkehrsrecht_content.py.
Interfaces: existing content schemas, actual-service qualified objection rule, calculator facts from Task 2.
- [x] Write/run failing content tests: literal objection dates, each qualification, no hearing-date fallback, drafts and schema.
- [x] Implement source records, guarded drafts, DE/EN/de-LS copy, >=15 synthetic goldset cases, notices and changelog.
- [x] Validate all modules; run saved dossier/plain deterministic reports and focused tests.

## Task 4: Integration and review

Files: API_DOCUMENTATION.md, docs/MODULE-AUTHORING.md, module-catalog.md,
roadmap-v3.0.0.md, TODO.md, DISCLAIMER_DE/EN.md, app/plain/core/*.yaml,
app/core/config.py, services/prompts.py, modules/sdk.py, pyproject.toml, uv.lock and affected pins.
- [x] Align versions, disclosure/source contracts and projections, record D-076.
- [x] Run lint/format/type, purpose drift, deterministic gates, full unit/integration/offline suites.
- [x] Fresh whole-branch review and regression-tested fixes, then delivered-state Git inspection.

## Execution record

Baseline d88b70c; owner's AGENTS.md addition preserved. Approved architecture is recorded in D-076.
Pre-flight: Task 1 source keys and stpo_43 are consumed by Task 3; Task 2 calculator facts are declared by Task 3's intake schema. Existing interfaces align.
Commands and observed results are recorded below as work progresses. No commit/push authorized.


### Progress and review ledger

- Baseline: 14 WP-133 content tests passed with disposable PostgreSQL; the
  initial sandbox denial was resolved by scoped execution approval.
- Task 1: 16 source/calendar/migration tests failed before implementation and
  then passed. Actual PostgreSQL tests exposed §1 also boosting §10; the
  segment-boundary fix passed all six new source integration regressions.
  Cached official text parsed to 404/465/275/22/350/1,754 paragraph chunks
  for OWiG/StVG/StVO/BKatV/FeV/StPO, preserving source identity. Annex/table
  coverage remains explicitly excluded, including in source descriptions.
- Task 2: 46 calculator tests failed before implementation and then passed.
  Current source verification supersedes catalog assumptions: standard
  §26(3) StVG now six months; four-month §25 regime now paragraph 3 no.1.
  Event dates before the 2026-11-27 snapshot are refused by calculators;
  qualified objection procedure remains a separate service-date rule.
- Task 3: 22 content tests failed before implementation. The completed
  content includes 20 synthetic cases, four actual guarded draft types and
  DE/EN/de-LS copy. Initial dossier 20/20 and plain 25/25 deterministic gates
  passed. Calendar/spec wording assertion fixes preserve the actual law
  citation rather than a brittle textual rendering.
- Task 4 first full check: 1,992 passed, four existing skips, 24 warnings
  (85.09s). All-module validation passed with expected draft/stub warnings.
  Ruff passed after formatting changed files. Mypy with Python 3.12 target
  passed for all 113 app files. Default target 3.11 under the installed 3.12
  environment stopped on NumPy's existing Python 3.12 `type` statement;
  CI's documented3.12 command is used without changing project settings.
- Local package metadata was refreshed offline for core 3.9.0. A stale
  ignored source-tree egg-info had shadowed the new editable distribution;
  report versions are re-generated after refreshing that metadata.
- Independent whole-change review (fresh subagent, read-only) found seven
  material issues. No architectural expansion was proposed. Each is fixed
  with observed failing regressions before the correction:
  1. Ban commencement was misleadingly aliased to expiry: remove the alias
     and qualify the user-facing summary (test_ban_never_presents_commencement_as_expiry).
  2. First-hearing/order could interrupt twice: reject repeated §33(1) no.1
     (test_first_hearing_order_and_actual_hearing_cannot_interrupt_twice).
  3. Earliest deletion preceded the completed one-year overlap: compute from
     overlap start and delete only afterwards, including leap boundaries
     (test_deletion_is_after_inclusive_overlap_and_handles_leap_year).
  4. Unavailable results could inherit reassuring model explanations: retain
     deterministic refusal commentary and assessment, including mixed results
     (test_unavailable_traffic_result_cannot_be_explained_as_success and
     test_mixed_available_and_unavailable_checks_keep_review_requirement).
     This is a bounded correction to existing result assembly, not a new
     calculator architecture; legacy/provisional successful paths remain.
  5. Calculated values vanished from dossier/explanation projections: use
     existing SDK computed_values.deterministic_result, with scope/status
     and parameter dates; failures retain null (four modes covered by
     test_actual_traffic_result_survives_explanation_and_dossier_projection).
  6. Weekly objection provenance incorrectly cited a days-only provision:
     cite §43(1) StPO for the two-week computation, retaining literal dates.
  7. Hearing/witness goldsets lacked their role-specific legal anchors:
     expect §§55/111 OWiG and §§52/55 StPO rather than objection provisions
     (test_weekly_objection_provenance_and_role_specific_goldset_anchors).
- No review finding was deferred or overruled. No human promotion, release,
  deployment ingestion, live inference, commit or push is authorized/performed.


### Final delivered-state verification

Tested state: branch `codex/wp-134-verkehrsrecht`, base/HEAD `d88b70c`, plus
this uncommitted WP-134 working tree. Owner's original AGENTS.md addition is
unchanged. No new commits, push, merge, release or deployment.

- `.venv/bin/pytest tests/unit/ tests/integration/ tests/offline/ -q`:
  **2,003 passed, four skipped, 24 warnings in 83.70s** after all review fixes,
  using the repository's automatic disposable PostgreSQL16/pgvector container
  and migrations through020. Existing Testcontainers/lxml deprecations,
  pytest-asyncio fixture-loop warning and asyncpg cancellation warnings remain.
- `.venv/bin/ruff check app/ modules/verkehrsrecht/ tests/unit/test_verkehrsrecht* tests/integration/test_traffic_sources.py tests/unit/test_calculation_availability.py`:
  passed. `.venv/bin/ruff format --check app/`: all113 files formatted.
- `.venv/bin/mypy app/ --python-version 3.12`: passed, all113 app files.
  Default `mypy app/` targeting3.11 cannot parse the installed NumPy Python3.12
  stub (`numpy/__init__.pyi:737`); not an application typing error and no
  configuration/dependency change was made to hide it. Python3.11 execution
  was not available locally; CI's documented Python3.12 invocation passed.
- `.venv/bin/python scripts/check_purpose_drift.py`: passed,42 files/101
  phrases. `.venv/bin/python -m scripts.validate_module --all`: ten modules,
  zero errors; existing experimental/stub/proposed-review warnings retained.
- Offline dossier gate:20/20, all four aggregate metrics1.000, actual draft
  annexes included. Plain-language gate:25/25, DE/EN/de-LS, review still draft.
  Saved core3.9.0 reports are in `modules/verkehrsrecht/goldset/reports/`.
- `git diff --check`: passed. Fresh independent review's seven findings were
  all fixed with failing-then-passing regressions and the complete green suite;
  no deferred minors or overruled findings.

Limits: experimental module; selected speed-table coverage, paragraph-only
corpus without annex/table retrieval, finite proposed parameters expiring
2026-12-31, no historical/transitional calculator regime, no deployment corpus
population, no live-inference quality result, no human review/promotion.
Accident settlement remains catalog stage2. No further implementation work
within the approved WP-134 scope remains.

### Pull-request publication

The owner's subsequent request, “prepare and open a pr with your work,”
authorizes committing this implementation, pushing `codex/wp-134-verkehrsrecht`
and opening a PR against `main`. D-076 records that scoped authorization.
The pre-existing AGENTS.md change is excluded. No product code changed after
the final 2,003-test run; publication adds only the authority/delivery records.
No merge, deployment, release or live inference is included.

### PR #23 CI follow-up: process-dependent retrieval fixture

The reported Python3.12 integration failure was reproduced with
`PYTHONHASHSEED=947` in the original
`test_retrieval_returns_chunks_with_metadata`: the supposedly deterministic
mock embedding used Python's process-randomized `hash(text)`. For this query
and seed, the low32-bit hash is divisible by1000, so every vector component
was zero. Pgvector then produced no usable cosine match; the unrelated
keyword query also returned nothing. This is a synthetic fixture defect,
not evidence that production retrieval thresholds need changing.

A regression first failed for hash independence/nonzero geometry. The test
fixture now uses SHA-256 over UTF-8 text and bounded positive components,
remaining close to the seeded synthetic vector direction. No production
retrieval, settings, threshold, workflow or database behavior changed.
The complete integration suite passed53/53 with the previously failing hash
seed. The new test is intentionally about fixture invariants, without live
inference or provider calls. AGENTS.md remains excluded from publication.

Final local follow-up verification:
`PYTHONHASHSEED=947 .venv/bin/pytest tests/unit/ tests/integration/ tests/offline/ -q`
passed **2,004 tests, four existing skips, 24 existing warnings in87.61s**.
Ruff lint/format for the changed test and `git diff --check` passed. This
supersedes the earlier2,003-test count for the PR's latest test-only follow-up.
