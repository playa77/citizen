# Target architecture

For `/api/v1/analyze`, aim for this:

```text
Stage 1: normalize locally                         < 1s
Stage 2+3: combined triage LLM call                 5–20s
Stage 4: retrieval                                  2–10s
Stage 5+6+7: single grounded-answer LLM call        20–70s
Audit persistence                                   async, after response

Total target:                                      30–100s
Hard cap:                                          120s
```

The big change: reduce from 5 sequential chat calls to 2 chat calls.

You can still keep the external 7-stage audit model. Internally, however, you should combine stages:

```text
classification + decomposition
construction + verification + generation
```

Then emit the same SSE stage events for compatibility.

---

# Priority roadmap

## Phase 1 — Stop the bleeding

Implement these first:

1. WP-001: Add latency instrumentation.
2. WP-002: Fix timeout/retry/fallback behavior.
3. WP-003: Parallelize or combine classification/decomposition.
4. WP-004: Reduce retrieval cost.
5. WP-005: Move audit persistence truly out of the response path.

This alone should cut many runs from 240s to perhaps 80–160s.

## Phase 2 — Real under-2-minute path

6. WP-006: Add combined triage function.
7. WP-007: Add combined final-answer function.
8. WP-008: Replace LLM verification with deterministic quote/citation verification.

This should get you reliably under 120s for 1500 words.

## Phase 3 — Stability and quality

9. WP-009: Add model routing.
10. WP-010: Add prompt/token budgeting.
11. WP-011: Add caching.
12. WP-012: Optimize OCR path separately.

---

# WP-001 — Add latency instrumentation

## Goal

Before optimizing, measure where the time goes. You need per-stage timings, per-LLM-call timings, model name, attempt count, timeout events, prompt size, and response size.

## Files to modify

- `app/core/pipeline.py`
- `app/core/router.py`
- optionally `app/api/routes/analyze.py`
- add `scripts/benchmark_analyze.py`

## Implementation tasks

1. Add structured timing logs for every pipeline stage.
2. Add structured timing logs for every OpenRouter request.
3. Include:
   - model
   - attempt
   - elapsed seconds
   - prompt character count
   - response character count
   - timeout/failure reason
4. Add a benchmark script that posts a 1500-word sample to `/api/v1/analyze` and records:
   - time to first SSE event
   - time per stage event
   - time to final event
   - total connection duration

## Acceptance criteria

- Running one analyze request prints a clear timing breakdown.
- You can answer: “Which stage consumed the most time?”
- Benchmark output should look roughly like:

```text
normalization:    0.02s
classification:  11.40s
decomposition:   10.91s
retrieval:        7.22s
construction:    28.40s
verification:    34.12s
generation:      42.80s
total:          134.87s
```

## Prompt for coding model

```text
Implement latency instrumentation for the Citizen FastAPI app.

Modify app/core/pipeline.py and app/core/router.py so that every pipeline stage
and every OpenRouter API call logs structured timing information. Include model,
attempt, elapsed seconds, prompt character count, response character count, and
error type if failed.

Also create scripts/benchmark_analyze.py. The script should POST a sample text
to /api/v1/analyze with the required X-Disclaimer-Ack header, consume the SSE
stream, print the time of each stage event, and print total elapsed time.

Do not change business logic yet. Preserve existing API behavior.
```

---

# WP-002 — Fix timeout, retry, and fallback behavior

## Goal

Prevent one slow model from consuming the entire 300-second pipeline budget.

## Current problem

In `app/core/router.py`:

```python
self.models: list[str] = [
    settings.PRIMARY_MODEL,
    settings.FALLBACK_MODEL_1,
    settings.FALLBACK_MODEL_2,
]
```

But your config uses the same model twice:

```python
PRIMARY_MODEL: str = "deepseek/deepseek-v4-flash"
FALLBACK_MODEL_1: str = "deepseek/deepseek-v4-flash"
```

Also:

```python
MAX_RETRIES: int = 3
REQUEST_TIMEOUT: float = 45.0
```

This is too generous for a multi-stage pipeline.

