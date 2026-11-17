# Citizen — Quality Plan: LLM Analysis Gate (Phase P14)

<!-- Version: 0.1.0 (DRAFT, awaiting owner approval) | 2026-11-17 — D-069 (proposed).
     Becomes 1.0.0 when the owner approves D-069. -->
<!-- Roadmap: docs/roadmap-v3.0.0.md § 7a (v3.1.0 draft) · Decision: DECISIONS.md D-069 -->

## 1. Why this plan exists

Citizen's product is the analysis a person reads: which problems their notice
has, which norms apply, and whether the notice is lawful. Deadlines and amounts
come from deterministic engines and are measured at 100 %. The language-model
analysis is not. At prompt set 3.0.1 the goldset reports (D-062,
`eval/results/20261116T175355Z-60c4afd.json`):

| Metric | Value | What a miss means for the person |
|---|---|---|
| Issue recall | 41.5 % | a problem in their notice is never raised — silently |
| Citation precision | 30.3 % | they cannot tell sound citations from wrong ones |
| Assessment match | 16.7 % | the bottom line is wrong in 10 of 12 cases |

A preparation aid that misses most problems and gets the verdict wrong is worse
than no tool: it looks authoritative and can make a person drop a valid
objection. Owner decision (2026-11-17): these three values are the most
important values of the project. Everything else is out of scope until each
exceeds **90 %**.

## 2. Target and gate rule

All three, simultaneously:

| Metric | Gate |
|---|---|
| Issue recall | **> 0.90** |
| Citation precision | **> 0.90** |
| Assessment match | **> 0.90** |

- **Aggregation (owner decision):** mean over the cases of the **held-out set**
  (§ 5), averaged over **3 runs** of the release tree. A run that errors on a
  case scores that case 0.
- **No trade-offs between metrics:** a release that lifts one value by
  lowering another below 0.90 fails.
- **Deterministic metrics stay strict** at their current gate
  (`calculation_exact_match`, `frist_exact_match`, `quote_verification_rate`,
  `leakage_rate`; `eval/regression_gate.py`).
- **Abstaining is a miss:** "Einordnung offen" scores as an assessment
  mismatch. It is an honest answer to the person, but it cannot be used to
  pass the gate.
- The gate applies to `sozialrecht` first. A module is promoted to `verified`
  only when it passes the same gate on its own held-out set (replaces the
  P13 sub-WP .8 "gate thresholds" with these values).

## 3. What the current numbers can and cannot tell us

Measured on the current tree (`eval/extractors.py` 1.1.0, `eval/metrics.py`
1.3.0, goldset v0.2.0) before any change:

1. **Recall cannot exceed 66.4 %.** An expected issue counts as found only if
   a § reference can be extracted from it and the pipeline names the same
   norm. 14 of 42 expected issues contain no extractable norm (e.g. GS-001-I1
   "§ 11b Abs. 3 …" without the statute name; all four GS-007 issues), and
   GS-001-I2 ("Übrige Berechnung … korrekt") is not a problem at all. GS-001
   and GS-007 have a recall ceiling of 0.
2. **Precision cannot exceed 83.3 %.** GS-011 and GS-012 have no expected
   citations; any citation there scores 0. Correct norms the reference list
   happens not to name also count as wrong.
3. **The assessment scorer was defective** (fixed in `eval/extractors.py`
   1.2.0, see § 6 Q1-a): it ignored negation ("nicht rechtswidrig" →
   `rechtswidrig`), let any "rechtswidrig" in the reasoning beat a
   "kein Verwaltungsakt" verdict, mapped "unzulässig" (a remedy term) to
   `rechtswidrig`, and could not read "keinen Verwaltungsakt" or
   "rechtmäßig".
4. **Raw outputs were not kept** (`*.outputs.json` is git-ignored), so the
   committed reports cannot be re-scored or diagnosed.
5. **12 cases × 1 run** cannot resolve 90 %: one case moves a value by ~8
   points.

Consequence: the true quality is **unknown**, in both directions. The first
work is to make the instrument trustworthy — and to freeze it before tuning,
so that improvements are real and not metric artefacts.

