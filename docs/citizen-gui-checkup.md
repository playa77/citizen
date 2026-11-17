# Integration checkup for the citizen-gui owner (core 3.4.0)

<!-- Version: 1.0.0 | 2026-11-17 — roadmap P12, D-067/D-068. -->

**For:** the maintainer of `playa77/citizen-gui` (the consumer UI, D-067).
**Against:** Citizen core **3.4.0**, `sozialrecht` **1.5.0**, contract
`API_DOCUMENTATION.md` in this repository (the only authoritative copy).
**How this was produced:** a static read of citizen-gui at commit `91465aa`
against the core source and its tests. The GUI was **not** built or run
here, so treat every finding as "verify, then fix". Each one names the GUI
file and the core contract it was checked against.

---

## 1. Mismatches found (fix first)

| # | Severity | GUI location | What the GUI expects | What the core sends | Fix |
|---|---|---|---|---|---|
| 1 | **critical** (duty of care) | `src/components/dossier/DeadlineBanner.tsx`, used in `AnalyzeView.tsx:379`, `CaseDetailView.tsx:266/344` | `final_output.fristen` (`bescheid_datum`, `frist_ende`, …) | **never sent**. `final_output` holds only the text sections (`sachverhalt`, `rechtliche_wuerdigung`, `ergebnis`, `handlungsempfehlung`, `entwurf`, `unsicherheiten`, `adversarial_pruefung`). Deadlines come only from the Fristen core | After the terminal event, take `case_run_id` and call `GET /api/v1/cases/{id}/plain?lang=…` (API § 8.13). Render `banner` first, then `deadlines[]`. **Remove the text "Keine Fristdaten im Bescheid ermittelt."** — today every person sees it, and it reads as "there is no deadline". `missing_input` must read as "enter the letter date now" (the copy says so) |
| 2 | high | `src/components/dossier/CalculationTable.tsx` | `final_output.berechnung` in cents (`anspruch_ermittelt_cent`, `positionen[]`) | never sent. Calculation results: dossier `sections.calculations` (`POST /cases/{id}/dossier`, API § 8.11); `GET /cases/{id}` merges the calculation stage as `final_output.calculation_*` keys; the SSE `calculation_check` stage carries only counts | Read the dossier `calculations` section: `items[]` with `label`, `relevant_rule`, `deterministic_result`, `authority_values`, `discrepancy_amount_eur` (euros as numbers, not cents), plus `summary` |
| 3 | medium | `src/types/api.ts` `adversarial_verhaeltnis` | `{behoerden_sicht, buerger_sicht, risiko_einschaetzung}` | never sent. The review is the `adversarial_review` SSE stage payload (`review_count`, `key_risks`, `overall_assessment`) and `final_output.adversarial_*` on `GET /cases/{id}` | Map from those keys |
| 4 | high | `src/components/documents/DocumentGeneratorForm.tsx:59/166`, type `GeneratorOptionsResponse` | `available_doc_types[]`, `frist_info`, `user_slots_required` | `{case_run_id, recommended, available: {<doc_type>: {available, frist_ende?, frist_typ?, reason?}}, claims: {total, verified_confirmed, unverified}}` (`app/api/routes/documents.py`) | Rebuild the option list from `available` + `recommended`; slots come back from `POST /documents/generate` (`slots[]`) |
| 5 | high | `nginx.conf` `location /api/` | uploads "bis 25 MB" (README) | the core accepts up to `MAX_FILE_SIZE_MB` (25) | nginx defaults `client_max_body_size` to **1 MB**, so every larger scan gets `413` before it reaches the core. Add `client_max_body_size 26m;` |
| 6 | medium | `src/components/layout/DisclaimerModal.tsx` → `GET /meta/disclaimer/text` | HTML text | still served (same shape), but since 3.4.0 the HTML is a plain-language summary — the old text falsely said uploads are not stored | Switch to `GET /meta/disclaimer/plain?lang=de` (§ 2.1): structured points, `ack_label` as the button text, `bcp47` for `lang` |
| 7 | low | `src/types/api.ts` `ModuleSummary.tier` | `"verified" \| "experimental"` | also `"planned"`, `"community"`; fields `origin`, `declared_tier` (core 3.3.0) | Widen the union; show `community` modules as such |
| 8 | medium | whole app | — | the appointment dossier (P10: `/cases/{id}/dossier*`) is not called anywhere | Without `PUT …/dossier/chronology` the person can never confirm the letter date, so deadlines stay `provisional`. Add the confirmation step (API § 8.11) |
| 9 | low | `docs/CITIZEN-API_DOCUMENTATION.md` | copy of the contract | the copy is from core 2.0.0 | Replace it with a link to the core repository, or refresh it per release |

