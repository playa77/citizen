# Changelog

All notable changes to the Citizen project are documented in this file.
Newest entries first. Dates in ISO 8601.

---

## 2026-07-12 — Phase 0 (Ground Truth) complete

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