## 4. Principles

- **Instrument before tuning.** The scorer and goldset are validated against
  the professional reviewer and then frozen (versioned). After the freeze, a
  scorer change requires a decision entry and re-scoring of every arm from
  saved outputs.
- **Held-out means held out.** The held-out cases are never used for prompt,
  retrieval or model tuning, and are not read by the developer agent (§ 5).
- **Deterministic first.** What an engine can decide (an arithmetic error, an
  income assigned to the wrong month, a wrong allowance band) is decided by an
  engine and fed into the analysis, consistent with "deadlines and amounts
  only from deterministic engines".
- **Structured over parsed.** Issues, citations and the verdict are emitted as
  structured fields from closed vocabularies; free text is for the person, not
  for the scorer. `/api/v1` changes stay additive (D-039).
- **Every live run is bounded** (calls, concurrency, time, cost) and uses an
  operator-provided key separate from the developer agent's (AGENTS.md).

## 5. Goldset v1.0.0

| Property | Target |
|---|---|
| Cases | ≥ 90 synthetic notices: **60 development**, **30 held-out** |
| Coverage | stratified by notice type (Bewilligung, vorläufige/endgültige Festsetzung, Aufhebung/Erstattung, Minderung/Meldeversäumnis, KdU/Kostensenkung, Versagung/Mitwirkung, Vermögen, Einkommen/Zufluss, Rückforderung/Aufrechnung, letters that are not a VA) and by assessment label; each label ≥ 15 % of the held-out set |
| Expected issues | each carries an **issue-taxonomy ID** (§ 6 Q1-b), its anchor norm(s), and the assessment of that issue |
| Non-issues | "this part is correct" statements move to `non_issues` (checked as false positives, not as recall) |
| Citations | `required` (must be cited) and `acceptable` (correct, not required); every case has at least one required norm or an explicit `none_expected: true` |
| Assessment | one label per case, with the reviewer's written rationale; label definitions written into the goldset's `evaluation_guide` so `rechtswidrig` vs `teilweise_rechtswidrig` is decidable |
| Review | every case reviewed and signed off by the professional reviewer (owner-appointed) |
| Provenance | synthetic only (dev posture: `X-Document-Tag: goldset`) |

