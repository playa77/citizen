# WP-97 — P9 exit gate: run report

**Date:** 2026-11-16
**Branch:** `p9/wp97-exit-gate` (4 commits on top of `origin/main` `a483be0`)
**Scope:** roadmap v3.0.0 WP-97 — goldset zero regression, full suite + ruff +
mypy strict + purpose-drift lint green, byte-identical `/analyze` behaviour for
requests without `legal_areas`, cut core 3.0.0 and `sozialrecht` 1.0.0,
CHANGELOG + D-entry.
**Verdict:** gate **PASSED** (zero deterministic regressions against B0′),
core **3.0.0** and module **1.1.0** cut, records written (D-062). One prompt
defect was found and fixed on the way (3.0.0 → 3.0.1); two pre-existing test
failures remain and are documented below.

---

## 1. Commits

| commit | content |
|---|---|
| `12ded4b` | golden SSE transcript gate for requests without `legal_areas`; fix of a test that read the developer `.env` |
| `0f3ae05` | version cut: core 3.0.0, `sozialrecht` 1.1.0, docs that name the version |
| `60c4afd` | prompt set 3.0.1 — P-04 claim-rule fix + 13 `prompts:*` golden digests re-baselined |
| `49eac73` | gate evidence (3 eval reports), D-062, CHANGELOG, ARCHITECTURE § 8, AGENTS.md, prompt inventory 2.0.1, module CHANGELOG, manifest `gate.baseline_report` |

Working tree clean, nothing pushed.

---

## 2. Environment bring-up

All steps verified before the next began; no step was assumed.

| step | command | result |
|---|---|---|
| repo state | `git fetch origin --prune; git status` | `main` == `origin/main` `a483be0`, clean; one stale remote branch pruned (`origin/docs/prompt-inventory`) |
| venv | `uv venv --python 3.12 .venv` | CPython 3.12.15 (CI matrix is 3.11 + 3.12) |
| install | `uv pip install -e ".[dev]"` | OK |
| database | `docker ps` | existing `p9-baseline-pg` (pgvector/pg16) on `:5432` |
| migration | `python -m alembic upgrade head` | `012_pg_collapse_sqlite_branch → 013_legal_module`; `alembic current` = `013_legal_module (head)` |
| parameters | `python -m scripts.seed_module_parameters` | `0 created, 0 updated, 27 unchanged (27 rows)`; modules ohne Parameter: 0 rows each |
| corpus | `select count(*) from legal_chunk` | 940 chunks (sgb2 + sgbx) |
| NER model | `python -m spacy download de_core_news_lg` | `de-core-news-lg 3.8.0`, loads with full pipeline |
| API key | `GET https://openrouter.ai/api/v1/key` | auth OK, non-free tier, limit $10 |

`.env` corrections (backup: `~/.hermes/cache/scratch/env-backup-<timestamp>`):

| key | old | action | why |
|---|---|---|---|
| `GOLDSET_PATH` | `eval/goldsets/goldset-v0.1.0.yaml` | commented out | path no longer exists (WP-93 moved goldsets into the module); the stale pin overrode the config default and breaks `GET /api/v1/goldset` |
| `DISCLAIMER_VERSION` | `v0.1.0` | commented out | WP-96 shipped `v3.0.0`; a pinned old value makes every acknowledged request answer 403 (`DEPLOYMENT.md` upgrade step 5) |
| `EMBEDDING_API_KEY` | `EMBEDDING_API_KEY=# Optional — falls back…` | **left as is** | checked `python-dotenv`: an inline `#` right after `=` parses as an empty value, so the documented fallback to `OPENROUTER_API_KEY` applies. Fragile-looking but correct |

Token cost of the whole session: account usage went **$2.5007 → $3.2986**
(≈ **$0.80** for one smoke case + 36 full pipeline runs).

---

## 3. Gate reference: why B0′ and not the WP-90 report

