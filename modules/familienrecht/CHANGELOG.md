# Changelog — module `familienrecht`

Module semver (ARCHITECTURE.md § 6.2), independent of the core version.

## 0.2.0 — 2026-11-16 (WP-96)

- `compliance/deny-phrases.json`: youth-welfare-office and family-court
  framing, DE/EN — read by the purpose-drift lint for the whole scan set.
- Manifest `compliance` section. MINOR: new declared artefact; no behaviour
  change.

## 0.1.1 — 2026-11-16 (WP-94)

- `intake.yaml`: every area row declares `order`, its rank in the global
  area-key order (replaces the core's former `LEGAL_AREA_ALLOWED` tuple,
  D-057). Values keep the v2.0.0 order; no behaviour change.

## 0.1.0 — 2026-11-16 (WP-93)

- Stub module at tier `experimental` (D-038): carries the v2.0.0 legacy
  area behaviour extracted from the core — intake keywords/synonyms, corpus
  source-type mapping, prompt profile, BGB § range chunk tags. No engines, no goldset.
