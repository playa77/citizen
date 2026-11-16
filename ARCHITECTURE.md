# Citizen — Architecture v3.0.0: Core + Legal-Area Modules

<!-- Version: 3.0.0-draft.2 | 2026-11-16 — WP-93: § 2.1/2.2 layout + manifest keys as
     built (prompts, document_templates), § 8 status column. -->
<!-- Status: TARGET architecture, partly delivered: WP-91 (registry/SDK),
     WP-92 (Fristen core) and WP-93 (Sozialrecht extraction) are in the code;
     § 8 marks what remains (WP-94 data model, WP-95 API). Every "target" statement below is delivered by
     docs/roadmap-v3.0.0.md; "as-is" statements describe the code today. -->
<!-- Decisions: D-034 … D-041 in DECISIONS.md. -->
<!-- Canonical package version: pyproject.toml (stays 2.0.0 until P9 exit). -->

---

## 0. Purpose of this document

Citizen is re-founded on the **free public path** (D-034): an MIT-licensed,
non-commercial, local-first assistant that helps a natural person understand a
letter or Bescheid in **their own matter**, meet every deadline, and arrive at a
lawyer or advice-center appointment with the information that person needs to
work efficiently. It prepares; it does not advise.

The v2.0.0 code is a single-area system: Sozialrecht (SGB II/X) logic is
hard-wired into the pipeline, the engines, the prompts and the data model. This
document defines the target structure that turns that system into a
**domain-neutral core** plus **pluggable legal-area modules**, with the existing
Sozialrecht implementation as the first module and the default (D-036).

Reading order: § 1 (shape) → § 2 (module contract) → § 3 (core services) → § 4
(data model) → § 5 (API) → § 6 (versioning) → § 7 (compliance per module) →
§ 8 (as-is coupling map, i.e. the refactor work list).

---

## 1. Shape of the system

```
                          ┌────────────────────────────────────────────┐
  client (API consumer,   │                CITIZEN CORE                 │
  later: citizen-web) ───►│  /api/v1  (FastAPI, SSE)                    │
                          │  ├─ module registry  (load · validate ·     │
                          │  │                    enable · resolve)     │
                          │  ├─ pipeline orchestrator (9 stages)        │
                          │  ├─ evidence binding + quote verification   │
                          │  ├─ Fristen core (calendar, Bekanntgabe,    │
                          │  │   rollover, Rechtsbehelfsbelehrung)       │
                          │  ├─ parameter store (versioned, namespaced) │
                          │  ├─ corpus framework (fetch · chunk · embed)│
                          │  ├─ document renderer ([BITTE PRÜFEN] slots)│
                          │  ├─ dossier generator (PDF + JSON)          │
                          │  ├─ intake interview engine                 │
                          │  ├─ pseudonymization · egress guard ·       │
                          │  │   inference profiles                      │
                          │  └─ compliance: DEPLOYMENT_MODE, disclaimer │
                          │     ack, Art. 50 disclosure/provenance,     │
                          │     purpose-drift lint, audit trail         │
                          └───────────────┬────────────────────────────┘
                                          │ typed module contract (§ 2)
        ┌───────────┬───────────┬─────────┴─┬───────────┬───────────┐
        ▼           ▼           ▼           ▼           ▼           ▼
   sozialrecht  schuldner-   mietrecht  arbeitsrecht  …          strafrecht
   (default,    recht                                (11 modules, see
    verified)                                         docs/module-catalog.md)
```

**Rule of the split.** The core knows *how* to analyse a German legal document
(extract → retrieve → bind evidence → verify → compute → draft → disclose). A
module knows *what* applies in one area of law (which statutes, which
deadlines, which amounts, which drafts, which questions a lawyer will ask).
Nothing area-specific may live in the core; nothing generic may be duplicated in
a module.

