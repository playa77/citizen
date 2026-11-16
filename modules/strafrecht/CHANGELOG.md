# Changelog — module `strafrecht`

Module semver (ARCHITECTURE.md § 6.2), independent of the core version.

## 0.2.0 — 2026-11-16 (WP-96)

- `compliance/deny-phrases.json`: law-enforcement framing (Annex III
  point 6 AI Act), DE/EN — read by the purpose-drift lint for the whole
  scan set.
- `DISCLAIMER_ADDENDUM.md`: experimental status, short StPO deadlines the
  module does not compute, purpose limitation, Art. 10 DSGVO; compiled into
  DISCLAIMER v3.0.0 Part D.3.
- Manifest `compliance` section (special regime Art. 10 DSGVO). MINOR: new
  declared artefacts; no behaviour change.

## 0.1.1 — 2026-11-16 (WP-94)

- `intake.yaml`: every area row declares `order`, its rank in the global
  area-key order (replaces the core's former `LEGAL_AREA_ALLOWED` tuple,
  D-057). Values keep the v2.0.0 order; no behaviour change.

## 0.1.0 — 2026-11-16 (WP-93)

- Stub module at tier `experimental` (D-038): carries the v2.0.0 legacy
  area behaviour extracted from the core — intake keywords/synonyms, corpus
  source-type mapping. No engines, no goldset.
