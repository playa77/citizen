# D-076 — WP-134 traffic administrative-offence backend

- **Date:** 2026-11-27
- **Status:** Experimental backend implemented and automated checks passed; human review/promotion deferred under D-071.
- **Authority:** Owner approved the [specific proposal](../superpowers/plans/2026-11-27-wp134-proposal.md): “approved. proceed.”
- **Reversibility:** Additive module/code/data and guarded migration downgrade.
- **Execution:** [plan and results](../superpowers/plans/2026-11-27-wp134-implementation.md).

## Context and decision

Implement M5 through existing module interfaces. Add OWiG, StVG, StVO, BKatV,
FeV and StPO corpus source types through the federal adapter, retrieval/citation
mappings and the single Alembic chain. Add shared StPO procedural rollover for
OWiG and later M10. Keep area applicability/content in modules.

## Rationale, alternatives and consequences

Module-only static references leave retrieval coverage incomplete and duplicate
procedure mechanics. A separate procedure service adds unnecessary infrastructure.
The approved additive approach needs migration, source/provenance regressions,
calendar golden tests and core/module-contract capability version updates.
No new service, dependency, storage system or module-selection default.
Annex and sanction coverage must be stated precisely; unknown qualifications,
interruptions or records cannot establish expiry, sanction or driving entitlement.

## Boundaries

Traffic administrative offences only; accident settlement remains stage 2.
Experimental tier and D-071 deferred human review/promotion. Preserve AGENTS.md.
No frontend, live inference, deployment ingestion, commit, push or publication.
Further material shared extensions require specific approval. Existing roadmap,
module changelog and this decision record carry status; deleted ledgers stay deleted.


## Supporting integration corrections

Exact-reference retrieval now matches complete hierarchy segments, avoiding
§1/§10 collisions exposed by real PostgreSQL tests. The calculator result
assembler retains deterministic refusal commentary and guards overall
assessments for `unavailable` as well as `missing_input`, including mixed
results. The traffic module publishes its values through the already
established `deterministic_result` projection for dossier/explanation use.
These bounded corrections preserve existing interfaces; no new architectural
surface is introduced. The execution record lists seven independently
reviewed issues and their regression tests.


## Verification and delivery

The execution record documents **2,003 passing tests, four existing skips**
with disposable PostgreSQL16/pgvector, Ruff lint/format, Python3.12 typing,
all-module validation and purpose-drift checks. Dossier20/20 includes actual
draft annexes; plain25/25 covers DE/EN/de-LS. Seven independent-review issues
were fixed with observed failing-then-passing regressions. The installed
NumPy3.12 stub prevents the default3.11-target mypy command; the documented
Python3.12 command passes without changing configuration or dependencies.

Sources were verified from six official consolidated snapshots and parsed
locally without embeddings. Paragraph-only retrieval excludes annexes and
tables; selected speed/point entries are bounded proposed parameters. No
actual deployment ingestion, live inference, human promotion or accident
settlement is claimed. Work remains uncommitted on
`codex/wp-134-verkehrsrecht`; no push/publication is authorized or performed.

## Pull-request publication authorization

After implementation verification, the owner requested: “prepare and open a pr
with your work.” This authorizes committing WP-134 on
`codex/wp-134-verkehrsrecht`, pushing that branch and opening a PR against
`main`. The owner's pre-existing AGENTS.md edit stays outside the commit and PR.
This supersedes the implementation-only no-commit/no-push boundary for these
specific actions. Merging, deployment, release and live inference remain
outside authorization. The execution record identifies the tested implementation;
publication adds only this authority note and the matching execution record.
