# Explicit backend module scope implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, with
> test-driven-development and verification-before-completion. The owner
> authorized committing and publishing this backend work as a PR on 2026-11-26.

**Goal:** Remove catalog default metadata and all implicit backend module selection.

**Architecture:** Implement the owner's choices in
[D-070](../../decisions/D-070-explicit-backend-module-scope.md), extending D-069.
Empty/unusable inference scope permits deterministic preparation only. Explicit
scope drives engines, templates and provenance; no new neutral profile or storage.

**Tech stack:** Existing locked Python/FastAPI development dependencies and
PostgreSQL 16/pgvector. Local setup adds no dependency declarations.

**Spec:** D-070 contains the grounded impact assessment, alternatives and owner
approvals from this chat. This plan implements only those approvals.

## Constraints and review focus

- Work only inside this backend checkout; preserve the pre-existing AGENTS edit.
- No GUI access, local session implementation, new dependencies, live inference,
  database substitute or release. Branch push and PR publication are authorized
  by the owner's 2026-11-26 instruction to open a PR.
- Watch omitted/empty scopes, unavailable restored modules, mixed scopes with a
  profile-less module, empty saved corpus sources and ambiguous case templates.
- Preserve explicit profile text, module rules, privacy/tier gates and SSE shapes.

## Tasks

- [x] Add contract regressions: absent catalog keys; no-module runtime
  resolution; explicit alias/multi-area preservation; no prompt fallback;
  no-module preparation without inference/retrieval; corpus empty/override
  handling; template/domain errors and case-scoped selection.
- [x] Remove metadata and default setting/registry/table/validator dependencies.
  Update API and decision references in the same work package.
- [x] Guard pipeline/chat/reasoning before legal inference, preserving
  deterministic preparation and explicit module behavior. Remove empty-scope
  retrieval and default-derived prompt constants; keep explicit profile content.
- [x] Implement approved preset, template, parameter, corpus and goldset policies.
  Update existing tests so previously implicit legal fixtures select their module.
- [x] Document backend client contracts; leave GUI acceptance incomplete.
- [x] Run offline regressions and available CI gates, review the whole diff,
  inspect Git state and report verified results and environmental limitations.
- [x] Run the full application suites, API-documentation parity guard, PostgreSQL
  integration/SSE checks, module validator, Ruff lint/format and mypy with the
  pinned development dependencies in `.venv` (Python 3.12.15).
- [ ] GUI/session and combined acceptance: assigned to the GUI owner, outside
  this session. Further module implementation remains blocked by TODO step 1.

## Execution record

- Initial state: main at 30f9642; only AGENTS.md modified by prior work.
- Branch: codex/remove-module-default-metadata; owner AGENTS edit preserved.
- Initial environment lacked the project venv and development dependencies.
  The initial handoff incorrectly treated installing declared prerequisites as
  adding new project dependencies. That incomplete verification is superseded
  by the 2026-11-26 results below.
- Installed the existing lockfile with `uv sync --locked --extra dev --python
  3.12`: Python 3.12.15, Ruff 0.6.9, mypy 1.11.2 and 97 packages in `.venv`.
  Python/download caches stay in ignored `tmp/verification-setup/`. Neither
  `pyproject.toml` nor `uv.lock` changed. Scoped network and Docker permission
  requests succeeded; no system Python or developer-agent configuration changed.
- Ruling: work in the named checkout on a local branch, respecting the owner's
  exact-path constraint; no additional worktree or commit approval ritual.
- Broader architecture explicitly approved via the two questions in this chat.
- Owner further specified that equal-best preset matches suggest every tied
  module. Added `suggestions` alternatives and candidate-union metadata; a tie
  chooses no scalar preset. No new priority data or module changes were needed.

## Verification at handoff — 2026-11-26

- Full `tests/unit/`, `tests/integration/` and `tests/offline/` run:
  **1,532 passed, 4 skipped, 21 warnings**, exit 0, 76.78 seconds. This includes
  the actual HTTP/API-documentation/SSE tests and PostgreSQL 16/pgvector tests;
  no test file or test was deselected. A fresh disposable testcontainer was
  started and migrated by the existing conftest, and stopped afterwards.