## Recommended defaults

For development:

```env
MAX_RETRIES=1
REQUEST_TIMEOUT=25
PIPELINE_TIMEOUT_SEC=120
TOP_K_RETRIEVAL=6
```

Later you can use per-stage timeouts.

## Implementation tasks

1. Deduplicate fallback models.
2. Let `chat_completion()` accept:
   - `timeout`
   - `max_retries`
   - `models`
3. Add config values:

```python
TRIAGE_TIMEOUT_SEC: float = 20.0
FINAL_TIMEOUT_SEC: float = 75.0
EMBEDDING_TIMEOUT_SEC: float = 15.0
```

4. Stop retrying slow models too much.
5. Make fallback chain explicit and non-duplicated.

## Example desired behavior

Instead of:

```text
model A attempt 1: 45s timeout
model A attempt 2: 45s timeout
model A attempt 3: 45s timeout
model A again attempt 1: 45s timeout
...
```

You want:

```text
triage model A attempt 1: timeout at 20s
fallback model B attempt 1: success at 8s
```

## Acceptance criteria

- No duplicated model names in fallback chain.
- No single triage call can exceed 20–25s.
- No final generation call can exceed 75–90s.
- A bad model fails fast and falls back once.

## Prompt for coding model

```text
Refactor app/core/router.py so OpenRouterClient deduplicates fallback models and
supports per-call timeout and max_retries parameters.

Add these settings to app/core/config.py:
- TRIAGE_TIMEOUT_SEC: float = 20.0
- FINAL_TIMEOUT_SEC: float = 75.0
- EMBEDDING_TIMEOUT_SEC: float = 15.0
- TRIAGE_MODEL: str | None = None
- FINAL_MODEL: str | None = None

Modify OpenRouterClient.chat_completion() so callers can pass:
- timeout: float | None
- max_retries: int | None
- model: str | None
- models: list[str] | None

If models are provided, use that fallback chain. Deduplicate model names while
preserving order. Default max_retries should still come from settings, but code
must support per-call overrides.

Preserve existing behavior for existing callers as much as possible.
```

---

# WP-003 — Parallelize classification and decomposition

## Goal

Classification and question decomposition both depend only on normalized text. They do not need to be sequential.

## Current code

In `app/core/pipeline.py`, stages run strictly one after another:

```python
_STAGES = [
    "normalization",
    "classification",
    "decomposition",
    "retrieval",
    "construction",
    "verification",
    "generation",
]
```

## Short-term fix

Run classification and decomposition concurrently after normalization.

The SSE output can still emit:

```text
classification complete
decomposition complete
```

in the same order after both tasks finish.

## Expected gain

If classification takes 12s and decomposition takes 14s:

- current: 26s
- parallel: about 14s

## Acceptance criteria

- Classification and decomposition execute concurrently.
- SSE still includes both stage events.
- No change to API response schema.
- Failure in either stage still fails the pipeline clearly.

## Prompt for coding model

```text
Modify app/core/pipeline.py so classification and decomposition can run
concurrently after normalization.

Keep the public SSE stage names the same:
- normalization
- classification
- decomposition
- retrieval
- construction
- verification
- generation

After normalization, run _stage_classification(state) and
_stage_decomposition(state) using asyncio.gather(). Then emit the classification
SSE event and decomposition SSE event with correct duration_ms values.

Do not change the endpoint contract. Preserve timeout enforcement.
```

---

# WP-004 — Reduce retrieval cost

## Goal

Retrieval currently embeds every question. For 3–5 questions, that means 3–5 embedding requests. This is not terrible, but it adds latency and failure surface.

## Better approach

For the first speed target, use one combined retrieval query:

```text
issues + questions + short normalized document summary
```

Generate one embedding and retrieve top `K`.

Later, you can support hybrid retrieval or multiple embeddings.

## Files to modify

- `app/services/retrieval.py`
- `app/core/config.py`
- possibly `app/core/pipeline.py`

## Implementation tasks

1. Add setting:

```python
RETRIEVAL_MODE: str = "combined"  # "combined" or "per_question"
```

