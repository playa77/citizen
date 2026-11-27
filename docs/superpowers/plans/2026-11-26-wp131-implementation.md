# WP-131 implementation plan

**Goal:** Implement the experimental tenant-side Mietrecht backend package.
**Spec:** [concrete scope](2026-11-26-wp131-proposal.md), roadmap WP-131 and module catalog M2.
**Authority:** Owner explicitly directed implementation again after receiving the concrete shared-extension proposal; no additional confirmation rounds.
**Architecture:** Extend existing Fristen/dossier facts and corpus storage; keep legal rules, regional data, calculators and content module-owned. No frontend, new service or dependency.
**Constraints:** Preserve local AGENTS.md; no commit/push/deploy/live inference; human reviews deferred (D-071); all source gaps explicit.

## Tasks and acceptance

- [x] Deadline contracts (parent): add receipt/event facts, guarded applicability, month-end anchoring and backwards offsets in existing Fristen/dossier path. Tests first for literal leap/month/weekend cases, missing dates, qualification and unrelated documents; preserve SGB/service behavior.
- [x] Source/parameter/calculation package (independent worker): official dated federal/state references, versioned coverage and parameters, pure qualified cent-exact calculators through SDK; no silent local defaults; tests first. Federal/state corpus adapters/storage remain parent-owned.
- [x] Module content (independent worker): four guarded drafts, dedicated prompts, public intake schema, dossier, DE/EN/de-LS copy and >=15 synthetic cases; existing formats and honest draft/experimental metadata. No shared config edits.
- [x] Corpus integration (parent): BetrKV/HeizkostenV and official state-source handling in existing ingestion/storage, single non-destructive migration, source retrieval mappings and fixtures.
- [x] Integration (parent): module 0.2.0, core/module API bump as needed, notices/prompt version/pins, ADR, changelogs/API docs/roadmap; regression and offline goldset reports.
- [x] Verification/review: focused RED→GREEN evidence; ruff/mypy, purpose drift, validators, offline dossier/plain, full PostgreSQL unit/integration suite; fresh whole-change review, fix relevant findings, final Git inspection.

## Review focus

Expired or unknown municipality coverage must refuse qualified ceilings. Receipt cannot borrow letter date. Backwards notice periods cannot receive forward rollover. Missing statutory exception checks cannot become affirmative conclusions. Unavailable calculations and draft actions must retain their guard status.

## Execution ledger

- Baseline: c292f52 equals fetched origin/main; only pre-existing AGENTS.md edit plus this task's proposal. Work in current checkout on dedicated branch to preserve user-visible workspace; no worktree creation or commits.
- Parallel work is limited to disjoint module calculator/source files and module content files under dispatching-parallel-agents; parent owns all core/schema/integration files.
- Network collection budget: per worker <=24 primary-source requests, one in flight per source, >=2 seconds between starts, <=20 seconds/request, no retries; workers must use disjoint hosts or coordinate ownership. No inference/embedding calls.

## Delivered scope and verification ledger — 2026-11-27

- Versions: module0.2.0, core3.6.0, SDK3.4, prompt set3.4.0,
  disclaimer v3.3.0. Local editable package and generated egg-info refreshed
  without dependencies/network so runtime/report versions match pyproject.
- Deadline RED→GREEN: 14 failures for unsupported receipt/event triggers became
  passing contracts; additional RED→GREEN regressions cover unsupported dates,
  service qualifications, and retained `facts_used` provenance. Four tenancy
  rules require confirmed triggers; no administrative date substitutes.
- Civil calendar: 16 initial missing-capability failures became passing tests;
  Gregorian Easter and statewide holidays avoid the legacy calendar's known
  inaccuracies. Local holiday confirmation remains explicit.
- Calculator: 42 missing-implementation failures became passing tests. Further
  RED→GREEN fixes cover last-day Saturday notice cutoff, comparison rent below
  existing rent, and exact fractional area/consumption arithmetic. All50 focused
  calculator cases now pass; unavailable results have no partial amount.
