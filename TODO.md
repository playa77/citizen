# Implementation order

## 1. Blocking TODO: module selection and session restore

**Do this before any other implementation work, including further legal-area
modules.** Status: not implemented. Decision:
[D-069](docs/decisions/D-069-module-selection-and-session-restore.md).

All modules are peers. `sozialrecht` has no default or automatically loaded
role. On first GUI/desktop launch, present all modules for the user to choose
which to load. On later launches, also offer **Restore last session** as an
explicit choice. Restoring a previous choice does not make those modules
defaults for new sessions.

- [ ] Remove the backend's dependency on a single `DEFAULT_MODULE`, including
  registry/startup validation, request resolution, corpus-source fallback,
  provenance and configuration examples. An omitted or empty selection must
  never silently select `sozialrecht` or another module.
- [ ] Address the legacy REST/MCP `default_module` and `is_default` fields
  without treating them as user choices. Define the API transition in line
  with the existing additive `/api/v1` compatibility rule (D-039).
- [ ] Implement the GUI/desktop startup module chooser. Present all modules
  without preselection or a preferred module; show availability and maturity
  separately. Installation/deployment enablement is not session selection.
- [ ] Persist the last session's module selection and session context, and
  offer **Restore last session** only when a saved session exists. A returning
  user can instead start a new session and choose modules again. Do not
  automatically restore or replace a missing/unavailable saved module.
- [ ] Pass the chosen/restored module scope explicitly through analysis,
  conversations, corpus setup and provenance. Never infer it from a global
  default or a module's position in the catalog.
- [ ] Verify first launch, new session, explicit multi-module selection,
  relaunch and restore, unavailable saved modules, and empty selection across
  backend and GUI. Verify that Sozialrecht receives the same loading
  treatment as every other module and that existing privacy/tier gates hold.

The current backend still implements the legacy default and exposes its
metadata. The current GUI is in `playa77/citizen-gui`. This checklist requires
changes in both repositories; this documentation update does not complete it.
Complete and verify every item above before proceeding to step 2.

## 2. Implement the remaining legal-area modules

- [ ] After step 1 is complete, implement the remaining modules in the
  [module catalog](docs/module-catalog.md). Its queue describes implementation
  sequencing, not startup defaults or preselection. Keep the existing
  authoring, legal-source review, goldset and promotion gates.
