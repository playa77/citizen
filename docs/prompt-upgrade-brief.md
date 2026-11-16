# Prompt Upgrade Brief

**Purpose:** a self-contained task prompt for a state-of-the-art model (with repository access or the relevant files attached) to rewrite every prompt in Citizen.

**Companion:** `docs/prompt-inventory.md` — byte-exact inventory of all 16 prompts, 6 shared blocks and 16 findings (P-01…P-16, S-01…S-06, F-01…F-16). Read it before § 3.

**Operator note (not part of the prompt).** Give the model: this file, `docs/prompt-inventory.md`, and read access to `app/services/prompts.py`, `app/services/{reasoning,intake,case_chat,chat_reasoning,calculation}.py`, `app/api/routes/presets.py`, `modules/sozialrecht/{calculators.py,regime.py,prompts/profile.yaml}`, `modules/erbrecht/prompts/profile.yaml`, `app/core/router.py`, `app/core/pipeline.py`, and `DECISIONS.md` D-050/D-051. Do not let it modify code; the deliverable is a proposal.

---

## Task

You are a senior prompt engineer and German legal-domain editor working on **Citizen**, an open-source legal-AI service. Your job is to rewrite **every** language-model prompt in this system to the best of your ability, and to state precisely which defects cannot be fixed by prompt text alone.

### 1. What Citizen is

Citizen is a **free, MIT-licensed, citizen-side preparation assistant** for German social-law notices — primarily SGB II (Bürgergeld), SGB X and SGB XII. It is deliberately **not** a lawyer tool and is **never** used by authorities, courts or law enforcement (decisions D-020, D-034, D-035 in `DECISIONS.md`). Its purpose is to help a person understand a notice they received, see the deadlines, check the arithmetic, and prepare their own reply or appointment.

Architecture in one paragraph: an API-only FastAPI service (`/api/v1` is the sole interface, contract in `API_DOCUMENTATION.md`). A pipeline normalizes an OCR'd document, asks a language model to identify the legal issues and questions, retrieves statute and case-law chunks from a pgvector corpus, has the model construct **evidence-bound claims**, verifies those claims against the retrieved chunks, runs an adversarial review, and produces a structured assessment plus a draft reply. **Deadlines and benefit amounts are never produced by the model** — they come from deterministic engines over versioned legal parameters (`app/fristen/`, `modules/sozialrecht/rules_engine.py`). The model reads, structures, cites and drafts; the engines compute.

The codebase is being split into a **domain-neutral core plus legal-area modules** (`modules/<id>/`). Sozialrecht is the default module and the only complete one; the seven other module directories are experimental stubs, and `verwaltungsrecht` is served from a small procedural library inside the core. Area knowledge — statutes, terminology, document examples, parameters, deadline specs, calculators and the *stage prompt profile* — lives in module data, not in core code. Core services must contain no area-specific literals.

### 2. The role the prompts play

These prompts **are the product's legal reasoning**. There is no fine-tuning, no tool use, no agent loop, no retrieval-augmented tool protocol: everything the system “thinks” is decided by the strings catalogued in § 6–9 of the inventory plus the chunks placed in the user message.

Concretely, one Sozialrecht analysis sends **five** system prompts:

| Call | Prompt | What it decides |
| --- | --- | --- |
| 1 | P-03 `triage` | which legal issues and questions the case is about (drives retrieval and everything downstream) |
| 2 | P-04 `grounded_answer` | the claims (with chunk id, verbatim quote, confidence, type) **and** the seven output sections the citizen reads |
| 3 | P-05 `adversarial_review` | the risk assessment, opposing arguments, procedural-error findings |
| 4 | P-14 `calc_extraction` | which numbers the deterministic engine may use (values only — no arithmetic) |
| 5 | P-15 `calc_explanation` | how the engine's findings are explained to the citizen |

The remaining eleven prompts cover the intake interview (P-09), preset routing (P-10), the two chat surfaces (P-11, P-12), OCR synthesis (P-13), the injected reform-state banner (P-16), and the five legacy stage prompts (P-01, P-02, P-06, P-07, P-08) that are still reachable by configuration and by stage re-evaluation.

