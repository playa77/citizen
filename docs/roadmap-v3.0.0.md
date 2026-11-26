# Citizen — Roadmap v3.0.0: Free Public Path — Modular Core, Appointment Dossier, Ten Area Modules

<!-- Version: 3.2.0 | 2026-11-26 — D-071: remove named approval gates; human review deferred until all modules are implemented.
     3.1.1 | 2026-11-26 — owner directs backend continuation; GUI remains separately owned; WP-130 foundation started.
     3.1.0 | 2026-11-26 — no default module (D-069/D-070): Sozialrecht's
     default designation superseded; WP-126 (explicit module selection and
     session restore) added as the first blocking task; D-039 exception for the
     removed catalog fields; P13 gated on WP-126.
     3.0.3 | 2026-11-17 — P12 backend status, WP-120 decided (D-067/D-068).
     3.0.2 | 2026-11-17 — P11 status added (D-066).
     3.0.1 | 2026-11-16 — release numbers shifted one minor: core 3.1.0
     went to the WP-97 follow-up (D-063), so P10 ships as 3.2.0, P11 3.3.0, P12 3.4.0
     (D-064); P10 status added.
     3.0.0 | 2026-11-16 -->
<!-- Supersedes: roadmap v2.0.0 (P6–P8, WP-60…WP-69) for all NEW work.
     Roadmap v2.0.0 remains the record of the compliance work it delivered;
     its open items are carried over in § 2 below. -->
<!-- Canonical version source: pyproject.toml. Baseline: v2.0.0. -->
<!-- Phase/WP numbering continues the decade scheme: P9→WP-90s, P10→WP-100s,
     P11→WP-110s, P12→WP-120s, P13→WP-130s (one WP per module, sub-WPs .1–.9),
     Track G→WP-140s. Numbering is identity, not order — order is § 10. -->
<!-- Decisions: D-034 … D-041 (appended to DECISIONS.md on 2026-11-16).
     Amended by D-069 and D-070 (2026-11-25), kept as individual decision
     records: the owner deliberately removed the root DECISIONS.md and
     CHANGELOG.md in `dead422`; they are not recreated. References to them
     below are historical. -->
<!-- Architecture: ARCHITECTURE.md · Module scope: docs/module-catalog.md -->

---

## 0. Baseline and Trigger

### 0.1 Baseline (v2.0.0, as shipped)

API-only FastAPI service (D-025) analysing SGB II/X Bescheide: 9-stage
evidence-bound pipeline, deterministic Fristen and SGB II calculation engines,
versioned parameter store, intertemporal regime handling, pseudonymization +
egress guard + inference profiles, goldset v0.2.0 + eval harness with
regression gate, `DEPLOYMENT_MODE` dev/self/provider (D-019), disclaimer-ack
gate, Art. 50 disclosure/provenance (D-032), purpose-drift lint (D-020),
PostgreSQL-only (D-024). Nine further area keys exist as **experimental**
prompt profiles without engines or goldsets.

### 0.2 Trigger

Owner decision of 2026-11-16 (D-034): Citizen follows the **free public path**
— MIT, non-commercial, not built for lawyers. The product is a client-side
preparation assistant: a person arrives at the lawyer or advice-center
appointment with the information the professional needs to work efficiently.
Concretely the owner instructed:

1. Redesign the project so the current Sozialrecht implementation is a
   **pluggable module**, still the **default** when nothing else is configured
   (D-036). *Default designation superseded on 2026-11-25 (D-069): no module
   is a default; Sozialrecht is one module among the others.*
2. Queue **ten further areas** of German law that affect citizens as natural
   persons, each as a full module serving the same API (D-038):
   Schuldner-, Miet-, Arbeits-, Verbraucher-/Vertrags-, Verkehrs-/Bußgeld-,
   Familien-, Aufenthalts-, Steuer- (ESt), Erb- und Strafrecht.
3. Include the full free-path scope: appointment dossier, module platform,
   polished consumer UI with plain-language layer, funding and governance.
