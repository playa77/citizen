# WP-136 safety supplement — specific approval requested

Status: approved by owner in this chat: “Approve both safety additions”, 2026-11-27.
Extends [approved proposal](2026-11-27-wp136-proposal.md) and D-078.

## Concrete changes

1. Add optional `excludes_confirmed: [qualification_key, ...]` to the existing
   module deadline spec model/loader. Existing specs default to an empty list.
   Both direct deadline evaluation and dossier evaluation reject a rule with
   any excluded qualification set true; the dossier returns `missing_input`
   with no date. M7 declares mutually incompatible asylum/administrative
   qualification keys in module YAML. No area-specific condition enters core.
   This prevents conflicting one-week/two-week confirmations from yielding the
   longer deadline. Existing API fact keys and endpoints are unchanged.
2. Add optional `referral_when_not_applicable: true` to module deadline-copy
   entries in the existing plain-copy schema. The renderer exposes an additive
   `referral_required: true` only for opted-in, critical, not-applicable items.
   The existing banner selector considers those items after missing-input and
   computed/provisional dates. It returns the existing module/spec pointer,
   with no invented date. M7 opts in; all other modules preserve their current
   banner behavior. This ensures unsupported old-law/airport/unknown asylum
   procedures retain a prominent translated urgent-help action. No new API
   workflow or endpoint.

## Why and alternatives

Mandatory positive confirmation alone cannot detect contradictory facts.
Warnings inside a non-banner card can disappear when a client renders only the
banner. Generic opt-in data keeps domain rules in the module and preserves
other modules' behavior.

Alternatives: leave these cases unavailable without a prominent banner (fails
M7's agreed duty of care), remove all deterministic asylum deadlines (loses
requested functionality), or introduce a separate asylum service (unnecessary
infrastructure). Recommended: the two additive fields above with explicit
regressions and API documentation.

## Checks and consequences

Test conflicting qualifications through direct evaluator and public dossier/plain
flow; no computed date. Test unsupported procedures in all eight languages;
no date, but actionable banner. Test unchanged behavior when optional fields
are absent. Update module API capability/schema version, documentation and
D-078 to record approval. No dependency, migration branch or inference change.