2. Implement `retrieve_chunks_combined()`:

```python
async def retrieve_chunks_combined(
    issues: list[str],
    questions: list[str],
    normalized_text: str,
    *,
    client: OpenRouterClient | None = None,
) -> list[dict[str, Any]]:
    ...
```

3. Build query like:

```text
Themen:
- issue 1
- issue 2

Rechtsfragen:
- question 1
- question 2

Dokumentauszug:
first 1200 characters
```

4. Generate one embedding.
5. Retrieve `TOP_K_RETRIEVAL` chunks.
6. Deduplicate and sort as before.

## Recommended settings

```env
TOP_K_RETRIEVAL=6
MAX_COSINE_DISTANCE=0.85
RETRIEVAL_MODE=combined
```

`0.75` may be too strict depending on embedding quality.

## Acceptance criteria

- Retrieval makes one embedding request in combined mode.
- Retrieval stage usually completes in under 10s.
- Existing per-question retrieval still works behind a setting.

## Prompt for coding model

```text
Add a faster combined retrieval mode.

In app/core/config.py add:
- RETRIEVAL_MODE: str = "combined"

In app/services/retrieval.py implement retrieve_chunks_combined(issues,
questions, normalized_text, client=None). It should create one combined German
search query from issues, questions, and the first 1200 chars of normalized_text,
generate one embedding, query pgvector once, and return the same chunk dict shape
as retrieve_chunks().

Modify app/core/pipeline.py retrieval stage so if settings.RETRIEVAL_MODE ==
"combined", it calls retrieve_chunks_combined(state.issues, state.questions,
state.normalized_text). Otherwise preserve existing retrieve_chunks(state.questions).

Keep API behavior unchanged.
```

---

# WP-005 — Move audit persistence out of the response path

## Goal

Right now `analyze.py` persists audit data inside the SSE generator after yielding the final event. Depending on the client, the response may not be considered complete until that DB work finishes.

## Current code

In `event_generator()`:

```python
yield _sse_format(final_payload)

# then persist audit trail
...
await persist_audit_record(db_session, audit_record)
```

This can delay connection close.

## Better approach

After yielding final output, schedule audit persistence in the background and immediately end the stream.

## Implementation options

Simple option:

```python
asyncio.create_task(_persist_audit_safely(audit_record))
return
```

More structured option:

- Use a small internal queue.
- Background worker consumes audit records.

For this project, `asyncio.create_task()` is acceptable.

## Acceptance criteria

- Final SSE event is sent as soon as generation completes.
- Connection closes within about 1s after final event.
- Audit still gets persisted.
- Audit failures are logged but never delay the user.

## Prompt for coding model

```text
Refactor app/api/routes/analyze.py so audit persistence happens outside the SSE
response path.

Create an async helper _persist_audit_safely(audit_record: AuditRecord) that
opens a fresh DB session and calls persist_audit_record(), catching and logging
all exceptions.

In event_generator(), after yielding the final payload, schedule persistence
with asyncio.create_task(_persist_audit_safely(audit_record)) and then return
immediately.

Do the same for failed audit records if possible. Preserve existing audit data
structure.
```

---

# WP-006 — Combine classification and decomposition into one triage call

## Goal

Instead of two LLM calls:

```text
classify_issues()
decompose_questions()
```

use one:

```text
triage_document()
```

that returns both:

```json
{
  "issues": ["..."],
  "questions": ["..."]
}
```

## Why this matters

Even with parallelization, you still pay for two remote requests. One combined call is faster and often better because the model sees the task holistically.

## Files to modify

- `app/services/reasoning.py`
- `app/core/pipeline.py`

## New function

```python
async def triage_document(normalized_text: str) -> dict[str, list[str]]:
    ...
```

## Suggested prompt

The model should return:

```json
{
  "issues": ["..."],
  "questions": ["..."]
}
```

Rules:

- German.
- 1–8 issues.
- 3–5 questions.
- Questions must be answerable using German social law.
- No prose.

## Pipeline compatibility

