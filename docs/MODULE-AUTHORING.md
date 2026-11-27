# Writing a Citizen module

<!-- Version: 1.6.0 | 2026-11-27 — WP-134: traffic/procedural sources and StPO rollover.
     1.5.0 | 2026-11-27 — WP-133: official EU article corpus support.
     1.4.0 | 2026-11-27 — WP-132: knowledge dates and qualified event applicability.
     1.3.0 | 2026-11-27 — WP-131: receipt/event deadlines, confirmed qualification/calendar facts.
     1.2.0 | 2026-11-26 — core_api 3.3: service facts/public intake schema; D-071 deferred human review.
     1.1.2 | 2026-11-26 — owner directs backend continuation; GUI separately owned.
     1.1.1 | 2026-11-25 — D-069: startup/session TODO before further module implementation.
     1.1.0 | 2026-11-17 — WP-122: plain-language copy (core 3.4.0, core_api 3.2).
     1.0.0 | 2026-11-17 — WP-115 authoring kit (core 3.3.0, core_api 3.1). -->
<!-- Architecture: ARCHITECTURE.md § 2 (module contract) · Catalog: docs/module-catalog.md -->

**Backend continuation authorized (2026-11-26):** the backend portion of
[TODO](../TODO.md), step 1 is implemented and verified. The owner directed
backend roadmap work to proceed; GUI/desktop selection and explicit restore
remain separately owned and unverified here. See the continuation record in
[D-069](decisions/D-069-module-selection-and-session-restore.md).

Every module is a peer; `sozialrecht` has no preferred loading role. First
launch presents all modules with none preselected. Later launches also offer
session restore or a new selection. Registry installation, tier and deployment
enablement describe availability, not which modules a session has loaded.

A module teaches Citizen one area of German law: which statutes matter,
which deadlines run, which amounts can be checked, what a person should
bring to an advice appointment. The core knows *how* to analyse a letter;
the module knows *what* applies. Modules are **mostly data** — YAML files a
reviewer can read line by line — plus, only where data cannot express it,
small pure Python functions behind `app.modules.sdk`.

Every module serves the same declared purpose (D-020/D-035): a natural
person preparing **their own matter** — understanding a letter, meeting the
deadline, arriving at the advice centre or lawyer with what is needed. Copy
speaks to that person ("Sie"). Nothing in a module may frame the tool for
the institution on the other side of the letter; the purpose-drift lint
enforces this for every module's copy and disclaimer addendum.

---

## 1. Quick start

```bash
# in-tree (this repository, tier experimental)
python -m scripts.new_module mietrecht_neu --title-de "Mietrecht" --title-en "Tenancy law"

# out-of-tree (installable package, tier community)
python -m scripts.new_module mein_modul --title-de "…" --title-en "…" --out-of-tree ../my-modules

# validate (offline: no database, no API key)
python -m scripts.validate_module modules/mietrecht_neu
python -m scripts.validate_module --all --json
```

The scaffold writes a module that passes the validator as generated. Every
legal value in it is a placeholder (`TODO`, `review_status: proposed`):
the scaffold encodes structure, never law.

## 2. Files

