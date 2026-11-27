# Changelog — module `vertragsrecht`

Module semver (ARCHITECTURE.md § 6.2), independent of the core version.

## 0.2.0 — 2026-11-27

- WP-133: experimental consumer withdrawal, warranty, termination and passenger-rights preparation.
- Qualified deterministic periods and calculators; EGBGB/EU261 corpus mapping; guarded drafts,
  intake schema, dossier, DE/EN/de-LS draft copy and synthetic offline fixtures.
- Human legal/language review, live evaluation and deployment ingestion remain deferred (D-071).

## 0.1.1 — 2026-11-16 (WP-94)

- `intake.yaml`: every area row declares `order`, its rank in the global
  area-key order (replaces the core's former `LEGAL_AREA_ALLOWED` tuple,
  D-057). Values keep the v2.0.0 order; no behaviour change.

## 0.1.0 — 2026-11-16 (WP-93)

- Stub module at tier `experimental` (D-038): carries the v2.0.0 legacy
  area behaviour extracted from the core — intake keywords/synonyms, corpus
  source-type mapping. No engines, no goldset.
