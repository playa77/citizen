# WP-136 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task.

**Goal:** Experimental M7 own-matter preparation with qualified dates/arithmetic and multilingual safety copy.
**Architecture:** Extend existing source, procedural-calendar and static-copy interfaces exactly as approved. Domain rules remain in module data/code importing only the SDK.
**Tech Stack:** Existing Python/FastAPI, PostgreSQL 16/pgvector, YAML, pytest.
**Spec:** [approved proposal](2026-11-27-wp136-proposal.md).

## Global Constraints

- Experimental/draft; no live inference, deployment ingestion, GUI, commits or publication.
- Preserve owner's AGENTS.md edit; work on codex/wp-136-aufenthaltsrecht, baseline 1daf5d8.
- Verify current primary law; one in-flight publisher request, >=2s interval, <=3 attempts/resource, <=10 minutes/publisher; honour Retry-After and stop persistent denial.
- No unqualified eligibility/status decisions, asylum narrative drafting or authority-side use.
- Existing module interfaces, additive API, single migration chain; no dependencies.

## Review Focus

- Changed 2026 asylum law and transition regimes: never silently use old §36 assumptions.
- Unknown procedure and missing service: retain urgent referral, no guessed date.
- Pending residence application: no invented status, travel or work permission.
- Multilingual unknown/missing results: urgent warnings and privacy/AI notices remain available.
- Naturalisation and livelihood: arithmetic is not eligibility; missing facts fail closed.

### Task 1: Source and procedural support

Files: source adapter/catalog, citations/retrieval, ORM source constraint, migration 022, rollover/evaluator/dossier; tests/unit/test_aufenthaltsrecht_corpus.py and integration source tests.
Interfaces: existing source metadata/chunk parser; get_rollover('vwgo_57') -> Roller.
- [x] Verify current seven statutes and relevant procedural/transition provisions; save dated source record.
- [x] Write/run failing source identity, migration and weekend/state-holiday tests.
- [x] Add seven sources, guarded migration and VwGO civil-calendar registration including local-holiday dispatch.
- [x] Run focused source/calendar tests; no live embeddings.

### Task 2: Qualified module behavior

Files: modules/aufenthaltsrecht/{module,corpus,intake,intake-schema,fristen,dossier,parameters,prompts,documents,compliance,calculators,README,CHANGELOG,errata}; tests/unit/test_aufenthaltsrecht_{content,calculators}.py.
Interfaces: SDK Calculator process_extraction(dict, overrides) -> list[dict]; parameter key residence_rules; existing explicit-service qualifications.
- [x] Write/run failing tests for literal ordinary/asylum dates, missing facts, special/transition refusals, local holidays, title expiry/application and qualified residence-period/cent arithmetic.
- [x] Implement confirmed statutory regimes and explicit exclusions after source verification; bounded parameter validity and no unsupported state-law objection inference.
- [x] Add guarded drafts, minimised schema, referral-first prompts and disclaimer addendum.
- [x] Verify actual document generation, calculators, source mappings and deadlines.

### Task 3: Multilingual copy and synthetic evaluation

Files: module copy/{de,de-LS,en,ar,fa,uk,tr,ru}, goldsets/reports; app/plain/core/{ar,fa,uk,tr,ru}.yaml; disclaimers/version pins; tests content/plain regressions.
Interfaces: existing copy formats, language metadata and ISO dates; no dynamic translation.
- [x] Write/run missing-language/core-copy and minimisation regressions.
- [x] Supply equivalent warning/status copy and core summaries, all draft pending human review.
- [x] Add >=15 synthetic pipeline/dossier/plain cases with independent literal expectations and guarded draft annex coverage.
- [x] Run module validation, deterministic dossier/plain evaluations and purpose check; inspect metrics.

### Task 4: Integration, records and delivery verification

Files: API documentation, authoring/catalog/roadmap/TODO, core/module capability versions, D-078, execution record and affected version expectations.
Interfaces: shared source types and language availability are additive; no defaults.
- [x] Record specific owner approval and all material limitations in D-078; update existing release records.
- [x] Run Ruff check/format, mypy (installed interpreter target and default), all-module validation, unit/integration suites and deterministic module gates.
- [x] Obtain fresh whole-change review under executing-plans/requesting-code-review; fix important issues with failing regressions first.
- [x] Re-run invalidated checks, inspect Git state and report actual results; no commit/push.

## Execution ledger

Owner approved proposal in this chat: “approved. proceed.” Existing scoped approval reused; inline execution avoids another approval round. Work remains on the dedicated branch in the current checkout, preserving existing edits; no additional worktree created.


### Implementation and review record

