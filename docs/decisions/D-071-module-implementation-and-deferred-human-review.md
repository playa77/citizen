# D-071 — Module implementation first; human review deferred

- **Date:** 2026-11-26
- **Status:** Accepted by owner in this Codex chat.
- **Reversibility:** Reversible; no release or deployment is authorized.
- **Amends:** Roadmap P13/WP-130–139, module catalog definition of done,
  module-authoring review prerequisites and earlier approval workflow.

## Context and authority

The owner requested completion of WP-130 and explicitly approved the proposed
additive backend extensions. When asked for parameter-steward and reviewer
identities, the owner instructed: **“excise all places from the roadmap where
you need a name for approval”** and **“all other human approval is deferred
until you have implemented all modules.”** GUI work remains separately owned
and outside this agent's implementation scope (D-069).

## Decisions

1. Remove named-person requirements as implementation/approval gates. Steward
   and reviewer roles may remain organizational descriptions, but obtaining a
   person's name or sign-off must not block implementation.
2. Defer remaining human approvals and reviews until all queued legal-area
   modules have been implemented. This includes parameter, plain-language,
   practitioner and owner review checkpoints. Do not repeatedly request those
   approvals while implementing the agreed roadmap.
3. Continue automated validation, deterministic regression tests, source
   verification, privacy/egress controls and quality measurements throughout
   implementation. Deferred human review is not completed review: retain honest
   `proposed`/`draft` metadata and record pending review. Do not claim verified
   promotion, completed live evaluations or completed corpus ingestion without
   evidence. Implementation completion and reviewed/public-release readiness
   are separate statuses.
4. Implement the specifically approved WP-130 shared extensions: explicit
   service date, document type and service-mode facts in the existing deadline
   engine/dossier contract; ZPO rollover support; and additive ZPO, InsO, RDG
   and RVG corpus catalog and PostgreSQL source-type support. Preserve existing
   SGB behavior and additive `/api/v1` compatibility. No new service or storage
   system is introduced.

## Rationale, alternatives and consequences

The owner chose implementation across the module queue before human approval
rounds. Waiting for named reviewers per subpackage was rejected. Automated
quality checks remain active, and deferred reviews are collected for the later
cross-module review phase. This decision does not authorize publication,
deployment, sending messages, spending on live inference, or use of developer
agent credentials for tests.

## Execution

See the [roadmap](../roadmap-v3.0.0.md), [module catalog](../module-catalog.md)
and [authoring guide](../MODULE-AUTHORING.md). WP-130 implementation and
validation results will be recorded alongside the module work.
