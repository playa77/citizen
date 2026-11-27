# WP-133 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for integration and superpowers:dispatching-parallel-agents for independent corpus and calculator work.

**Goal:** Implement experimental consumer-side Vertragsrecht 0.2.0.
**Architecture:** Approved EGBGB/EUR-Lex additions use existing corpus storage and dispatch. Contract rules remain module-owned; composite dates use calculators rather than a shared deadline redesign.
**Tech Stack:** Existing Python/FastAPI/YAML/PostgreSQL 16/pgvector environment.
**Spec:** [approved proposal](2026-11-27-wp133-proposal.md).

## Global constraints

No new service/dependency/frontend, deployment ingestion/live inference or commit/push.
Preserve AGENTS.md; keep draft/proposed metadata and explicit module selection.
Core 3.8.0, module API 3.6, module 0.2.0. Execute on codex/wp-133-vertragsrecht.

## Review focus

- Missing qualifications never establish withdrawal or flight entitlement.
- Presumption duration is not a deadline to file or an automatic warranty extension.
- Missing/expired rate periods must refuse interest arithmetic.
- EUR-Lex articles retain official identity/provenance, without BGB aliases.
- Unknown regimes and unconfirmed draft facts remain explicit review items.

## Task 1: Official corpus support

Files: app/services/corpus.py, existing source catalog, app/services/retrieval.py,
app/citations/laws.py, alembic/versions/019_contract_sources.py,
tests/unit/test_vertragsrecht_corpus.py.
Interface: scrape_and_chunk(source_type, client=...) returns existing chunks;
source keys egbgb/eu261. No shared deadline-engine changes.
- [x] Write/run failing parser, source mapping, citation and migration tests.
- [x] Implement official EGBGB mapping and bounded EUR-Lex article ingestion.
- [x] Verify focused tests and preserve dated source coverage.

## Task 2: Qualified deterministic contract tools