4. Versioning: this roadmap is v3.0.0; the API stays `/api/v1`, additive only
   (D-039). *One owner-authorized exception: D-070 removes `default_module`
   and `is_default` from the module catalog.*

### 0.3 Why this is a re-founding, not a pivot

The v2.0.0 compliance program was designed for exactly this product: the
declared purpose was already claimant-side self-help (D-020), the endpoint
already "jede Sozialberatungsstelle". The free path keeps the lowest
regulatory friction of all evaluated paths (own-matter RDG posture, FOSS
carve-out of the AI Act with Art. 50 already implemented, no commercial
UWG/pricing exposure). What changes is **breadth** (eleven areas instead of
one) and **surface** (dossier + UI). Both change the declared purpose, so
D-020 is widened by D-035 rather than silently stretched.

### 0.4 Governing principles for every work package

- **Implementation before human approval rounds (D-071).** Implement all queued
  modules before requesting remaining human approvals or reviews. No person's
  name or sign-off is an implementation gate. Automated checks and source
  verification continue; review metadata remains draft/proposed until review
  occurs. Human review, promotion and release readiness are recorded separately
  from completed implementation.
- **Prepares, does not advise.** D-021 invariant in every module.
- **Explicit module selection, no default (D-069/D-070).** Only modules the
  user has selected (or explicitly restored) are in scope. An omitted or empty
  scope selects no legal module: no borrowed persona, prompt, parameter
  domain, template or unscoped retrieval, and no module in provenance. Catalog
  listings and preset suggestions never load a module. Missing or unavailable
  selections are surfaced, never substituted.
- **Every date and every euro comes from a deterministic engine**, never from
  an LLM guess.
- **Every correctness surface is goldset-gated** — including plain-language
  simplification.
- **Depth before breadth:** module refactor → dossier → module platform → UI
  → explicit module selection (WP-126) → area modules. Breadth without the
  dossier is feature theatre.
- **Everything versioned** (ARCHITECTURE.md § 6): core, module, parameter set,
  goldset, dossier schema, provenance spec, disclaimer.

---

## 1. Decisions (ratified 2026-11-16, see DECISIONS.md)

| ID | Tag | Decision |
|---|---|---|
| D-034 | R2 | Free public path: MIT, non-commercial, no Kanzlei features |
| D-035 | R2 | Declared purpose widened to citizen-side self-help and appointment preparation in own matters across modules (amends D-020) |
| D-036 | R2 | Core + module architecture; Sozialrecht = first module and `DEFAULT_MODULE` — *default designation superseded by D-069; architecture stands* |
| D-037 | R2 | Module enablement defaults keyed to `DEPLOYMENT_MODE` |
| D-038 | R1 | Queue of ten modules, order, legacy-key mapping |
| D-039 | R2 | `/api/v1` stays, additive only; versioning scheme for core/modules/artefacts — *owner-authorized exception in D-070 for `default_module`/`is_default`; otherwise stands* |
| D-040 | PENDING | Consumer UI lives in a separate repository (`citizen-web`); D-025 stands for this repo |
| D-041 | R1 | Licensing: all first-party modules MIT, no CLA; AGPL components (gettsim) only as unmodified sidecars |

### 1.1 Amending decisions (2026-11-25)

| ID | Tag | Decision |
|---|---|---|
| D-069 | R2 | No module is a default. A fresh GUI session presents all modules for explicit selection, none preselected; with a prior session, startup also offers **Restore last session** (explicit action, sets no default for new sessions). Enablement and maturity determine availability, not loading. Removing the fallback and implementing selection/restore is the **first implementation task**; no further legal-area modules until its TODO checklist passes. Supersedes the default designation in D-036; D-037, D-039 and D-067 remain applicable. |
| D-070 | — | Explicit backend module scope: `default_module`/`is_default` removed from REST and MCP (exception to D-039); no configured default; empty scope selects no legal module; deterministic preparation without inference or retrieval when no usable profile is selected (no neutral inference profile); explicit template IDs and parameter domains; no-match presets return none, ties return all equally best candidates; unconfigured corpus sources are empty; `/goldset` stays the explicit Sozialrecht compatibility alias. Backend verified 2026-11-26; GUI acceptance open. |

