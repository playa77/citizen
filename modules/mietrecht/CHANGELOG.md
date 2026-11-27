# Changelog — module `mietrecht`

Module semver (ARCHITECTURE.md § 6.2), independent of the core version.

## 0.2.0 — 2026-11-27 (WP-131)

- Implement explicit receipt/event/service deadlines, qualified cent-exact rent,
  operating/heating cost, notice-period and deposit checks.
- Add versioned positive regional designations with per-Land source/coverage
  records; missing or expired coverage never establishes a default ceiling.
- Add dedicated prompts, public intake schema, guarded drafts, dossier,
  DE/EN/de-LS copy and synthetic evaluation fixtures.
- Remain experimental/proposed/draft; human review deferred under D-071.
  Deployment corpus ingestion and live-inference evaluation are not claimed.

## 0.1.1 — 2026-11-16 (WP-94)

- `intake.yaml`: every area row declares `order`, its rank in the global
  area-key order (replaces the core's former `LEGAL_AREA_ALLOWED` tuple,
  D-057). Values keep the v2.0.0 order; no behaviour change.

## 0.1.0 — 2026-11-16 (WP-93)

- Stub module at tier `experimental` (D-038): carries the v2.0.0 legacy
  area behaviour extracted from the core — intake keywords/synonyms, corpus
  source-type mapping. No engines, no goldset.
