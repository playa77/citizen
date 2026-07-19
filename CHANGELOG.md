# Changelog

All notable changes to the Citizen project are documented in this file.
Newest entries first. Dates in ISO 8601.

---

## 2026-07-19 — Production Bugfixes

### Fixes

- **Embedding API 404**: `.env.example` had `EMBEDDING_MODEL=text-embedding-3-small` (missing `openai/` prefix). OpenRouter requires the full provider-prefixed model name. Fixed to `openai/text-embedding-3-small`. (D-008)
- **Prüfstand tab UI crash**: `fetchGoldset()` called `handleApiError()` on non-OK responses, which triggered `showDisclaimerModal()` → hid the entire `#app` container. Fixed by handling errors gracefully within the Prüfstand view without cascading to the disclaimer modal. (D-009)
- **Goldset SSE timeout**: The nginx config only had 180s `proxy_read_timeout` for `/api/v1/analyze`. The Prüfstand demo endpoint (`/api/v1/goldset/{case_id}/analyze`) fell through to the generic `/` location with default 60s timeout, cutting off SSE streams before the deepseek-r1 pipeline (5+ LLM calls) could complete. Added a dedicated `/api/v1/goldset` nginx location with 300s timeout and `proxy_buffering off`. Updated DEPLOYMENT.md. (D-010)
- **No progress indicator**: Demo progress stages showed static icons (○/◉/✓) with no animation to indicate active work. Added CSS `@keyframes demo-pulse` animation on the active stage icon for a visible pulsing indicator.

## 2026-07-13 — Release v1.0.0

### Production Deployment (2026-07-13)
- Deployed to VPS (37.60.240.152) at https://workbench.gronowski.cc
- PostgreSQL 16 + pgvector via Docker Compose, nginx reverse proxy, Let's Encrypt TLS
- Fixed missing dependencies: `asyncpg>=0.29.0`, `pgvector>=0.3.0` (D-001, D-002)
- Fixed migration DAG branch targeting: PostgreSQL targets `006`, SQLite targets `heads` (D-004)
- Applied missing schema columns from SQLite-branch migrations 008–010: `regime`, `notes`, `pii_mapping` (D-005)
- Fixed alembic startup deadlock: migrations now run in subprocess instead of `asyncio.to_thread` (D-006)
- Created DEPLOYMENT.md and DECISIONS.md

### Citizen v1.0.0
Local-first, evidence-constrained legal reasoning engine for German social law (SGB II).

- **21 work packages** across 6 phases (WP-00 through WP-54)
- **9-stage pipeline**: normalization, classification, decomposition, retrieval, construction,
  verification, generation, adversarial review, calculation check
- **37 API endpoints** across 14 route modules
- **802 unit tests** (0 failures, 0 mypy errors)
- **13 shared UI components** (Prüfstand + Result Report + Demo)
- **Key deterministic kernels**: Fristen engine (85 tests), calculation engine (200 tests),
  quote verification, intertemporal regime selection, OCR quality gate
- **Safety guardrails**: pseudonymization gate, egress guard with inference profiles,
  document generator guardrail (verified + confirmed claims only)
- **Goldset-driven eval**: v0.1.0 (10 cases) → v0.2.0 (12 cases with PII annotations)
- **4 retrieval levers**: tightened threshold, per-question mode, §-reference direct lookup,
  always-on hybrid RRF fusion

### Versioning
- **Canonical version**: `pyproject.toml` → `v1.0.0`
- **Frontend**: `index.html` (v1.0.0), `app.js` (v1.0.0), `style.css` (v1.0.0)
- **Database**: 13 ORM models, 10 migrations (001–010)

---

## 2026-07-13 — WP-50/51: Test suite + mypy hardening

### WP-50: Test audit
- Full suite: **802 passed, 3 skipped, 0 failures**
- Fixed 44 test errors from WP-00.5 client consolidation migration
- All `_get_client` references migrated to `app.core.router.get_shared_client`