D-070 carries no R-tag in its record; its stated reversibility is "reversible
in code; clients must adapt to removed fields".

---

## 2. Carry-over from roadmap v2.0.0

Open items verified against the repository on 2026-11-16:

| ID | Item | Evidence | Lands in |
|---|---|---|---|
| C-1 | D-021 (RDG single-case invariant) is cited as built but was never appended to the ledger — only proposed in roadmap v2.0.0 § 1 | `DECISIONS.md` has no D-021 entry | WP-90 |
| C-2 | `AI-USAGE.md` (WP-63, D-022) not created | file absent | WP-140 |
| C-3 | Purpose-drift lint does not scan `DISCLAIMER_*.md`; two default globs match nothing (D-029) | `scripts/check_purpose_drift.py` `DEFAULT_TARGETS` | WP-96 |
| C-4 | Art. 50(2) coverage gaps: conversation first-message pipeline terminal event and case-chat `done` carry no provenance (D-032) | D-032 sub-decisions | WP-96 |
| C-5 | Provider go/no-go artefact (WP-69) and DPIA/AVV chain (WP-68) not present as documents | no `PROVIDER-GO-NOGO.md`, no DPIA document | WP-125 (re-scoped for consumer distribution) |

---

## 3. Phase P9 — Module Architecture (Sozialrecht becomes module 1)

**Goal:** the core contains no area-specific knowledge; Sozialrecht runs as
`modules/sozialrecht` with zero behaviour change. **Release: core 3.0.0,
`sozialrecht` module 1.0.0.**

**Status note (2026-11-26, D-069/D-070):** P9 shipped Sozialrecht as the
configured default and implicit fallback (`DEFAULT_MODULE` in WP-91, the
byte-identical no-`legal_areas` behaviour in WP-97). Both are superseded: the
setting, its startup requirement and the catalog default fields are removed,
and empty scope now resolves to no module (WP-126). The WP text below remains
the record of what P9 delivered.

### WP-90 — Ratify and document
- Append C-1 (D-021) to the ledger as a ratification event.
- Freeze a **v2.0.0 baseline eval report** for goldset v0.2.0 (`--save`);
  this is the zero-regression reference for the P9 exit gate.
- Exit: baseline report committed under `eval/results/`; D-021 in ledger.

### WP-91 — Module contract and registry
- `app/modules/sdk.py` (stable import surface), `manifest.schema.json`,
  `registry.py` (discover → validate → enable → resolve), settings
  `DEFAULT_MODULE` (default `sozialrecht`), `ENABLED_MODULES` (default: tier
  rule of D-037). conftest defaults for both. *`DEFAULT_MODULE` removed by
  D-070.*
- Module lint: module code imports only `app.modules.sdk`.
- Exit: registry unit tests; startup refuses an invalid enabled manifest.

### WP-92 — Fristen core split
- Move calendar, holidays, Bekanntgabe fiction library, rollover library,
  Rechtsbehelfsbelehrung extension into `app/fristen/`; implement the
  `fristen.yaml` spec evaluator (ARCHITECTURE.md § 2.3).
- Express the existing SGB X/SGG rules as `modules/sozialrecht/fristen.yaml`.
- Exit: every existing `tests/unit/test_fristen.py` case passes through the
  spec path unchanged; new spec-evaluator tests.

### WP-93 — Extract Sozialrecht
- Move into `modules/sozialrecht/`: prompts, intake routing, presets,
  corpus scope, parameters (seed loader replaces
  `scripts/seed_legal_parameters.py`), calculators (`rules_engine.py`,
  calculation extraction prompt), regime provider, document templates,
  goldset v0.2.0. Full list: ARCHITECTURE.md § 8.
- Remaining nine legacy areas become **stub modules** at tier
  `experimental` carrying their existing prompt profiles and corpus mapping —
  behaviour preserved, no engines (`schenkungsrecht` as alias of `erbrecht`,
  `verwaltungsrecht` folded into the core procedural library, `andere` as
  catch-all; D-038).