You can still emit two SSE events:

1. `classification`
2. `decomposition`

But internally they come from the same LLM result.

## Acceptance criteria

- Stage 2+3 use one LLM call.
- SSE events remain unchanged.
- `state.issues` and `state.questions` are populated.
- Fallback to old separate calls can be enabled via setting if desired.

## Prompt for coding model

```text
Add a combined triage LLM call.

In app/services/reasoning.py create async function triage_document(normalized_text:
str) -> dict[str, list[str]]. It should call OpenRouter once and return a dict
with:
- issues: list[str]
- questions: list[str]

Use a strict JSON prompt. Validate that issues is a list and questions is a
list. Return empty lists on malformed content only after the existing JSON retry
logic fails.

In app/core/config.py add:
- COMBINE_TRIAGE_STAGES: bool = True

In app/core/pipeline.py modify classification/decomposition execution. If
COMBINE_TRIAGE_STAGES is true, call triage_document() once after normalization,
populate state.issues and state.questions, and emit the existing classification
and decomposition SSE events. If false, preserve the old behavior.

Use settings.TRIAGE_MODEL if provided, and settings.TRIAGE_TIMEOUT_SEC.
```

---

# WP-007 — Combine construction, verification, and generation into one grounded answer call

## Goal

This is the biggest win.

Currently you do:

```text
construct_claims()  -> LLM
verify_claims()     -> LLM
generate_output()   -> LLM
```

Replace with:

```text
generate_grounded_answer() -> LLM once
deterministic verification -> local
```

## New output shape

Ask the LLM to return both the final six sections and claim/evidence metadata:

```json
{
  "claims": [
    {
      "claim_text": "...",
      "confidence_score": 0.82,
      "claim_type": "interpretation",
      "question": "...",
      "evidence_chunk_id": "...",
      "evidence_hierarchy": "SGB II > § 31 > Abs. 1",
      "evidence_quote": "exact quote copied from source chunk"
    }
  ],
  "sections": {
    "sachverhalt": "...",
    "rechtliche_wuerdigung": "...",
    "ergebnis": "...",
    "handlungsempfehlung": "...",
    "entwurf": "...",
    "unsicherheiten": "..."
  }
}
```

## Why this is safe

You can instruct the LLM:

- Only use provided chunks.
- Every legal claim must have an evidence quote.
- If evidence is insufficient, say so.
- Do not invent statutes.
- Copy evidence quotes exactly.

Then local code checks whether the quote actually appears in the retrieved chunk.

## Files to modify

- `app/services/reasoning.py`
- `app/core/pipeline.py`
- `app/services/audit.py` maybe not necessary, but evidence binding quality improves.

## Acceptance criteria

- After retrieval, the app makes one final LLM call.
- Pipeline still emits:
  - construction
  - verification
  - generation
- `state.claims` is populated from the LLM result.
- `state.verified_claims` is populated by deterministic verification.
- `state.final_output` is populated from `sections`.
- Total chat calls per analyze request should be 2:
  - triage
  - grounded answer

## Prompt for coding model

```text
Implement a combined grounded answer generation path.

In app/services/reasoning.py add async function generate_grounded_answer(
    normalized_text: str,
    issues: list[str],
    questions: list[str],
    chunks: list[dict[str, Any]],
) -> dict[str, Any].

It should call the LLM once and require strict JSON with this shape:
{
  "claims": [
    {
      "claim_text": str,
      "confidence_score": float,
      "claim_type": "fact" | "interpretation" | "recommendation",
      "question": str,
      "evidence_chunk_id": str,
      "evidence_hierarchy": str,
      "evidence_quote": str
    }
  ],
  "sections": {
    "sachverhalt": str,
    "rechtliche_wuerdigung": str,
    "ergebnis": str,
    "handlungsempfehlung": str,
    "entwurf": str,
    "unsicherheiten": str
  }
}

The prompt must instruct the model in German to use only the provided chunks,
copy evidence_quote exactly from a chunk, and explicitly state uncertainty when
sources are insufficient.

Add config setting:
- COMBINE_FINAL_STAGES: bool = True

In app/core/pipeline.py, if COMBINE_FINAL_STAGES is true, after retrieval call
generate_grounded_answer() once. Use its claims for construction, run a local
verification helper for verification, and use sections for generation. Emit the
same three SSE events as before.

Preserve old construct_claims(), verify_claims(), generate_output() path behind
COMBINE_FINAL_STAGES=false.
```

