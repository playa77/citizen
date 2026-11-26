# D-070 — Explicit backend module scope and catalog compatibility exception

- **Date:** 2026-11-25
- **Status:** Accepted by owner; backend implementation verified on 2026-11-26
  with the locked development environment and disposable PostgreSQL/pgvector.
  GUI/session acceptance remains incomplete. See the linked verification record
  for skips and existing warnings.
- **Reversibility:** Reversible in code; clients must adapt to removed fields.
- **Extends:** [D-069](D-069-module-selection-and-session-restore.md).
- **Authority:** Owner's backend handoff request in this Codex chat and explicit
  answers approving deterministic preparation and explicit-selection policies.
- **Execution:** [TODO step 1](../../TODO.md),
  [implementation plan](../superpowers/plans/2026-11-25-explicit-module-scope.md).

## Context and observed impact

The starting checkout was `main` at `30f9642`, with only the owner's
uncommitted architecture-ownership addition to `AGENTS.md`. No implementation
from the earlier agent was present. No GUI repository was inspected.

The catalog fields and internal selection are independent mechanisms:

| Observed source | Existing behavior | Required change |
|---|---|---|
| `app/api/routes/modules.py`, `app/mcp/server.py` | List envelopes include `default_module`; list/detail summaries include `is_default` | Remove both keys entirely |
| `app/modules/registry.py`, `app/core/config.py`, `app/main.py` | Configured default must be enabled for startup | Remove the setting and requirement; retain tier, manifest and enablement validation |
| `app/modules/runtime.py` | Empty scope selects the default; calculators, regime providers, dossier/plain content and provenance share it | Empty scope resolves to no module |
| `app/modules/areas.py` | Table assembly requires a default's preset, prompt and corpus data | Assemble peer tables without a privileged module |
| `app/services/prompts.py`, `app/services/reasoning.py` | Missing/unknown/profile-less scope borrows legal prompts, including import-time constants | Require an explicitly selected usable profile before legal inference |
| `app/core/pipeline.py` | Empty scope retrieves across the corpus plus default-derived norm references | Deterministic preparation only when scope has no usable profile; no retrieval or inference |
| `app/services/chat_reasoning.py`, `app/services/case_chat.py` | Empty scope borrows the default persona; conversation retrieval is unscoped | Selection-required deterministic response before client/retrieval access when no usable profile exists |
| `app/api/routes/presets.py` | No match yields a default-derived preset | Return no preset on no match; preserve actual matches and explicit apply |
| `app/services/document_generators.py`, `app/api/routes/documents.py` | Missing module selects default templates; REST omits the module even for scoped cases | Require an explicit internal ID; resolve REST templates from case scope and require a choice for ambiguity |
| `app/services/parameter_store.py` | Missing domain selects the default | Require explicit nonempty domains; calculator callers already supply their module's domain |
| `app/services/corpus.py` | Unconfigured sources use default-module data; empty/unknown-only runtime selection falls back again | Unconfigured means no sources; saved empty selection stays empty; preserve explicit configuration and one-shot overrides |
| `app/api/routes/goldset.py` | Demo scope uses the default although `GOLDSET_PATH` documents a Sozialrecht compatibility alias | Keep the documented Sozialrecht alias explicit |
| `app/modules/validate.py` | Offline integration validation chooses a configured/candidate default | Validate peer table composition without choosing one |

These are observations of the named source files. The conclusion that changing
only provenance would conceal remaining prompt/data borrowing is an inference
from their independent call paths, not a test result.

Explicit module IDs, aliases, multi-module composition, procedural-key ownership,
unknown/disabled request errors, versioned deterministic rules, privacy/tier
gates and human review constraints remain applicable. A preset suggestion or a
catalog listing does not load modules. Existing module-declared profile
inheritance is explicit module data, not implicit request selection.

## Decisions

1. Remove `default_module` and `is_default` from REST and MCP list/detail
   responses. This is an **owner-authorized exception to D-039's additive
   `/api/v1` rule**. No deprecated, null, false or replacement preference field
   remains. D-039 continues to govern other changes.
2. No configured module default remains. Omitted/empty scope selects no legal
   module, including in provenance and derived content.