- Exit: grep of `app/` for area ids returns only registry/alias tables.

### WP-94 — Data model migration
- Migration `013`: `legal_module` table; `case_run_area.legal_area` FK +
  `module_version`; drop CHECK `ck_case_run_area_legal_area`;
  `legal_parameter.domain` `sgb2 → sozialrecht`. Idempotent DDL (D-005/D-027
  practice), single linear chain.
- Exit: G2 (single head) green; fresh and upgraded DBs identical.

### WP-95 — API additions (additive)
- `GET /modules`, `GET /modules/{id}`, `GET /modules/{id}/goldset`; error codes
  `MODULE_NOT_ENABLED`, `MODULE_UNKNOWN`; `resolved_modules` in responses;
  `modules` key on `/meta/version`.
- `API_DOCUMENTATION.md` updated in the same change (G4 parity guard).
- Exit: route-surface and doc-parity tests green; existing routes unchanged.

### WP-96 — Compliance deltas for modularity
- Provenance spec `citizen-provenance-v1.1`: `modules[{id, version,
  parameter_set}]` (additive); close C-4 gaps.
- Lint: add `DISCLAIMER_*.md`, `ARCHITECTURE.md`, `docs/*.md`,
  `modules/*/copy/**`, `modules/*/DISCLAIMER_ADDENDUM.md`; per-module deny
  phrases from manifests; drop dead globs (C-3).
- `DISCLAIMER_DE.md` / `DISCLAIMER_EN.md` v3.0.0: Part A/C rewritten for the
  widened purpose (D-035), new Part D (module addenda); `DISCLAIMER_VERSION`
  bump.
- Exit: lint green over the extended scan set; disclosure tests extended.

### WP-97 — P9 exit gate
- Goldset v0.2.0 eval **zero regression** vs WP-90 baseline; full suite +
  ruff + mypy strict + lint green; requests without `legal_areas` behave
  byte-identically (golden SSE transcripts). *Superseded by D-070: such
  requests now receive deterministic preparation only.*
- Cut core **3.0.0**; `sozialrecht` **1.0.0**; CHANGELOG + D-entry.

---

## 4. Phase P10 — The Appointment Dossier (Mandatsvorbereitung)

**Goal:** the product's central deliverable exists for Sozialrecht and is
generic for every later module. **Release: core 3.2.0** (planned as 3.1.0;
see D-064).

**Status (2026-11-16, D-064/D-065):** WP-100…WP-104 built. Exit criteria:
schema-valid dossier for every goldset case ✓ (12/12), deadline completeness
100 % ✓ (dossier goldset v1.0.0, `eval/dossier_eval.py`); owner review of two
PDF samples with a practitioner — **open**.

- **WP-100 — Dossier schema.** JSON Schema `citizen-dossier-v1.0` (8 sections,
  ARCHITECTURE.md § 3.7); storage decision (`case_run.dossier_json` vs table).
- **WP-101 — Chronology builder.** Sachverhalts-Chronologie from confirmed OCR
  texts + extracted dates; user confirmation step via API.
- **WP-102 — Module dossier content.** `dossier.yaml` (Dokumentencheckliste,
  Fragenliste) for Sozialrecht; generic merge for multi-module cases.
- **WP-103 — Generator + export.** `POST/GET /cases/{id}/dossier`;
  print-ready PDF (local rendering, no external service) + JSON; provenance
  marker embedded in both.
- **WP-104 — Dossier goldset.** Expected dossier sections per goldset case;
  metrics: deadline completeness (must be 100 %), checklist recall,
  chronology accuracy.
- **Exit:** every goldset case produces a schema-valid dossier; deadline
  completeness 100 %; human review of two PDF samples is deferred under D-071.

---

## 5. Phase P11 — Module Platform

**Goal:** modules can be developed, versioned, updated and contributed
safely. **Release: core 3.3.0.**