---

# WP-008 — Deterministic quote/evidence verification

## Goal

Replace expensive LLM verification with fast local verification.

## Current issue

Your `verify_claims()` LLM output does not include evidence fields, even though `analyze.py` expects fields like:

```python
vc.get("evidence_chunk_id")
vc.get("evidence_quote")
vc.get("evidence_hierarchy")
```

So your audit evidence bindings are probably mostly empty.

## New local verifier

For each claim:

1. Find matching chunk by `evidence_chunk_id`.
2. Check whether `evidence_quote` appears in `chunk["text_content"]`.
3. If yes:
   - `verified=True`
   - keep or slightly increase confidence.
4. If no:
   - try normalized substring match.
5. If still no:
   - `verified=False`
   - reduce confidence to max `0.45`.
6. Preserve evidence fields.

## Files to modify

- `app/services/reasoning.py` or new file `app/services/verification.py`
- `app/core/pipeline.py`

## Acceptance criteria

- Verification stage takes under 1s.
- Claims with exact evidence quotes are marked verified.
- Claims without matching quote are downgraded.
- Evidence bindings in audit records are populated.

## Prompt for coding model

```text
Add deterministic evidence verification.

Create app/services/verification.py with function verify_claims_against_chunks(
claims: list[dict[str, Any]], chunks: list[dict[str, Any]]
) -> list[dict[str, Any]].

For each claim, use evidence_chunk_id to find the source chunk. Check whether
evidence_quote appears exactly in text_content. If not, normalize whitespace and
try again. If matched, set verified=true and preserve confidence_score. If not
matched, set verified=false and reduce confidence_score to max 0.45.

Preserve these fields:
- claim_text
- confidence_score
- claim_type
- question
- evidence_chunk_id
- evidence_hierarchy
- evidence_quote
- verified
- reasoning

Reasoning should be a short German string explaining whether the quote was found.

Modify the combined final pipeline path to use this verifier for the verification
stage instead of the LLM verify_claims() call.
```

---

# WP-009 — Add model routing

## Goal

Do not use the same model for every stage. Use a fast model for triage, and a better model only for the final grounded answer.

## Suggested config

```python
TRIAGE_MODEL: str = "some-fast-cheap-model"
FINAL_MODEL: str = "some-balanced-quality-model"
OCR_SYNTHESIS_MODEL: str = "some-fast-ocr-model"
```

Keep these generic in code; configure concrete model names in `.env`.

## Example model strategy

```text
Triage:
  fast, cheap, low latency, okay reasoning

Final answer:
  better reasoning model, longer timeout

OCR synthesis:
  fast model, or disabled unless needed
```

## Files to modify

- `app/core/config.py`
- `app/services/reasoning.py`

## Acceptance criteria

- `triage_document()` uses `TRIAGE_MODEL` if set.
- `generate_grounded_answer()` uses `FINAL_MODEL` if set.
- Old functions can continue using primary model.
- Logs show which model was used for each stage.

## Prompt for coding model

```text
Add model routing.

In app/core/config.py add:
- TRIAGE_MODEL: str | None = None
- FINAL_MODEL: str | None = None
- OCR_SYNTHESIS_MODEL already exists; keep it.

Modify triage_document() to call OpenRouterClient.chat_completion() with
model=settings.TRIAGE_MODEL if set, timeout=settings.TRIAGE_TIMEOUT_SEC, and
max_retries=1.

Modify generate_grounded_answer() to call OpenRouterClient.chat_completion() with
model=settings.FINAL_MODEL if set, timeout=settings.FINAL_TIMEOUT_SEC, and
max_retries=1.

Ensure logs include the selected model.
```

---

