# D-078 — WP-136 experimental Aufenthaltsrecht backend

- Date: 2026-11-27
- Status: Experimental backend implemented; automated verification passed. Human review/promotion deferred under D-071.
- Authority: Owner approved the [specific proposal](../superpowers/plans/2026-11-27-wp136-proposal.md): “approved. proceed.”
- Reversibility: Additive module/content, source catalog, guarded migration and calendar entry.
- Execution: [plan/results](../superpowers/plans/2026-11-27-wp136-implementation.md).

## Context and decision

Implement M7 through existing SDK, qualified deadline and deterministic-copy
interfaces. Add seven federal sources to catalog, citations/retrieval and the
single PostgreSQL migration chain. Add VwGO rollover to the existing civil
calendar including confirmed local holidays. Add AR/FA/UK/TR/RU module copy
and core disclaimer/AI/privacy summaries; reuse existing language metadata
and ISO date fallback. No new service, dependency or selection default.

## Rationale, alternatives and consequences

Extending existing libraries avoids duplicate date mechanics and supports
primary-source retrieval and multilingual safety notices. Module-only static
references would leave retrieval incomplete. A separate migration-law or
translation service adds infrastructure and privacy exposure without need.
Migration/source identity, calendar and every-language regressions are required.

## Boundaries

Experimental own-matter preparation; strongest urgent referral profile. No
asylum narratives, credibility/protection predictions or authority-side use.
Human legal/language review and promotion deferred under D-071; translated copy
remains draft. Backend copy is not verified GUI i18n, RTL or P12 acceptance.
No live inference, deployment ingestion, commits, pushes or publication.
Current primary law governs implementation; unsupported/transition regimes
require review rather than applying outdated roadmap shorthand.

## Approved safety supplement

The owner separately approved the [specific safety supplement](../superpowers/plans/2026-11-27-wp136-safety-supplement.md):
“Approve both safety additions”. Deadline specs gain optional
`excludes_confirmed`, enforced in the direct and dossier paths. Plain-copy
entries can opt into `referral_when_not_applicable`; only opted-in critical
items expose additive `referral_required` and enter the existing banner selector.
Existing modules retain their behavior. Contradictory asylum-regime confirmations
produce no date; unsupported M7 procedures retain urgent referral.

Source parser correction preserves lettered section identities (§34a, §87e,
§12b), retaining numeric BGB area-range tagging independently. This is necessary
supporting correctness work exposed by review, not a new source/storage model.
Interim applications reuse the existing explicit-event interface:
`ereignis_datum` means independently confirmed effective Bekanntgabe; lawsuits
use formal service. Module data requires the distinct qualifications. The dossier
now forwards the existing service-mode fact to event evaluation as well.

M7's existing calculator cross-check hook replaces model output with a strict,
minimised explicit source JSON block (`CITIZEN_RESIDENCE_FACTS:`) or clears
unbound confirmations. Pure calculator calls consume explicitly supplied facts;
the LLM path cannot establish confirmation merely by emitting a boolean.
Unexpected sensitive fields are excluded from the explanation summary. No new
endpoint, dependency or trusted model assertion is introduced.

Translations have distinct lawsuit/interim/objection titles; script-aware
sentence checks and selected discouragement phrases extend the existing static
copy gate. These automated checks do not establish fluent-human review.


## Verified limits

The module remains experimental with proposed parameters and draft translations.
Current §36 interim relief uses paragraph 2; §87e transition, airport/border and
other unsupported regimes require immediate individual review. All sixteen states
remain unavailable for automatic objection/direct-action selection. Explicit
qualified confirmation is a prerequisite, not evidence that state-law coverage
or individual legal review has been completed. No source population or live
inference was run. GUI i18n/RTL and combined P12 acceptance remain separately
owned. Parameter validity is bounded to 2026-11-27 through 2026-12-31.

The linked execution record contains source inspection, tests and offline report
results and the installed NumPy/default-target typing limitation. No commits,
pushes, release, deployment or verified-tier promotion are authorized or claimed.


## Verification and delivery

The execution record documents **2175 passing tests, four existing skips** on
disposable PostgreSQL 16/pgvector through migration 022, Ruff lint/format,
Python-3.12-target typing, eleven-module validation and purpose-drift checks.
Offline dossier 24/24 includes actual guarded drafts with every metric 1.0;
plain 29/29 covers all eight language variants. Default-target mypy retains
the existing installed NumPy stub limitation. All material review findings were
reproduced and corrected with regressions; no deferred review finding or second
review is claimed. Work is uncommitted on `codex/wp-136-aufenthaltsrecht`;
the owner's AGENTS.md edit remains preserved, and nothing was pushed/published.


## Pull-request publication authorization

After verification, the owner requested: “prepare and open a pr with this
session's work.” This authorizes committing WP-136 on
`codex/wp-136-aufenthaltsrecht`, pushing that branch and opening a PR against
`main`. The owner's pre-existing AGENTS.md edit remains outside the commit/PR.
This supersedes the earlier implementation-only no-commit/no-push boundary for
these specific actions. Merge, deployment, release, live inference and verified
promotion remain outside scope. The verified executable state is unchanged;
publication adds this authority note and the matching execution record.
