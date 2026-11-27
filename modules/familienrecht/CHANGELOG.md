# Changelog — module `familienrecht`

## 0.3.0 — 2026-11-27

- WP-135 experimental statutory checks, qualified ordinary complaint dates, guarded drafts, intake/dossier and DE/EN/de-LS copy.
- D-077, module API3.8; no bundled guideline table or self-retention data (OQ-7).
- Human review deferred under D-071; no verified promotion or live quality claim.


Module semver (ARCHITECTURE.md § 6.2), independent of the core version.

## 0.2.1 — 2026-11-16 (prompt set 3.0.0, D-060)

- No file change: the module inherits the `erbrecht` prompt profile, whose
  0.2.0 change alters the prompts rendered for this module. PATCH.
- Entry backfilled 2026-11-17 (WP-110): the version shipped without a
  changelog entry; found by the new changelog/manifest consistency check.

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
