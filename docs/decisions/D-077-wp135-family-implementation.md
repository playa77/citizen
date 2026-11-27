# D-077 — WP-135 experimental Familienrecht backend

- Date: 2026-11-27
- Status: Experimental backend implemented; automated verification passed. Human review/promotion deferred under D-071.
- Authority: Owner approved the [specific proposal](../superpowers/plans/2026-11-27-wp135-proposal.md): “approved. proceed.”
- Reversibility: Additive module/source data, code and guarded migration downgrade.
- Execution: [plan and results](../superpowers/plans/2026-11-27-wp135-implementation.md).

## Context and decision

Build out M6 through existing module interfaces. Add FamFG, UVG and MinUhV
sources through the federal adapter, retrieval/citation mappings and the
single migration chain. Add narrowly scoped FamFG procedural rollover using
the existing current civil calendar and explicit confirmed facts.

## Rationale, alternatives and consequences

Shared extensions provide retrieval and avoid duplicating procedural mechanics.
Static module-only references leave corpus coverage incomplete; a separate
family-procedure service is unnecessary infrastructure. No new dependency,
service, storage or selection default. Tests must cover source identity,
migration, holiday rules and refusal of unsupported procedural regimes.

## Boundaries

Experimental; human review/promotion deferred under D-071. Own-matter preparation,
qualified statutory arithmetic and guarded drafts only. Child welfare, custody
and contact are referral-first, with strict third-party data minimisation.
OQ-7 remains open unless publisher reuse terms are established; no bundled
Düsseldorfer Tabelle or guideline self-retention values in that case. No live
inference, deployment ingestion, frontend, commits, pushes or publication.

## Verification and delivery

The linked execution record documents **2057 passing tests, four existing skips**
with disposable PostgreSQL 16/pgvector migrated through 021; Ruff lint/format,
Python 3.12 typing, ten-module validation and purpose drift passed. Dossier 20/20
includes actual draft annexes with complete deterministic metrics; plain 25/25
covers DE/EN/de-LS. Integration failures were corrected with observed failing
then passing checks; fresh review found no material actionable issue. Default
3.11-target mypy retains the previously documented installed NumPy 3.12 stub
limitation; no configuration/dependency workaround hides it.

Official snapshots were inspected and parsed locally without embeddings.
Publisher material did not establish guideline reuse permission, so OQ-7
remains open and no table/self-retention data is bundled. No entitlement,
live-quality, deployed-ingestion or human-promotion claim is made. Work remains
uncommitted on `codex/wp-135-familienrecht`; no push or publication performed.


## Pull-request publication authorization

After implementation verification, the owner requested: “prepare and open a pr
with this session's work.” This authorizes committing WP-135 on
`codex/wp-135-familienrecht`, pushing that branch and opening a PR against
`main`. The owner's pre-existing AGENTS.md edit remains outside the commit/PR.
This supersedes the implementation-only no-commit/no-push boundary for those
specific actions. Merging, deployment, release and live inference remain
outside this publication scope. The execution record identifies the tested
implementation; publication adds only this authority note and its matching
execution record.