### WP-51: mypy strict
- **0 mypy errors** across entire `app/` package
- 18 files fixed: added missing generic type parameters (`dict` → `dict[str, Any]`, `Pattern` → `Pattern[str]`),
  renamed shadowed variables, added return type annotations, dialect-dependent import `# type: ignore` annotations
- Installed `types-PyYAML` stub package
- 0 ruff errors (pre-existing only)

---

## 2026-07-13 — WP-20: Retrieval remediation (levers 1-4)

### WP-20: Retrieval improvements
- **Lever 1**: Tightened `MAX_COSINE_DISTANCE` 0.95 → 0.55 (was effectively no filter)
- **Lever 2**: Switched default `RETRIEVAL_MODE` from "combined" to "per_question"
- **Lever 3**: Added `retrieve_chunks_by_norm_reference()` — extracts § references from
  input text, queries `legal_chunk.hierarchy_path` directly, returns exact matches with `distance=0.0`
- **Lever 4**: Added `_rrf_fuse()` — Reciprocal Rank Fusion for always-on hybrid
  vector+keyword search (was fallback-only); keyword search now runs alongside every vector query
- **Files**: `app/core/config.py`, `app/services/retrieval.py`

---

## 2026-07-13 — WP-12: Deterministic quote verification

### WP-12: Quote verification
- Enhanced `app/services/verification.py` (v0.1.0 → v0.2.0):
  - Added hyphenation-normalized matching as third strategy (exact → whitespace → hyphenation)
  - Changed `verified` bool to `verification_status` string: `"exakt"`, `"normalisiert"`, `"unverifiziert"`
  - Backward-compatible: `verified` computed field preserved alongside `verification_status`
- Added `compute_quote_verification_rate()` to `eval/metrics.py`
- Added `quote_verification_rate` to `CaseMetrics`, aggregate, regression gate
- 55 unit tests (47 verification + 8 eval metrics)

---

## 2026-07-13 — WP-23: Calculation engine expansion

### WP-23: Calculation engine
- Extended `app/services/rules_engine.py` (v0.1.0 → v0.2.0):
  - Added `_OLD_FREIBETRAG_BRACKETS` for pre-2023-07-01 (pre-Bürgergeld)
  - Added `_select_bracket_table()` — regime-aware bracket selection
  - Added `compute_bedarf()` — total Bedarf: Regelbedarf + KdU + Mehrbedarfe
  - Added `ReconciliationLineItem` dataclass
  - Added `reconcile_bedarf_einkommen()` — full Bedarf-vs-Einkommen reconciliation
  - Added `detect_additionsfehler()` — arithmetic error detection (GS-010)
  - Added `aggregate_months()` — multi-month aggregation
  - Extended `process_extraction()` with reconciliation + additionsfehler checks
- Added `compute_reconciliation_exact_match()` to `eval/metrics.py`
- 200 total tests (67 new)

---

## 2026-07-13 — WP-24: Intertemporal law selection

### WP-24: Regime selection
- Created `app/services/regime.py` (193 lines):
  - `legal_regime(date)` — maps dates to 4 regime tags (a.F._vor_2023, a.F._2023, a.F._2025, n.F._2026)
  - `regime_transition_dates()` — returns key reform dates
  - `regime_for_period_range()` — handles period-splitting across 2026-07-01 boundary
  - `regime_banner()` — human-readable German regime description
- Modified `app/services/parameter_store.py`: `param()` accepts optional `regime` kwarg
- Modified `app/core/pipeline.py`: `PipelineState.legal_regime_banner`, injected into
  construction/generation prompts
- 40 tests

---

## 2026-07-13 — WP-30: Pseudonymization gate