**Held-out custody:** the 30 held-out cases are kept outside the public repo
(owner's custody; open question OQ-Q2 decides where) and run by the owner. Only
the aggregate report and its outputs are committed after a gate run.

## 6. Work packages (P14, WP-150 … WP-155)

Order is strict for Q0–Q2; Q3 and Q4 iterate.

### Q0 — WP-150 Decision and freeze

- D-069 approved; roadmap v3.1.0 (P14 before P13); AGENTS.md "Next" updated.
- `eval/regression_gate.py`: issue recall, citation precision and assessment
  match become **strict** with the § 2 thresholds (they are warn-only since
  D-062). The gate fails today; that is intended.
- Public release go/no-go gains item G15 (this gate).

### Q1 — WP-151 Fix the instrument

- **a. Assessment scorer** — `eval/extractors.py` 1.2.0 (done in this draft,
  `tests/unit/test_eval_assessment.py`): reads the verdict sentence first,
  ignores negated mentions, earliest match wins in the fallback, no
  "unzulässig", labels `rechtmaessig` / `einordnung_offen` for real answers no
  goldset label equals. Next: the pipeline emits a structured `assessment`
  field (closed vocabulary from `result_categories`; additive, documented in
  `API_DOCUMENTATION.md`) and the scorer reads that field; text extraction
  remains only for legacy outputs.
- **b. Issue taxonomy** — module data `modules/sozialrecht/issues.yaml`
  (versioned): stable IDs, anchor norms, notice types it applies to,
  definition. The pipeline emits taxonomy IDs per finding (plus free text);
  recall = matched expected IDs / expected IDs. Deterministic, no norm-string
  matching, no LLM judge.
- **c. Citation precision** — precision over `required ∪ acceptable`;
  `none_expected` cases score precision as "no citation = 1.0". A
  `citation_recall` over `required` is reported alongside so precision cannot
  be gamed by citing less.
- **d. Reports** — per case: extracted assessment, matched/missed/extra issue
  IDs, extra citations. Gate runs commit their `*.outputs.json` (synthetic
  data). Report format version bump.
- **e. Validation** — the reviewer labels a sample of real pipeline outputs
  independently; the scorer must agree with the reviewer on **≥ 95 %** of
  items for each metric before the freeze. Then: scorer frozen at a version.

### Q2 — WP-152 Goldset v1.0.0

Per § 5. The reviewer's time is the bottleneck; cases can be drafted from the
issue taxonomy and reviewed in batches of 10. The development set may start
being used once the first 30 development cases are signed off.

### Q3 — WP-153 Diagnose

- Fresh reference run at the current tree (also needed for D-063), 3 runs,
  development set, outputs saved.
- New metric `retrieval_norm_recall`: share of required norms present in the
  chunks handed to the model. Classifies every miss as **retrieval** (norm
  never reached the model), **reasoning** (reached, not used / wrong), or
  **format** (correct but not scoreable).
- Output: a ranked miss table that decides the order of Q4.

### Q4 — WP-154 Improve (order set by Q3)

Candidate levers, each measured as an arm on the development set (3 runs):

1. **Checklists per notice type** — the taxonomy entries applicable to the
   detected notice type are given to the model as an explicit check list;
   the model must answer each (finding / not applicable / open).
2. **Deterministic detectors** — engine checks that emit taxonomy findings
   directly (Additionsfehler, Zuflussmonat, Freibetragsstaffel, Bewilligungs-
   zeitraum, presence of Rechtsbehelfsbelehrung, § 35 SGB X Begründung).
3. **Retrieval** — corpus coverage of every taxonomy anchor norm; queries
   built from taxonomy anchors; reranking.
4. **Citation discipline** — citations limited to norms present in retrieved
   chunks or in the taxonomy entry of the finding.
5. **Assessment as a function of findings** — the verdict derived by a
   documented rule from the issue findings and the VA classification, instead
   of free model judgement; the model explains, the rule decides.
6. **Model per stage, multi-pass / self-consistency** for triage and issue
   finding (cost and latency measured per arm).
7. Engine defect `rules_engine.py:1324` (error count reported as euros) fixed
   before any calculation-explanation arm.

### Q5 — WP-155 Gate and release

- 3 runs of the release tree on the held-out set (owner-run), all three values
  > 0.90, deterministic gate green.
- Decision entry, published report (WP-145), core release.
- Only then does P13 resume.

## 7. What is frozen until Q5 passes

- **Frozen:** P13 (all area modules), new features, open follow-ups of
  P10–P12 that are not defects.
- **Allowed:** security and privacy fixes, defect fixes, compliance
  obligations, work in this plan. Track G (funding, governance) is the
  owner's call (OQ-Q3).

## 8. Live-run budget

Each run states before it starts: cases × stages × runs = max calls (12 cases
× 5 calls × 3 runs = 180 for the current goldset; 90 × 5 × 3 = 1 350 for
goldset v1.0.0), concurrency 1 per provider quota, a wall-clock limit, a cost
bound from the profile's per-token price, and the stop mechanism. Keys are
operator-provided and separate from the developer agent's.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Metric fixed to look good | reviewer validation (Q1-e) and freeze before tuning |
| Overfitting to the development set | held-out set in owner custody; 30 cases |
| Reviewer capacity | batches of 10; dev set usable from 30 cases |
| 90 % not reachable with the current architecture | Q3 shows where misses come from; the deterministic-first and checklist levers change the architecture, not only prompts |
| Cost/latency of multi-pass arms | measured per arm; latency is reported, not gated |

## 10. Open questions

| ID | Question | Owner |
|---|---|---|
| OQ-Q1 | Name and availability of the professional reviewer; hours per batch | owner |
| OQ-Q2 | Where the held-out set lives (private repo, encrypted file, reviewer-held) | owner |
| OQ-Q3 | Does Track G continue during the freeze (WP-140 due 2026-11-30)? | owner |
| OQ-Q4 | Inference budget per month for live runs | owner |
