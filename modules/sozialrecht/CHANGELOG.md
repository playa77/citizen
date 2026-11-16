# Changelog — module `sozialrecht`

Module semver (ARCHITECTURE.md § 6.2), independent of the core version.
1.0.0 is unreleased until the P9 exit gate (roadmap WP-97).

## 1.0.0 — unreleased (WP-91 → WP-93)

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