### WP-30: Pseudonymization
- Created `app/services/pseudonymization.py` (923 lines):
  - Hybrid detection: regex for structured IDs (BG-Nummer, Aktenzeichen, SV-Nummer, Steuer-ID,
    IBAN, phone, email, street+number, PLZ, birth dates) + spaCy NER + first-name gazetteer +
    salutation heuristics
  - `PiiMapping` dataclass with `to_dict()`/`from_dict()` for DB serialization
  - `pseudonymize()`, `depseudonymize()`, `depseudonymize_tolerant()`
  - Correctly preserves: city names, Bundesländer, authority names, dates, EUR amounts, §§ references
- Added `pii_mapping` JSONB column to `CaseRun` (migration 010)
- Added `PSEUDONYMIZATION_ENABLED: bool = True` config setting
- Integrated into pipeline: pseudonymize before LLM calls, depseudonymize after
- 46 tests

---

## 2026-07-13 — WP-32: Goldset v0.2.0

### WP-32: Goldset v0.2.0
- Created `eval/goldsets/goldset-v0.2.0.yaml`: 12 cases
  - All 10 v0.1.0 cases with PII annotations (person, address, bg_nummer entries)
  - GS-011: OCR-degraded text with 7 PII types (IBAN, phone, email, address)
  - GS-012: Over-redaction trap (5 negative controls + 3 PII annotations)
- All PII metric functions already present in `eval/metrics.py`
- `eval/runner.py` already had PII fields + `--pii-gate on|off` CLI arg
- 92 goldset/eval/pseudonymization tests

---

## 2026-07-13 — WP-40: Action document generators

### WP-40: Document generators
- Created `app/services/document_generators.py` (839 lines):
  - 4 generators: Widerspruch, Widerspruch (Jahresfrist), § 44 Überprüfungsantrag, § 25 Akteneinsicht
  - `DocumentSlot` / `GeneratedDocument` dataclasses
  - `validate_slot_claim()` guardrail: only verified + user-confirmed claims usable
  - `select_generator()` — Frist-aware selection: open → Widerspruch, lapsed + fehlerhafte RBB →
    Jahresfrist, lapsed → § 44, kein VA → Akteneinsicht
  - Mandatory footer: disclaimer + generation metadata (version, profile, date)
- Created `app/api/routes/documents.py`: `POST /api/v1/documents/generate`,
  `GET /api/v1/documents/generator-options/{id}`
- 52 tests

---

## 2026-07-13 — WP-42: OCR confirmation gate

### WP-42: OCR quality gate
- Recalibrated `app/services/ocr_quality.py` scoring: 30% char integrity, 30% readable words,
  25% German word match, 15% structure
- Garbage/artifact penalties applied as multipliers
- Fixed pipeline test mock for OCR_QUALITY settings
- 12 tests

---

## 2026-07-13 — WP-41: Result Report & Case Journey Redesign

### WP-41: Result Report (Analyze Mode)
- **Frontend HTML** (`static/index.html`):
  - Replaced single `#result-report-content` placeholder div with 9 structured container IDs inside `#result-report-section`:
    `#deadline-banner`, `#result-summary`, `#findings-list`, `#calculation-diff`, `#frist-timeline`, `#traps-list`, `#next-steps`, `#doc-actions`, `#report-footer`
  - Each container is a stable anchor populated individually by JS; empty regions collapse via `:empty { display: none }`
  - Case header with `#report-case-actions` for back/chat buttons
- **Frontend JS** (`static/app.js`):
  - Rewrote `renderResultReport(output, caseRunId)` to populate each container by ID using shared components instead of building one monolithic HTML string
  - Render order per design doc §11.1: DeadlineBanner → SummaryBlock → ClaimList → CalcDiffTable → FristTimeline → TrapCallouts → NextSteps → DocActions → Footer
  - `renderClaimItem(finding, context)` now accepts the context flag (`'report' | 'pruefstand' | 'demo'`) per design doc §2.1 component contract; defaults to `'report'` for backward compatibility
  - Extracted `renderSummaryBlock`, `renderDocActions`, `renderReportFooter` helper functions
  - Fixed broken `elements.resultsSection` references (pointed to non-existent `#results-section`, would throw TypeError in `handleRemoveFile`, `handleUseText`, `handleUpload`, `handleAnalyze`, `handleCaseDelete`) — repointed to `#result-report-section`
  - SSE progress display (`#progress-section`, progress bar, stage indicators) unchanged
