# WP-130 Schuldnerrecht foundation implementation plan

**Goal:** Install a reviewable experimental debt-matter module with explicit
scope, intake routing, corpus requirements and appointment preparation content.

**Spec:** Roadmap WP-130, module catalog M1, D-069 backend continuation direction.
The owner instructed inline execution; GUI work remains separately owned.

**Architecture:** Use the existing module manifest and data loaders. No new
core extension, inference profile, scraper, database schema or dependency.
Catalog order is presentation only. Empty request scope stays empty.

## Acceptance and boundaries

- Experimental module resolves only when explicitly selected; provider mode
  retains its verified-only deployment rule.
- Existing modules retain their relative catalog order and behavior.
- Appointment preparation lists creditor balances, titles, payment records and
  service evidence; it asserts no deadline or amount.
- Unsupported corpus sources are declared and visible as pending requirements;
  no ingestion, embeddings or inference is run in this package.
- Canonical notices, acknowledgement setting and plain notices share v3.1.0.
- No promotion: source coverage, parameters, service-trigger support, engines,
  templates, reviewed copy, goldset and external quality gates remain open.

## Tasks

1. Write regressions for explicit resolution, tier gating, absent inference and
   engines, corpus requirements and deterministic dossier selection. Run RED.
2. Add module 0.1.0 data and dated source-review notes. Run GREEN. Update existing
   installed-set expectations while preserving legacy relative order.
3. Add bilingual addendum, bump disclaimer and re-pin plain notices. Record
   implementation progress without claiming completion of WP-130.1 or WP-130.
4. Run focused contracts, full unit/integration tests where available, offline
   module/dossier/plain checks, Ruff, mypy and purpose drift. Review final diff.

## Progress

- Baseline offline module validator: eight modules, zero errors; existing warnings.
- Initial pytest attempt: Docker blocked by sandbox; retried with scoped escalation.
- Core `app/fristen/specs.py` accepts only `bekanntgabe` triggers. A future
  service-trigger extension requires a specific architecture proposal; do not
  disguise `zustellung` as `bekanntgabe` or add area rules to core.

## Delivered state and verification — 2026-11-26

- Tasks 1–4 completed for this bounded foundation, not the whole WP-130.
  Three initial regressions failed because the module was absent, then passed
  with the implementation. A fourth test covers intake suggestions without
  session loading. All four passed in the full suite.
- Added `modules/schuldnerrecht` 0.1.0: manifest, intake/corpus declarations,
  dossier checklist/questions, errata, bilingual addendum, sources and changelog.
- Canonical notices and plain-copy pins are v3.1.0. Part B's general plain
  summaries still apply; the new area limitations are in Part D. Human plain
  review remains draft. Prompt set is 3.2.0 because the generated intake enum
  now includes the new area; existing legal profile text is unchanged.
- Historical regression projection removes only the added debt catalog entry
  before comparing original WP-93 surfaces, retaining the old digests. Installed
  module expectations now include the new peer without changing legacy order.
- `.venv/bin/python -m pytest tests/unit/ tests/integration/ -q`:
  **1,520 passed, 4 skipped**, 21 warnings, 76.83 seconds, disposable PG16/pgvector.
  Warnings include existing testcontainers/BeautifulSoup deprecations and async
  cancellation warnings; pytest-asyncio also warns about unset fixture-loop scope.
- Ruff lint and format passed for `app/` and the new test. Strict mypy with
  `--python-version 3.12` passed for all 112 app source files. `git diff --check`
  passed. No separate Python 3.11 environment was exercised.
- Offline module validator: nine modules, zero errors. Debt warnings: no
  goldset and four unsupported corpus source types. Earlier module warnings
  remain. These are pending integration/promotion work, not waived gates.
- Purpose-drift passed. Offline Sozialrecht dossier and plain-language gates
  passed; the dossier evaluator used fallback provenance and omitted its draft
  annex because settings were unavailable. No debt quality gate is claimed.
- Independent read-only review found no important defects. Its historical
  config-comment correction was applied. No live inference, embeddings, corpus
  ingestion, GUI changes, commit, push or release performed.

## Remaining roadmap work

WP-130.1 still needs complete statutory-anchor review, source adapter/storage
integration and verified corpus ingestion. WP-130.2–.5 and .7–.9 are open;
.6 has initial appointment content only. No legal engine, prompt persona,
parameter value or document template is asserted by this foundation. In
particular, do not activate legal inference on a partial BGB-only corpus.