The manifest declared `gate.baseline_report: eval/results/20261116T094340Z-e9fb87a.json`
(D-050, WP-90). D-061 already recorded that this report **is not comparable**:
the eval extractors/metrics changed to 1.1.0/1.2.0 afterwards, and the report
stores metrics only, so it cannot be re-scored. D-061 named the replacement
reference **B0′ = commit `55ec1f2`** (prompt set 2.0.0 texts + the new eval
code) and noted it had **never been run**.

B0′ was therefore produced for this gate in a detached worktree
(`55ec1f2`), with the repo's `.env` copied in and the module code loaded from
the worktree via `PYTHONPATH`:

```bash
git worktree add /tmp/citizen-b0p 55ec1f2
cp .env /tmp/citizen-b0p/.env
cd /tmp/citizen-b0p && PYTHONPATH=$PWD /home/devops/src/citizen/.venv/bin/python \
  -m eval.runner --module sozialrecht --save
```

Result: `eval/results/20261116T170321Z-55ec1f2.json`, prompt set **2.0.0**,
12/12 cases, no errors.

The same worktree technique produced the **pre-P9 transcript** used in § 7.

---

## 4. Eval runs

Three full runs (12 cases each, live DB + live LLM API) plus one smoke case.

| # | state | prompt set | commit | report | wall time |
|---|---|---|---|---|---|
| smoke | release candidate | 3.0.0 | `12ded4b` | not saved | 3 min |
| B0′ | reference | 2.0.0 | `55ec1f2` | `20261116T170321Z-55ec1f2.json` | 33 min |
| R1 | candidate (red) | 3.0.0 | `0f3ae05` | `20261116T170935Z-0f3ae05.json` | 31 min |
| R2 | release (green) | 3.0.1 | `60c4afd` | `20261116T175355Z-60c4afd.json` | 34 min |

Command used for every run (the `eval/goldsets/…` path still quoted in older
docs does not exist any more):

```bash
python -m eval.runner --module sozialrecht --save
```

### 4.1 Aggregate

| metric | B0′ (2.0.0) | R1 (3.0.0) | R2 (3.0.1) |
|---|---|---|---|
| issue recall | 29.0 % | 44.3 % | 41.5 % |
| citation precision | 27.1 % | 27.6 % | 30.3 % |
| calculation exact | 100 % | 100 % | 100 % |
| Frist exact | 100 % | 100 % | 100 % |
| assessment match | 0.0 % | 33.3 % | 16.7 % |
| quote verification | 43.9 % | **33.2 %** | **70.5 %** |
| quote verification (sourced) | 94.4 % | 96.9 % | 95.1 % |
| mean latency | 165 s | 147 s | 173 s |

### 4.2 Per-case quote verification (the gate's strict metric)

| case | B0′ | R1 (3.0.0) | R2 (3.0.1) | R2 recall | R2 precision | R2 assessment |
|---|---|---|---|---|---|---|
| GS-001 | 15.4 | 40.0 | 60.0 | 0.0 | 40.0 | 0.0 |
| GS-002 | 33.3 | 40.0 | 80.0 | 66.7 | 33.3 | 0.0 |
| GS-003 | 54.5 | **0.0** | 80.0 | 50.0 | 75.0 | 0.0 |
| GS-004 | 41.7 | 50.0 | 66.7 | 40.0 | 50.0 | 0.0 |
| GS-005 | 63.6 | 75.0 | 87.5 | 50.0 | 30.0 | 100.0 |
| GS-006 | 25.0 | 33.3 | 50.0 | 25.0 | 30.8 | 0.0 |
| GS-007 | 66.7 | **60.0** | 66.7 | 0.0 | 33.3 | 0.0 |
| GS-008 | 44.4 | 50.0 | 80.0 | 66.7 | 20.0 | 0.0 |
| GS-009 | 40.0 | **0.0** | 66.7 | 50.0 | 11.1 | 0.0 |
| GS-010 | 36.4 | 50.0 | 75.0 | 50.0 | 40.0 | 100.0 |
| GS-011 | 62.5 | **0.0** | 66.7 | 0.0 | 0.0 | 0.0 |
| GS-012 | 42.9 | **0.0** | 66.7 | 100.0 | 0.0 | 0.0 |