- **Frontend CSS** (`static/style.css`):
  - Added WP-41 report styles (additive, appended at end — no modifications to existing rules):
    - `.report-result` container + `.report-region` section spacing with `:empty` collapse
    - `.report-case-header` / `.report-case-title` / `.report-case-actions` layout
    - `.report-section-heading` uppercase label styling
    - `.report-summary` block with green/red/gray verdict variants (`.report-summary-green/red/gray`)
    - `.report-calc-summary` recessed summary line
    - `.report-doc-buttons` / `.report-doc-btn` / `.report-doc-status` / `.report-doc-output` / `.report-doc-rendered` / `.report-doc-text` / `.report-doc-warnings` document generation panel
    - `.report-footer` / `.report-footer-disclaimer` footer styling
    - `.report-error` error state
    - DeadlineBanner red-state pulse animation (`@keyframes report-deadline-pulse`, 2.2s, gated behind `prefers-reduced-motion: no-preference`) per design doc §3.2
    - Responsive rules at `max-width: 639px` for narrow screens
  - All shared components use `.c-` prefix (`.c-deadline-banner`, `.c-claim-list`, `.c-claim-item`, `.c-calc-diff`, `.c-frist-timeline`, `.c-trap-callout`, `.c-next-steps`, `.c-section-chip`); report-specific layout uses `.report-` prefix

---

## 2026-07-13 — WP-14: Prüfstand View (Goldset Browser, Eval Overlay, Demo Mode)

### WP-14: Prüfstand View
- **Backend** (`app/api/routes/goldset.py`, `app/api/routes/eval_reports.py`):
  - `GET /api/v1/goldset` — returns goldset manifest + 10 case summaries as structured JSON
  - `GET /api/v1/goldset/{case_id}` — returns full case detail (input document, findings, citations, calc diff, frist, traps, next steps)
  - `POST /api/v1/goldset/{case_id}/analyze` — triggers the standard 9-stage pipeline on a goldset case's input text, streams SSE
  - `GET /api/v1/eval/reports` — lists versioned eval report summaries (empty array if no reports)
  - `GET /api/v1/eval/reports/{report_id}` — returns full eval report JSON
  - YAML is parsed server-side via `eval/goldset_loader.py`; no YAML raw text ever appears in API responses
  - Goldset path and eval results dir configurable via `GOLDSET_PATH` / `EVAL_RESULTS_DIR` settings
  - File-mtime caching on goldset loads to avoid re-parsing on every request
  - Fixed 4 UP038 lint errors (use `int | float` instead of `(int, float)` in isinstance calls)
- **Frontend HTML** (`static/index.html`):
  - 4th mode toggle button "Prüfstand" in header alongside Analyze, Chat, Settings
  - `#pruefstand-mode` container with header, gallery, detail, and demo comparison sections
  - Version bumped to 1.0.0
- **Frontend JS** (`static/app.js`):
  - `fetchGoldset()` — loads goldset manifest, renders header + gallery
  - `fetchGoldsetCase(caseId)` — loads case detail, renders two-column layout
  - `fetchEvalReports()` — loads eval reports, renders aggregate tile or "Noch keine Prüfläufe" empty state
  - `startDemoAnalysis(caseId)` — POSTs to pipeline endpoint, streams SSE, renders comparison view
  - `renderPruefstandHeader(data)` — badges, baseline cards (Regelbedarf, § 11b Treppengrafik, Sanktionen, FristTimeline), open questions
  - `renderCaseGallery(cases)` — responsive grid of cards with verdict color bars
  - `renderCaseDetail(case)` — two-column: LetterRender (Behördenbrief) left, findings/calc/frist/traps/steps right
  - `renderEvalOverlay(reports)` — latest eval tile or clean empty state
  - `renderDemoComparison(caseData, pipelineResult)` — expected vs actual side-by-side
  - `renderFristTimelineSVG(frist, isFull)` — inline SVG timeline with 4 stations, delta labels, rollover arc
  - `renderDeadlineBanner(frist)` — 5-state hero (normal, amber, red, lapsed, kein VA)
  - `renderCalcDiffTable(rows)` — Jobcenter vs Korrekt vs Differenz with ▲/▼/— glyphs
  - `renderClaimItem(finding)` — traffic-light finding with § chips
  - Formatting helpers: `formatDate()`, `formatDateTime()`, `formatEuro()` (German locale)
  - Version bumped to 1.0.0