**Modules are mostly data.** A module is a versioned package of
data and content (manifest, corpus scope, parameters, deadline specs, prompts,
templates, intake schema, dossier checklist, plain-language copy, goldset).
Code is allowed only for deterministic calculators that cannot be expressed as
data, and only through the typed interfaces in § 2.4. This is what keeps
community contribution bounded and reviewable (docassemble's
jurisdiction-package pattern, in MIT form).

---

## 2. The module contract

### 2.1 Package layout

First-party modules live in this repository under `modules/<module_id>/`
(target) and are installed with the core. Out-of-tree modules (Python entry
point group `citizen.modules`) are a later capability (roadmap WP-112) and are
always loaded at tier `community` at most.

```
modules/sozialrecht/
├── module.yaml               # manifest (§ 2.2) — the only required file
├── corpus.yaml               # corpus scope: source types + § ranges
├── parameters/               # versioned legal parameters (YAML, with source quotes)
│   └── 2026.yaml
├── fristen.yaml              # deadline specs (§ 2.3)
├── calculators.py            # optional: Calculator implementations (§ 2.4)
├── rules_engine.py, regime.py  # further module code, imported relatively (sozialrecht)
├── prompts/profile.yaml      # stage prompt profile (persona, statutes, terms) or {inherit: <id>}
├── documents/templates.yaml  # action-draft templates, slot definitions, generator selection
├── intake.yaml               # intake-interview schema (questions, routing keywords; per area key its global `order`, WP-94)
├── dossier.yaml              # document checklist + lawyer-question list (§ 3.7)
├── copy/                     # plain-language layer: de/, de-LS/ (Leichte Sprache), en/, …
├── goldset/
│   └── goldset-v0.2.0.yaml   # verified synthetic cases + thresholds
├── compliance/deny-phrases.json  # module deny phrases for the purpose-drift lint
├── DISCLAIMER_ADDENDUM.md    # area-specific limits (feeds DISCLAIMER_* Part D)
└── CHANGELOG.md              # module changelog (own semver)
```

### 2.2 Manifest (`module.yaml`)

```yaml
id: sozialrecht                 # stable key; equals legal_area value; never renamed
version: 1.0.0                  # module semver (§ 6.2)
core_api: ">=3.0,<4.0"          # compatible core contract range
title: { de: "Sozialrecht", en: "Social-benefits law" }
tier: verified                  # planned | experimental | verified | community
scope:
  summary_de: "Bürgergeld/Grundsicherung (SGB II), Verfahren (SGB X), Sozialgerichtsverfahren (SGG)"
  own_matter_only: true         # RDG posture, see § 7
  out_of_scope: ["Rentenversicherung (SGB VI)", "Krankenversicherung (SGB V)"]
corpus: corpus.yaml
parameters: { domain: sozialrecht, files: [parameters/*.yaml] }
fristen: fristen.yaml
calculators: calculators:CALCULATORS        # optional
documents: [widerspruch, widerspruch_jahresfrist, ueberpruefungsantrag_44, akteneinsicht_25]
intake: intake.yaml
prompts: prompts/profile.yaml
document_templates: documents/templates.yaml
dossier: dossier.yaml
regimes: { provider: calculators:REGIMES }  # optional intertemporal regimes (e.g. 2026-07-01 reform)
goldset: { path: goldset/goldset-v0.2.0.yaml, gate: { finding_recall: 0.85, hallucination_rate_max: 0.02 } }
compliance:
  purpose_drift_deny_file: compliance/deny-phrases.json   # module-specific deny phrases (JSON list, lint format)
  special_regimes: ["DSGVO Art. 9 (Gesundheits-/Behinderungsdaten)"]
  referral: { required: false, targets: ["Sozialberatung", "Fachanwalt für Sozialrecht"] }
  disclaimer_addendum: DISCLAIMER_ADDENDUM.md
legacy_aliases: []              # e.g. erbrecht declares ["schenkungsrecht"]
```