Calculation exact match is 100 % in every case and every run; Frist exact match
100 % wherever the goldset defines one (GS-007/011/012: `n/a`).

---

## 5. Gate runs

### 5.1 R1 against B0′ — **FAILED**

```
❌ Deterministic failures (5):
   • Case GS-003 — quote_verification_rate: baseline=0.5455, current=0.0000 (Δ=-0.5455)
   • Case GS-007 — quote_verification_rate: baseline=0.6667, current=0.6000 (Δ=-0.0667)
   • Case GS-009 — quote_verification_rate: baseline=0.4000, current=0.0000 (Δ=-0.4000)
   • Case GS-011 — quote_verification_rate: baseline=0.6250, current=0.0000 (Δ=-0.6250)
   • Case GS-012 — quote_verification_rate: baseline=0.4286, current=0.0000 (Δ=-0.4286)

⚠ LLM regressions (warn-only, 9):
   • prompt set differs: baseline=2.0.0, current=3.0.0
   • citation precision: GS-002 -0.036, GS-004 -0.089, GS-010 -0.197
   • quote verification (sourced): GS-003/009/011/012 current=None, GS-007 1.000→0.750
```

Gate exit code 1. No version was cut at this point.

### 5.2 R2 against B0′ — **PASSED**

```
⚠ LLM regressions (warn-only, 6):
   • prompt set differs: baseline=2.0.0, current=3.0.1
   • GS-001 citation_precision 0.4167 → 0.4000
   • GS-005 citation_precision 0.3333 → 0.3000
   • GS-006 issue_recall 0.5000 → 0.2500
   • GS-006 citation_precision 0.4000 → 0.3077
   • GS-008 citation_precision 0.2857 → 0.2000

✓ Gate PASSED — no deterministic regressions.
```

Gate exit code 0. The prompt-set difference is reported as a warning by design
(`eval/regression_gate.py` 1.1.0, CR-09).

Gate runs are cheap and repeatable without LLM calls:

```bash
python -m eval.runner --module sozialrecht \
  --rescore eval/results/<run>.outputs.json \
  --baseline eval/results/20261116T170321Z-55ec1f2.json
```

---

## 6. Root cause of the red gate — a prompt defect, not the refactor

Measured from the saved raw outputs (`*.outputs.json`):

| case | B0′ claims / sourced | R1 claims / sourced | R1 "nicht belegbar" claims |
|---|---|---|---|
| GS-003 | 11 / 6 | 3 / **0** | 3 / 3 |
| GS-009 | 10 / 4 | 3 / **0** | 3 / 3 |
| GS-011 | 8 / 5 | 5 / **0** | 5 / 5 |
| GS-012 | 7 / 3 | 5 / **0** | 5 / 5 |
| GS-001 | 13 / 3 | 5 / 2 | 3 / 5 |

Prompt set 3.0.0 rewrote P-04 (`grounded_answer`) with two rules that
interact badly:

1. *"Beantworte jede Rechtsfrage mit 1 oder 2 Claims, insgesamt höchstens 10."*
2. *"Trägt keine Quelle eine Antwort auf eine Frage: genau ein Claim mit
   claim_text „Mit den bereitgestellten Quellen nicht belegbar: …“"* — i.e.
   **one such claim per unanswered question**.

