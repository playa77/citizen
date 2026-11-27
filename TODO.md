# Implementation order

## 1. Blocking TODO: module selection and session restore

**Backend prerequisite completed; GUI work remains separately owned.** The
owner's 2026-11-26 continuation direction in D-069 permits backend roadmap work
to continue without this agent taking ownership of GUI implementation or
claiming combined acceptance. Status: backend changes implemented and verified with the locked
development environment; owner-managed GUI/session work and combined acceptance
remain incomplete. Decisions:
[D-069](docs/decisions/D-069-module-selection-and-session-restore.md),
[D-070](docs/decisions/D-070-explicit-backend-module-scope.md).

All modules are peers. `sozialrecht` has no default or automatically loaded
role. On first GUI/desktop launch, present all modules for the user to choose
which to load. On later launches, also offer **Restore last session** as an
explicit choice. Restoring a previous choice does not make those modules
defaults for new sessions.

- [x] Remove the backend's dependency on a single `DEFAULT_MODULE`, including
  registry/startup validation, request resolution, corpus-source fallback,
  provenance and configuration examples. An omitted or empty selection must
  never silently select `sozialrecht` or another module.
- [x] Remove REST/MCP `default_module` and `is_default` entirely. D-070 records
  the owner's explicit exception to D-039. HTTP/MCP contract and regression
  checks pass in the full application/database suite.
- [ ] **GUI owner, outside this session:** implement the GUI/desktop startup
  module chooser. Present all modules
  without preselection or a preferred module; show availability and maturity
  separately. Installation/deployment enablement is not session selection.
- [ ] **GUI owner, outside this session:** persist the last session's module
  selection and session context, and
  offer **Restore last session** only when a saved session exists. A returning
  user can instead start a new session and choose modules again. Do not
  automatically restore or replace a missing/unavailable saved module.
- [x] **Backend:** honor explicitly supplied scope through analysis,
  conversations, corpus setup and provenance. Never infer scope from a global
  default or a module's catalog position.
- [ ] **GUI owner, outside this session:** pass the chosen/restored scope
  explicitly on requests, including corpus setup; complete client integration.
- [ ] Verify first launch, new session, explicit multi-module selection,
  relaunch and restore, unavailable saved modules, and empty selection across
  backend and GUI. Verify that Sozialrecht receives the same loading
  treatment as every other module and that existing privacy/tier gates hold.

The backend implementation and verification record is in D-070 and its linked
plan: 1,532 tests passed with four documented skips using the locked dev
dependencies and disposable PostgreSQL 16/pgvector. Lint/format, typing, module
validation and deterministic dossier/plain gates passed. Existing async
cancellation/dependency warnings and the skipped checks are recorded there.
The GUI is owned separately; its implementation and acceptance were not inspected
or verified in this session. This checklist requires both repositories.
The separately owned GUI and combined checks remain open; the owner's newer
direction permits backend step 2 to proceed (D-069, backend continuation direction).

## 2. Implement the remaining legal-area modules

- [x] WP-130 backend implementation: `schuldnerrecht` 0.2.0, core 3.5.0 /
  module API 3.3. Verification and operational limits: D-072 and its linked
  completion plan. Human reviews remain deferred until all modules are
  implemented (D-071); no verified promotion is claimed.
- [x] WP-131 experimental backend implementation: `mietrecht` 0.2.0,
  core 3.6.0 / module API 3.4. Regional-source coverage remains explicitly
  partial; unknown or expired designations return unavailable results.
  Verification and operational limits: [D-073](docs/decisions/D-073-wp131-tenancy-implementation.md).
  No human review/promotion, deployment corpus population or live-inference
  quality claim (D-071).
- [x] WP-132 experimental backend implementation: `arbeitsrecht` 0.2.0,
  core 3.7.0 / module API 3.5. Critical dismissal warning, separate knowledge
  facts, qualified statutory calculators and 18 synthetic cases. §38 timing
  limits remain explicit; non-working-day backwards targets require separate
  review. Verification and operational limits: [D-074](docs/decisions/D-074-wp132-employment-implementation.md).
  No deployment ingestion, live-inference or human-promotion claim (D-071).
- [x] WP-133 experimental backend implementation: `vertragsrecht` 0.2.0,
  core 3.8.0 / module API 3.6. Qualified consumer dates and arithmetic,
  EGBGB/EUR-Lex article identities, guarded drafts and 20 synthetic cases.
  §477 is not a filing deadline; direct EUR-Lex ingestion remains unverified
  because the publisher returned challenge/empty responses. Verification and
  limits: [D-075](docs/decisions/D-075-wp133-contract-implementation.md).
  Human review/promotion, deployment ingestion and live inference remain pending.
- [x] WP-134 experimental backend implementation: `verkehrsrecht` 0.1.0,
  core 3.9.0 / module API 3.7. Qualified objection dates, shared StPO rollover,
  selected speed-table and current-regime limitation/ban/register checks,
  guarded drafts and 20 synthetic cases. Annex/table retrieval remains partial;
  no complete BKat coverage, live quality or human promotion is claimed.
  Verification and limits: [D-076](docs/decisions/D-076-wp134-traffic-implementation.md).
- [ ] With the backend prerequisite complete and continuation approved, implement the remaining modules in the
  [module catalog](docs/module-catalog.md). Its queue describes implementation
  sequencing, not startup defaults or preselection. Keep the existing
  authoring, legal-source review, goldset and promotion gates.