- **Frontend CSS** (`static/style.css`):
  - Warm-paper design tokens per `devdocs/design_v1.0.0.md` (additive — no regression to existing vars)
  - Component classes prefixed `c-` per design spec §15.2: `c-letter-render`, `c-deadline-banner`, `c-frist-timeline`, `c-claim-list`, `c-claim-item`, `c-section-chip`, `c-calc-diff`, `c-trap-callout`, `c-next-steps`, `c-eval-overlay`
  - § 11b Treppengrafik (step graphic) for Freibeträge baseline card
  - Responsive: gallery 1-col <640px, 2-col tablet, auto-fill desktop; detail stacks <768px
  - Version bumped to 1.0.0
- **Design system** (`devdocs/design_v1.0.0.md`):
  - 13-component shared library spec (DeadlineBanner, FristTimeline, ClaimList, ClaimItem, SectionChip, CalcDiffTable, NextSteps, TrapCallout, LetterRender, ExperimentalBadge, EvalOverlay, SummaryBlock, ConfidenceRibbon)
  - Warm-paper light theme as v1.0.0 default (D-2)
  - 4 locked decisions: +4-day Bekanntgabefiktion (D-1, goldset-authoritative), warm-paper default (D-2), Chat parked (D-3), spec persisted (D-4)

## 2026-07-12 — WP-21: Deterministic Fristen engine

### WP-21: Fristen engine
- `app/services/fristen.py` — pure, deterministic Widerspruchsfrist calculator:
  - `compute_widerspruchsfrist()` — main public function with 7 rule-stages:
    1. Non-VA check (§ 31 SGB X → `frist_typ="kein_va"`)
    2. Bekanntgabe fiction (§ 37 Abs. 2 SGB X, post-2025 reform: +4 days)
    3. Jahresfrist for missing/wrong RBB (§ 66 Abs. 2 SGG)
    4. 1-month Monatsfrist (§ 84 Abs. 1 SGG + § 188 Abs. 2 BGB)
    5. Workday rollover (§ 64 Abs. 3 SGG)
    6. OQ-1 flag (ambiguous 4-day fiction on weekends/holidays)
    7. Bundesland-specific holiday table (fixed + movable holidays 2024-2027)
  - `FristResult` dataclass with `bekanntgabe`, `frist_ende`, `frist_typ`,
    `rollover_applied`, `oq1_flag`, `oq1_alternate_ende`, `explanation_de`
  - Holiday tables: all fixed holidays per Bundesland, movable holidays
    (Karfreitag, Ostermontag, Christi Himmelfahrt, Pfingstmontag, Fronleichnam)
    computed from Easter dates 2024-2027
- `tests/unit/test_fristen.py` — 85 test cases covering all code paths,
  edge cases, and all 10 goldset cases (GS-001 through GS-010)
- `eval/metrics.py` — `compute_frist_exact_match()` now calls the Fristen engine
  against goldset widerspruchsfrist expectations instead of returning None
- `eval/runner.py` — Fristen column added to eval table output; `frist_exact_match`
  included in per-case metrics and aggregate computation

## 2026-07-12 — WP-22: Legal parameter store completion

