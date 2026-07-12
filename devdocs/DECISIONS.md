# Citizen — Decision Register

<!-- Version: 1.0.0 | 2026-07-12 -->
<!-- Maintained by project lead. Each entry: ID, status, date, summary, rationale. -->

## D-1: Sozialrecht-only support claim (v1.0.0)

- **Status:** Ratified
- **Date:** 2026-07-11 (roadmap)
- **Actor:** Orchestrator
- **Summary:** For v1.0.0, the application's main support claim is restricted to SGB II (Grundsicherung für Arbeitsuchende). All other legal areas (Erbrecht, Mietrecht, Arbeitsrecht, etc.) are preserved structurally but barred from the primary user journey. They remain accessible through direct configuration override (settings, preset) or developer mode.
- **Rationale:** Scope reduction. The goldset covers SGB II exclusively. Full multi-area reliability requires area-specific eval goldsets (Phase 3). Until then, claiming multi-area support undermines measured reliability.

## D-2: Four tangible user-facing answers

- **Status:** Ratified
- **Date:** 2026-07-11 (roadmap)
- **Actor:** Orchestrator
- **Summary:** Every analysis result must deliver four concrete, auditable answers:
  1. **Sachverhalt** — wird das Recht erfasst? (area classification)
  2. **Berechnung** — konkrete Zahlen in Euro (calculation result)
  3. **Fristen** — deterministisch (deadline engine)
  4. **Widerspruch** — Mustertext, vorausgefüllt mit Fall-Variablen (action document)
- **Rationale:** Forces measurable, user-actionable output from every pipeline run. Vague prose is not enough.

## D-3: Measured reliability (eval-gated)

- **Status:** Ratified
- **Date:** 2026-07-11 (roadmap)
- **Actor:** Orchestrator
- **Summary:** Every analysis result carries a measured reliability signal derived from goldset evaluation. The application is honest about uncertainty. No "xxx% confident" claims without eval backing.
- **Rationale:** Core differentiator vs. generic LLM chat. Users deserve to know when the engine is guessing.

## D-4: Stufe 1 Datenautonomie (pseudonymization + EU inference)

- **Status:** Ratified
- **Date:** 2026-07-11 (roadmap)
- **Actor:** Orchestrator
- **Summary:** Stufe 1 of data autonomy: pseudonymize PII before egress to OpenRouter (non-EU), document that inference currently runs through US jurisdiction, enable model switching so EU-hosted models (Mistral, Llama EU) can be added as they become available.
- **Rationale:** Legal minimum for social-law use cases. Full data sovereignty (Stufe 2: local inference) is post-v1.0.0.

## D-5: Park Chat + Electron

- **Status:** Ratified
- **Date:** 2026-07-11 (roadmap)
- **Actor:** Orchestrator
- **Summary:** Chat mode and Electron desktop wrapper are preserved in the codebase but removed from the primary user journey. Chat remains accessible via Settings or direct URL. Electron build pipeline is not touched.
- **Rationale:** Chat undermines evidence-constrained positioning. Electron work is orthogonal to core reliability improvements. Both are post-v1.0.0 items.

## D-6: CI regression thresholds for LLM-variance metrics

- **Status:** Open
- **Date:** —
- **Actor:** (set during WP-11)
- **Summary:** (to be determined) What thresholds trigger CI failure for inherently LLM-variance-sensitive eval metrics.
- **Rationale:** Cannot set meaningful numbers without eval harness data. Deliberately left open until WP-11 produces first run.

## D-7: Per-stage model staffing per legal profile

- **Status:** Open
- **Date:** —
- **Actor:** (output of WP-13)
- **Summary:** (to be determined) Which model runs which pipeline stage for which legal area.
- **Rationale:** Requires WP-13 model eval matrix data. Current defaults: PRIMARY_MODEL for everything tier-1.

## D-8: Client consolidation — single factory + contextvars

- **Status:** Ratified
- **Date:** 2026-07-12
- **Actor:** Orchestrator (per @oracle H2 finding)
- **Summary:** Replace four separate `OpenRouterClient` singletons (reasoning.py, chat_reasoning.py, intake.py, case_chat.py) with a single shared factory in `app/core/router.py`. Case identity propagated via `contextvars.ContextVar("case_id")` for future egress guard (WP-31).
- **Rationale:** Prerequisite for WP-31 (egress guard needs a single choke point). Also fixes resource leak (2 of 4 clients were never closed). Implementation: WP-00.5.

## D-9: Canonical version source — pyproject.toml → tag v0.1.0

- **Status:** Ratified
- **Date:** 2026-07-12
- **Actor:** Orchestrator (per @oracle H5 finding)
- **Summary:** `pyproject.toml` is the single source of truth for the application version. The current value is `0.1.0`. Frontend files (`index.html` v0.4.0, `app.js`/`style.css` v0.3.0) and config (`config.py` v0.2.0) have independent version strings — all are now acknowledged as non-canonical documentation.
- **Rationale:** `pyproject.toml` is machine-readable, consumed by packaging, and already the source for `get_app_version()`. Previous version drift between files was an artifact of release-less development.

## D-10: Eval backend — PostgreSQL

- **Status:** Ratified
- **Date:** 2026-07-12
- **Actor:** Orchestrator
- **Summary:** Evaluation results (WP-11 harness output, per-case metrics, regression history) are stored in PostgreSQL alongside existing models. No separate eval database.
- **Rationale:** Simpler ops, zero new infrastructure, existing models provide versioning/audit patterns. The 10-case goldset is too small to benefit from a specialized eval store.

## R2-1: Pseudonymization approach — Presidio

- **Status:** Open (recommendation from @oracle: use Microsoft Presidio as primary, not just optional)
- **Date:** 2026-07-12 (oracle recommendation)
- **Actor:** @oracle
- **Summary:** (to be determined in WP-30) Microsoft Presidio provides trained German NER models for PII detection (names, addresses, dates, IDs). @oracle recommends it as the primary pseudonymization layer rather than an optional enhancement.
- **Rationale:** Roadmap §R2-1 lists Presidio as optional. @oracle argues it should be primary given the quality gap between regex-based and ML-based PII detection, and that German social law cases are rich in named entities that regex patterns miss.

## R2-4: Reranker in retrieval pipeline

- **Status:** Open (deferred to WP-20 eval data)
- **Date:** —
- **Actor:** (WP-20)
- **Summary:** (to be determined) Whether to add a cross-encoder reranker after initial retrieval to improve relevance ranking.
- **Rationale:** Without eval metrics on current retrieval quality, the cost/benefit of a reranker is unknown. WP-20 will produce retrieval-specific eval data to inform this decision.

---

## Rejected Proposals

None yet.