The registry validates every manifest against a JSON Schema
(`app/modules/manifest.schema.json`, versioned with the core contract) at
startup and refuses to start if an *enabled* module is invalid.

### 2.3 Deadline specs (`fristen.yaml`) — data, not code

The v2.0.0 Fristen engine (`app/services/fristen.py`) mixes a generic calendar
(holidays per Land, workday rollover, same-day-next-month arithmetic) with
SGB-specific rules (§ 37 Abs. 2 SGB X, § 84 SGG, § 66 Abs. 2 SGG). The target
splits these: the **calendar and arithmetic stay in the core**; each module
declares its deadlines as specs the core evaluates.

```yaml
- id: widerspruch_sgg_84
  label_de: "Widerspruchsfrist"
  trigger: bekanntgabe              # bekanntgabe | zustellung | zugang | kenntnis | ereignis
  bekanntgabe_fiction: sgbx_37_2    # core library: sgbx_37_2 | vwvfg_41_2 | ao_122_2 | none
  duration: { months: 1 }
  rollover: sgg_64_3                # core library: bgb_193 | zpo_222 | sgg_64_3 | vwgo_57 | stpo_43 | ao_108
  missing_rechtsbehelfsbelehrung: { duration: { years: 1 }, basis: "§ 66 Abs. 2 SGG" }
  basis: "§ 84 Abs. 1 SGG"
  severity: critical                # critical deadlines are banner-mandatory in every client
  applies_when: { document_type: verwaltungsakt }
```

Deadline arithmetic therefore stays LLM-free, unit-tested once in the core, and
reused by all eleven modules. Each module's `fristen.yaml` is covered by
golden date tests in its goldset.

### 2.4 Code extension points (typed, pure, parameter-backed)

| Interface | Purpose | Rules |
|---|---|---|
| `Calculator` | deterministic area math (§ 11b SGB II cascade, Pfändungstabelle, Kappungsgrenze, Kündigungsfrist § 622 BGB, Tagessatz …) | pure function of (extraction, parameter snapshot, period) → typed result with "authority computed X / correct would be Y / difference Z"; no I/O, no LLM; every constant from the parameter store |
| `RegimeProvider` | intertemporal law selection (e.g. SGB II reform 2026-07-01) | generalises `app/services/regime.py`; returns regime key per period |
| `DocumentTypeClassifier` hints | area-specific document-type vocabulary (Bescheid, Mahnbescheid, Strafbefehl, Kündigung …) | data in `intake.yaml`; code only if a structural parser is required |

Module code may import only `app.modules.sdk` (stable, versioned with
`core_api`); importing anything else from `app.*` fails the module lint.

### 2.5 Tiers and lifecycle

| Tier | Meaning | Default availability |
|---|---|---|
| `planned` | catalogued, no package yet | never loadable |
| `experimental` | package exists; engines may be partial; no goldset gate passed | enabled in `dev`/`self`, disabled in `provider` (D-037) |
| `verified` | full definition of done (roadmap § 7) incl. passing goldset gate | enabled in every mode |
| `community` | out-of-tree package, not reviewed by maintainers | opt-in only, never in `provider` without explicit listing |

Promotion `experimental → verified` is a decision-ledger event (one D-entry per
module) and requires the published eval report.

---

## 3. Core services (target responsibilities)

### 3.1 Module registry (`app/modules/registry.py`, new)

- Discovers `modules/*/module.yaml` (and later entry points), validates,
  computes the **enabled set**:
  `ENABLED_MODULES` setting if set, else the tier default for the current
  `DEPLOYMENT_MODE` (D-037).
- Resolves a request's module(s): explicit `legal_areas` → intake-suggested
  module → `DEFAULT_MODULE` (default `sozialrecht`, D-036). Legacy aliases
  (`schenkungsrecht → erbrecht`) resolve here and are reported back.
- Syncs a `legal_module` row per installed module (§ 4) so audit records can
  reference module id **and version**.