### WP-22: Legal parameter store
- `app/db/models.py`: Added `regime` (String(50)) and `notes` (Text) columns to `LegalParameter`
- `alembic/versions/009_add_regime_and_notes_to_legal_parameter.py`: Migration adding both columns
- `app/services/parameter_store.py`: Added synchronous `param()` function backed by in-memory cache; added `reload_parameter_cache()` called at startup; extended `get_parameter_numeric()` / `get_parameter_json()` to return `"status": "verification_required"` for proposed rows with notes
- `app/main.py`: Lifespan now imports `async_session_factory` and calls `reload_parameter_cache()` after migrations
- `scripts/seed_legal_parameters.py`: Seeds 27 parameters (SGB II) — Regelbedarf 2024/2025, §11b brackets, Vermögensfreibeträge a.F., Vermögensfreibeträge n.F. (OQ-3/proposed), Sanktionen a.F. and n.F.
- `app/api/routes/meta.py`: Added `GET /api/v1/meta/legal-timestamp` returning `parameter_freshness` and `corpus_freshness`
- `static/index.html`: Added "Rechtsstand" indicator in analyze mode header
- `static/app.js`: Added `fetchRechtsstand()` — calls legal-timestamp endpoint, formats DD.MM.YYYY, applies warning (>90d) or stale (>180d) style
- `static/style.css`: Added `.rechtsstand*` styles and `.header-actions` wrapper

## 2026-07-12 — Phase 0 (Ground Truth) complete

### WP-11: Eval harness
- `eval/pipeline_adapter.py` — `PipelineOutput` dataclass + `run_pipeline_for_case()` adapter that drains SSE generator
- `eval/extractors.py` — deterministic norm reference, citation, assessment, calculation, and issue extractors (regex-based, no LLM)
- `eval/metrics.py` — `compute_issue_recall`, `compute_citation_precision`, `compute_calculation_exact_match`, `compute_frist_exact_match` (N/A until WP-21), `compute_assessment_match`
- `eval/runner.py` — CLI entry point (`python -m eval.runner`), per-case + aggregate tables, JSON report save, regression gate integration
- `eval/regression_gate.py` — per-case monotonic gate (D-6): strict on deterministic metrics, warn-only on LLM metrics
- Results stored as versioned JSON in `eval/results/`, not DB (YAGNI until WP-14 Prüfstand)

### WP-00: Repo inventory & gap report
- `devdocs/ARCHITECTURE-ACTUAL.md` — full module, pipeline, DB, LLM, config, and frontend map
- `devdocs/GAP-REPORT.md` — 13 gaps found vs roadmap §1 assumptions (G-001 through G-013)

### WP-00.5: Client consolidation + STAGE_NAME_ALLOWED fix
- Replaced 4 separate `OpenRouterClient` singletons with single shared factory in `router.py`
- Added `contextvars.ContextVar("case_id")` for future egress guard (WP-31)
- Updated 5 service modules (`reasoning.py`, `chat_reasoning.py`, `intake.py`, `case_chat.py`, `calculation.py`)
- Consolidated `main.py` shutdown to single `close_client()`
- Fixed `STAGE_NAME_ALLOWED` in `models.py` — removed `disclaimer_ack`, added `adversarial_review` and `calculation_check`
- Created `alembic/versions/008_fix_stage_name_allowed.py` migration

### WP-01: Baseline v0.1.0
- Tagged `v0.1.0` (canonical version from `pyproject.toml`)
- Created `.github/workflows/ci.yml` — lint, type-check, unit + integration tests on Python 3.11/3.12
- Created `devdocs/DECISIONS.md` — 10 ratified decisions, 3 open

### WP-02: Scope cut — Sozialrecht-only
- Added `LEGAL_AREA_TIER` dict in `models.py` + frontend
- Experimental badge on all non-Sozialrecht areas in intake UI
- Updated subtitle: "SGB II Bürgergeld (SGB X, SGG)"
- `.experimental-badge` CSS styling (amber, uppercase, tooltip)