Two properties make these prompts compliance-relevant, not just quality-relevant:

* They carry the **no-invention rules** and the **evidence-bound stance** (shared block S-01, claim rules in P-04). Without them the product would state law it cannot source.
* They shape the **“not legal advice” framing** the disclaimer promises. The disclaimer says the output is AI-generated preparation aid; the prompts must not promise more.

### 3. Why the current prompts are insufficient

**3.1 Measured quality.** The only end-to-end measurement is the WP-90 baseline (`eval/results/20261116T094340Z-e9fb87a.json`, recorded inside `DECISIONS.md` D-050), 12 goldset cases through the real pipeline: issue recall **11.8 %**, citation precision **1.8 %**, quote verification **38.9 %**, assessment match **33.3 %**, calculation exact match **100 %**, Frist exact match **100 %**. The deterministic halves are perfect; the language-model halves are not. Part of the recall gap is a metric/format mismatch (F-09), but the prompt is the only lever that exists today and it has never been optimised against these numbers.

**3.2 The prompts have been refactored, never tuned.** Their current text dates from the v0.x design and was carried through the v1.0.0 and v2.0.0 refactors; WP-93 explicitly pinned them **byte-identical** while moving them into module data (`app/services/prompts.py:38–58`). No prompt has been rewritten for a current-generation model, and none has been evaluated against an alternative wording.

**3.3 Structural defects (details and line references in inventory § 12).** The most consequential:

* **F-01** The adversarial stage is asked to review claims, emit a `claim_index` for each, and never receives the claims — the prompt declares an input the message does not contain. Stage 7 currently reviews a document, not the analysis that ships.
* **F-02** JSON output is enforced by prose only. The router sends `model`, `messages`, `temperature` — no JSON schema, no structured-output mode, no `max_tokens`. A truncated or schema-invalid answer is handled by re-asking at temperature 0 with a shorter input.
* **F-03** The English strict suffix (S-05) tells the model to return `[]` or `{}` when it cannot comply — directly contradicting every schema that requires mandatory keys. The escape hatch turns a parse failure into a *semantically empty success*.
* **F-04** Per-stage sampling is inert: `STAGE_TEMPERATURES` and the `per_stage` block in `config/inference_profiles.yaml` are read by nobody; everything runs at 0.1.
* **F-05** Both chat prompts hardcode an SGB persona regardless of the case's modules; `legal_areas` only reaches the provenance marker. The module architecture promises area-aware behaviour the chat surfaces do not deliver.
* **F-06** The reform-state banner is computed from *today's* date, not from the notice's period, then instructs the model to “apply” that law — historically wrong for older notices.
* **F-07 / F-09** Context is silently truncated without a marker while verbatim quoting is required; and issue naming is not tied to the norm citations the evaluation measures.
* **F-10 … F-16** Invalid JSON example inside the intake prompt, mixed-language user headers, one German enum in an English contract, typos, no prompt versioning, an unenforceable multi-area conflict rule, and a preset prompt with no “no match” path.

**3.4 What this means for you.** Roughly half of the defects are prose problems you can fix in the prompt. The other half are **code-level** and must be requested explicitly, not papered over with instruction wording. A prompt that says “be sure to return valid JSON” cannot substitute for a schema; a prompt that asks for `claim_index` cannot invent the claims it never saw.

### 4. Hard constraints

These are product, legal and architectural invariants. Violating any of them makes the proposal unusable, however elegant the prose.

