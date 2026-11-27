# Vertragsrecht 0.2.0 (experimental)

WP-133 supports preparation of your own consumer matter. Explicit module selection is required.
No live inference or deployment corpus ingestion forms part of this package. All legal/language
review metadata remains draft; no promotion or legal-quality claim follows from offline gates.

## Supported boundaries
The ordinary withdrawal period needs a confirmed complete trigger, timely adequate notice,
applicable consumer right and no exclusion/extinguishment. Late or absent notice is calculator-only;
financial-service/special regimes remain review items. Goods limitation excludes § 475e, digital
components, buildings/materials, special rights, fraud, shortened terms, suspension and restart.
The § 477 one-year period is an evidentiary presumption window, never a filing deadline;
animals and digital-element regimes are excluded. Regular limitation requires manual confirmation
of December 31 of the year in which both entitlement and knowledge conditions were met.
The existing month_end anchor is used; the engine does not validate that legal qualification.
Do not mark it confirmed for another date. No automatic general termination period is encoded.

Flight calculation requires qualified applicability and entitlement; long-delay entitlement depends
on relevant CJEU jurisprudence and is not established by the regulation text alone. An unknown
cause, reduction or special regime remains a review requirement. No automatic distance inference.

All generated documents are drafts with factual placeholders. Selection defaults to review notes;
four specific drafts are available for deliberate use after checking their conditions.

## Offline checks
`python -m scripts.validate_module modules/vertragsrecht`
`python -m eval.dossier_eval --module vertragsrecht`
`python -m eval.plain_eval --module vertragsrecht`
Goldset expected dates are literal hand-derived values. Fixtures are synthetic and cannot establish
real-world pipeline quality. Source evidence is in `sources/`; rate coverage is finite in parameters.
