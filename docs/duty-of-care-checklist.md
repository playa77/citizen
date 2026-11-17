# Duty-of-care checklist for consumer copy and UI (WP-123)

<!-- Version: 1.0.0 | 2026-11-17 — roadmap P12, D-068. -->

Applies to every text a person reads: module plain-language copy
(`modules/<id>/copy/`), core plain copy (`app/plain/core/`), and every
consumer UI built on `/api/v1` (`playa77/citizen-gui`). The machine-checkable
items are enforced by `python -m eval.plain_eval` and
`python -m scripts.validate_module`; the others are reviewer and usability-test
items.

## 1. Language (gated)

| # | Rule | Enforced by |
|---|---|---|
| L1 | No discouraging language: never "aussichtslos", "keine Chance", "lohnt sich nicht", "zu spät", "selbst schuld" or their English equivalents. Prospects are for the advice centre or lawyer. | `app/plain/checks.py` `DISCOURAGING_PHRASES` (gate + validator) |
| L2 | Sentence length: Bürgersprache and plain English ≤ 22 words, Leichte Sprache ≤ 14 words. | `eval.plain_eval` readability check |
| L3 | Every finding names a next step and the advice centre. | Goldset `contains` assertions |
| L4 | "Citizen found no error" never means "the letter is right": the copy says the tool can miss errors and points to advice before the deadline. | Goldset PL-F03 |
| L5 | An unrecognised or missing classification falls back to the neutral "cannot classify yet" copy, never to reassuring copy. | `classify_ergebnis`, goldset PL-F06/F07 |
| L6 | Purpose: citizen-side preparation in the person's own matter (D-035). No authority-side framing. | `scripts/check_purpose_drift.py` (scans `app/plain/core/*.yaml` and module copy) |
| L7 | Dates are spelled out with the weekday; never only "4 Wochen" or a bare number. | `app/plain/languages.format_date` |

## 2. Deadlines (UI, reviewer-checked)

| # | Rule |
|---|---|
| D1 | The `banner` deadline from `GET /cases/{id}/plain` is shown first, above findings, and cannot be collapsed or dismissed. |
| D2 | `missing_input` is shown as an urgent call to enter the letter date — never as "keine Frist" or an empty state. |
| D3 | `provisional` is shown with its date **and** the request to confirm the letter date (chronology). |
| D4 | No client-side deadline arithmetic and no deadline taken from LLM text (AGENTS.md: deadlines only from the Fristen core). |
| D5 | A deadline in the past is still shown, with a pointer to advice (a Überprüfungsantrag may still be possible); no "zu spät" wording. |

## 3. Accessibility target (WCAG 2.1 AA / BITV 2.0)

| # | Rule |
|---|---|
| A1 | `lang` attribute per text block from the API's `bcp47` (Leichte Sprache is `de`). |
| A2 | Deadline banner is a landmark (`role="region"` + label) and announced on load (`aria-live="polite"` once, not on every re-render). |
| A3 | Language switch reachable by keyboard; the choice persists per device only (no server profile). |
| A4 | Contrast ≥ 4.5:1, touch targets ≥ 44 px, no information by colour alone (severity also as text). |
| A5 | Screen-reader journey test (NVDA + Firefox, VoiceOver + Safari): disclaimer → upload → OCR confirm → analyse → banner → findings → dossier → draft. Recorded in the usability-test protocol (P12 exit). |

## 4. Human review (OQ-3, open)

Every copy file carries `review.status`. `draft` copy passed the gate but no
human reviewer has signed it off. Before a public release
(`docs/public-release-go-nogo.md`): Bürgersprache and English reviewed by a
Sozialberatungsstelle, Leichte Sprache by a Prüfgruppe; set
`review: {status: reviewed, reviewer: <organisation>, date: <ISO date>}` and
bump the module PATCH version.

---

*Changes to this document follow semantic versioning.*
