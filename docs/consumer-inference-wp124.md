# Consumer inference default — measurement protocol (WP-124, OQ-2)

<!-- Version: 1.0.0 | 2026-11-17 — roadmap P12, D-068. -->

**Question (OQ-2):** which local runtime/model passes the Sozialrecht goldset
gate, so the consumer distribution can default to the `on-prem` profile?
**Status:** not measured. The build environment has no GPU and no local
model; the plumbing below is in place and unit-tested, the measurement is an
operator task.

## 1. What core 3.4.0 provides

- Inference profiles may name an OpenAI-compatible `chat_endpoint`
  (`config/inference_profiles.yaml` 0.3.0). The router sends every chat call
  there; the egress guard checks that URL's host against the profile's
  `host_allowlist`.
- The `on-prem` profile is pre-configured for a loopback runtime
  (`http://127.0.0.1:11434/v1/chat/completions` — Ollama's default; llama.cpp
  server and vLLM expose the same API on their own ports) with
  `host_allowlist: [127.0.0.1, localhost]`. It stays **`enabled: false`**
  until a run passes the gate.

## 2. Preconditions for a run

1. A local runtime serving the candidate model(s). Set `PRIMARY_MODEL`,
   `FALLBACK_MODEL_1`, `FALLBACK_MODEL_2` (and optionally `CALCULATION_MODEL`)
   to the runtime's model names.
2. **Embeddings stay compatible:** `ChunkEmbedding.embedding` is
   `Vector(1536)`. Either keep the corpus embeddings produced by
   `openai/text-embedding-3-small` and serve query embeddings from the same
   model (not local — then the run is not fully on-prem), or re-embed the
   corpus with a local 1536-dimension model and point `EMBEDDING_BASE_URL`
   at a loopback host. A different dimension needs a migration and is a
   separate decision.
3. In a scratch copy of the profiles file set `on-prem.enabled: true`
   (and the port, if not Ollama), then `INFERENCE_PROFILE=on-prem`.
4. Separate operator-provided environment for the run (AGENTS.md "Execution
   and AI testing"): no developer-agent keys; a local runtime needs none.

## 3. Run and gate

```bash
python -m eval.runner --module sozialrecht --save
```

- Gate: the manifest's `goldset.gate` (zero regression against the
  reference). D-063: the committed reference predates core 3.1.0; first
  produce a fresh `eu-avv` reference at the current tree, then compare the
  local candidate against it with `--baseline <report>`.
- Record per candidate: model + quantisation, runtime + version, hardware,
  aggregate metrics, `avg_latency_ms`, wall-clock time per case, and peak
  memory. A candidate that passes the gate but needs > 8 minutes per case
  breaks the D-017 timeout chain and is not eligible as a default.
- Budget: the goldset has 12 cases; one run is ≈ 12 × 9 stage calls ≈ 110
  local calls. No external cost; stop with Ctrl-C (the runner writes no
  partial report).

## 4. Decision rule

- **Pass** (gate passed, latency within the D-017 chain): record a decision
  entry naming model, runtime and report; ship the consumer distribution with
  `INFERENCE_PROFILE=on-prem` and `on-prem.enabled: true`.
- **Fail:** the consumer distribution documents the `eu-avv` option (EU
  endpoint, pseudonymization required, AVV) and `GET /api/v1/meta/privacy`
  tells the person where texts go. The plain-language privacy copy already
  has texts for both profiles.

---

*Changes to this document follow semantic versioning.*