**Status (2026-11-17, D-066):** WP-110…WP-116 built; core 3.3.0,
`sozialrecht` 1.4.0, module contract 3.1. Exit criterion ✓ — pinned by
`tests/integration/test_p11_exit.py` (scaffold → validate → signed parameter
feed → `/modules`, through the shipped CLIs). Not verified in the build
environment: live runs against gesetze-im-internet.de, rechtsprechung-im-
internet.de and Open Legal Data (fixtures only); open owner actions: publish
a release key, decide whether the disclaimer names community modules.

- **WP-110 — Module versioning and errata.** Module semver rules
  (ARCHITECTURE.md § 6.2), per-module CHANGELOG, errata surfacing on
  `/modules/{id}`, `case_run.module_version` queries for affected cases.
- **WP-111 — Signed update channel.** Static signed feeds (GitHub releases)
  for parameter sets and corpus change notices; signature verification before
  apply; no telemetry.
- **WP-112 — Out-of-tree modules.** Entry-point loading at tier `community`;
  never enabled in `provider` unless explicitly listed.
- **WP-113 — Corpus automation.** Daily `gii-toc.xml` change detection for
  gesetze-im-internet sources; RII/OLDA case-law ingestion (free, keyless)
  for verified modules.
- **WP-114 — Citation service.** German §/ECLI citation parser + verification
  (eyecite pattern, BSD-licensed reference, MIT reimplementation).
- **WP-115 — Module authoring kit.** `scripts/new_module.py` scaffold,
  manifest validator CLI, `docs/MODULE-AUTHORING.md`, goldset template.
- **WP-116 — MCP surface (optional).** Read-only MCP server over modules,
  corpus and deadline catalog for civic-tech integrations.
- **Exit:** a scaffolded test module passes validation, ships a parameter
  update via the signed feed, and is visible via `/modules`.

---

## 6. Phase P12 — Consumer UI and Plain-Language Layer

**Goal:** a polished, accessible, local-first guided journey for citizens.
**Release: `citizen-web` 1.0.0; core 3.4.0 (plain-language API fields).**

**Status (2026-11-17, D-067/D-068):** WP-120 decided — the UI is
`playa77/citizen-gui`, D-025 stands. Backend half built in core 3.4.0
(`sozialrecht` 1.5.0, module contract 3.2): WP-122 plain-language layer +
gate, WP-123 duty-of-care rules on copy and `bcp47`, WP-124 plumbing
(`chat_endpoint`, `on-prem` configured, disabled), WP-125 plain disclaimer/ack,
privacy view, go/no-go checklist (`docs/public-release-go-nogo.md`). Open:
human copy review (OQ-3), local-model measurement (OQ-2), GUI work
(WP-121, WP-123 UI, integration findings in `docs/citizen-gui-checkup.md`),
P12 exit (usability test, accessibility audit).

**Status (2026-11-26, D-069/D-070):** WP-126 added. Backend half verified on
2026-11-26 (unreleased; branch/PR publication authorized, no release
authorized). GUI chooser, local session persistence, restore and combined
acceptance are open, assigned to the GUI owner, and block all further
implementation work, including legal-area modules (D-069).

- **WP-120 — UI location decision (D-040).** Owner confirms separate
  repository consuming `/api/v1` (recommended) or reverses D-025.
- **WP-121 — Guided journey.** Module selection (WP-126: full catalog, none
  preselected, or explicit *Restore last session*; intake presets may suggest
  but never load modules) → upload → OCR confirm →
  analyse → **Fristen banner (impossible to miss)** → findings in plain
  language → adjudication → dossier → drafts.
- **WP-122 — Plain-language layer.** Per finding type and deadline:
  Bürgersprache DE, Leichte Sprache DE for critical copy, EN; further
  languages per module need (M7). Served as module `copy/` content; API adds
  `plain` fields (additive). Language is goldset-gated (OQ-3).
- **WP-123 — Accessibility.** WCAG 2.1 AA / BITV 2.0 target; screen-reader
  journey test; no discouraging language (duty-of-care checklist).
- **WP-124 — Consumer inference default.** Measure local-model runtimes against
  the goldset (OQ-2); ship the consumer distribution with an `on-prem`
  profile default if it meets the gate, otherwise documented EU-API option.
