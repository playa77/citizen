# Changelog — module `sozialrecht`

Module semver (ARCHITECTURE.md § 6.2), independent of the core version.

## 1.5.0 — 2026-11-17 — released with core 3.4.0 (P12, D-068)

- `copy/` (new, WP-122): plain-language copy in Bürgersprache (`de`),
  Leichte Sprache (`de-LS`) and plain English (`en`) for the five finding
  categories (`rechtswidrig`, `teilweise_rechtswidrig`,
  `ueberwiegend_rechtmaessig`, `kein_verwaltungsakt`, `einordnung_offen`) and
  for `widerspruch_sgg_84` in every reachable status. Review status `draft`
  in all three languages — human review is open (OQ-3).
- `goldset/plain-v1.0.0.yaml` (new): 13 synthetic cases (6 deadline cases
  through the Fristen core, 7 finding-classification cases), gated by
  `python -m eval.plain_eval --module sozialrecht`.
- Manifest: `plain_language` block; `core_api: ">=3.2,<4.0"` (the key is
  core_api 3.2).

## 1.4.0 — 2026-11-17 — released with core 3.3.0 (P11)

- `errata.yaml` (new, WP-110): **E-2026-001** — objection deadlines for
  letters posted before 2025-01-01 were one day too late in module versions
  1.0.0–1.2.x (core < 3.2.0; fixed by D-065 in core 3.2.0 / module 1.3.0).
  Affected stored cases: `GET /api/v1/modules/sozialrecht/errata/E-2026-001/cases`.
- `corpus.yaml`: `case_law` (WP-113) — BSG decisions since 2023-01-01 from
  rechtsprechung-im-internet.de into source type `bsg` (max. 200, newest
  first). Opt-in ingestion; retrieval uses them once ingested.
- `fristen.yaml`: comment on the § 37 Abs. 2 SGB X fiction states the
  intertemporal rule (3 days before 2025-01-01, 4 since); no data change.
- Manifest: `errata: errata.yaml`; `core_api: ">=3.1,<4.0"` (the `errata`
  key is core_api 3.1).

## 1.3.0 — 2026-11-16 — released with core 3.2.0 (D-064)

- `dossier.yaml` (new, WP-102): document checklist (6 always, 8 by keyword),
  10 appointment questions (4 always, 6 by keyword), 11 chronology cues,
  dossier goldset + gate (deadline completeness 1.0, checklist recall ≥ 0.9,
  chronology accuracy ≥ 0.8).
- `goldset/dossier-goldset-v1.0.0.yaml` (new, WP-104): expected deadlines,
  checklist and chronology for the 12 cases of goldset v0.2.0.
- Manifest declares `dossier: dossier.yaml`.

## 1.2.0 — 2026-11-16 — released with core 3.1.0 (D-063)

- `corpus.yaml`: new `default_ingest_sources: [sgb2, sgbx]` — the sources a
  fresh deployment ingests when `CORPUS_SOURCES` is unset and no runtime
  selection exists. Moved out of the core config default; effective ingest
  list unchanged.
- Manifest note: `goldset.gate.baseline_report` predates core 3.1.0's
  pseudonymization fixes (different LLM inputs in 11/12 goldset cases); the
  next gate re-establishes the reference first.

## 1.1.0 — 2026-11-16 — released with core 3.0.0 (WP-97)

First published version. The roadmap named 1.0.0, but D-060's prompt-profile
change was a MINOR bump while 1.0.0 was still unreleased, so the P9 exit gate
publishes 1.1.0; 1.0.0 is retired without ever having been released.

Contents (everything below was unreleased until this entry):

- WP-91: manifest (`module.yaml`), tier `verified`, `DEFAULT_MODULE`.
- WP-92: deadline specs (`fristen.yaml`: Widerspruchsfrist § 84 SGG with
  § 37 Abs. 2 SGB X fiction, § 64 Abs. 3 SGG rollover, § 66 Abs. 2 SGG).
- WP-93: content extracted from the v2.0.0 core, behaviour-preserving:
  - `corpus.yaml` — source types for pre-flight/retrieval, default
    §-reference lookup sources;
  - `intake.yaml` — routing keywords, synonyms, preset
    `sozialrecht-allgemein` and its keyword fallback;
  - `prompts/profile.yaml` — stage prompt profile (persona, statutes,
    terminology anchors);
  - `parameters/sgb2.yaml` — the 27 SGB II parameter rows (Regelbedarf
    2024/2025, § 11b brackets, Vermögensfreibeträge, Sanktionen);
  - `calculators.py` + `rules_engine.py` — the SGB II calculation check
    (extraction schema/prompts, parameter loader, deterministic engine);
  - `regime.py` — regime provider (reform boundaries 2023-07-01,
    2025-01-01, 2026-07-01);
  - `documents/templates.yaml` — Widerspruch, Widerspruch (Jahresfrist),
    Überprüfungsantrag § 44 SGB X, Akteneinsichtsantrag § 25 SGB X;
  - `goldset/` — goldsets v0.1.0 and v0.2.0.
- WP-94: `parameters.domain` is the module id `sozialrecht` (migration 013
  rewrote stored `sgb2` rows; parameter keys keep their `sgb2.` prefix);
  `intake.yaml` area row declares `order: 10` (global area-key order, D-057).
- WP-96: compliance declarations in the manifest —
  `compliance/deny-phrases.json` (benefit-agency framing, DE/EN; read by the
  purpose-drift lint), `DISCLAIMER_ADDENDUM.md` (scope, deadlines, amounts,
  drafts, Art. 9 DSGVO, referral; compiled into DISCLAIMER v3.0.0 Part D.2),
  special regime Art. 9 DSGVO. Parameter-set id for provenance v1.1:
  `1.1.0+<latest valid_from>`.
- WP-97 (P9 exit gate): goldset v0.2.0 zero deterministic regression against
  B0′ (`eval/results/20261116T170321Z-55ec1f2.json` → release run
  `eval/results/20261116T175355Z-60c4afd.json`; D-062). Prompt set 3.0.1
  (P-04 claim-rule fix, D-062). `goldset.gate.baseline_report` now names the
  release run so the next gate compares like-for-like (the WP-90 report is not
  comparable, D-061).

## 1.0.0 — retired before release

Never published: the version number was superseded by 1.1.0 while the module
was still unreleased. The history above is the content that 1.0.0 would have
carried before D-060.
