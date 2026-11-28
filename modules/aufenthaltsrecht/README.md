# Aufenthaltsrecht — experimental 0.1.0

For preparing your own residence/asylum/naturalisation appointment. This is not legal advice or an authority-side assessment. No asylum narratives, credibility scores or outcome predictions.

Interim applications use independently confirmed effective notification in `ereignis_datum`; lawsuits use formal service. Never substitute a later service date. Conflicting procedure confirmations yield no date, and unsupported procedures retain a prominent urgent-referral banner.

Qualified current-law ordinary administrative and selected asylum dates require actual confirmed domestic service, correct remedy notice, current procedural applicability and local calendar confirmation. Klage and Eilantrag remain separate. Missing facts/unsupported regimes never become an ordinary fallback date. §87e AsylG transition cases, old law, border/airport and other special regimes need immediate individual advice. State objection coverage is explicitly unverified; the concrete remedy requires dated Land-law confirmation, never automatic state selection.

As verified on 2026-11-27, §36 interim relief is in paragraph 2 and §34a in paragraph 3. The roadmap's older §36(3) shorthand is not implemented as current law. Ordinary two-week and qualified one-week lawsuit periods are separate rules. No replacement period for defective notices is automatically computed.

Calculators perform conditional title/application date comparison, five-year residence anniversary arithmetic or confirmed individual cent-budget differences. They grant no status, work/travel rights, fiction effect, secured livelihood or naturalisation entitlement. No implicit Sozialrecht load or guessed statutory need values. Parameter validity is deliberately bounded to 2026-11-27 through 2026-12-31; other periods require review.

DE/EN/de-LS/AR/FA/UK/TR/RU static copy and core safety summaries are draft pending human review. ISO dates remain unambiguous for the additional languages. GUI/RTL/accessibility acceptance is separately owned. Do not upload sensitive narratives or unnecessary identifiers.

Offline gates: `python -m scripts.validate_module modules/aufenthaltsrecht`, `python -m eval.dossier_eval --module aufenthaltsrecht`, `python -m eval.plain_eval --module aufenthaltsrecht`. These do not prove live-inference quality or deployment corpus ingestion.

In the LLM-driven calculator path, explicit minimal calculator inputs must be
provided as one `CITIZEN_RESIDENCE_FACTS:` JSON object in the source. Include
`own_matter_confirmed: true`, `calculation_type`, `as_of` and all relevant
qualified facts from the intake schema. Model-generated confirmation alone is
not accepted. Unexpected/sensitive fields are rejected. No such block is needed
for pure programmatic calculator calls with explicit inputs. No legal verification
or status decision is implied by a source block.