1. **Language.** Instruction prose stays **German**. User-visible content stays **German**. JSON keys and enum values stay **English exactly as the parsers expect** (`fact` / `interpretation` / `recommendation`); the one German enum (`risk_level`) may only be changed together with its consumer. You may fix inconsistency, but you may not introduce a second convention.
2. **Contract stability.** The JSON schemas in P-01…P-08, P-09, P-10, P-14 and P-15 are consumed by parsers and by the API response. Treat each schema as frozen unless you justify a change, list every consumer, and mark it as a breaking change proposal. `/api/v1` changes are additive only.
3. **Evidence discipline.** `evidence_chunk_id` must be an id that was actually provided; `evidence_quote` must be a verbatim copy; claims must not assert facts, statutes, deadlines, case numbers or official acts absent from the document or the chunks. Unsourced statements must be *marked* unsourced, not softened.
4. **No legal computation in prompts.** Never ask the model to calculate a deadline or a benefit amount, and never let a prompt imply that a model-produced number is authoritative. P-14 extracts values only; P-15 explains engine output and may not question it.
5. **Layout conventions.** Keep the sectioned layout (`<rolle>`, `<kontext>`/`<eingaben>`, `<aufgabe>`, `<regeln>`, `<ausgabeformat>`), keep exactly **one** output-format block, and keep it **last**. One canonical example per prompt.
6. **Module boundaries.** P-01…P-08 are rendered from `modules/<id>/prompts/profile.yaml`. If a rewrite needs a new interpolation slot, it goes into the profile schema and into every shipped profile (`sozialrecht`, `erbrecht`, and the keys inheriting it: `familienrecht`, `schenkungsrecht`), never as an area literal in core code. `app/modules/lint` and `tests/unit/test_modules_content.py` enforce this.
7. **Purpose.** Citizen-side only. No prompt may position the system as helping an authority assess, decide or defend a benefit claim, and no prompt may promise legal advice, representation or a guaranteed outcome.
8. **Runtime reality.** The model router supports only `model`, `messages`, `temperature`. If your design needs `response_format`, `max_tokens`, a JSON mode, a tool call or a second pass, say so as a **code-change request with a minimal diff sketch** — do not assume the capability exists.
9. **Budget.** The default path already sends 13,279 characters of instruction. Keep each stage prompt ≤ 6,000 characters unless you can defend the increase against the pipeline timeout chain (D-017) and the token budget; report the delta for every prompt.
10. **No goldset leakage.** Do not copy examples from `modules/sozialrecht/goldset/` into prompts, and do not encode case-specific answers.

### 5. Deliverable

For **each** of P-01 … P-16 produce one section with:

1. **New full text**, German, in a single fenced block, ready to paste — not a diff, not “add a sentence here”.
2. **What changed and why** — bullets, each tied to a mechanism (e.g. “moved the citation requirement from an example into a hard rule, because the goldset matches §-references”).
3. **Expected effect** — which goldset metric this should move and in which direction; if it should move none, say so.
4. **Risk and blast radius** — what could regress, which tests/goldens change, which downstream consumer is affected.
5. **Size delta** — characters before → after.

Then produce four cross-cutting sections:

6. **Shared blocks (S-01 … S-06).** Rewrite them once, with the same discipline. Resolve F-03 explicitly: either the escape hatch becomes schema-valid for every consumer, or it is removed and the failure behaviour is described truthfully.
7. **Code changes the prompts require.** A table: finding → why prose cannot fix it → minimal change (file, function, shape) → effect on prompts. Cover at least F-01 (claims into the adversarial message), F-02 (structured output / `max_tokens`), F-04 (wire the per-stage temperature that already exists as metadata), F-05 (module-aware chat personas), F-06 (anchor the regime to the notice period), F-08 (cache key includes prompt version), F-14 (prompt identity/version).
8. **Measurement plan.** How to tell whether the rewrite helped, using what exists: the goldset runner (`python -m eval.runner modules/sozialrecht/goldset/goldset-v0.2.0.yaml --baseline <report> [--save]`), per-prompt A/B on the 12 cases, and which metrics gate the change. State the expected direction and a stop condition (e.g. “if quote verification drops below X, revert P-04”).
9. **Migration notes.** Prompt version identifier, golden re-baseline steps (`tests/unit/golden/wp93_v2_baseline.json` regenerated via `tests/unit/wp93_golden_collect.collect` in the same change, recorded in `DECISIONS.md`), changelog entry, and the order in which the prompts should land.

### 6. Method requirements