Tasks 1–3 implemented. Source/calendar regressions initially failed for the
missing source types/rollover/migration, then passed with the shared support.
New module tests initially failed for missing content, then passed. Multilingual
sentence/duty-of-care checks failed on Cyrillic/Arabic/Persian boundaries and
selected discouraging phrases, then passed after the scoped extension.

A fresh reviewer inspected the uncommitted changes. Six material findings were
reproduced and corrected with failing then passing regressions: lettered source
identity; contradictory asylum regimes; independent interim-notification anchor;
missing urgent banner for unsupported procedures; indistinguishable translated
remedies; and model-only calculator confirmations/sensitive summary keys.
The owner approved both additional shared safety fields in the linked supplement.
No review finding remains intentionally deferred; no second review is claimed.

The ingestion-to-lookup regression additionally exposed the old norm-reference
regex swallowing prose after the law name. A failing adjacent-prose test and
actual PostgreSQL retrieval now verify both §34a and §87e without §34/§87
collisions. The matching pattern uses the existing statute catalog and preserves
SGB multiword names and FreizügG/EU. A monetary-display regression verifies that
15001 cents is displayed as 150.01 EUR rather than an unlabelled 15001.

Ruling: use the existing explicit-event interface for independently confirmed
asylum Bekanntgabe (`ereignis_datum`), retaining formal service for lawsuits —
this avoids a new date field and prevents a later service date extending an
interim period. Clients must provide both anchors where they differ.
Ruling: automatic state-law remedy selection stays unavailable for all states;
require concrete qualified individual confirmation instead of inventing coverage.
This leaves state-rule automation and unsupported procedures for later review.

Local editable distribution metadata and the ignored generated egg-info were
refreshed with the existing setuptools/uv toolchain, offline and without changing
dependencies, so runtime provenance and reports identify core 3.11.0 rather than
stale 3.10.0. No agent/runtime configuration was edited.

Offline reports are tracked under modules/aufenthaltsrecht/goldset/reports:
24/24 dossier cases including actual guarded draft annexes, all deterministic
metrics 1.0; 29/29 plain cases across DE/EN/de-LS/AR/FA/UK/TR/RU. All translations
remain draft. Reports record base commit 1daf5d8 because implementation is
uncommitted; they are not a claim of committed publication or live quality.

Ruff app lint/format, additional calculator/migration lint, all eleven module
validators, purpose drift and mypy with --python-version 3.12 passed. Default
mypy retains the existing installed NumPy stub syntax failure when targeting
3.11; no project configuration or dependency workaround was applied. Only the
installed Python 3.12 interpreter was exercised, not a separate 3.11 environment.


### Final verification and handoff — 2026-11-27

Delivered state: uncommitted WP-136 on `codex/wp-136-aufenthaltsrecht`, based
on merged WP-135 `1daf5d8`; main and the fetched origin/main reference also
identify that commit. The owner's pre-existing AGENTS.md edit is preserved and
excluded from WP-136 scope. No commit, push, PR, release or deployment performed.

`pytest tests/unit/ tests/integration/ -q -rs` completed against a disposable
PostgreSQL 16/pgvector container migrated through 022: **2175 passed, 4 skipped,
24 warnings**, in 89.15 seconds. Skips: obsolete CORS-field test; pre-existing
GET intake exception-handling gap; two spaCy pseudonymization checks because
`de_core_news_lg` is not installed. Existing pytest-asyncio/testcontainers/bs4
warnings and asyncpg cancellation-coroutine warnings remain. No spaCy/model
provisioning or unrelated intake-route repair was introduced.

Final Ruff lint/format, mypy `app/ --python-version 3.12`, eleven-module
validation and purpose-drift checks passed. Default-target mypy's installed
NumPy 3.12-stub limitation remains explicitly recorded above. Offline dossier
24/24 with actual drafts and plain 29/29 reports pass; source hashes, limits and
proposed parameter validity are in the new module's sources/ and README.
Only documentation/progress-record edits followed the final executable checks;
`git diff --check` was rerun for the handoff.

All four tasks complete within the approved experimental-backend scope.
There is no claim of human promotion, complete state/EU/transition coverage,
live inference quality, deployed corpus population or GUI acceptance.


### Pull-request preparation authorization

The owner requested a PR for this session's work after the final verified
handoff. D-078 records authorization to commit WP-136, push its dedicated branch
and open a PR against main, excluding the pre-existing AGENTS.md edit.
`git fetch origin` confirmed origin/main still identifies 1daf5d8; no rebase or
merge is required. The implementation and existing test evidence are unchanged;
only publication-authority records were added before staging.
