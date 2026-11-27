# D-075 — WP-133 consumer contract backend

- **Date:** 2026-11-27
- **Status:** Experimental backend implemented; automated checks passed. Human review/promotion deferred under D-071; raw EUR-Lex ingestion remains unverified.
- **Authority:** Owner approved the [specific proposal](../superpowers/plans/2026-11-27-wp133-proposal.md): “approved. proceed.”
- **Reversibility:** Additive module/code/data; guarded migration downgrade.
- **Execution:** [plan and results](../superpowers/plans/2026-11-27-wp133-implementation.md).

## Context and decision

The contract stub retrieves BGB only. Add EGBGB and Regulation (EC) 261/2004
through existing corpus catalog/storage/dispatch with official EUR-Lex article
identity and the single Alembic chain. Keep qualified consumer calculations,
composite dates and exceptions in the module using existing SDK interfaces.
Core 3.8.0/module API 3.6 records the new corpus capability.

## Rationale, alternatives and consequences

Static references leave source coverage incomplete. A separate ingestion service
adds unnecessary infrastructure. The additive adapter requires migration and
provenance/parser regressions, with no new dependency/service/database or
selection default. No broader deadline/citation redesign is authorized.
Unsupported regimes and uncertain facts require review rather than arithmetic.

## Boundaries

Experimental 0.2.0; D-071 human review/promotion deferred. No frontend, deployment
ingestion, live inference, commit/push or publication. Preserve AGENTS.md.
Module changelog, roadmap and this record carry implementation status; do not
recreate deliberately removed release ledgers.


## Verification and delivery

The [execution record](../superpowers/plans/2026-11-27-wp133-implementation.md)
records 1,896 passing tests with four existing skips, all-module validation,
static checks and saved deterministic dossier/plain reports. Dossier 20/20
includes actual draft annexes; plain 24/24 covers DE/EN/de-LS. Independent review
findings on nested EGBGB identity, article boundaries, accepted law spellings
and ambiguous bare-section verification were fixed with failing-then-passing
regressions and actual PostgreSQL integration tests.

The adapter rejects unavailable/partial EUR-Lex output. Publisher challenge and
empty responses prevented raw-publisher ingestion verification; the source
snapshot describes the original act, not complete case-law coverage. Regular
limitation uses explicit manual year-end qualification; uncertain outer-limit
rollover requires separate confirmation. Bounded proposed rate/rule parameters
expire on 2026-12-31 without fallback. No verified promotion, deployment
population or live quality result is claimed. Work remains uncommitted.


## Pull-request publication authorization

After the implementation handoff, the owner requested: “prepare and open a pr
with this session's work”. This authorizes committing WP-133 on
`codex/wp-133-vertragsrecht`, pushing that branch and opening a PR against
`main`. The owner's pre-existing AGENTS.md edit stays outside the commit and PR.
This supersedes the implementation-only no-commit/no-push boundary for these
specific actions; merging, deployment, release and live inference remain outside
this authorization. The implementation verification record remains applicable;
publication adds only this authority note and the matching execution record.
