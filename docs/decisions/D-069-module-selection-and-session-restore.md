# D-069 R2 — Module selection and session restore

- **Date:** 2026-11-25
- **Status:** Accepted by owner; backend verified under D-070 on 2026-11-26.
  GUI/session implementation and combined acceptance remain pending with their
  separate owner. The 2026-11-26 continuation direction below supersedes the
  earlier gate on further backend implementation.
- **Supersedes:** the Sozialrecht default designation in historical D-036.
  The core/module architecture, deployment-tier rules (D-037), API compatibility
  rule (D-039) and separate GUI repository (D-067) remain applicable.
- **Execution record:** [first blocking TODO](../../TODO.md).

## Context

Sozialrecht was the first implemented legal-area module. Earlier documentation
promoted it to the implicit module for a new request or installation. The owner
has replaced that loading model: Sozialrecht is one module among all the
others, which are to be implemented after this prerequisite is finished.

The backend currently still contains `DEFAULT_MODULE`, implicit request and
corpus fallbacks, and REST/MCP default metadata. Documenting the new behavior
does not change those implementations.

## Decision

No module is a default. A fresh GUI/desktop session presents all modules for
explicit loading selection, with none preselected. When a prior session
exists, startup also offers **Restore last session**. Restoration is an
explicit user action and recovers the prior session's selection and context;
it does not establish defaults for future new sessions.

Deployment enablement and module maturity determine availability, not what
the user has loaded into a session. A catalog listing is not a request to
load every module. Missing or unavailable restored modules must be surfaced,
never silently replaced with Sozialrecht or another fallback.

Removing the single-module fallback and implementing startup selection and
session restoration is the **first implementation task**. Implement no
further legal-area modules until its [TODO checklist](../../TODO.md) passes.

## Rationale and alternatives

Explicit selection gives each module equal loading status while supporting
continuity for returning users. Keeping Sozialrecht preselected would retain
the rejected default model. Loading every module automatically would bypass
the user's choice. Automatically restoring without offering the choice would
not implement the requested startup flow.

## Consequences and acceptance

The backend and `playa77/citizen-gui` both need changes before new modules are
implemented. Registry/configuration, request scope, corpus setup, provenance,
REST/MCP metadata and GUI session persistence must follow explicit selection.
Existing `/api/v1` clients need a documented compatible transition; this
decision does not silently remove fields or change current error contracts.

The linked TODO defines completion checks. Until they pass, API reference
sections describing the current fallback are legacy implementation facts,
not the intended product behavior. Historical release notes remain historical.

## D-070 implementation follow-up — 2026-11-25

[D-070](D-070-explicit-backend-module-scope.md) records the owner's specific
approval to remove the catalog fields outright, superseding the compatible
transition constraint above for those two fields only. It also records the
subsequently approved deterministic preparation and explicit backend selection
policies. Backend changes are in the working tree and passed the application/database
checks; see its verification record for skips and existing warnings.
GUI chooser, local session persistence and combined acceptance remain incomplete
and are assigned to the GUI owner outside this session.

## Owner approval and scope clarification — 2026-11-26

The owner confirmed in this Codex chat that the GUI and roadmap work are already
approved and instructed this agent to record approval and continue. The owner
then explicitly clarified that GUI work is noted here, not implemented here,
and is neither this agent's job nor owned by this agent. The initial execution
note incorrectly assigned GUI ownership to this agent; this correction removes
that assignment. GUI implementation remains outside this session and in the
separate `playa77/citizen-gui` repository. Approval does not establish completed
GUI implementation or combined acceptance. The existing D-069/D-070 design
remains in force.

### Backend continuation direction

After explicitly excluding GUI implementation from this agent's ownership, the
owner reiterated the existing approval and instructed this agent to get to work
on the backend roadmap. This newer direction supersedes the requirement to wait
for separately owned GUI acceptance before continuing backend P13 work. It does
not claim that GUI implementation or combined acceptance has been verified;
those open items remain with the GUI owner. Existing module source-review,
testing, privacy and promotion requirements remain applicable.