* Start from inventory § 12. Every finding must end up **fixed in prompt text**, **escalated as a code change**, or **explicitly declined with a reason**. No silent omissions.
* Read each prompt against the message it actually receives (§ 6–8 of the inventory), not against what it claims to receive. Where they diverge, the message is the truth.
* Prefer explicit, enumerable requirements over adjectives. Replace “sorgfältig”, “präzise”, “streng” with a checkable rule whenever the rule can be stated.
* Keep the model's job separable: one decision per field, one field per fact the consumer needs. Where a prompt currently asks for judgement and formatting in one call (P-04), state the ordering inside the prompt so conflicts resolve deterministically.
* Do not add hidden chain-of-thought. If reasoning must be captured, add an explicit field and say which consumer ignores it.
* Do not weaken the escape hatches for insufficient evidence — make them *usable* (schema-valid, distinguishable from “nothing found”).
* German legal register: correct citation format `§ X Abs. Y Satz Z <Gesetz>`; no invented norms, no obsolete section numbers presented as current; the reform-state banner is the only place where temporal law is signalled, and it must be phrased as a constraint on which rules apply, not as an assertion about the case.
* Write for a model, not for a human reviewer: short sentences, one instruction per line, no motivating prose, no meta-commentary about being an AI.

### 7. Acceptance criteria

The proposal is accepted when:

1. All 16 prompts and all 6 shared blocks have a complete new text.
2. Every one of F-01 … F-16 is addressed in one of the three ways § 6 requires.
3. No new prompt contradicts another block; in particular the strict-JSON suffix and the schema of every prompt that uses it are mutually consistent.
4. Every schema is either unchanged or the change is listed with all consumers and marked as breaking.
5. Every prompt is ≤ 6,000 characters or the overage is justified in § 5.5.
6. The code-change table is actionable: file, function, shape of the change, and the prompt behaviour it unlocks.
7. The measurement plan names the baseline report, the metrics, the expected direction and a stop condition.
8. No German legal claim in any prompt is invented, anachronistic, or attributed to the wrong norm.

### 8. Output format

One markdown document, in this order:

```
# Prompt upgrade proposal
## 0. Summary table            (P-01…P-16: what changed, size delta, metric target)
## 1. P-01 … P-16              (five subsections each, per § 5)
## 2. Shared blocks            (S-01 … S-06)
## 3. Code changes required    (table + minimal diffs)
## 4. Measurement plan
## 5. Migration and sequencing
## 6. Declined findings        (finding → why not fixed in prompt)
```

Do not modify repository files. Do not produce partial drafts; if a prompt cannot be improved safely, say so and leave it unchanged with a reason.

### 9. Non-goals

* Do not redesign the pipeline, the retrieval strategy or the API.
* Do not add modules, area keys, parameters or calculators.
* Do not touch the disclaimer, the disclosure builder or the provenance marker.
* Do not write tests, migrations or changelog entries — describe them.
* Do not introduce new providers, models or dependencies.
* Do not “improve” the deterministic engines: deadlines, benefit math, document templates and claim verification are out of scope by design.

### 10. Reference map

| What you need | Where |
| --- | --- |
| Every prompt, verbatim, with call sites and message layout | `docs/prompt-inventory.md` § 6–10 |
| Defect register with evidence | `docs/prompt-inventory.md` § 12 |
| Stage templates and shared blocks | `app/services/prompts.py` |
| Area profiles (data) | `modules/*/prompts/profile.yaml` |
| Pipeline orchestration and flags | `app/core/pipeline.py`, `app/core/config.py` |
| Model routing, egress, timeouts | `app/core/router.py`, `config/inference_profiles.yaml`, D-017 |
| Quantitative baseline | `DECISIONS.md` D-050, `eval/results/20261116T094340Z-e9fb87a.json` |
| Architectural and compliance constraints | `ARCHITECTURE.md`, `AGENTS.md`, `DISCLAIMER_DE.md` |
| Eval harness | `eval/runner.py`, `modules/sozialrecht/goldset/goldset-v0.2.0.yaml` |
| Why prompts live in module data | `DECISIONS.md` D-051, D-052, D-053 |
