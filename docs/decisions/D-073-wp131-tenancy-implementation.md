# D-073 — WP-131 tenancy backend implementation

- **Date:** 2026-11-27
- **Status:** Experimental backend implemented and automated checks passed; human review/promotion deferred under D-071. Regional coverage remains explicitly partial. Verification is recorded in the linked plan.
- **Reversibility:** Additive code/data; source migration downgrade refuses while new source rows exist.
- **Authority:** Owner requested WP-131 implementation and explicitly repeated that direction after the concrete shared-extension proposal; continue without additional confirmation rounds. This authorizes the described implementation, not publication, deployment or live inference.
- **Scope:** [proposal](../superpowers/plans/2026-11-26-wp131-proposal.md), [execution and evidence](../superpowers/plans/2026-11-26-wp131-implementation.md).

## Context and decision

Mietrecht was a routing-only 0.1.1 stub. The existing Fristen engine supported
administrative notification and actual court service, but not receipt,
calendar-month-end or backwards notice periods. Existing corpus storage did
not accept BetrKV, HeizkostenV or state tenancy ordinances.

Implement module 0.2.0 through the existing boundaries, with core 3.6.0 /
module API 3.4:

- Extend the existing Fristen spec and dossier facts additively with explicit
  receipt/event dates, month-end anchoring, backwards offsets and module-owned
  qualification keys. Unknown qualifications return missing-input status,
  never an inferred receipt, service or legal exception decision.
- Use a precise civil calendar for new BGB rollover and module termination
  checks. The legacy calendar has inaccurate state holiday entries and repeats
  boundary-year Easter dates. Preserve its existing administrative/ZPO path in
  this package; new civil rules use Gregorian Easter, current statewide rules
  from 2024 and explicitly confirmed local holidays. Do not apply forward
  rollover to backwards notice periods. SDK exports the civil holiday helper.
- Add the three corpus types through existing adapters and one Alembic chain.
  State-source normalization validates official host, Land, publication,
  validity and content digest; it preserves jurisdiction and labels the limited
  source excerpt. State scraping is not advertised as implemented. Collected
  applicability excerpts are not full ordinance corpora or proof of deployment
  readiness for every municipality.
- Keep rent ceilings, regional applicability, cost arithmetic, termination
  periods and deposit calculations in module-owned versioned parameters/pure
  SDK calculators. Require exact municipality names and separate cap/brake
  validity. Positive coverage only; absent/expired/ambiguous data refuses an
  amount rather than treating the 20% federal ceiling as a local clearance.
- Implement guarded draft templates, public intake schema, dedicated prompts,
  dossier and DE/EN/de-LS copy. No inferred reduction percentage, automatic
  consent, sending or promotion. Human content review stays deferred (D-071).

## Alternatives and consequences

Module-only preparation would leave the catalog's deadline/source package
incomplete. Reusing Bekanntgabe or letter dates for receipt, applying fixed-day
month intervals or putting tenancy rules in core would change legal semantics
or breach module ownership. A separate crawler/storage system is unnecessary;
source-checked snapshots reuse current storage and ingestion interfaces.

The additive fact contract and SDK capability require updated authoring/API
documentation and regression checks. Deployment still needs migration,
parameter seeding and explicitly selected corpus ingestion with independently
configured embeddings. A chunk-count readiness flag is not proof of complete
regional corpus coverage. Gaps and source restrictions are recorded under
`modules/mietrecht/sources/coverage.yaml`, not silently completed.

Disclaimer v3.3.0 adds the tenancy notice and requires renewed acknowledgement.
Prompt set 3.4.0 identifies the dedicated tenancy profile/calculator prompts.
Core plain copy still summarizes unchanged Part B obligations; its pins are
updated after checking own-matter, AI fallibility, draft and human-check text.

## Verification boundaries

Use synthetic fixtures and disposable PostgreSQL 16/pgvector. Offline dossier
and plain reports establish deterministic/content contracts, not live inference
quality. Human review/promotion, live evaluation and deployment ingestion remain
separate. No GUI, credential extraction, live inference, commit, push or release
is authorized by this implementation task. Preserve the pre-existing AGENTS.md
edit. Root CHANGELOG.md/DECISIONS.md were deliberately removed; retain the
module changelog, this decision and roadmap as the release record.

## Pull-request publication authorization

After the implementation handoff, the owner explicitly requested preparation
and opening of a PR with this session's work. Commit and publish the WP-131
changes on `codex/wp-131-mietrecht` against `main`, preserving the pre-existing
uncommitted `AGENTS.md` edit outside the PR. This authorizes PR publication,
not merging, deployment or release.