Goldset questions are partly *document-factual* ("Enthält der Bescheid eine
Rechtsbehelfsbelehrung nach § 36 SGB X?", "Für welchen Zeitraum ist der
Regelbedarf bewilligt?"). No corpus chunk can answer those, so each one
consumed a claim slot and produced an empty-evidence claim. Cases whose
questions were mostly of that kind ended with **zero sourced claims**, hence
0 % quote verification. Claim count per case halved (8–13 → 3–6).

Note the second metric: `quote_verification_rate_sourced` (the one D-061 added
precisely for this effect) was **96.9 %** — the remaining sourced claims were
almost all verified. The proposal's A3 acceptance rule (sourced rate,
assessment match, citation precision) passes; the raw rate, which the gate
treats as deterministic-strict, does not. Both readings were reported to the
owner before acting; the instruction was to fix the prompt rather than the
gate.

**Fix — prompt set 3.0.1** (`app/services/prompts.py`, text only):

* one "nicht belegbar" claim per **response** instead of one per question;
* document-factual questions (Angaben, Daten, Fristen, Beträge) are exempt —
  they belong in `sachverhalt`/`handlungsempfehlung`;
* claim density back to **1–3 per legal question**, cap 12.

`PROMPT_SET_VERSION` 3.0.0 → 3.0.1; the module docstring records the change.
The 13 `prompts:*` digests in `tests/unit/golden/wp93_v2_baseline.json` were
re-baselined (`_meta.rebaselined`), no other key changed, and the prompt stays
inside the 6,000-character budget (5,940).

---

## 7. Transport contract for requests without `legal_areas`

New: `tests/integration/test_analyze_transcript.py` +
`tests/integration/golden/analyze_transcript_no_areas.txt`.

`run_pipeline` is stubbed with a fixed event sequence; the raw SSE bytes are
compared against the golden file, so event order, JSON key order, SSE framing
and every deterministic value are pinned. Deliberately volatile values are
normalised and asserted separately: uuids, `provenance.timestamp_utc`,
`provenance.app_version`, module `version`/`parameter_set`.

**Pre-P9 comparison (one-off, recorded as evidence).** The same stub was run
against a detached worktree of `aae2888` (last commit before WP-93) and
against the release tree. The normalised transcripts differ in **exactly one
line** — the terminal event's `provenance`:

```diff
- "spec_version": "citizen-provenance-v1.0", … "deployment_mode": "dev"}
+ "spec_version": "citizen-provenance-v1.1", … "deployment_mode": "dev",
+  "modules": [{"id": "sozialrecht", "version": "1.1.0", "parameter_set": "1.1.0+…"}]}
```

That is the documented WP-96 delta (D-059). Every stage event and every other
terminal field — `sections`, `final_output`, `case_run_id`, `disclosure` — is
byte-identical.

---

## 8. Test and gate matrix