Files: modules/vertragsrecht/calculators.py, parameters/*.yaml,
tests/unit/test_vertragsrecht_calculators.py.
Interface: SDK process_extraction(extraction, param_overrides), load_parameters(extraction, source),
CALCULATORS tuple. Types: default_interest, withdrawal, flight_compensation.
- [x] Write/run failing boundaries, missing qualification, rate-segment and invalid-input tests.
- [x] Implement pure parameter-backed tools, exact money arithmetic and refusal results.
- [x] Run focused calculator tests.

## Task 3: Module content and deterministic acceptance

Files: modules/vertragsrecht manifest, corpus/intake/intake-schema/fristen/dossier,
documents/templates, prompts/profile, copy/de/en/de-LS, disclaimer/compliance, sources,
goldset and reports; tests/unit/test_vertragsrecht_content.py.
Interface: existing module data shapes; qualified event rules; calculator facts from Task 2.
- [x] Verify primary-source anchors with bounded collection; retain evidence.
- [x] Add tests for guards, distinct legal effects, copy and draft output.
- [x] Implement content, >=15 synthetic cases, validate and run offline reports.

## Task 4: Integration and final review

Files: API_DOCUMENTATION.md, docs/MODULE-AUTHORING.md, docs/module-catalog.md,
docs/roadmap-v3.0.0.md, TODO.md, DISCLAIMER_DE/EN.md, app/plain/core/*.yaml,
app/core/config.py, app/services/prompts.py, app/modules/sdk.py, pyproject.toml and affected pins.
- [x] Align versions, notices, API/source contracts and historical test projections.
- [x] Run lint/format/type, purpose drift, all-module validation, deterministic regressions,
  full unit/integration/offline suites against disposable PostgreSQL.
- [x] Independent whole-change review; fix material issues with regression tests.
- [x] Record results/limitations and Git status; leave uncommitted.

## Execution record

Baseline d076e56. Specific proposal approved and execution instructed; no additional approval round.
AGENTS.md edit preserved. Independent corpus and calculator work proceeds alongside content,
with separate file ownership and source quotas. No commit/push authorized.


### Implementation findings and review

- Native execution uses `codex/wp-133-vertragsrecht` on fetched merged main
  `d076e56`. The owner's original twelve-line AGENTS.md addition is retained.
  No commit, push, merge, deployment or live inference was performed.
- Baseline employment content tests passed (7) with the existing Python 3.12
  environment and disposable PostgreSQL. Docker/network sandbox denials were
  resolved through scoped execution approvals; no controls were disabled.
- Failing tests demonstrated missing corpus/source identities and calculators
  before implementation. The registry's native YAML-date requirement and schema
  module API version pin were corrected after observed validation/test failures.
- Current official §356 BGB puts the outer limit in paragraph 4. Corrected the
  catalog reference; the notice prerequisite remains paragraph 3. Source evidence
  records the dated current snapshot, not historical consolidation coverage.
- Independent review identified EGBGB article-scope loss, Article 1 prefix
  collisions with Articles 10–19, accepted regulation spelling lookup loss and
  ambiguous bare EGBGB section verification. Five regression tests failed before
  fixes and all 18 focused corpus tests passed afterwards. PostgreSQL integration
  tests additionally prove the migrated source constraint and exact lookup using
  synthetic sibling articles/sections; no embeddings or network are involved.
- Ruling: regular limitation uses a manually confirmed relevant 31 December in
  the existing event contract, rather than expanding the shared engine. Wrong
  confirmation can produce a wrong date; schema/copy/drafts require qualification,
  and no date is inferred from the invoice or letter.
- Ruling: disputed outer-cap weekend/holiday extension requires an explicit
  `outer_limit_rollover_confirmed` fact if it affects the result. Otherwise the
  calculator refuses the boundary; it does not decide the legal question.
- Ruling: the EUR-Lex adapter covers the official original act with its 2005
  applicability date, not consolidated case-law coverage. Empty/challenge and
  incomplete article responses fail closed. Actual publisher HTML ingestion
  could not be verified; future operators must check access before ingestion.
- The withdrawal outer duration and flight reduction divisor are versioned data,
  with two observed failing missing-parameter tests before the final correction.
  There is no hard-coded fallback when either legal parameter is absent.
- Old profile-less fixtures used the Vertragsrecht stub. They now use a remaining
  profile-less Strafrecht peer. Historical WP-93 projections exclude only the
  appended contract keywords and source additions, preserving the old pins.
  Dedicated tests cover the new module behavior; privacy/selection guards remain.
- Existing source-tree egg-info shadowed refreshed installed package metadata.
  Refreshed editable metadata offline without dependencies; reports now identify
  effective core 3.8.0. Aligned the lockfile's local-package version; offline
  `uv lock --check` passes without changing dependency resolutions.
- Human review/promotion, raw EUR-Lex compatibility, deployment ingestion and
  live inference are deliberately not asserted. The independent reviewer listed
  these and manual qualification boundaries as explicit deferrals; no unrelated
  minor change is pending from that review.

### Verification record

- Configured offline Vertragsrecht dossier: **20/20**, all aggregate metrics
  **1.0**, real draft annex included. Plain gate: **24/24**, DE/EN/de-LS; human
  review remains draft. Saved core-3.8.0 reports are in the module goldset reports.
  Git SHA identifies the base commit; reports exercised this uncommitted tree.
- Sozialrecht, Mietrecht and Arbeitsrecht dossier/plain regression gates pass.
  These are deterministic content checks, not a live legal-quality evaluation.
- All nine modules validate (zero errors); proposed-parameter and existing stub
  warnings remain. Purpose drift passes, scanning 37 files and 98 deny phrases.
- Ruff app/new-module/test lint and format pass; strict mypy on `app/` with
  Python 3.12 passes (113 source files). Calculator/migration compile checks pass.
  Python 3.11 was not separately executed in this environment.
- Initial whole suite after content integration: 1,886 passed, four skipped,
  one schema/API-version pin failure. After schema and citation fixes: 1,894
  passed, four skipped. Final parameter-only refinement is covered by 26 pure
  calculator tests and the final full-suite result below.


### Final delivered-state verification and handoff

- `.venv/bin/pytest tests/unit/ tests/integration/ tests/offline/ -q`:
  **1,896 passed, four skipped, 24 warnings, 80.33 seconds** on Python 3.12.15
  and disposable PostgreSQL 16/pgvector. Includes migration 019 and the real DB
  article-identity tests. No production database or inference was used.
- The four existing skips concern the removed CORS setting, the pre-existing
  unknown-intake error-route check and two unavailable German spaCy-model
  controls. Existing testcontainers/lxml deprecations, two unawaited asyncpg
  cancellation warnings and a pending async-generator task at interpreter exit
  remain. No test failure remains; warning-free execution is not claimed.
- Final lint/format/type/module/purpose/compile/diff checks pass after the last
  production edit. Offline lock validation passes. Documentation changes after
  that run only complete this record; no tested production code was changed.
- Delivered: module 0.2.0, core 3.8.0/module API 3.6, prompt set 3.6.0,
  disclaimer v3.5.0, migration 019. Re-acknowledgement and application-template
  pins are aligned. Deployment instructions describe migration, parameter
  seeding, bounded rates and explicit source selection without performing them.
- Branch `codex/wp-133-vertragsrecht`, base/HEAD `d076e56` (merged WP-132).
  Relevant changes: full `modules/vertragsrecht` content/tools/tests/reports;
  corpus/citation/retrieval/storage support and migration; notices, versions,
  API/authoring/catalog/roadmap/TODO and D-075. All work is uncommitted, with no
  branch upstream or push. Fetched `origin/main` was current at task start;
  no later synchronization claim is made. AGENTS.md is the unchanged owner's
  pre-existing twelve-line edit, outside WP-133 implementation.
- No independent review minor findings remain. The recorded qualification and
  source-access limits are deliberate boundaries, not completed human review.


### PR preparation

The owner subsequently authorized preparation and opening of a PR. Commit and
push the WP-133 implementation on `codex/wp-133-vertragsrecht`, target `main`,
and preserve AGENTS.md outside publication (D-075 publication authorization).
A fresh fetch confirmed `origin/main` remains `d076e56`, the tested base. Only
publication documentation changes follow the final full-suite verification;
no production code or fixtures changed. Local checks are recorded above; remote
CI is a separate result and is not inferred from local success.
