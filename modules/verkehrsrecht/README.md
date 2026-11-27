# Verkehrsrecht 0.1.0 (experimental)

WP-134 supports your own traffic administrative-offence preparation. Explicit selection is required.
No accident settlement, criminal proceedings, alcohol/drug sanctions or licence-withdrawal determination.
No deployment corpus population or live inference was performed. Review remains draft/proposed (D-071).

## Supported boundaries
Objection: actual valid domestic service of a fine notice, confirmed ordinary procedure and local
holiday calendar. No letter/hearing-date fallback; no automatic extension for missing instructions.
File-access requests do not stop objection time. Witness duties and personal particulars differ from
the affected person's right to silence about the allegation. Drafts require deliberate review and use.

Calculators require as-of dates and event dates covered by the bounded snapshot from 2026-11-27.
Older and transitional regimes are refused. Limitation uses the current six-month standard
§24(1)/§26(3) StVG regime, complete-file confirmation, no suspension/court proceedings, and only
qualified §33(1) nos.1/9 OWiG interruptions (no.1 only once). It returns a mathematical boundary, never a finding
that prosecution is barred. Event days count; no weekend extension. Absolute cap: two years in
this narrow regime, subject to the explicit exclusions. Other interruptions need individual review.

Driving-ban checks support current §25(2) and ordered §25(3) no.1 StVG custody/endorsement cases.
They calculate latest effectiveness, not the end of the ban. Duration only starts upon required
custody/endorsement; no automatic driving entitlement. Multiple bans, credits, foreign alternatives
and older regimes are outside the calculator. Four months requires the specifically confirmed order.

Register checks support only confirmed one-/two-point OWi entries: 30/60 months from finality,
then one-year retention overlap, with earliest deletion on the following day. The sum is unadjusted input points, not a current legally effective
score. Tattagprinzip, measures, deductions, probationary licences and other §29 special rules need
separate review. Deletion is only an earliest boundary; do not derive driving entitlement.

Sanctions cover only BKat no.11.3 speed table 1c (vehicles outside nos.11.1/11.2), confirmed
ordinary negligence, no aggravation, no repeat-offender rule, confirmed location and excess AFTER
validated tolerance deduction. No guessed tolerance, fees or complete BKat coverage.

## Corpus and source limitations
All six official federal sources use the existing paragraph scraper. It omits annexes and tables;
BKatV, FeV and StVO source descriptions expose this. Selected sanction/point annex entries are
verified and versioned as parameters, not falsely presented as a complete retrievable corpus.
See sources/verification-2026-11-27.md for dated primary-source hashes and statutory anchors.

## Offline acceptance
Run scripts.validate_module --all, eval.dossier_eval --module verkehrsrecht and
 eval.plain_eval --module verkehrsrecht with the existing Python environment.
The 20 synthetic cases and literal expected dates establish deterministic contracts, not live legal quality.