| File | Required | What it holds |
|---|---|---|
| `module.yaml` | yes | manifest: id, version, `core_api`, title, tier, scope, file declarations |
| `CHANGELOG.md` | yes (validator) | `## X.Y.Z — date` entries, newest first, first = manifest version |
| `corpus.yaml` | for retrieval | `areas.<key>.source_types`; optional `chunk_tags`, `case_law` |
| `intake.yaml` | for routing | `areas.<key>.order` (globally unique), keywords, synonyms, presets |
| `intake-schema.yaml` | optional, `intake_schema` manifest key (core_api 3.3) | public JSON Schema in YAML for module-specific confirmed facts; served by REST/MCP module detail; existing API envelopes/guards stay in force |
| `fristen.yaml` | for deadlines | deadline specs evaluated by the Fristen core (§ 4) |
| `parameters/*.yaml` | for amounts | versioned values with validity, basis and review status |
| `dossier.yaml` | for the dossier | appointment checklist, questions, chronology cues |
| `errata.yaml` | from the first erratum | published corrections (§ 6) |
| `goldset/goldset-vX.Y.Z.yaml` | for promotion | synthetic test cases + gate |
| `copy/<lang>/plain.yaml` + `goldset/plain-vX.Y.Z.yaml` | for verified modules (sub-WP .7) | plain-language copy per finding category and deadline (§ 9a), declared under `plain_language` |
| `compliance/deny-phrases.json` | recommended | module-specific purpose-drift phrases |
| `DISCLAIMER_ADDENDUM.md` | recommended | area limits, `## DE` / `## EN` |
| `prompts/profile.yaml`, `documents/templates.yaml` | optional | stage prompt profile; action-draft templates |
| `calculators.py`, `regime.py` | optional code | `sdk.Calculator`, `sdk.RegimeProvider` only |

Every path the manifest declares must exist inside the module directory;
`..` and absolute paths are refused.

## 3. The rules the validator enforces

Errors (the module must not ship):

- manifest schema (`app/modules/manifest.schema.json`, core_api 3.2) and
  declared files;
- `core_api` admits the running core (`">=3.2,<4.0"` for new modules;
  `plain_language` needs 3.2, `errata` 3.1; public `intake_schema` and
  actual-service rules need 3.3);
- plain-language copy validates (`citizen-plain-copy-v1.0`) and contains no
  discouraging phrase (`docs/duty-of-care-checklist.md`);
- module code imports nothing from `app.*` except `app.modules.sdk`;
- `scope.own_matter_only: true`;
- deadline specs, parameter files, dossier content, prompt profile and
  templates load; code references resolve to the SDK types;
- area keys fit the installed modules (one owner per key, unique `order`,
  no synonym claimed twice) — checked by assembling the same tables the core
  builds at startup;
- changelog and errata discipline (§ 6);
- tier `verified` declares a goldset.

Warnings (allowed, but a reviewer looks): parameters not yet `verified`,
corpus source types the core does not store, no goldset, no addendum, no
errata file, `case_law` on a module that is not `verified`.

## 4. Deadlines and amounts

Deadlines and amounts come only from deterministic engines on versioned
parameters, never from model output. A deadline is data:

```yaml
- id: einspruch_beispiel
  label_de: "Einspruchsfrist"
  trigger: zustellung
  bekanntgabe_fiction: none
  duration: { days: 14 }
  rollover: bgb_193
  basis: "§ … …"
  severity: critical
```

The Fristen core owns calendars, fictions and rollover rules; a module
picks from its libraries. Each spec needs golden date tests before
promotion. Amounts: every constant lives in `parameters/` with `valid_from`,
`basis` and honest `review_status` metadata; human parameter review is deferred
until all modules are implemented (D-071). Calculators are
pure functions of (extraction, parameters).

## 5. In-tree vs. out-of-tree

**In-tree** modules live in `modules/<id>/`, are reviewed with the core and
start at tier `experimental` (enabled in `dev`/`self`, not in `provider`).
Adding one is also a disclaimer change: its addendum goes into Part D of
`DISCLAIMER_DE.md` / `DISCLAIMER_EN.md` and `DISCLAIMER_VERSION` is bumped
(`tests/unit/test_disclaimer_addenda.py`).

**Out-of-tree** modules are Python packages registering an entry point:

```toml
[project.entry-points."citizen.modules"]
mein_modul = "citizen_module_mein_modul"   # package whose directory holds module.yaml
```

The core loads them at tier `community` whatever the manifest says, never
enables them implicitly (not even in `dev`), and enables them only when
`ENABLED_MODULES` lists them. An out-of-tree package cannot replace an
in-tree module id; a broken package is rejected and logged, not fatal. Once
enabled, its code must pass the import lint or the service refuses to
start. Out-of-tree modules are not covered by the maintainers' review or the
disclaimer's Part D.

