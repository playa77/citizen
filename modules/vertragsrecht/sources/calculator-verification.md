# WP-133 calculator verification — 2026-11-27

Status: proposed parameters; human legal review pending. These pure checks do
not establish entitlement, applicability, default or completeness of evidence.
No live inference, ingestion or embeddings were run.

## Primary evidence and bounded snapshot

- Deutsche Bundesbank, [official §247 BGB rate table](https://www.bundesbank.de/de/bundesbank/organisation/agb-und-regelungen/basiszinssatz-607820),
  retrieved 2026-11-27: effective 2025-01-01 2.27%, 2025-07-01
  1.27%, 2026-01-01 1.27%, 2026-07-01 1.52%. Four explicit half-year
  segments end 2026-12-31; no extrapolation. Retrieval used one search and one
  open, serially, with more than two seconds between calls; no retries.
- [§288 BGB](https://www.gesetze-im-internet.de/bgb/__288.html), retrieved
  2026-11-27 by the integration worker: five percentage points generally;
  nine only for confirmed Entgeltforderungen with no consumer involved.
  §286 default and a constant principal must be confirmed independently.
  The calculator adds no €40 charge, costs, compound interest or higher
  contractual rate. Integer basis points and Fraction arithmetic preserve
  exact cents through actual days / calendar-year days; rounding half-up
  occurs once after summing all segments. The selected day-count convention
  and confirmed interest-bearing inclusive period remain review assumptions.
- [§355 BGB](https://www.gesetze-im-internet.de/bgb/__355.html) and
  [§356 BGB](https://www.gesetze-im-internet.de/bgb/__356.html), retrieved
  2026-11-27 by the integration worker: 14 days; goods receipt variants in
  §356(2); information prerequisite in (3); outer limit twelve months and
  14 days in **(4)** in the retrieved current text. Services use §355(2)'s
  contract date. A qualified trigger and excluded exceptions, including
  early extinguishment under §356(5), are mandatory. Financial services,
  digital content and other special regimes are unsupported. Late adequate
  notice yields the earlier of notice +14 days and the outer cap. Absent
  notice yields the cap. Calendar calculations exclude the triggering day;
  a missing anniversary day becomes the final day of that month (§188(3)).
  The selected expiry is adjusted under §193 using an explicitly confirmed
  complete local holiday calendar. If this would extend the selected outer cap,
  separate `outer_limit_rollover_confirmed=true` legal confirmation is required;
  otherwise this disputed boundary returns unavailable.
- [Official EUR-Lex original Regulation (EC)261/2004](https://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=CELEX:32004R0261:DE:HTML),
  retrieved 2026-11-27 by the corpus worker: Art7(1) €250 through 1500km;
  €400 for intra-Community journeys over 1500km and other journeys through
  3500km; otherwise €600. Art7(4) requires great-circle distance. Art7(2)
  allows 50% reduction only for qualifying Art8 rerouting and the applicable
  2/3/4-hour arrival threshold. The calculator requires explicit legal
  confirmation of either reduction or unreduced treatment. It does not
  derive entitlement from distance, notice, delay or extraordinary events.
  `long_delay` is accepted only with independently qualified entitlement;
  this original regulation alone is not evidence of the CJEU delay extension.
  [CURIA press release for joined C402/07 and C432/07](https://curia.europa.eu/site/upload/docs/application/pdf/2009-11/cp090102en.pdf),
  verified by the integration worker on 2026-11-27, supports the final-destination
  arrival delay of at least three hours subject to extraordinary-circumstances
  exceptions. `entitlement_confirmed` must include that qualified legal test.

Both parameter sets are bounded to as_of 2026-11-27 through 2026-12-31.
Historical triggers and rate segments may be used within this current legal
snapshot; this does not claim verification of historical versions of general
rules. Unknown/expired/missing parameters return unavailable without fallback.

## Acceptance evidence

Focused pure regression suite covers segmented interest, one rounding point,
nonconsumer payment-claim qualification, missing facts, strict integer amounts,
rate coverage gaps, leap-year denominator, withdrawal weekend/holiday rollover,
leap anniversary, absent and late notice outer caps, unsupported regimes,
flight distance boundaries/intra-EU bands, qualified reduction, expired rules,
unknown calculation types and SDK parameter snapshot identity.

The suite is run with `--confcutdir=tests/unit` to avoid global DB fixtures:
these tests use only pure calculator functions and YAML. The normal command
initially failed before collection because Docker socket access was denied by
the sandbox. Integration owns full PostgreSQL-backed verification.
