# Changelog — module `erbrecht`

Module semver (ARCHITECTURE.md § 6.2), independent of the core version.

## 0.2.0 — 2026-11-16 (prompt set 3.0.0, D-060)

- `prompts/profile.yaml`: `issue_terms` gain norm anchors; new
  `result_categories`. MINOR: the rendered stage prompts change.
- Entry backfilled 2026-11-17 (WP-110): the version shipped without a
  changelog entry; found by the new changelog/manifest consistency check.

## 0.1.1 — 2026-11-16 (WP-94)

- `intake.yaml`: every area row declares `order`, its rank in the global
  area-key order (replaces the core's former `LEGAL_AREA_ALLOWED` tuple,
  D-057). Values keep the v2.0.0 order; no behaviour change.

## 0.1.0 — 2026-11-16 (WP-93)

- Stub module at tier `experimental` (D-038): carries the v2.0.0 legacy
  area behaviour extracted from the core — intake keywords/synonyms, corpus
  source-type mapping, prompt profile, BGB § range chunk tags, presets. No engines, no goldset.
