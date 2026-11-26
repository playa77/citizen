# D-072 — WP-130 backend implementation

- **Date:** 2026-11-26
- **Status:** Implemented under D-071; human review deferred, no release.
- **Reversibility:** Additive code/data changes. Migration downgrade refuses
  while new-source rows exist rather than deleting corpus data.
- **Authority:** Owner request to finish WP-130, specific extension approval
  and deferred-review direction recorded in [D-071](D-071-module-implementation-and-deferred-human-review.md).
- **Execution:** [completion plan](../superpowers/plans/2026-11-26-wp130-completion.md).

## Context and decision

The 0.1.0 foundation lacked court service triggers, supported corpus storage,
calculators, templates and copy. Implement the package through the existing
module and backend boundaries, without adding a service or dependency:

- Core 3.5.0 / module API 3.3 adds explicit service date, document type and
  service-mode facts, ZPO rollover and a public module-owned `intake_schema`.
  HTTP and read-only MCP module detail expose the schema; API request and
  privacy validation retain their own existing contracts.
- Service rules never borrow letter dates, postal fictions, Verwaltungsakt
  assumptions or SGG Rechtsbehelfsbelehrung extensions. Domestic rules require
  confirmed service and explicit region for holiday rollover. A missing region
  could otherwise turn a local holiday into a misleading exact deadline.
  Unknown/foreign/public service yields missing-input status, while an explicit
  different document type makes only the nonmatching rule inapplicable.
- ZPO, InsO, RDG and RVG reuse the existing source catalog/parser and the single
  PostgreSQL migration chain (`016_debt_sources`). No source is preselected.
- Module 0.2.0 owns its two deadline specifications, parameter-backed monthly
  attachment/P-account checks, qualified limitation and collection-cost checks,
  prompts, five guarded draft templates, intake/dossier and multilingual copy.
  Missing qualifications or matching parameter periods produce unavailable
  results, not guessed amounts. The calculation harness preserves unavailable
  status instead of presenting a successful arithmetic check.
- All content remains experimental/proposed/draft. Human names and sign-offs
  are not implementation gates; reviews remain deferred under D-071.

## Rationale and alternatives

Encoding service as Bekanntgabe or using a letter date would calculate a
different trigger and was rejected. Core-owned debt calculations would breach
module ownership. Reusing an unrelated legal persona would breach D-069/D-070.
Existing parser/storage and SDK extension points avoid a new service/schema
architecture. A public intake schema gives clients the module-specific form
contract without changing existing HTTP request envelopes or adding GUI code.

## Consequences and verification boundaries

Run Alembic and seed the module's versioned parameters before deployment use;
populate the explicitly selected corpus with an independently configured
embedding setup. Empty/missing corpus remains guarded. Source snapshots and
synthetic fixtures are not proof of a populated deployment or live inference
quality. Those operational checks remain pending; human review and promotion
are deferred until all modules are implemented. No live-inference credential,
corpus embeddings, publication, commit, push or release was used here.

Deterministic dossier/plain reports, source hashes and attachment-table
comparison evidence are stored under the module. Final commands and test
results are recorded in the completion plan.

## Pull-request publication authorization

After the implementation handoff, the owner explicitly requested a pull request
with this session's work. Commit and publish the session changes on
`codex/wp-130-schuldnerrecht` against `main`, preserving the pre-existing
uncommitted `AGENTS.md` edit outside the PR. This authorizes PR publication,
not merging or releasing.