- Exposes manifests to the API (§ 5) and to provenance (§ 6.4).

### 3.2 Pipeline orchestrator (`app/core/pipeline.py`)

The nine stages stay. What changes is where each stage gets its area knowledge:
prompts, retrieval scope, deadline specs, calculators, regime banner and
document generators come from the resolved module(s) via the registry instead
of from module-global dictionaries. Multi-module cases (e.g. Mietschulden +
Jobcenter: `mietrecht` + `sozialrecht`) are a first-class path — the
existing `legal_areas` list and `case_run_area` table already model it.

### 3.3 Corpus framework (`app/services/corpus.py`)

One shared corpus. Statutes are fetched once (gesetze-im-internet.de XML, daily
`gii-toc.xml` for change detection; RII/OLDA case law later) and chunked once.
A module does not own statutes; it declares a **corpus scope**
(`source_type` + optional § ranges, e.g. `bgb §§ 535–580a` for Mietrecht).
Retrieval filters by the union of the enabled request modules' scopes. This
replaces both `AREA_TO_SOURCE_TYPES` and the § range → `legal_area` tagging in
`corpus.py`, which cannot express that one BGB is shared by five modules.

### 3.4 Parameter store (`app/services/parameter_store.py`)

Already versioned with validity periods and source quotes. Target: the
existing `legal_parameter.domain` column (default `sgb2` today) becomes the
module namespace (`sozialrecht`, `mietrecht`, …); parameter files ship inside
modules and are seeded by a generic loader replacing
`scripts/seed_legal_parameters.py`. Parameter updates travel on the signed
update channel (§ 3.9) independently of code releases.

### 3.5 Fristen core (`app/services/fristen.py` → `app/fristen/`)

Holiday calendar per Land, Bekanntgabe/Zustellung fiction library, rollover
library, Rechtsbehelfsbelehrung-defect extension, non-Verwaltungsakt
detection hook. Evaluates module deadline specs (§ 2.3). Output contract
unchanged in shape (`FristResult`), extended with `module_id` and `spec_id`.

### 3.6 Document renderer (`app/services/document_generators.py`)

The slot mechanism (every legal assertion bound to a verified, user-confirmed
claim; anything unbound renders as `[BITTE PRÜFEN]`) is generic and stays in
the core. The concrete templates (Widerspruch, § 44 SGB X, § 25 SGB X) move to
`modules/sozialrecht/documents/`. Other modules add their own (Einspruch
gegen Bußgeldbescheid, Widerspruch gegen Mahnbescheid, Antwort auf
Mieterhöhungsverlangen, …). Drafts remain drafts: the human signs.

### 3.7 Dossier generator (new; roadmap P10)

The product's central deliverable: the **Mandatsvorbereitungs-Dossier**. A
core service assembling, for one case across its modules:

1. Sachverhalts-Chronologie (from OCR'd correspondence, user-confirmed)
2. Dokumentencheckliste (module `dossier.yaml`)
3. Fristen banner (Fristen core)
4. rechnerische Ergebnisse (module calculators)
5. verifizierte Belege (evidence bindings with verbatim quotes + confidence)
6. Fragenliste für den Anwalts-/Beratungstermin (module `dossier.yaml`)
7. Entwürfe as annex (module document templates)
8. Export: print-ready PDF **and** machine-readable JSON validated against a
   versioned schema (`citizen-dossier-v1.0`).

### 3.8 Intake engine (`app/services/intake.py`)

Generic interview runner (docassemble-style DSL pattern). Area routing
keywords and question sets move from the hard-coded dictionaries in
`intake.py` / `app/api/routes/presets.py` into module `intake.yaml`. Intake
output is a module suggestion plus structured facts; the user confirms the
module choice.

### 3.9 Update channel (new; roadmap P11)

Signed, public, static feeds (GitHub releases) for parameter sets and corpus
change notices, per module. The client verifies signatures before applying.
No hosted service, no telemetry — running cost stays ≈ zero.

### 3.10 Unchanged core guarantees

Pseudonymization before any external inference, egress guard, inference
profiles (`eu-avv`, `extern-openrouter`, `on-prem`; consumer distributions
default to a local model, roadmap WP-124), PostgreSQL-only (D-024), timeout
chain ordering (D-017), disclaimer-ack gate, Art. 50 disclosure/provenance
(D-032), `DEPLOYMENT_MODE` (D-019), audit trail. Modules cannot switch any of
these off.

---

## 4. Data model (target deltas)

| Table / column | As-is | Target |
|---|---|---|
| `legal_module` | — | **new**: `id` (PK, = module id), `version`, `tier`, `manifest_sha256`, `installed_at`, `enabled` — synced by the registry at startup |
| `case_run_area.legal_area` | CHECK against `LEGAL_AREA_ALLOWED` (hard-coded tuple in `models.py`) | CHECK removed; `legal_area` keeps the stored area key. New `module_id` FK → `legal_module.id` (NULL only for core-procedural keys) plus `module_version`, so every case records the module and version it ran with (as built: D-057 — the FK sits beside the key because `schenkungsrecht`/`verwaltungsrecht` are not module ids) |
| `legal_chunk.legal_area` | single tag derived from § range | kept for backward compatibility, no longer used for filtering; retrieval uses module corpus scopes (§ 3.3). Dropped in a later major |
| `legal_parameter.domain` | default `sgb2` | holds module id; migration rewrites `sgb2 → sozialrecht`; no column default |
| `case_run` | — | `dossier_json` (nullable, versioned schema) — or a separate `dossier` table if size requires (decided in WP-100) |

All changes extend the single linear Alembic chain (`… → 012 → 013 …`); no
branch DAGs (D-024). The `LEGAL_AREA_ALLOWED` / `LEGAL_AREA_TIER` constants in
`app/db/models.py` are removed; the registry is the source of truth (area keys
and their order: `order` in each module's `intake.yaml`).

**Status:** `legal_module`, the `case_run_area` module binding and the domain
rewrite are done (WP-94, migration `013_legal_module`, D-057);
`legal_chunk.legal_area` and `case_run.dossier_json` remain open.

---

## 5. API (target; `/api/v1`, additive only)

The contract in `API_DOCUMENTATION.md` remains authoritative for what exists
today and is guarded by `tests/unit/test_api_documentation.py`. Target
additions (each lands together with its doc row, keeping the parity guard
green):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/modules` | installed modules: id, version, tier, enabled, corpus readiness |
| `GET` | `/api/v1/modules/{module_id}` | full manifest (public parts), deadline catalog, document types, dossier checklist |
| `GET` | `/api/v1/modules/{module_id}/goldset` | module goldset manifest (generalises `/goldset`) |
| `POST` | `/api/v1/cases/{case_id}/dossier` | build dossier; `?format=json|pdf` |
| `GET` | `/api/v1/cases/{case_id}/dossier` | last built dossier (JSON) |

Behavioral rules (D-039):

- `legal_areas` on `/analyze`, `/intake`, `/presets` keeps its name and shape;
  its values are module ids. Empty/absent → `DEFAULT_MODULE`
  (today's behaviour for Sozialrecht callers is unchanged).
- Requesting a module that is installed but not enabled → `422` with error
  code `MODULE_NOT_ENABLED`; unknown id → `422 MODULE_UNKNOWN`; legacy alias →
  accepted, response carries `resolved_modules`.
- `/api/v1/goldset*` stays as the Sozialrecht alias of
  `/modules/sozialrecht/goldset` until `/api/v2`.
- `GET /api/v1/meta/version` gains `modules: {id: version}` (additive key).
- Analyze terminal event, chat `done` and `GeneratedDocument` provenance gain
  `modules: [{id, version, parameter_set}]` (provenance spec
  `citizen-provenance-v1.1`, additive).

No `/api/v2` is planned in roadmap v3.0.0. A v2 is only opened when a
non-additive change becomes unavoidable, and gets its own decision.

---

## 6. Versioning

Versioning is a correctness surface here: a deadline or an amount is only
reproducible if every input that produced it is pinned.

### 6.1 Core

- Semver in `pyproject.toml` (canonical). **3.0.0** is cut at the exit of
  roadmap phase P9 (module refactor): the declared purpose widens (D-035),
  which is a major event for a compliance-bound system even though `/api/v1`
  stays compatible.
- `core_api` contract version (module SDK + manifest schema) is semver'd
  separately; breaking it requires a core major.

### 6.2 Modules

Each module carries its own semver and `CHANGELOG.md`:

| Bump | When |
|---|---|
| MAJOR | a deadline spec, calculator or document type is removed/renamed, or a calculator's legal semantics change |
| MINOR | new deadline spec, document type, calculator, goldset cases, new parameter validity period, new language in `copy/` |
| PATCH | correction of a wrong parameter value or copy error — additionally flagged as **errata** in the module changelog and surfaced via `/modules/{id}` so affected cases can be identified by `module_version` |

### 6.3 Pinned artefacts

| Artefact | Version source |
|---|---|
| goldset | file name `goldset-vX.Y.Z.yaml`, per module |
| eval report | `eval/results/<module>/<goldset>-<core>-<module>-<timestamp>.json` |
| parameter set | per module, `parameter_set` id = module version + max `valid_from` |
| corpus | `Rechtsstand` timestamp per source (exists) |
| dossier | JSON Schema `citizen-dossier-vMAJOR.MINOR` |
| provenance | `PROVENANCE_SPEC_VERSION` (`citizen-provenance-v1.1` adds modules) |
| disclaimer | `DISCLAIMER_VERSION` (bumps whenever any enabled module's addendum changes) |
| documents | roadmaps and this file: semver in header comment |

### 6.4 Audit

Every `case_run` records core version, module ids + versions, parameter-set
ids, corpus Rechtsstand, inference profile, disclaimer version. A case is
reproducible from its audit row plus the tagged release.

---

## 7. Compliance architecture per module

The v2.0.0 posture applies unchanged to the core. Modules add a bounded,
declared layer:

- **Declared purpose** (D-035): citizen-side self-help and preparation in the
  user's **own matter**, plus assistance to advice centers acting within their
  own RDG basis. Every module states its scope in its manifest; authority-side
  framing is forbidden in all copy.
- **Purpose-drift lint** scans README, `DISCLAIMER_*.md` (closing the coverage
  gap logged in D-029) and every module's `copy/` and `DISCLAIMER_ADDENDUM.md`;
  each module adds its own deny phrases (e.g. Aufenthaltsrecht: authority-side
  migration framing, Annex III(7); Strafrecht: law-enforcement framing,
  Annex III(6)).
- **RDG invariant** (D-021) is enforced by the core renderer for every module:
  outputs are Rechtsinformation plus building blocks requiring human
  adjudication; drafts carry `[BITTE PRÜFEN]`.
- **Area-specific regimes** are declared in the manifest and drive copy and
  referral behaviour, e.g. StBerG (Steuerrecht: help for third parties is
  reserved to Steuerberater/Lohnsteuerhilfevereine), Art. 10 DSGVO
  (Strafrecht), Art. 9 DSGVO (Sozial-, Familien-, Aufenthaltsrecht),
  mandatory referral banners for very short or very high-stakes deadlines
  (AsylG, StPO).
- **Disclaimer**: core text stays in `DISCLAIMER_DE.md` / `DISCLAIMER_EN.md`;
  module addenda are compiled into a new Part D. One ack version covers all.

---

## 8. As-is coupling map (the refactor work list for P9)

Every place where v2.0.0 code is area-specific, and where it goes:

| As-is location (v2.0.0) | Area coupling | Target | Status |
|---|---|---|---|
| `app/db/models.py` `LEGAL_AREA_ALLOWED`, `LEGAL_AREA_TIER`, CHECK `ck_case_run_area_legal_area` | closed area list + tiers in code/DB | registry + `legal_module` table (§ 4) | done (WP-94, D-057): key set/order from module `intake.yaml` `order`; `case_run_area.module_id` FK + `module_version` |
| `app/services/corpus_readiness.py` `AREA_TO_SOURCE_TYPES` | area → source types | module `corpus.yaml` | done (WP-93) |
| `app/services/corpus.py` `CORPUS_SOURCE_METADATA`, § range → area tagging | SGB-centric source list, BGB range tagging | core source catalog + module corpus scopes | done (WP-93): tags = module `chunk_tags`; source catalog stays core |
| `app/core/config.py` `CORPUS_SOURCES=["sgb2","sgbx"]`, `ENABLE_CALCULATION_CHECK` | Sozialrecht defaults | `DEFAULT_MODULE`, `ENABLED_MODULES`; calculation toggle per module | partly: calculators per module (WP-93); global toggle + default ingest sources remain |
| `app/services/prompts.py` area profiles + prompt sets | per-area prompts in one file | `modules/*/prompts/` | done (WP-93) |
| `app/services/intake.py` area keyword maps and question sets | hard-coded routing | `modules/*/intake.yaml` | done (WP-93) |
| `app/services/presets.py`, `app/api/routes/presets.py` | preset list + keyword scorer, fallback `sozialrecht-allgemein` | presets declared by modules; fallback = `DEFAULT_MODULE` | done (WP-93) |
| `app/services/fristen.py` | generic calendar + SGB X/SGG rules mixed | Fristen core + `modules/sozialrecht/fristen.yaml` | done (WP-92; shim removed WP-93) |
| `app/services/rules_engine.py`, `app/services/calculation.py` | SGB II math, Regelbedarf tables, extraction prompt | `modules/sozialrecht/calculators.py` + parameters; generic extraction/explanation harness stays in core | done (WP-93) |
| `app/services/regime.py` | SGB II reform 2026-07-01 | `RegimeProvider` in the Sozialrecht module | done (WP-93) |
| `app/services/document_generators.py` | Widerspruch/§ 44/§ 25 templates | renderer in core, templates in module | done (WP-93) |
| `app/api/routes/goldset.py`, `eval/` | goldset assumed Sozialrecht | per-module goldsets; `eval.runner --module` | partly: goldsets in `modules/sozialrecht/goldset/`; `--module` and `/modules/{id}/goldset` → WP-95 |
| `scripts/seed_legal_parameters.py`, `legal_parameter.domain='sgb2'` | SGB II seeding | generic module parameter loader | done: loader (WP-93, `scripts/seed_module_parameters.py`); domain `sgb2 → sozialrecht` (WP-94) |

Legacy area keys (D-038) after WP-94: `schenkungsrecht` is declared by the
`erbrecht` stub (stays a distinct stored `legal_area`, bound to module
`erbrecht` via `module_id`, D-057); `verwaltungsrecht` is
served by the core procedural library `app/modules/procedural/`; `andere`
is the engine-less catch-all stub. All stubs are tier `experimental` and
carry only their v2.0.0 intake/corpus/prompt data.

**Refactor invariant (P9 gate):** after extraction, the Sozialrecht goldset
eval must show **zero regression** against the last v2.0.0 baseline report,
the full test suite stays green, and every `/api/v1` route behaves identically
for requests that do not name a module.

---

*Changes to this document follow semantic versioning. Statements marked target
describe planned structure, not shipped behaviour. Legal characterisations are
engineering-planning inputs, not legal advice.*