- Reproduction entry point is the local, ignored
  `tmp/verification-setup/run_pytest.py`, invoked with the venv interpreter,
  `tests/unit/ tests/integration/ tests/offline/ -q -ra --durations=10`, and an
  explicit `env -i` allowlist: PATH, PYTHONPATH, TMPDIR, local DOCKER_HOST,
  dummy OPENROUTER_API_KEY/EMBEDDING_API_KEY, dev/synthetic-data posture,
  DISCLAIMER_VERSION, INFERENCE_PROFILE and PYTHONHASHSEED=0. The wrapper
  rejects non-loopback socket connections and keeps generated test salt in
  the task's ignored runtime directory. No real inference credentials or live
  inference were used. Logs: `tmp/verification-setup/full-final.log`.
- First real full run found **6 failures, 1,526 passes and 4 skips**. Five
  fixtures still assumed default modules or the old retrieval seam: explicit
  corpus sources, chat prompt selection/scoped retrieval, module-owner ordering,
  and explicit module scope for a plain-language finding corrected them. No
  product fallback was restored. All 111 tests in those affected files passed
  before the complete rerun.
- The sixth failure was already in HEAD: the purpose guard watched deliberately
  removed `ARCHITECTURE.md`, while its repository test forbade warnings. The
  guard now scans current `docs/decisions/*.md` instead. A regression first
  failed because decision-file drift was missed, then all 17 purpose tests
  passed. No warning was suppressed and no deleted document was restored.
- Ruff 0.6.9: `ruff check app/ scripts/check_purpose_drift.py` passed;
  `ruff format --check app/ scripts/check_purpose_drift.py` passed (113 files).
  One formatting issue in `app/services/reasoning.py` was corrected before the
  final complete test run. Mypy 1.11.2 with `app/ --python-version 3.12` passed
  all 112 source files. The Python 3.11 matrix lane was not run locally.
- `python -m scripts.validate_module --all`: 8 modules checked, zero errors.
  Existing warnings remain: experimental-module content/review omissions and
  three proposed Sozialrecht parameters. No module was promoted or changed.
- `python -m eval.dossier_eval --module sozialrecht`: PASS over 12 synthetic
  cases (schema/deadline completeness 1.000, checklist recall 0.979,
  chronology accuracy 0.935).
- `python -m eval.plain_eval --module sozialrecht`: PASS, 13/13 cases,
  de/de-LS/en. Human review remains pending; existing draft status is retained.
- Purpose drift: default scan passed over 15 files without the deleted-document
  warning. Syntax compilation and `git diff --check` passed.
- Skips: existing removed CORS setting test; existing intake GET error-handling
  test; two NER tests because `de_core_news_lg` is not installed. Native OCR,
  that NER model and live model quality were not tested by this work.
- Warnings: testcontainers/HTML-parser deprecations and two un-awaited
  `asyncpg.Connection._cancel` warnings. The same two cancellation warnings at
  the same test sites reproduced using HEAD's unchanged app/tests in an ignored
  source snapshot, alongside the same deprecations (21 warnings). They are not
  claimed fixed. The first baseline snapshot omitted API docs/.gitignore,
  causing five resource-check failures; after completing those resources,
  those five checks passed and the existing purpose-warning test still failed.
  Baseline logs are retained under `tmp/verification-setup/baseline*.log`.
- Independent review of the backend found and prompted corrections for
  preparation preflight, deterministic snapshot persistence, scoped hybrid
  retrieval and recorded case scope. No further concrete defects were reported.
- Docker inspection after the runs found no running pgvector testcontainers.
  `.venv` and the ignored setup/log artifacts are retained for further work.
- PR handoff requested by the owner on 2026-11-26, from
  `codex/remove-module-default-metadata` to `main`, based on `30f9642`.
  The pre-existing owner's `AGENTS.md` edit is preserved locally and excluded
  from this implementation commit. No GUI inspection or acceptance occurred.
  Ignored setup/cache/log artifacts and dependency files are excluded from the PR.
