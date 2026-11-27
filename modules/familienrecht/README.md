# Familienrecht — experimental backend (WP-135)

Version 0.3.0, core 3.10.0/module API 3.8; D-077. Supports people preparing
their own family matter and advice appointment. No frontend or automatic filing.

- Qualified ordinary complaint dates only after confirmed formal domestic
  written notification outside §113 FamFG. Urgent/special cases, unsuccessful
  notification and representation/grounds rules need prompt individual review.
- Qualified statutory 2026 minimum-maintenance/child-benefit and UVG arithmetic.
  Age is for the target month, not today. No income assessment or entitlement
  decision; unsupported periods, partial UVG months and deductions refuse.
- Conditional §1613 Abs.1 month start, never a general filing deadline.
- Guarded information-request, response-outline and UVG-preparation drafts;
  minimised intake, appointment dossier, DE/EN/de-LS static copy.
- Twenty synthetic cases; deterministic dates/refusals and separate calculator
  tests. Offline dossier/plain reports measure deterministic preparation only.

OQ-7: publisher material inspected did not establish reuse permission for
bundling the Düsseldorfer Tabelle. No income groups, table percentages,
self-retention or spousal-maintenance guideline values are bundled. Consult the
[current publisher overview](https://www.olg-duesseldorf.nrw.de/infos/Duesseldorfer_Tabelle/index.php)
with qualified advice. Statutory parameters derive independently from MinUhV,
BGB, UhVorschG and EStG; see `sources/verification-2026-11-27.md`.

Custody, contact, child welfare and violence are referral-first; no automatic
parental-fitness or custody recommendation. Do not upload unnecessary children's
or former partners' names, birth dates, addresses, diagnoses or narratives.
Bring necessary records securely to the advice appointment.

Parameter and copy review remain proposed/draft under D-071. Deployment ingestion,
live inference, human review and promotion have not been performed or claimed.