# WP-010 — Add prompt and token budgeting

## Goal

Prevent accidental giant prompts. Even a 1500-word input can become large after adding questions, chunks, claims, and instructions.

## Files to modify

- `app/services/reasoning.py`
- maybe new `app/utils/tokens.py`

## Implementation tasks

1. Add helper:

```python
def trim_text(text: str, max_chars: int) -> str:
    ...
```

2. Add settings:

```python
MAX_TRIAGE_INPUT_CHARS: int = 8000
MAX_FINAL_INPUT_CHARS: int = 5000
MAX_CHUNK_CONTEXT_CHARS: int = 7000
MAX_CHUNKS_FOR_FINAL: int = 6
```

3. For final answer:
   - use only top 6 chunks by retrieval score
   - include chunk id, hierarchy, and text
   - hard cap total chunk context

## Acceptance criteria

- Logs show prompt size.
- Final prompt never exceeds configured character budget.
- Very long documents do not explode latency.

## Prompt for coding model

```text
Add prompt-size budgeting.

In app/core/config.py add:
- MAX_TRIAGE_INPUT_CHARS: int = 8000
- MAX_FINAL_INPUT_CHARS: int = 5000
- MAX_CHUNK_CONTEXT_CHARS: int = 7000
- MAX_CHUNKS_FOR_FINAL: int = 6

In app/services/reasoning.py add helpers to trim document input and chunk context.
Modify triage_document() and generate_grounded_answer() to respect these limits.
For generate_grounded_answer(), include only the top settings.MAX_CHUNKS_FOR_FINAL
chunks and cap total chunk text to MAX_CHUNK_CONTEXT_CHARS.

Log final prompt character counts.
```

---

# WP-011 — Add local caching

## Goal

Avoid paying for repeated work during development and repeated user submissions.

## Best first caches

1. Embedding cache:
   - key: `sha256(model + text)`
   - value: vector
2. Triage cache:
   - key: `sha256(model + normalized_text)`
   - value: issues/questions
3. Retrieval cache:
   - key: `sha256(questions + corpus_version)`
   - value: chunk ids/results

## Simple implementation

Use a local SQLite file or a JSONL cache. Since this is local-first, SQLite is fine.

Add table:

```sql
cache_entry(
  key text primary key,
  value_json jsonb/text,
  created_at timestamp,
  expires_at timestamp nullable
)
```

But to keep it simple, use the existing PostgreSQL database.

## Acceptance criteria

- Repeating the same analyze request skips triage and embeddings.
- Repeated request should complete dramatically faster.
- Cache can be disabled via setting.

## Prompt for coding model

```text
Implement a simple local cache service.

Create app/services/cache.py with async functions:
- get_json_cache(session, key: str) -> Any | None
- set_json_cache(session, key: str, value: Any, ttl_sec: int | None = None) -> None
- make_cache_key(namespace: str, model: str, text: str) -> str

Add SQLAlchemy model CacheEntry in app/db/models.py:
- key: string primary key
- value_json: JSONB
- created_at
- expires_at nullable

Add setting:
- ENABLE_CACHE: bool = True
- CACHE_TTL_SEC: int = 86400

Use the cache in triage_document() and embedding generation if reasonably easy.
If DB migrations are not present, include a note or helper to create the table.
```

---

# WP-012 — Optimize OCR separately

## Goal

Your reported issue is for 1500-word text analysis, but ingestion/OCR can also be slow because it may call an LLM for OCR synthesis.

Current OCR path:

```text
Tesseract A
Tesseract B
LLM synthesis
```

For large PDFs, this can be expensive.

## Recommended settings

Add:

```python
ENABLE_OCR_LLM_SYNTHESIS: bool = False
MAX_OCR_SYNTHESIS_CHARS: int = 6000
OCR_MAX_PAGES: int = 10
```

Default to no LLM synthesis unless explicitly enabled.

## Acceptance criteria

- OCR works without remote LLM call.
- User can enable OCR synthesis via config.
- Large PDFs do not silently process 80 pages.

## Prompt for coding model

