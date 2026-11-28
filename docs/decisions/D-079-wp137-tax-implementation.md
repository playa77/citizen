# D-079 — WP-137 experimental Steuerrecht backend

- Date: 2026-11-28
- Status: Experimental backend implemented; automated verification passed. Human review/promotion deferred under D-071.
- Authority: Owner approved the [specific proposal](../superpowers/plans/2026-11-28-wp137-proposal.md): “approved. proceed.”
- Reversibility: Additive module/content, source maps, guarded migration and procedural entries.
- Execution: [plan and results](../superpowers/plans/2026-11-28-wp137-implementation.md).

## Context and decision

Implement M8 as experimental own-matter tax preparation through the existing
module SDK. Extend the federal corpus/catalog/citation/retrieval adapters with
EStG, AO, SolZG, FGO and StBerG and the single PostgreSQL migration chain with
023. Add an AO domestic-post notification fiction and §108 rollover using the
existing civil/state calendar plus confirmed local holidays. Narrow AO evaluator
and dossier safeguards reject missing dispatch, disputed/later/nonreceipt and
unsupported modes; earlier actual receipt does not shorten the presumption.
Other modules retain their date semantics.

Add optional `scope.third_party_assistance` metadata, requiring false for this
module and exposing it through existing REST/MCP catalog views. It describes
supported use and reuses existing own-matter safeguards; it is not an
authenticated advice-center exclusion system. No roles/accounts are introduced.

## Rationale and alternatives

Existing retrieval and procedural interfaces keep one implementation of source
identity and workday rollover. Module-local references would leave primary-law
retrieval incomplete; calculator-local procedural code would duplicate it. A
separate tax service adds infrastructure without a demonstrated need. Approved
changes require a guarded migration, source/parser and direct-engine/dossier
regressions, additive catalog checks and updated capability versions.

## Consequences and limits

Core 3.12.0 / module API 3.10; tax module 0.1.0. Drafts cover objection,
suspension and simple amendment; none files automatically. Tariff, capped
allowances, signed assessment comparison and ordinary unadvised filing checks
are deterministic, parameter-backed and limited to 2026. Filing uses an explicit
versioned precomputed statutory date, 2027-08-02, requiring confirmed scope and
no additional local holiday; it is not a new general date engine. Other years,
advised/voluntary/individual-extension regimes and special tariffs are unavailable.
The existing calculator cross-check hook accepts only a single strict explicit
`CITIZEN_TAX_FACTS:` source block, not model-established confirmations.

Public source verification is dated and hashed. No deployment ingestion,
embeddings, live inference, GUI work, new dependencies or AGPL embedding.
Human legal/language review and promotion remain deferred under D-071;
parameters stay proposed and copy stays draft. Adding the module updates both
canonical disclaimers to 3.9.0, acknowledgement pins and prompt set to 3.10.0.
No commit, push, PR, release or deployment is authorized by this implementation.

## Release records

The historical top-level CHANGELOG.md/DECISIONS.md/ARCHITECTURE.md are absent
from HEAD. Do not recreate them incidentally. Module changelog, this decision,
the execution record and current roadmap/catalog form the scoped change record.

## Verification and delivery

Final `pytest tests/ -q -rs`: **2,292 passed, four existing skips**, with
PostgreSQL 16/pgvector migrated through 023. Includes the tax source
store/cite/exact-retrieval integration checks, deadline safeguards, all 47 tax
calculator tests, real module detail and rendered draft checks. Ruff lint/format,
Python-3.12-target mypy, twelve-module validation and purpose drift pass.
Dossier 20/20 (actual guarded drafts included; every metric 1.0) and plain
24/24 pass, with reports retained in the module goldset directory.

Independent whole-change review and narrow summary-fix review found no material
defects. The execution record documents the existing default-target NumPy typing
limitation, bare-pytest vendor-cache collection errors, skipped checks and async
cancellation/dependency warnings. No live-inference or human-reviewed readiness
claim. Work is uncommitted on `codex/wp-137-steuerrecht` based on merged WP-136
`598f68d`; owner's AGENTS.md edit remains preserved. Nothing pushed or published.

## Pull-request publication authorization

After verification the owner requested: “prepare and open a pr with this
session's work.” This authorizes committing WP-137 on
`codex/wp-137-steuerrecht`, pushing that branch and opening a PR against
`main`. The pre-existing owner edit to AGENTS.md remains outside the commit
and PR. This supersedes the earlier implementation-only no-commit/no-push
boundary for these specific actions. Merge, release, deployment, live inference
and verified promotion remain outside scope.