3. The owner selected **deterministic preparation; require selection before
   inference**. Do not introduce a neutral inference profile. Input preparation
   may proceed, but absent scope, procedural-only scope or a selected module
   without a usable profile must not silently use another legal persona or
   retrieve unscoped legal data. Keep successful SSE envelope shapes; explain
   the selection requirement through deterministic output.
4. Require explicit template IDs and parameter domains internally. Resolve
   document template eligibility from recorded case scope. A missing/ambiguous
   eligible module produces a documented client error, with eligible choices;
   an explicit choice must belong to that case's scope.
5. No-match presets return no preset. All equally best keyword candidates are
   suggested together, per the owner's further explicit direction; no scalar
   winner is chosen for a tie. Add `suggestions` alternatives while retaining
   scalar fields for a unique winner. Report the union of candidate modules;
   suggesting does not load them. Unconfigured corpus sources are empty;
   persisted empty selections remain empty. Preserve explicit source selection,
   existing storage and one-shot job overrides. Do not add session storage.
6. Preserve `/goldset` as the documented Sozialrecht compatibility alias;
   its dataset-path configuration does not become a general module selector.

## Alternatives and consequences

The owner rejected adding a core-owned neutral inference profile for unscoped
processing. It would retain inference without a legal module but introduce a
new prompt persona and quality-evaluation obligation. Deterministic preparation
avoids borrowing any module's legal prompts or data and postpones inference
until a usable selection exists. Returning an apparently empty provenance list
while retaining legal prompts or global retrieval was rejected as misleading.

Returning only one tied preset would impose a choice the owner did not request.
The owner explicitly required suggesting all tied modules. Preserving the old
priority through new module data and choosing a winner by catalog order were
therefore both rejected. Catalog order may order alternatives, never suppress
an equally best alternative. Module data/versions remain unchanged.

Keeping missing-ID/template/domain and no-match/corpus fallbacks would preserve
legacy convenience but retain implicit module preference. The owner approved
explicit-selection policies instead. Actual matched presets and explicitly
scoped engines retain their behavior. Clients must handle selection-required
results and document-module errors, and stop reading the removed catalog keys.

## GUI contract and remaining acceptance

The GUI owner must present the catalog with no preselection, persist session
context locally, offer restore explicitly, revalidate every saved area against
the catalog's `area_keys` and `enabled` fields, and surface every missing or
disabled selection without substitution. Send the complete chosen/restored
`legal_areas` on each analysis/conversation request. Case operations use recorded
case scope; corpus setup uses explicit source keys through existing endpoints.
No restore endpoint or GUI/local-session storage is introduced here.

GUI-dependent TODO checks remain incomplete and assigned to the owner. Backend
completion does not establish first-launch, relaunch, restore or cross-repository
acceptance. Further legal-area implementation remains blocked by D-069.

## Unreleased change record and verification

This record carries the unreleased backend change notes because the owner
deliberately removed the historical root `DECISIONS.md` and `CHANGELOG.md` in
`dead422`. Those deleted documents are not recreated. The owner authorized branch/PR
publication on 2026-11-26; no release is authorized. Verification results are
recorded in the linked plan.

### Supporting corrections found in contract review

- Skip corpus preflight for preparation-only requests; retain unknown/disabled
  scope validation first. Empty-source stubs otherwise could never reach the
  agreed deterministic preparation path.
- Reuse the existing generation snapshot to persist deterministic preparation
  and the existing PII reinsertion path before delivering/saving that output.
  No storage schema is added.
- Forward conversation area keys to the existing per-area retrieval engine.
  Its keyword branch previously escaped the vector branch's source filter;
  carry the same explicit source types into keyword retrieval as well.
- Re-evaluation reconstruction previously dropped area keys. Read recorded case
  scope, primary first with a deterministic secondary-key order, and refuse
  unusable/unavailable scope rather than recovering an implicit module.
- Prompt set becomes `3.1.0` because the preset output example no longer names
  a preferred module/preset. Explicit legal profile text remains unchanged;
  no neutral inference profile is introduced. No live quality evaluation ran.

- Verification follow-up: installed only the project's declared, locked
  prerequisites locally; corrected the stale test fixtures uncovered by the
  actual application/database run. The purpose guard now watches current
  decision records instead of the deliberately removed architecture document;
  a regression proves those records are checked rather than suppressing warnings.