- Content: real-renderer empty-input/guard tests passed. Twenty synthetic pipeline
  fixtures audit clean; no live-pipeline evaluation was performed.
- Corpus: synthetic parser/normalizer tests plus actual PostgreSQL CHECK and
  jurisdiction storage tests passed. Four checked-in state applicability excerpts
  pass offline normalization without persistence. They are visibly partial.
- Independent read-only final review found decimal allocation units, omitted
  heating form fields and nullable-qualification mismatch. Each received a
  failing public-contract regression followed by a fix and passing test. Added
  the also-required `nonallocable_costs_present` public property. No deferred
  review findings remain; no repeated review dispatch.
- Full initial run: 23 failures from old Mietrecht-stub expectations and schema
  version/anchor assumptions, 1704 passes, four existing skips. Updated those
  fixtures to a remaining profile-less module; retained historical WP-93 pins
  by projecting only the intentional tenancy source/tag expansion and adding
  explicit new-module contracts. A subsequent fixture copy-tree omission was
  fixed. No baseline digest was blindly regenerated.
- Whole-suite green checkpoint: 1740 passed, four skipped, 21 warnings in78.09s.
  A final run after the added `facts_used` regression and package metadata refresh
  is recorded below when complete.
- Static checks: Ruff app/module/new-test lint and app formatting, strict mypy
  for Python3.12, all9 module validations, purpose drift and diff whitespace
  checks pass. Offline uv lock check passes; parameter seed dry-run validates
  two rows without touching a database. No Python3.11 runtime run was performed.
- Saved deterministic reports are included under
  `modules/mietrecht/goldset/reports/`: dossier20/20, all four aggregate metrics
  1.000; plain23/23 in de/en/de-LS, gate passed. These are working-tree reports
  against base c292f52, not an implementation commit or live-inference result.

## Operational and review boundaries

The state worker exhausted its initial24-request source budget and received an
explicit bounded extension to40 total official source requests, no retries.
The16-Land coverage matrix records exact unsupported/blocked/unresolved scope.
Federal official web checks succeeded for the stated anchors; a bounded direct
shell download attempt failed for all eight URLs with transport URLError, with
no retries or persisted raw downloads. BetrKV§1 was not fully captured; allocable
costs require explicit qualified confirmation. No source gaps become inferred
legal values. Human review, OQ-7 source-term review and promotion remain pending
under D-071. No deployment corpus population, embeddings, live inference, GUI,
commit, push or release occurred. The owner's AGENTS.md edit remains intact.

## Final delivered-state acceptance

Command: `OPENROUTER_API_KEY=synthetic-test-key CITIZEN_SYNTHETIC_DATA_ONLY=true
.venv/bin/python -m pytest tests/unit/ tests/integration/ -q -rs`, disposable
PostgreSQL16/pgvector with migration017 applied by test setup.

Result: **1741 passed, 4 skipped, 21 warnings in 78.95s (0:01:18)**. This includes the actual chronology PUT/storage
and dossier POST tenancy integration test, new facts provenance regression,
all calculator/source/draft tests and preserved HTTP/SSE/MCP contracts.

The four skips remain the removed-CORS test, existing intake GET error-handling
gap and two missing spaCy-model cases. Warnings are existing testcontainers/BS4
deprecations and async connection-cancellation warnings; pytest-asyncio also
reports its unset fixture-loop scope. No failures remain.

Final static/offline checks pass: Ruff lint/format, strict Python3.12 mypy,
nine-module validation, purpose drift, uv lock consistency, parameter dry-run,
dossier20/20 and plain23/23. The final reports identify core3.6.0/module0.2.0.
Git: `codex/wp-131-mietrecht`, based on fetched `origin/main` c292f52, no upstream
configured for the new branch, no implementation commits or push. Changes are
local; the pre-existing12-line AGENTS.md addition is unchanged.