## 6. Versions, changelog, errata

Module semver (ARCHITECTURE.md § 6.2):

| Bump | When |
|---|---|
| MAJOR | a deadline spec, calculator or document type removed/renamed, or a calculator's legal semantics change |
| MINOR | new deadline spec, document type, calculator, goldset cases, parameter validity period, language |
| PATCH | correction of a wrong value or copy — **plus an erratum** |

An erratum tells people whose case ran with a faulty version what to do:

```yaml
format: citizen-module-errata-v1.0
errata:
  - id: E-2027-001
    published: 2027-01-15
    affected_versions: ">=1.0.0,<1.4.1"
    fixed_in: 1.4.1
    severity: critical          # critical | major | minor
    component: parameter        # parameter | deadline | calculator | template | dossier | copy | prompt | other
    summary_de: "…"
    summary_en: "…"
    action_de: "…"
```

`fixed_in` must be a changelog version, not newer than the manifest, and
outside `affected_versions`. The API serves errata on
`GET /api/v1/modules/{id}` and lists affected stored cases on
`GET /api/v1/modules/{id}/errata/{erratum_id}/cases`.

## 7. Parameter updates between releases

A corrected value does not have to wait for a release: the maintainer
publishes a signed feed (`citizen-update-feed-v1.0`, Ed25519) that
operators verify and apply with `python -m scripts.module_update`
(DEPLOYMENT.md). Feed rows use the same format as `parameters/*.yaml`; the
parameter domain comes from the installed manifest, never from the feed.
The next module release must carry the corrected value in its files.

## 8. Case law

A `verified` module may declare case law for the corpus automation:

```yaml
case_law:
  - source_type: bsg        # a source type the module retrieves from
    provider: rii           # rii (rechtsprechung-im-internet.de) | olda (Open Legal Data)
    court: BSG              # RII court prefix / OLDA court slug
    since: 2023-01-01
    max_documents: 200
```

Ingested decisions change what retrieval returns for the module: rerun the
goldset gate after the first ingestion.

## 9. Goldset and promotion

Goldset cases are **synthetic** — invented people, invented letters. A
module moves from `experimental` to `verified` only with ≥ 15 cases, a
published eval report and a decision-ledger entry (roadmap § 7); it is never
promoted to meet a date. Until then the scaffold's
`goldset/goldset-v0.1.0.yaml` documents the case shape.

## 9a. Plain-language copy (sub-WP .7)

Declare it in the manifest (core_api 3.2):

```yaml
plain_language:
  files: { de: copy/de/plain.yaml, de-LS: copy/de-LS/plain.yaml, en: copy/en/plain.yaml }
  goldset: goldset/plain-v1.0.0.yaml
```

- `findings`: one entry per result category of your prompt profile plus
  `einordnung_offen` (keys are slugs: `überwiegend rechtmäßig` →
  `ueberwiegend_rechtmaessig`), each `title`, `text`, `next_step`.
- `deadlines.<spec_id>`: `title`, `action`, `texts` keyed by status
  (`computed`, `provisional`, `missing_input`, `not_applicable`), optionally
  refined by `frist_typ` (`computed.jahr`). Only `{frist_ende}`,
  `{bekanntgabe}`, `{basis}` may appear, and only where the status provides
  them (no `{frist_ende}` in `missing_input`).
- `de` and `en` cover everything; `de-LS` (Leichte Sprache) at least every
  `severity: critical` deadline.
- Never discourage (`docs/duty-of-care-checklist.md`); sentences ≤ 22 words
  (Leichte Sprache ≤ 14).
- `review.status: draft` until human review occurs. No reviewer-name approval
  gate blocks implementation; human reviews are deferred until all modules
  are implemented (D-071).
- Gate: `python -m eval.plain_eval --module <id>`. Model `goldset/plain-*.yaml`
  on `modules/sozialrecht/goldset/plain-v1.0.0.yaml`: deadline cases give
  `facts` and run through the Fristen core; finding cases give an `ergebnis`
  opening sentence.