## 2. New in core 3.4.0 — adopt for the P12 journey

1. **Plain-language disclaimer + ack (WP-125):**
   `GET /api/v1/meta/disclaimer/plain?lang=de,de-LS,en` — readable *before*
   the ack (no header needed). Show `texts[lang].disclaimer.points`, use
   `ack_label` for the confirm button, then send
   `X-Disclaimer-Ack: <ack.value>`. Keep showing `disclosure.texts` from AI
   responses (Art. 50(1)); `ai_notice` is the plain companion, not a
   replacement.
2. **Privacy view (WP-125):** `GET /api/v1/meta/privacy?lang=…` — the active
   inference profile, external hosts, storage and deletion routes, plus
   texts for this installation's mode and profile. Show it next to the
   disclaimer.
3. **Plain finding on analyse (WP-122):** send
   `"plain_languages": ["de"]` (or the person's choice) with
   `POST /api/v1/analyze`; the terminal event then carries `plain.finding`.
   Without the key the terminal event is unchanged.
4. **Case view (WP-121/122):** `GET /api/v1/cases/{id}/plain?lang=…` →
   `banner`, `deadlines[]` (texts with dates already spelled out),
   `finding`, `facts_used`. Never compute or reformat deadline dates in the
   browser (AGENTS.md: deadlines only from the Fristen core).
5. **Module copy for caching:** `GET /api/v1/modules/{id}/plain`;
   `GET /api/v1/modules/{id}` now has `plain_languages`.
6. **Languages:** `de` (Bürgersprache), `de-LS` (Leichte Sprache — only for
   critical copy in some modules; a missing language is listed in
   `missing_languages`, show the `de` text then), `en`. Every block has
   `bcp47`: put it on the element's `lang` attribute (WP-123).
7. **Review status:** all copy is `review_status: "draft"` until OQ-3 review.
   Showing it is fine (it passed the gate); do not label it as reviewed.

## 3. Joint verification checklist

Run the core (`docker compose up -d --build` + migrations) with
`DEPLOYMENT_MODE=dev`, `CITIZEN_SYNTHETIC_DATA_ONLY=true`, then the GUI
container in front of it. Use only synthetic letters.

| # | Check | Expected |
|---|---|---|
| V1 | `GET /api/v1/meta/version` through the GUI proxy | `api_version` `3.4.0`, `modules.sozialrecht` `1.5.0` |
| V2 | First visit without stored ack | modal from `/meta/disclaimer/plain`; no protected call before the ack; `403 disclaimer_required` never reaches the person |
| V3 | Upload a 5 MB synthetic PDF in dev mode | `X-Document-Tag: synthetic` sent (dev mode is detected from `/meta/deployment-mode`); no `413` (finding 5) |
| V4 | OCR confirm → analyse with `plain_languages` | SSE arrives unbuffered stage by stage; terminal event has `plain`, `disclosure`, `provenance` |
| V5 | Art. 50 order | `disclosure.texts[lang]` visible before any result text |
| V6 | Banner | the case view shows the `banner` deadline above findings; for the letter dated 06.07.2026 (default Bundesland), `provisional` "voraussichtlich … Montag, 10. August 2026" |
| V7 | Confirm the letter date (`PUT …/dossier/chronology` with `facts.bescheid_datum`) | `/cases/{id}/plain` turns `computed`; banner text changes without "voraussichtlich" |
| V8 | Letter without a date | banner shows the `missing_input` text ("Datum … so bald wie möglich"), never "keine Frist" |
| V9 | Not a Verwaltungsakt (`facts.ist_verwaltungsakt: false`) | `not_applicable`, `banner: null` |
| V10 | Language switch de → de-LS → en | texts change; `lang` attribute follows `bcp47`; deadlines keep the same date |
| V11 | Long run | a run of ~8 minutes completes (nginx 540 s > `PIPELINE_TIMEOUT_SEC` 480 s, D-017) |
| V12 | Screen reader (NVDA/VoiceOver) over V2–V10 | banner announced once; every control labelled (`docs/duty-of-care-checklist.md` § 3) |
| V13 | Disclaimer bump simulation (`DISCLAIMER_VERSION=v9.9.9` on the core) | GUI re-asks for the ack; `/meta/disclaimer/plain` answers `503 plain_copy_stale` — GUI shows an error, not an empty modal |

---

*Changes to this document follow semantic versioning.*
