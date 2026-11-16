# Changelog — module `sozialrecht`

Module semver (ARCHITECTURE.md § 6.2), independent of the core version.

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