```text
Add OCR performance controls.

In app/core/config.py add:
- ENABLE_OCR_LLM_SYNTHESIS: bool = False
- MAX_OCR_SYNTHESIS_CHARS: int = 6000
- OCR_MAX_PAGES: int = 10

Modify app/services/ocr.py so process_document() only performs LLM OCR synthesis
when ENABLE_OCR_LLM_SYNTHESIS is true. Otherwise combine the two OCR outputs and
normalize locally.

For PDFs, process at most OCR_MAX_PAGES pages unless the setting is 0 or None.
Return a warning in logs if pages were skipped.
```

---

# Recommended final pipeline after WPs 006–008

Internally:

```python
normalization
triage_document()                  # fills issues + questions
retrieve_chunks_combined()
generate_grounded_answer()         # fills claims + sections
verify_claims_against_chunks()     # local
```

Externally, keep SSE stages:

```text
normalization
classification
decomposition
retrieval
construction
verification
generation
final
```

This gives compatibility without forcing seven expensive operations.

---

# Suggested latency budget

Use this as your performance contract:

| Step | Target | Hard max |
|---|---:|---:|
| Normalization | < 1s | 2s |
| Triage LLM | 5–15s | 25s |
| Retrieval | 2–8s | 15s |
| Final grounded answer LLM | 20–60s | 85s |
| Deterministic verification | < 1s | 2s |
| Audit scheduling | < 1s | 2s |
| Total | 30–90s | 120s |

If the final model cannot answer within 85s, fail gracefully with:

```text
The selected model exceeded the latency budget. Try a faster FINAL_MODEL or reduce context.
```

Do not let it drift to 300s.

---

# Practical `.env` starting point

After implementing the config changes, try something like:

```env
PIPELINE_TIMEOUT_SEC=120
REQUEST_TIMEOUT=25
MAX_RETRIES=1

COMBINE_TRIAGE_STAGES=true
COMBINE_FINAL_STAGES=true
RETRIEVAL_MODE=combined

TRIAGE_TIMEOUT_SEC=20
FINAL_TIMEOUT_SEC=75
EMBEDDING_TIMEOUT_SEC=15

TOP_K_RETRIEVAL=6
MAX_COSINE_DISTANCE=0.85

MAX_TRIAGE_INPUT_CHARS=8000
MAX_FINAL_INPUT_CHARS=5000
MAX_CHUNK_CONTEXT_CHARS=7000
MAX_CHUNKS_FOR_FINAL=6

ENABLE_CACHE=true
CACHE_TTL_SEC=86400
```

Also make sure your fallback models are distinct:

```env
PRIMARY_MODEL=...
FALLBACK_MODEL_1=...
FALLBACK_MODEL_2=...
TRIAGE_MODEL=...
FINAL_MODEL=...
```

Do not set `PRIMARY_MODEL` and `FALLBACK_MODEL_1` to the same value.

---

# Suggested implementation order

If you want the shortest path to real improvement:

## Sprint 1

1. WP-001 instrumentation
2. WP-002 timeout/retry/fallback cleanup
3. WP-005 async audit persistence

## Sprint 2

4. WP-006 combined triage
5. WP-004 combined retrieval
6. WP-009 model routing

## Sprint 3

7. WP-007 combined final generation
8. WP-008 deterministic verification
9. WP-010 prompt budgeting

## Sprint 4

10. WP-011 caching
11. WP-012 OCR performance controls

---

# Definition of done

You should consider the optimization work successful when:

1. A 1500-word text completes in under 120 seconds.
2. The typical path uses no more than:
   - 2 chat-completion calls
   - 1 embedding call
   - 1 vector DB retrieval
3. No single LLM call can consume the whole pipeline timeout.
4. The final output still has the six required sections.
5. Claims are tied to evidence quotes.
6. Audit records are still persisted.
7. The benchmark script produces a clear timing report.

The biggest conceptual shift is this:

> Keep the 7-stage product/audit model, but do not implement it as 7 expensive sequential operations.

You can preserve the stage semantics while collapsing the remote calls.