### WP-10: Goldset integration
- Copied `goldset-v0.1.0.yaml` (10 cases) into `eval/goldsets/`
- Created `eval/goldset_loader.py` — Pydantic-typed YAML loader with audit function
- Validates against `LEGAL_AREA_ALLOWED`, case ID uniqueness, known assessment values
- Added `PyYAML` to project dependencies

---

## 2026-07-12 — v1.0.0 UI/UX design direction approved

### Added
- `devdocs/design_v1.0.0.md` — comprehensive UI/UX design specification for the v1.0.0
  release. Covers four work packages: WP-02 (Scope Cut / Experimental Badge), WP-14
  (Prüfstand View), WP-41 (Result Report & Case Journey Redesign), WP-42 (OCR
  Confirmation Gate). Defines a 13-component shared library, color token system, the
  FristTimeline showpiece, DeadlineBanner 5-state hero, traffic-light ClaimList,
  CalcDiffTable, OCR confidence gate, accessibility and responsive strategy.

### Decisions locked (design review)
- **D-1: Bekanntgabefiktion = +4 days** (strict goldset conformity). The goldset is the
  executable specification for all legal behavior — § 37 Abs. 2 SGB X is rendered as posting_date
  + 4 days. FristTimeline renders "+4 Tage Fiktion".
- **D-2: Warm-paper light theme** is the v1.0.0 default. Dark theme preserved as
  `[data-theme="dark"]` opt-in toggle. Unifies the current split light (Analyze) /
  dark (Chat) personality.
- **D-3: Chat mode parked but accessible.** Removed from primary mode toggle
  (Analysieren · Prüfstand · Einstellungen); reachable via secondary menu / direct route.
  Existing sessions preserved. No regression.
- **D-4: Design spec persisted** to `devdocs/design_v1.0.0.md` as implementation
  reference.

### Notes
- No code changes yet — this is design/strategy only. Implementation pending alignment
  on component build order.
- Typography direction: Source Serif 4 (headings) + Atkinson Hyperlegible (body) +
  IBM Plex Mono (numbers/§ chips). All Google Fonts, full German diacritic support.
- The existing `style.css` (v0.3.0, 2845 lines) will be refactored incrementally — no
  big-bang rewrite (regression risk). New component classes prefixed `c-`, tokens in
  `:root`.

---

## 2026-07-12 — WP-31: Inference profile layer + egress guard

### WP-31: Inference profiles + egress guard
- `config/inference_profiles.yaml` — versioned inference profiles (eu-avv, extern-openrouter, on-prem)
  with per-stage model/temperature overrides, host allowlists, compliance settings
- `app/services/inference_profiles.py` — `InferenceProfile` dataclass, `load_profiles()`,
  `get_active_profile()`, `validate_profile()`, and `reset_profile_cache()`
- `app/core/router.py` — `EgressBlockedError` exception, `_egress_check()` function with
  host allowlist enforcement + PII scan (casefolded + diacritics-normalized matching),
  wired into `chat_completion()`, `chat_completion_stream()`, and `get_embedding()`
- `app/core/config.py` — `INFERENCE_PROFILE` (default: `"eu-avv"`) and `AVV_OVERRIDE` settings
- `app/services/pseudonymization.py` — `get_known_values()` helper for egress guard
- `app/core/router.py` — `set_pii_context()` / `get_pii_context()` contextvars for
  passing PiiMapping to the egress guard
- `app/main.py` — startup validation: loads active profile, validates, logs warnings
- `app/api/routes/meta.py` — `GET /api/v1/meta/active-profile` endpoint with profile
  name, label, avv_status, pseudonymization
- Frontend: profile banner in header (green for signed, amber for not-signed), profile
  info in footer, `fetchActiveProfile()` JS function
- `tests/unit/test_inference_profiles.py` — 19 tests: YAML loading, profile resolution,
  AVV gate (blocked/allowed/override), disabled profile, validate warnings
- `tests/unit/test_egress_guard.py` — 21 tests: host allowlist, PII scan (block/pass/empty),
  casefold/diacritics matching, no cleartext in errors, client integration