## 10. Review checklist

- [ ] `python -m scripts.validate_module <dir>` passes; warnings understood
- [ ] every parameter has a `basis`, validity and honest review status; human
      review is deferred under D-071
- [ ] every deadline spec has golden date tests
- [ ] `python -m eval.plain_eval --module <id>` passes (verified modules)
- [ ] copy speaks to the person, in their own matter; purpose-drift lint green
- [ ] `DISCLAIMER_ADDENDUM.md` states the limits and the point where an
      advice centre or lawyer is indispensable
- [ ] `CHANGELOG.md` entry for the version; errata for every correction

## 11. Receipt/event deadlines (module API 3.4, WP-131)

Use `trigger: zugang` with confirmed `zugang_tatsaechlich`, or `trigger:
ereignis` with confirmed `ereignis_datum`; always declare a `document_type`
selector. `anchor: month_end` selects the last day of the target calendar
month; default `same_day` retains anniversary arithmetic. Negative durations
are allowed only for event rules without rollover. Do not roll backwards
notice periods forward. `requires_confirmed` lists module-owned qualification
keys in dossier `facts.qualifikationen`; each must be explicitly `true`.

Civil `rollover: bgb_193` requires explicit Bundesland and
`feiertagskalender_bestaetigt: true`. Supply `feiertage_zusaetzlich` with all
confirmed local holidays at the legally relevant place. The SDK
`civil_is_holiday(date, land)` implements statewide holidays from 2024,
including Gregorian Easter; local holidays remain an explicit input. This
calendar does not alter the historical administrative calendar path. No letter
date, postal fiction or Rechtsbehelfsbelehrung supplies a receipt/event date.


## 12. Knowledge-date deadlines (module API 3.5, WP-132)

Specs may use `trigger: kenntnis`; callers provide explicit `kenntnis_datum`
through the normal chronology facts contract. Neither receipt nor a letter or
event date can substitute. Require `core_api: ">=3.5,<4.0"` for this capability.
Applicability and special regimes remain module-owned qualification facts.
Arbeitsrecht keeps the dismissal banner critical even when dates are missing;
jobseeker dates have explicit conservative-planning limits. Do not encode a
knowledge date as administrative notification or as receipt to bypass validation.

An explicit-date spec must supply either a `document_type` selector or nonempty
`requires_confirmed` qualifications. The latter supports a confirmed event that
can arise from multiple document types without duplicating rules or suppressing
registration reminders on a dismissal. Missing qualifications still block dates.

## 13. Official EU article sources (module API 3.6, WP-133)

Contract module corpus keys `egbgb` and `eu261` use the existing source catalog
and storage. `eu261` identifies Regulation (EC) 261/2004; articles retain their
EU identity, official source URL and document hash. Ingestion rejects challenge
pages or incomplete article sets rather than storing them as law. An enabled
module is not an ingestion request: operators still choose sources explicitly.
Human review and live pipeline evaluation remain separate from offline checks.


## 14. Traffic procedure support (module API 3.7, WP-134)

The shared procedure library provides `stpo_43` rollover using the current
statewide calendar plus explicitly confirmed local holidays through existing
service/event fact contracts. Specs using it require an explicit state and
`feiertagskalender_bestaetigt`; legal applicability stays in module data.
It does not create service fictions, restore missed deadlines or extend
substantive limitation/retention periods. OWiG objection uses actual valid
service; hearing/questionnaire and issue dates do not substitute for it.

Federal sources `owig`, `stvg`, `stvo`, `bkatv`, `fev`, `stpo` are selectable
through existing corpus APIs. The scraper remains paragraph-only; annexes
and tables are not covered. Declare this source limitation and version any
selected table parameters with precise scope, dates and primary evidence.
Never infer full source coverage from a populated source key. D-076 records
approved boundaries; no new module code import surface is introduced.