- **WP-125 — Consumer compliance surfaces.** Art. 50 notice in the UI,
  disclaimer in Bürgersprache, ack flow; privacy profile for B2C distribution;
  re-scoped C-5 go/no-go checklist for a public release.
- **WP-126 — Explicit module selection and session restore (D-069, D-070).**
  **First blocking task:** no further implementation work, including
  WP-130…WP-139, starts until the D-069 TODO checklist passes. Release: none
  authorized; the backend changes are unreleased.
  - *Backend (core repo; verified 2026-11-26):*
    - `DEFAULT_MODULE` and its startup requirement removed; tier, manifest
      and enablement validation retained.
    - `default_module` and `is_default` removed from REST and MCP list/detail
      responses. No deprecated, null, false or replacement field remains
      (exception to D-039).
    - Omitted or empty scope selects no legal module, including in provenance
      and derived content (calculators, regime providers, dossier/plain
      content).
    - Absent scope, procedural-only scope, or a selected module without a
      usable profile → deterministic preparation only: no retrieval, no
      inference, successful SSE envelope shapes kept, selection requirement
      explained by deterministic output. Conversation and case chat respond
      the same way before any client or retrieval access. No neutral
      inference profile.
    - Document templates resolve from recorded case scope; missing or
      ambiguous module → documented client error listing eligible choices;
      an explicit choice must belong to the case scope. Parameter domains
      must be explicit and nonempty.
    - Presets: no match → no preset; ties → all equally best candidates in
      `suggestions` (scalar fields only for a unique winner); suggesting does
      not load.
    - Corpus: unconfigured sources are empty; a persisted empty selection
      stays empty; explicit source selection and one-shot job overrides
      preserved.
    - `/goldset` stays the explicit, documented Sozialrecht compatibility
      alias. Offline module validation composes peer tables without choosing
      a module. Re-evaluation reads recorded case scope and refuses
      unusable or unavailable scope.
    - Prompt set 3.1.0 (preset output example no longer names a preferred
      module); no live quality evaluation ran. Supporting corrections:
      D-070 § "Supporting corrections found in contract review".
  - *GUI (`playa77/citizen-gui`; open, GUI owner):*
    - Fresh session: full catalog, no preselection. With a prior session:
      also offer **Restore last session**. Restoring is explicit, recovers
      the prior selection and context, and sets no default for new sessions.
    - Persist session context locally; revalidate every saved area against
      the catalog's `area_keys` and `enabled`; surface every missing or
      disabled selection without substitution.
    - Send the complete chosen/restored `legal_areas` on every analysis and
      conversation request; case operations use recorded case scope; corpus
      setup uses explicit source keys through existing endpoints.
    - Handle selection-required results and document-module errors; stop
      reading the removed catalog keys.
    - No restore endpoint or backend session storage is introduced.
  - **Exit:** the D-069 TODO checklist passes, including first-launch,
    relaunch, restore and cross-repository combined acceptance, which backend
    completion alone does not establish.
- **Exit:** usability test with ≥ 5 people from the target clientele (via a
  partner Beratungsstelle) completing the journey on a synthetic Bescheid;
  accessibility audit passed.

---

## 7. Phase P13 — Area Modules M1–M10

**Goal:** ten further modules reach `verified`, each serving the same API.
Profiles and statutory anchors: `docs/module-catalog.md`.

**Owner continuation direction (2026-11-26):** backend WP-126 is complete.
The owner instructed backend implementation to continue; GUI implementation
and combined acceptance remain separately owned and unverified here. This
supersedes the wait for GUI acceptance in the earlier status and sequencing
text above and below; see D-069's backend continuation direction.

**Backend gate (D-069, amended 2026-11-26):** backend continuation is authorized. Each
module is a peer: no module is preselected, and none serves as another's
fallback.

Each module is one WP with the same nine sub-WPs:

| Sub-WP | Content |
|---|---|
| .1 | Scope & sources: verify statutory anchors (dated), manifest, corpus scope ingested |
| .2 | Parameters with source quotes and validity periods; human review deferred under D-071 |
| .3 | Deadline specs + golden date tests |
| .4 | Calculators (pure, parameter-backed, cent-exact tests) |
| .5 | Action-draft templates (`[BITTE PRÜFEN]` slots) |
| .6 | Intake schema + dossier checklist + lawyer-question list |
| .7 | Plain-language copy (DE Bürgersprache, EN; Leichte Sprache for critical); human review deferred under D-071 |
| .8 | Goldset ≥ 15 cases, published eval report, gate thresholds |
| .9 | Compliance: disclaimer addendum, deny phrases, special regimes; human promotion approval and release review deferred under D-071 |

| WP | Module | Notes |
|---|---|---|
| WP-130 | M1 `schuldnerrecht` | Pfändungstabelle parameter feed (annual, 1 July) |
| WP-131 | M2 `mietrecht` | Landesverordnungen sourcing (Kappungsgrenze, Mietpreisbremse) |
| WP-132 | M3 `arbeitsrecht` | § 4 KSchG banner = `critical` |
| WP-133 | M4 `vertragsrecht` | EUR-Lex source type for VO 261/2004 |
| WP-134 | M5 `verkehrsrecht` | builds core OWiG procedure library |
| WP-135 | M6 `familienrecht` | Düsseldorfer Tabelle reuse terms (OQ-7) |
| WP-136 | M7 `aufenthaltsrecht` | requires P12 i18n; strongest duty-of-care profile |
| WP-137 | M8 `steuerrecht` | StBerG: own-matter only; no gettsim embedding (D-041) |
| WP-138 | M9 `erbrecht` | absorbs `schenkungsrecht` alias |
| WP-139 | M10 `strafrecht` | Art. 10 DSGVO inference policy decision in .1 |

**WP-130 implementation (2026-11-26):** `schuldnerrecht` 0.2.0 implements
domestic service-based deadlines, versioned qualified calculators, guarded
drafts, public intake schema, dossier content, a debt-specific profile and
DE/EN/de-LS copy. Core 3.5.0 / module API 3.3 adds the shared service-input and
source-storage support. Twenty synthetic cases, dossier/plain reports and
official attachment-table comparison evidence are included. See
[D-072](decisions/D-072-wp130-backend-implementation.md) and the
[completion plan](superpowers/plans/2026-11-26-wp130-completion.md).
Actual deployment corpus ingestion and live-inference evaluation are not
claimed. Human approval/reviews remain deferred under D-071; the module is
experimental, not promoted or released.

Modules may run in parallel once P11 and WP-126 exit (community stewards); the queue
order is the maintainer's default order. A module that cannot pass its gate
stays `experimental` — it is never promoted to meet a date.

---

## 8. Track G — Sustainability and Governance (WP-140s; starts immediately)

- **WP-140 — Prototype Fund application.** Window closes **2026-11-30**
  (14 days from this roadmap). Pitch: local-first, evidence-bound,
  AI-Act-compliant legal self-help with public eval metrics; phases P9–P10
  as the funded scope. Also create `AI-USAGE.md` (C-2) — applicants are
  better served by transparent authorship.
- **WP-141 — NLnet application.** Deadline **2027-01-03**; check fit with the
  stricter generative-AI policy (Oct 2026) first (OQ-5).
- **WP-142 — GOVERNANCE.md + MAINTENANCE.md.** Maintainer, module stewards,
  parameter-steward duty per module, review rules, bus-factor plan, release
  cadence.
- **WP-143 — CONTRIBUTING.md.** Modules are the contribution surface; MIT
  inbound = outbound, no CLA (D-041); DCO sign-off.
- **WP-144 — Institutional adopters.** Partner Beratungsstellen /
  Verbraucherzentralen / Mietervereine / Schuldnerberatungen as validators,
  plain-language reviewers and goldset case sources (synthetic only).
- **WP-145 — Public quality evidence.** Publish eval reports per module and
  release; the goldset is the public quality claim.

---

## 9. Roles

