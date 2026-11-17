# Public release go/no-go — consumer distribution (WP-125, carry-over C-5)

<!-- Version: 1.1.0 (DRAFT, with D-069) | 2026-11-17 — item G15: P14 LLM analysis
     quality gate.
     1.0.0 | 2026-11-17 — roadmap P12, D-068. Re-scopes the provider
     go/no-go of roadmap v2.0.0 WP-69 to a free consumer distribution
     (citizen core + playa77/citizen-gui). -->

A public release is **go** only when every item in § 1 is checked and its
evidence is named. The owner signs the release decision as a DECISIONS.md
entry referencing this checklist version. Items in § 2 are known limits to
publish, not blockers.

**Distribution profile (B2C):** `DEPLOYMENT_MODE=self` on the person's own
machine (Docker Compose: core + Postgres + citizen-gui), no account, no
telemetry, no server operated by the project. Organisations that run it for
clients use `provider` and are themselves controllers (DISCLAIMER B.4).

## 1. Gate items

| # | Item | Evidence today (core 3.4.0) | State |
|---|---|---|---|
| G1 | Art. 50(1) notice shown before results, in the person's language | `disclosure` on every AI surface; plain companion `GET /meta/disclaimer/plain` `ai_notice`; GUI shows it before results | backend ✓, GUI to verify (checkup note § 3) |
| G2 | Art. 50(2) provenance persisted with every AI output | `provenance` v1.1 on all surfaces | ✓ |
| G3 | Disclaimer ack flow in plain language, version-pinned | `GET /meta/disclaimer/plain` (de, de-LS, en) + `ack`; core copy pinned to `v3.0.0`, refused with 503 when stale | backend ✓, GUI to switch from `/meta/disclaimer/text` |
| G4 | Privacy statement matches the running configuration | `GET /meta/privacy` (deployment mode, profile, external hosts, storage, deletion) | backend ✓ |
| G5 | Inference default decided (OQ-2) | `docs/consumer-inference-wp124.md`; `on-prem` configured but not gate-verified | **open** |
| G6 | Plain-language copy reviewed by humans (OQ-3) | all copy `review.status: draft` | **open** |
| G7 | Accessibility audit passed (WCAG 2.1 AA / BITV 2.0) + screen-reader journey | `docs/duty-of-care-checklist.md` § 3 | **open** (GUI) |
| G8 | Usability test, ≥ 5 people from the target clientele, synthetic Bescheid (P12 exit) | — | **open** (needs partner Beratungsstelle) |
| G9 | Goldset gates green at the release tree: analysis (`eval.runner`), dossier (`eval.dossier_eval`), plain language (`eval.plain_eval`) | plain + dossier offline gates green; analysis gate needs a fresh reference (D-063) | partly |
| G10 | Deadline engine known defects closed or published as errata | `app/fristen/calendar.py` holiday-table errors (D-065) open | **open** |
| G11 | DPIA (Art. 35 DSGVO) for the consumer distribution — the person is controller for own data in `self`; document the residual risks (pseudonymization limits, external inference) | not written | **open** |
| G12 | Release key published, update channel trust file populated (WP-111) | trust file empty | **open** (owner) |
| G13 | `DEPLOYMENT_MODE=self` start without synthetic-data guard; dev banner absent; `X-Document-Tag` not required | dev guard only in `dev` | ✓ |
| G14 | No discouraging language anywhere in consumer copy | gate `duty_of_care` | ✓ (module + core copy) |
| G15 | LLM analysis quality gate (P14, D-069): issue recall, citation precision, assessment match each > 0.90, mean over the held-out goldset, 3 runs | 41.5 / 30.3 / 16.7 % at prompt set 3.0.1 (goldset v0.2.0, scorer cannot measure 90 %, `docs/quality-plan.md` § 3) | **open** — blocks release |

## 2. Known limits to publish with the release

- Only `sozialrecht` is `verified`; other modules are `experimental` and
  compute no deadlines or amounts.
- Pseudonymization reduces but does not remove re-identification risk
  (privacy copy `residual_risk`).
- Deleting a case keeps documents of the conversation it came from until that
  conversation is deleted (`GET /meta/privacy` `storage.note`).

---

*Changes to this document follow semantic versioning.*