| check | command | result |
|---|---|---|
| unit tests | `pytest tests/unit/ -q` | **1156 passed, 2 failed, 2 skipped** (66 s) — failures are the pre-existing pseudonymization negative controls, see I-07 |
| integration tests | `pytest tests/integration/ -q` | **42 passed** (8 s) |
| combined run | `pytest tests/unit/ tests/integration/ -q` | 1196 passed, **4 failed** — test-harness artefact, see I-08; CI runs the suites separately and so did every accepted run in this report |
| lint | `ruff check app/` | All checks passed |
| format | `ruff format --check app/` | 74 files already formatted |
| types | `mypy app/ --python-version 3.12` | Success, 74 source files (CI's 3.12 invocation) |
| compliance lint | `python scripts/check_purpose_drift.py` | OK — 12 files, 76 deny phrases |
| prompt/golden | `pytest tests/unit/test_wp93_golden.py tests/unit/test_prompt_set_v3.py tests/unit/test_prompts.py tests/unit/test_endpoint_prompts_v3.py` | 92 passed |
| module surface | `pytest tests/unit/test_modules_{api,sync,content}.py tests/unit/test_disclaimer_addenda.py` | 100 passed |

`mypy` without `--python-version` fails on numpy's PEP-695 stubs (`Type
statement is only supported in Python 3.12 and greater`) — a known environment
trap; CI passes the flag on the 3.12 job (`ci.yml:58-64`).

---

## 9. Issues found / surfaced

Severity: **S1** blocks the release, **S2** wrong behaviour or unusable
artefact, **S3** documentation/process defect, **S4** observation.

| ID | sev | area | symptom | root cause | status |
|---|---|---|---|---|---|
| I-01 | S1 | prompt set 3.0.0 | 5 deterministic quote-verification regressions, 4/12 cases with zero citations | P-04 asked for a claim per question plus one "nicht belegbar" claim per unanswerable question; document-factual questions consumed every slot | **fixed** in 3.0.1; gate green (`60c4afd`) |
| I-02 | S2 | eval gate | the declared gate baseline (`e9fb87a`, D-050) cannot be used | metric definitions changed after it was produced (D-061); B0′ had never been run | **resolved**: B0′ produced (`55ec1f2`) and committed; manifest now points at the release run |
| I-03 | S2 | config | `GET /api/v1/goldset` would fail | `.env` pinned `GOLDSET_PATH=eval/goldsets/…`, a path WP-93 deleted | **fixed** (`.env`, local only — not in the repo) |
| I-04 | S2 | config | every acknowledged request would answer 403 after the WP-96 upgrade | `.env` pinned `DISCLAIMER_VERSION=v0.1.0` while the code ships `v3.0.0`; documented upgrade step was missed | **fixed** (`.env`, local only) |
| I-05 | S2 | test | `test_default_deployment_mode_is_dev` red on a provisioned dev box, green in CI | the test built `Settings()` which reads the repo `.env` (`CITIZEN_SYNTHETIC_DATA_ONLY=true`) instead of asserting class defaults | **fixed**: `Settings(_env_file=None)` (+ removed a dead import) |
| I-06 | S3 | eval docs/tooling | first smoke run died with `FileNotFoundError: eval/goldsets/goldset-v0.2.0.yaml` | goldsets moved into `modules/sozialrecht/goldset/` at WP-93; skill + some docs still named the old path | **fixed** in the `citizen-eval-runs` skill; `--module sozialrecht` is the durable form |
| I-07 | S2 | pseudonymization | `Jobcenter Köln` / `Agentur für Arbeit` redacted as `[[FIRMA_1]]`; 2 tests red with spaCy installed | spaCy NER tags authority names as ORG and the mapper redacts ORG as company; the negative controls assume regex-only detection | **open, pre-existing** — fails identically at `aae2888` (D-051); CI green because it does not install the model. Changing it changes eval inputs, so it was not touched at the exit gate |
| I-08 | S3 | test harness | combined `pytest tests/unit tests/integration` → 4 failures (`cannot perform operation: another operation is in progress`) | one async engine/connection pool reused across event loops; the route's audit write fails, `case_run_id` drops off the terminal event | **documented** in the transcript test docstring; CI and all accepted runs use separate invocations. Not fixed (pre-existing engine lifecycle) |
| I-09 | S3 | deployment doc | `DEPLOYMENT.md` listed the migration chain as `… → 012` | migration `013_legal_module` (WP-94) was never added | **fixed** |
| I-10 | S3 | module docs | module CHANGELOG said 1.0.0 unreleased and had no entry for the D-060 bump to 1.1.0 | version bumped without the changelog | **fixed**: rewritten, 1.1.0 released, 1.0.0 retired unpublished |
| I-11 | S3 | README/catalogue | "Stand des Codes: v2.0.0 … Umbau zu Modulen ist Phase P9" | stale after P9 landed | **fixed** (README status row, module catalogue M0 row) |
| I-12 | S4 | prompt budget | after the first P-04 fix the prompt was 6,199 chars and failed the 6,000-char budget test | duplicated exemption wording | **fixed**: trimmed to 5,940 |
| I-13 | S4 | test | `test_prompt_set_v3` pinned the literal `"3.0.0"` | version bump | **fixed**: compares against `PROMPT_SET_VERSION` |
| I-14 | S4 | golden tooling | first re-baseline produced a 768-line diff | re-serialised with `indent=2` + `ensure_ascii=False` instead of the file's `indent=1` convention | **fixed**: 50-line diff, content identical |
| I-15 | S4 | metrics | assessment match 33.3 % (WP-90 report) vs 0.0 % (B0′) for the same system family | metric definitions changed in D-061; the WP-90 number is not comparable | **observation** — recorded, no action |
| I-16 | S4 | config | `EMBEDDING_API_KEY=# Optional — falls back…` looks like a live key | `python-dotenv` treats the inline `#` as a comment → empty value → documented fallback applies | **verified correct**, left untouched |
| I-17 | S4 | environment | repo `.env` is read by any `Settings()` in tests and tools | pydantic-settings loads `.env` from the process CWD | **observation** — run suites from the repo root as CI does; do not point tests at the corpus DB (`DATABASE_URL` unset lets testcontainers provision their own) |

---

## 10. Artefacts

**Committed**

```
eval/results/20261116T170321Z-55ec1f2.json   B0′ reference (prompt 2.0.0)
eval/results/20261116T170935Z-0f3ae05.json   red gate run  (prompt 3.0.0)
eval/results/20261116T175355Z-60c4afd.json   release run   (prompt 3.0.1)
tests/integration/test_analyze_transcript.py
tests/integration/golden/analyze_transcript_no_areas.txt
tests/unit/golden/wp93_v2_baseline.json      (13 prompts:* keys re-baselined)
```

**Local only (scratch)** — logs, worktrees, the pre-P9 transcript pair, the
env backup, the golden re-baseline script:
`~/.hermes/cache/scratch/{b0p-run,head-run,head2-run,gate-head2,smoke-gs001,pytest-*}.log`,
`citizen-b0p/` and `citizen-aae2888/` worktrees, `transcript-{aae2888,head}.txt`,
`rebaseline_golden.py`, `env-backup-*`.

---

## 11. Open items (not part of WP-97)

1. **I-07 over-redaction of authority names** — needs a decision: exempt a
   known authority list from ORG redaction (changes what the model sees, so it
   needs a fresh B0′-style reference), or make the two negative controls
   model-aware.
2. **Measurement plan arms A1–A5** (`docs/prompt-upgrade-proposal.md` § 4) are
   still unrun; B0′ was produced once, without the 3-repetition spread that
   would make the warn-only metric moves evidence.
3. **`quote_verification_rate_sourced` semantics** — for four cases R1 had no
   sourced claims at all, which the gate compares as `1.0 → None` (an
   undefined value, not a measured zero). A future gate revision may want to
   distinguish "no denominator" from "0 %".
4. Residual couplings recorded in ARCHITECTURE.md § 8: `CORPUS_SOURCES`
   default and the global `ENABLE_CALCULATION_CHECK` toggle.

---

## 12. Reproduction

```bash
# environment
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
export DATABASE_URL="$(python -c "from dotenv import dotenv_values;print(dotenv_values('.env')['DATABASE_URL'])")"
python -m alembic upgrade head
python -m scripts.seed_module_parameters
python -m spacy download de_core_news_lg          # ~610 MB, one-off

# tests (separate invocations, as CI does)
unset DATABASE_URL
pytest tests/unit/ -q
pytest tests/integration/ -q
ruff check app/ && ruff format --check app/
mypy app/ --python-version 3.12
python scripts/check_purpose_drift.py

# eval + gate
python -m eval.runner --module sozialrecht --save
python -m eval.runner --module sozialrecht \
  --rescore eval/results/<run>.outputs.json \
  --baseline eval/results/20261116T170321Z-55ec1f2.json

# golden re-baseline (deliberate contract change only)
UPDATE_GOLDEN=1 pytest tests/integration/test_analyze_transcript.py
```
