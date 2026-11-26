# WP-130 implementation completion plan

**Spec:** roadmap WP-130, M1 catalog, D-071 (specific shared extensions approved;
human approvals deferred until all modules implemented). GUI excluded.

**Architecture:** Extend the existing Fristen input/evaluator, dossier facts,
corpus catalog and single PostgreSQL migration chain. All debt-specific rules,
values, prompts and templates remain in the module. No new services/dependencies.

## Work and acceptance

1. Service deadline contracts: explicit actual service, document type and mode;
   no letter-date substitution, VA assumption or borrowed RBB extension. Domestic
   two-week rules, correct leap/weekend/holiday handling; unsupported modes ask
   for confirmation/review. Preserve all Sozialrecht golden behavior.
2. Corpus support: ZPO/InsO/RDG/RVG source catalog/adapters and additive CHECK
   migration; source fixtures test parsing/storage. Keep ingestion/embeddings
   separate from fixture-based tests; do not imply a populated deployment.
3. Module calculators: parameter-backed, cent-exact, period-aware attachment,
   P-account, qualified limitation and conservative collection-cost checks.
   Missing qualification/parameters produce an explicit refusal, never defaults.
4. Module drafts/profile/copy/intake: existing SDK/renderer only, unresolved
   assertions retain review placeholders, DE/EN/de-LS copy stays draft.
5. At least 15 synthetic cases plus deterministic dossier/plain goldsets and
   saved reports; no live-inference quality claim without measured outputs.
6. Version and notice alignment, module changelog, ADR/API documentation and
   source records. No human-name gate. Remain experimental until actual quality
   evidence supports promotion; deferred human reviews do not block coding.
7. Focused RED→GREEN contracts, then full unit/integration suites, lint/typing,
   offline module/dossier/plain gates, code review and final Git inspection.

## Work ownership and progress

- Parent: shared Fristen/dossier/corpus/schema integration, manifest/versioning,
  migration, documentation, quality runs and final integration.
- Calculator agent: module calculators, parameters, focused tests only.
- Copy agent: templates/profile/copy/deny phrases, then synthetic goldsets and
  intake schema, focused tests only.
- Bounded source-snapshot collector: 30 requests total, one in flight, at least two
  seconds between starts, 15-second timeout, no retries; all returned successfully.
  No inference or embeddings. EU GDPR page was access-challenged; do not retry
  or claim a full fetch from that source.
- Service contracts: RED demonstrated unsupported service spec (10 errors) and
  GREEN 13/13, pure tests with `--noconftest` (no database contract exercised).

## Delivered implementation and final evidence — 2026-11-26

All implementation tasks above are complete. Operational corpus/inference
acceptance and human review are separate statuses, described below.

- Core **3.5.0**, module API **3.3**, module **0.2.0**, prompt set **3.3.0**,
  disclaimer **v3.2.0**. No dependencies added. The existing editable project
  installation and stale generated egg-info were refreshed so report/runtime
  version matches pyproject.toml; agent configuration was not changed.
- Source catalog, citation mapping and migration 016 support the four missing
  statutes; actual PG16 constraint inserts passed. Module declaration requires
  all five statute types and does not preselect any source/module.
- Additive public intake schema is validated and exposed on REST/MCP detail.
  Its form schema supplements, rather than replaces, existing request/privacy
  validation. Dev synthetic-only restrictions remain in the ingestion path.
- Service deadline branch has 14 pure regressions, including a final RED→GREEN
  missing-region check. No explicit region means no exact holiday rollover.
  Legacy Bekanntgabe semantics and historical legal text digests remain pinned.
- Calculator tests cover period selection, missing qualifications, legal
  boundaries, cents, dependent amounts, refusal and audit snapshots. Real
  module parameter loading catches YAML date types. A review found reversed
  P-account discrepancy labels; two failing tests reproduced it, then passed
  after the kind-specific sign correction. No findings remain deferred.
- Actual source-table comparison: **3,906 official monthly cells**, **7,812**
  lower/upper interval-boundary assertions, **zero mismatches**, across 2025
  and 2026. The earlier 3,894 count excluded the two zero-income rows. Report:
  `modules/schuldnerrecht/goldset/reports/attachment-table-check.json`.
- Dossier goldset: **20/20**, schema/deadline/checklist/chronology metrics all
  **1.000**. Saved module report includes the guarded draft annex, using an
  explicit allowlist of dummy offline settings; no inference/DB request was
  made by that evaluator. Plain-language gate: **28/28**, all three languages.
  Both reports identify core 3.5.0/module 0.2.0. Existing Sozialrecht dossier
  and plain gates also passed.
- Full delivered-state test command:
  `.venv/bin/python -m pytest tests/unit/ tests/integration/ -q -rs`:
  **1,615 passed, 4 skipped, 21 warnings**, **78.08 seconds**, disposable
  PostgreSQL 16/pgvector, with migration 016 applied by the test fixture.
  The four skips are existing removed-CORS coverage, an existing intake GET
  error-handling gap, and two unavailable spaCy-model tests. Warnings include
  testcontainers/BeautifulSoup deprecations and async cancellation warnings;
  pytest-asyncio separately warns about its unset fixture-loop scope.
- Ruff lint/format, strict mypy (`--python-version 3.12`), all-module validation,
  purpose-drift and diff checks passed. No separate Python 3.11 interpreter
  run was performed. Parameter-seed dry-run accepted four rows.
- Independent read-only final review found the P-account direction issue
  above; it was fixed and verified by the full suite. No repeated reviewer
  dispatch or unbounded fix loop was used.

## Honest operational and review boundaries

Source downloads/hashes, parser/storage tests and deterministic goldsets do
not establish a populated user deployment corpus, embedding quality or live
pipeline performance. No separate operator test key or live-evaluation outputs
were supplied, so no live inference, embeddings or full pipeline quality score
is claimed. Preserve the corpus-readiness guard. Installation commands are in
the module README. These are execution prerequisites, not human approval gates.
Human reviews and promotion remain deferred under D-071, without requiring
names to continue implementation. The module therefore stays experimental;
parameter/copy statuses remain proposed/draft. No GUI work, commit, push,
publication or release was performed. The user's pre-existing AGENTS.md edit
remains preserved on `codex/remove-module-default-metadata`.
