# D-074 — WP-132 employment backend implementation

- **Date:** 2026-11-27
- **Status:** Experimental backend implemented; automated checks passed. Human review/promotion deferred under D-071. §38 timing coverage remains qualified; see the execution record.
- **Authority:** Owner approved the specific linked proposal: “approved. proceed.”
- **Reversibility:** Additive code/data; migration downgrade refuses while new source rows exist.
- **Scope:** [approved proposal](../superpowers/plans/2026-11-27-wp132-proposal.md), [execution record](../superpowers/plans/2026-11-27-wp132-implementation.md).

## Context and decision

The Arbeitsrecht stub has no deterministic tools and maps only BGB. Existing
corpus storage lacks six catalog statutes; KSchG/BUrlG have no enabled adapter.
The declared `kenntnis` trigger cannot be evaluated. Implement the two approved
shared extensions through existing corpus and deadline interfaces: six source
types in the single migration chain, federal adapters, and explicit confirmed
knowledge dates independent of receipt, letter and event dates. Core 3.7.0 /
module API 3.5 records the additional capability. Keep legal qualifications and
employment arithmetic in the experimental module 0.2.0.

## Rationale, alternatives and consequences

A module-only subset with static warnings would leave corpus and deadline
subpackages incomplete. Reusing receipt for knowledge misstates the trigger;
employment rules in core violate ownership. The additive extension preserves
existing semantics and requires migration, API documentation and regression
checks. No new service, dependency, database or selection default is introduced.
Unsupported special regimes and uncertain facts remain explicit review items.

## Boundaries

No frontend, publication, deployment ingestion, live inference, commit or push
is authorized. Keep synthetic tests and draft/proposed review metadata. Deferred
human review is not verified promotion. Preserve the owner's AGENTS.md edit.
Root release ledgers were deliberately removed: module changelog, this record
and roadmap carry release/implementation status.


## Implementation rulings

- §38 short dates are conservative planning aids, not lateness or benefit decisions:
  current individualized agency-readiness/hindrance treatment is unresolved in the
  retrieved sources. See the module's dated source evidence. The long branch
  requires qualified confirmation that the backwards target is a working day;
  unsupported forward-rollover cases return missing input. This is an explicit
  coverage limit, not a claim that §26 SGB X never extends a backwards target.
- Registration is qualified by the confirmed reporting duty and branch, not a
  particular document label: dismissal, fixed-term contracts and agreements can
  all establish knowledge. Explicit-date spec validation accepts an existing
  nonempty qualification gate in place of a single document selector. No new general applicability mechanism is introduced.
- Whole-month employment periods use inclusive §187(2)/§188 boundaries distinct
  from plain clamped date addition; month-end/leap regressions pin the distinction.


## Pull-request publication authorization

After the implementation handoff, the owner explicitly requested: “prepare and
open a pr with this session's work.” Commit the WP-132 changes on
`codex/wp-132-arbeitsrecht`, push that branch and open a PR against `main`.
Preserve the owner's pre-existing uncommitted `AGENTS.md` edit outside the PR.
This supersedes the implementation-only publication boundary above for these
specific actions; merging, deployment, release and live inference remain outside
this authorization.