| Role | Responsibility |
|---|---|
| Maintainer (Dan) | core, releases, decision ledger, final review |
| Module steward | one per module: scope, parameters, goldset, copy review routing |
| Parameter steward | per module: transcribes and dates parameter changes until LegalDocML.de makes them machine-readable |
| Plain-language reviewer | per module/language; correctness of simplification |
| Practitioner reviewer | lawyer/advisor sample review of dossiers (not legal advice to the project; quality feedback) |

---

## 10. Sequencing and dates

```
2026-11 ─ Track G: WP-140 (Prototype Fund, due 2026-11-30)
        ─ P9  WP-90 → WP-91 → (WP-92 ∥ WP-94) → WP-93 → WP-95 → WP-96 → WP-97  ⇒ core 3.0.0
2026-12 ─ 2026-12-02: Art. 50(2) transition end — binds only in provider mode
2027-01 ─ Track G: WP-141 (NLnet, due 2027-01-03)
        ─ P10 dossier                                                         ⇒ core 3.2.0
        ─ P11 module platform (WP-115 authoring kit first)                   ⇒ core 3.3.0
        ─ P12 consumer UI (may start in parallel with P11 after WP-120)     ⇒ citizen-web 1.0.0, core 3.4.0
        ─ WP-126 explicit module selection (D-069/D-070; backend ✓ 2026-11-26,
          GUI + combined acceptance open)  ⇒ gate: blocks all further implementation
        ─ P13 (after WP-126) M1 → M2 → M3 → M4 → M5 → M6 → M7 (needs P12 i18n) → M8 → M9 → M10
```

No calendar commitments beyond the external deadlines are made here: this is a
single-maintainer, grant-dependent project, and the gates — not the dates —
decide promotion. Funding outcomes re-plan P12/P13 capacity by decision entry.

---

## 11. Explicitly out of scope

- Kanzlei features: billing, RVG invoicing, Aktenverwaltung, multi-mandant,
  SSO (D-034).
- Monetization, accounts, hosted multi-tenant service.
- Authority-side use of any module (D-020/D-035); the lint enforces it.
- Drafting of substantive legal reasoning for court filings (Klagebegründung,
  Asylvortrag, Verteidigungsschrift) — drafts stay form-level building blocks.
- Embedding AGPL/GPL code into the MIT core (D-041).
- Any `/api/v2` (opened only by a dedicated decision).
- A default or implicit fallback module, in the backend or the GUI (D-069).
- A neutral, module-less inference profile (rejected by the owner, D-070).

---

## 12. Open questions

| ID | Question | Owner | Blocks |
|---|---|---|---|
| OQ-1 | Prototype Fund: apply in class 03? Which stream (data security / software infrastructure / resilience)? | Dan | WP-140, within days |
| OQ-2 | Consumer default inference: which local runtime/model passes the goldset gate? | maintainer | WP-124 |
| OQ-3 | Human review of plain-language simplifications | Later cross-module review phase | Deferred until all modules are implemented (D-071); does not block WP-122 or .7 implementation |
| OQ-4 | Module order: confirm the necessity hypothesis with user-need evidence (adopter case statistics) | Dan + adopters | P13 order |
| OQ-5 | NLnet generative-AI policy fit | Dan | WP-141 |
| OQ-6 | UI repository location (D-040) — **resolved 2026-11-17 (D-067): `playa77/citizen-gui`** | Dan | WP-120 |
| OQ-7 | Reuse terms of Düsseldorfer Tabelle and Landes-Mietrechtsverordnungen as parameter data | counsel/adopters | WP-131, WP-135 |
| OQ-8 | Art. 10 DSGVO: may Strafrecht cases ever use external inference, even pseudonymized? | counsel | WP-139 |
| OQ-9 | StBerG boundary for the Steuerrecht module's advice-center use (currently disabled) | counsel | WP-137 |

---

*Changes to this document follow semantic versioning. This is roadmap v3.0.0;
it supersedes roadmap v2.0.0 for new work only and does not alter the record of
completed P0–P8 work. Legal characterisations herein are engineering-planning
inputs, not legal advice.*
