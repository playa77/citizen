# Mietrecht backend package (WP-131)

Module 0.2.0 / core 3.6.0 / module API 3.4. Experimental, human legal and
plain-language review deferred under D-071. Intended only for your own matter
as a residential tenant. No landlord representation, automatic rent reduction,
consent, sending, court filing or claim that a termination has been cured.

## Inputs and checks

- Actual receipt plus document type drives §558b consent and §556 objections.
  Both use the statutory calendar-month end, not a fixed day count.
- Hardship objection uses the confirmed termination date, backwards two months,
  with confirmed ordinary termination and timely rights notice. Otherwise it
  asks for review; a missing rights notice can allow later objection.
- The cure-period check needs confirmed court service/pendency, arrears and no
  previous qualifying cure in two years. It does not cure a separate ordinary
  termination or establish the amount/full payment needed.
- Civil rollover requires the correct Land and confirmed additional local
  holidays. Statewide rules start in 2024. Dates outside supported arithmetic
  return missing input. Ordinary termination counts Saturdays within the first
  three Werktage; a last-day Saturday rolls to the next workday (§193 BGB).
- Rent checks need a legally qualified reference date/comparison rent,
  confirmed exceptions and exact official municipality name. Unknown coverage
  never falls back to 20% or establishes absence of a rent brake. Comparison
  rent below current rent does not establish an entitlement to rent reduction.
- Cost checks verify arithmetic of confirmed allocable costs and allocation
  keys only. Repairs/administration, special heating regimes, unconfirmed keys
  and reduction percentages require separate assessment.

## Sources and coverage

`parameters/` stores proposed, date-selected legal values. `sources/coverage.yaml`
records all 16 Länder, including unsupported/blocked/unresolved coverage;
`regional-designations.yaml` contains positive verified-source subsets only.
A source hash proves integrity of the recorded excerpt, not legal review.
Municipality lists and instruments require maintenance as they change. No
claim of complete nationwide executable ordinance coverage is made.

BGB, ZPO, BetrKV and HeizkostenV use existing federal corpus adapters. State
ordinance snapshots use `app.services.corpus.normalize_state_ordinance(record)`
and the existing embedding/upsert boundary. Required fields and an example are
in `sources/state-ordinances.yaml`. Only official per-Land HTTPS hosts and
matching content digests are accepted. Snapshots are explicitly labeled limited
applicability excerpts; they are not a complete state-law corpus. No automatic
state scraper is advertised. Corpus chunk counts alone cannot prove geographic,
temporal or substantive source coverage; the model must bind each assertion to
matching evidence or leave it unresolved.

## Installation and offline checks

Use the existing development environment and a disposable PostgreSQL16/pgvector
for tests. Apply migration `017_tenancy_sources`, then seed parameters:

```bash
python -m alembic upgrade head
python -m scripts.seed_module_parameters --module mietrecht
python -m scripts.validate_module modules/mietrecht
python -m eval.dossier_eval --module mietrecht
python -m eval.plain_eval --module mietrecht
```

Select modules/sources explicitly; enablement does not choose a session scope.
Populate the deployment corpus only through independently authorized ingestion
and embedding configuration. No deployment ingestion/embedding or live
inference was performed during implementation. The 20 synthetic pipeline cases
and deterministic dossier/plain reports do not prove live inference quality.
Keep `review_status: proposed` and copy review `draft` until actual review.
The disclaimer acknowledgement changes to `v3.3.0`.
