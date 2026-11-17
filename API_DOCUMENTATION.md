# Citizen API Documentation

Complete reference for the Citizen HTTP API. A developer — human or agentic —
with no prior knowledge of this repository can build a fully functional client
against this document alone.

- **Product:** Citizen — local-first, evidence-constrained legal reasoning
  engine; core plus legal-area modules, German social law (SGB II / SGB X) is
  the default module. Citizen-side self-help and appointment preparation in
  the person's own legal matters only (D-035, DISCLAIMER 3.0.0).
- **Architecture:** single FastAPI service, PostgreSQL 16 + pgvector,
  OpenRouter LLM/embedding backends.
- **Interface:** this REST-ish JSON API is the **only** external network
  interface. There is no web UI, no GUI client in this repository. Since
  core 3.3.0 an optional, read-only MCP server (`python -m app.mcp`, stdio,
  roadmap WP-116, D-066) exposes a subset of the reference data — module
  catalog, deadline catalog, corpus status, statute text, citation check —
  to local MCP clients; it opens no port and is not part of this contract.

---

## 1. Base URLs and deployment

| Environment | Base URL | Notes |
|---|---|---|
| Local dev (uvicorn) | `http://127.0.0.1:8000` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Docker Compose | `http://localhost:8000` | service `citizen-app`; Postgres on `127.0.0.1:5432` |
| Production | behind nginx reverse proxy | proxy timeouts: 300–540 s for SSE endpoints |

All application endpoints are mounted under the `/api/v1` prefix. Two
service-level routes live outside it: `GET /health` and `GET /robots.txt`.

Machine-readable OpenAPI description is served by the app itself:

- `GET /openapi.json`
- `GET /docs` (Swagger UI), `GET /redoc`

## 2. Versioning

- **API version:** path-based (`/api/v1/...`). Breaking changes introduce a new
  prefix (`/api/v2`); v1 remains served during any transition.
- **Application version:** `GET /api/v1/meta/version` →
  `{"api_version": "3.3.0", "disclaimer_version": "v3.0.0", "disclosure_version": "1.0",
  "modules": {"sozialrecht": "1.4.0", …}}`. The package
  version is also embedded in the OpenAPI title and `/health`.
- **Module versions:** each legal-area module is versioned on its own (semver
  in its manifest); `GET /api/v1/modules` and the `modules` key of
  `meta/version` report them. Within `/api/v1` all changes are additive
  (D-039): new keys may appear in responses, existing keys keep their shape.
- **Disclaimer version:** independent of the app version. Clients must fetch it
  via `GET /api/v1/meta/disclaimer/version` and echo it in `X-Disclaimer-Ack`.

## 3. Content types

| Direction | Types |
|---|---|
| Requests | `application/json`; file uploads use `multipart/form-data` |
| Responses | `application/json`; analysis/chat endpoints return `text/event-stream` (SSE); case export optionally `text/markdown`; appointment dossier optionally `application/pdf` (§8.11) |
| Errors | always `application/json`, shape `{"detail": <string or object>}` |

Character encoding is UTF-8 throughout. All timestamps are ISO 8601 strings
(naive UTC as produced by the database, e.g. `2026-08-25T12:00:00`).

## 4. Authentication and authorization model

**There is no user authentication.** Citizen is local-first software: whoever
can reach the network port is trusted. Do not expose an instance to the public
internet without putting your own authentication proxy in front of it.

Instead, three header-based gates protect integrity and compliance posture:

| Header | Applies to | Value | Effect if missing/wrong |
|---|---|---|---|
| `X-Disclaimer-Ack` | every `/api/v1/*` route except `/meta/disclaimer/version` and `/health` | exact value of `GET /api/v1/meta/disclaimer/version` | `403` `{"error": "disclaimer_required" \| "disclaimer_version_mismatch", ...}` |
| `X-Document-Tag` | document uploads (`POST /ingest`, conversation uploads) when `DEPLOYMENT_MODE=dev` | `synthetic` or `goldset` | `403` `{"detail": {"error": "synthetic_data_only", ...}}` |
| *(startup)* | whole instance | when `DEPLOYMENT_MODE=dev`, startup refuses unless `CITIZEN_SYNTHETIC_DATA_ONLY=true` | process exits at boot |

Exempt from `X-Disclaimer-Ack`: `GET /health`, `GET /robots.txt`,
`GET /api/v1/meta/disclaimer/version`. Everything else under `/api/v1`
requires it.

`GET /robots.txt` returns `User-agent: *\nDisallow: /\n` on dev instances,
`Allow: /` otherwise. Responses additionally carry no-index headers
(`X-Robots-Tag`) on dev instances.

## 5. Conventions

### 5.1 Error format

All errors are JSON. FastAPI validation failures use the framework's native
shape; application errors use `HTTPException` with a string or structured
`detail`.

```json
// Validation error (422)
{"detail": [{"loc": ["body", "text"], "msg": "...", "type": "..."}]}

// Application error — simple form (400/403/404/409/415/500)
{"detail": "Case not found"}

// Application error — structured form (used by analyze/corpus/guards/modules)
{"detail": {"error": "corpus_not_ready", "message": "...", "areas": {...}}}
{"detail": {"error": "MODULE_NOT_ENABLED", "message": "...", "legal_areas": ["mietrecht"], "action": "..."}}
```

The disclaimer middleware uses a bare object (not wrapped in `"detail"`):

```json
{"error": "disclaimer_version_mismatch",
 "required_version": "v3.0.0",
 "acknowledged_version": "v9.9.9"}
```

### 5.2 Error code catalog

| HTTP | Where | Meaning |
|---|---|---|
| 400 | ingest, analyze, cases, intake, documents, presets, ocr | missing/empty field, oversized file (> `MAX_FILE_SIZE_MB`, default 25 MB), OCR failure, invalid UUID string, empty text |
| 403 | all `/api/v1` (middleware) | missing/mismatched `X-Disclaimer-Ack` |
| 403 | upload routes on dev instances | missing/invalid `X-Document-Tag` (`synthetic_data_only`) |
| 404 | cases, conversations, corpus jobs, goldset, intake, eval reports | unknown resource id |
| 400 | `PUT /cases/{case_id}/dossier/chronology` | `invalid_chronology_update` — unknown entry id, bad status/date, unknown or invalid fact |
| 404 | `GET /cases/{case_id}/dossier` | `dossier_not_built` — the case exists but no dossier was built yet |
| 404 | `/modules/{module_id}*` | `MODULE_UNKNOWN` — no installed module has this id; `goldset_not_declared` — the module ships no goldset; `erratum_unknown` — the module declares no erratum with this id |
| 409 | `POST /analyze` | `corpus_not_ready` — a selected legal area has no corpus chunks |
| 409 | intake `message` | interview turn limit reached |
| 415 | `POST /ingest` | unsupported MIME type (allowed: PDF, JPG, PNG, TXT, HTML, EML) |
| 422 | `POST /analyze` | `MODULE_UNKNOWN` — a `legal_areas` value no installed module (or the core procedural library) serves |
| 422 | `POST /analyze` | `MODULE_NOT_ENABLED` — a `legal_areas` value whose module is installed but not enabled in this deployment (`enabled: false` in `GET /modules`) |
| 422 | everywhere | FastAPI request-validation failure (`detail` is a list, not an object) |
| 500 | anywhere | unrecoverable internal error; detail string present |

SSE streams signal errors **inside the stream** as a final
`data: {"error": "...", ...}` event (see §7) — the HTTP status stays 200 once
streaming has begun.

### 5.3 Pagination

There is **no pagination**. List endpoints return bounded result sets
(cases: most recent 100 completed; conversations: recent list; eval reports:
all files in the results directory). Clients should not expect cursor/page
parameters.

### 5.4 Rate limits

**No application-level rate limiting is active.** A token-bucket middleware
(`app/middleware/rate_limit.py`, settings `RATE_LIMIT_REQUESTS` /
`RATE_LIMIT_WINDOW`) exists but is not mounted. Deployments behind nginx may
impose their own limits there. Agentic clients should self-throttle:
LLM-backed endpoints run multi-second to multi-minute workloads.

### 5.5 Long-polling and webhooks

None. The only asynchronous operation is corpus update, which uses
request-then-poll against an in-memory job store (§8.4). There are no
webhooks.

---

## 6. Service-level endpoints

### 6.1 `GET /health`

Liveness probe (used by Docker healthcheck). No disclaimer header needed.

```json
// 200
{"status": "ok", "version": "v2.0.0"}
```

### 6.2 `GET /robots.txt`

Returns `text/plain` robots policy (Disallow on dev instances).

---

## 7. Analysis pipeline

### 7.1 `POST /api/v1/analyze`

Run the full evidence-constrained analysis pipeline on a document text.
Response is a **Server-Sent Events stream** (`text/event-stream`).

**Request**

```json
{"text": "<document text>",
 "legal_areas": ["sozialrecht"],
 "intake_session_id": null}
```

- `text` (required, non-empty): the normalized input document.
- `legal_areas` (optional): JSON array or comma-separated string (the array
  form is accepted since WP-95; before, only the string form passed request
  validation). Values drawn from
  the area keys of the installed modules (e.g. `sozialrecht`, `erbrecht`,
  `schenkungsrecht`, `familienrecht`, `andere`; since WP-94 the key set is
  module data, no longer a DB enum — the stored case records each key's
  module id and module version). Triggers per-area retrieval and area-specific
  prompts.
  Each value resolves to the module that owns it (legacy key
  `schenkungsrecht` → module `erbrecht`, `verwaltungsrecht` → core procedural
  library; empty → the default module `sozialrecht`). The `calculation_check`
  stage and the legal-regime banner run the **resolved modules'** calculators
  and regime providers: only `sozialrecht` ships them (since WP-93). A request
  whose areas resolve to no such module gets `calculation_check` with an empty
  `calculations_found` and a summary stating that no deterministic calculation
  check is available (previously the SGB II check ran for every area). Payload
  shape unchanged.
  Every value is validated before anything runs (WP-95): unknown →
  `422 MODULE_UNKNOWN`, module installed but not enabled →
  `422 MODULE_NOT_ENABLED` (see §5.2; `GET /api/v1/modules` lists ids and
  enablement). Since WP-95 an unknown value no longer surfaces as
  `409 corpus_not_ready`.
- `intake_session_id` (optional): UUID linking a preceding intake interview.

**Event stream** — each event is a line pair `data: {json}\n\n`:

| `stage` | `status` | payload highlights |
|---|---|---|
| `corpus_health` | `ok` \| `warning` | `total_chunks`, `total_sources`, `warnings[]` |
| `ocr_quality` | `info` | OCR quality report of the input |
| `normalization` | `running` → `complete` | `text_length`, `duration_ms` |
| `classification` | `running` → `complete` | detected issues |
| `decomposition` | `running` → `complete` | generated questions; `legal_regime` `{regimes, as_of, end, source}` when a module ships a regime provider (prompt set 3.0.0: the reference date comes from the document — benefit period or letter date — and `source` says which, or that today's date was used) |
| `retrieval` | `running` → `complete` | retrieved chunk metadata |
| `construction` | `running` → `complete` | claims with confidence scores; streaming tokens appear as separate stream events |
| `verification` | `running` → `complete` | verified claims incl. `evidence_chunk_id`, `evidence_quote` |
| `generation` | `running` → `complete` | `final_output` sections |
| `adversarial_review` | `running` → `complete` | counter-analysis: `review_count`, `key_risks` (populated since prompt set 3.0.0 — before, the review output was discarded and both were always empty; shape unchanged) |
| `calculation_check` | `running` → `complete` | arithmetic verification |
| *(all LLM stages)* | `complete` | `prompts[]` (prompt set 3.0.0, additive): `{id, version, sha256}` of each system prompt the stage sent — `classification`/`decomposition`, `construction`, `verification`, `adversarial_review`, `calculation_check`; recorded in the stage audit log (`stages[].output_snapshot`) |
| *(final)* | — | `{"session_id", "sections": [...], "final_output": {...}, "case_run_id": "<uuid>", "disclosure": {...}, "provenance": {...}, "resolved_modules": [...]}` — `resolved_modules` only when the request carried a non-empty `legal_areas` |

The final summary event embeds two Art. 50 (VO (EU) 2024/1689) objects:
`disclosure` (`{version, must_display_before: "results", texts: {de, en}}`) —
the consuming client MUST display `texts[lang]` to the natural person before
presenting any AI-generated result — and `provenance`
(`{spec_version: "citizen-provenance-v1.1", generator: "citizen", app_version,
model_profile, timestamp_utc, deployment_mode, modules}`). Both are always
present; error events carry neither.

**Provenance spec `citizen-provenance-v1.1`** (WP-96, D-059; additive to
v1.0 — the six v1.0 fields are unchanged, `spec_version` reads `-v1.1`):
`modules` lists the legal-area modules that produced the content, in request
order, each `{id, version, parameter_set}`:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | module id (a legacy alias such as `schenkungsrecht` names its owning module `erbrecht`) |
| `version` | string | module semver at generation time |
| `parameter_set` | string \| null | pinned legal-parameter set: `"<module version>+<latest valid_from>"`, e.g. `"1.2.0+2026-01-01"`; `null` for a module without parameters |

Resolution follows the engines: no/empty `legal_areas` → `[DEFAULT_MODULE]`;
keys served by the core procedural library (`verwaltungsrecht`) add no
module, so a procedural-only request yields `[]`. If a field cannot be
determined it reads `"unknown"` (never an error); if the modules cannot be
resolved at all, the list is `[{"id": "unknown", "version": "unknown",
"parameter_set": "unknown"}]`. Every surface that carries `provenance` uses
this same shape (§7.2, §8.5, §8.6).

`resolved_modules` (WP-95) has one entry per requested `legal_areas` value,
in request order:

```json
[{"legal_area": "schenkungsrecht", "module_id": "erbrecht", "module_version": "0.2.0",
  "legacy_alias": true, "enabled": true},
 {"legal_area": "verwaltungsrecht", "module_id": null, "module_version": null,
  "legacy_alias": false, "enabled": true}]
```

`module_id: null` marks a key served by the core procedural library (no
module). The same entry shape appears on intake and preset responses (§8.2,
§8.8), where `enabled: false` warns that `/analyze` would answer
`422 MODULE_NOT_ENABLED` for that key.

Terminal error event instead of the summary:

```json
{"error": "pipeline_failed", "detail": "...", "session_id": "..."}
```

**Example**

```
POST /api/v1/analyze
X-Disclaimer-Ack: v3.0.0
Content-Type: application/json

{"text": "Bescheid vom Jobcenter ... Kürzung ... § 31 SGB II ..."}
```

```
data: {"stage":"normalization","status":"complete","payload":{"text_length":722,"duration_ms":0}}

data: {"stage":"classification","status":"complete","payload":{"issues":["SGB II § 31"]}}

data: {"stage":"generation","status":"complete","payload":{"final_output":{"sachverhalt":"...","ergebnis":"..."}}}

data: {"session_id":"…","sections":["sachverhalt","…"],"final_output":{…},"case_run_id":"…","disclosure":{"version":"1.0",…},"provenance":{"spec_version":"citizen-provenance-v1.1",…,"modules":[{"id":"sozialrecht","version":"1.2.0","parameter_set":"1.2.0+2026-01-01"}]}}
```

**Errors before streaming starts:** `400` (missing/empty `text`),
`404` (unknown `intake_session_id`), `422` `MODULE_UNKNOWN` /
`MODULE_NOT_ENABLED` (structured body, §5.1), `409` structured body:

```json
{"detail": {"error": "corpus_not_ready", "legal_areas": ["erbrecht"],
            "missing_source_types": ["bgb"], "action": "POST /api/v1/corpus/update …"}}
```

**Timeout chain (D-017):** nginx proxy ≤ 540 s > pipeline budget
(`PIPELINE_TIMEOUT_SEC`, default 480 s) > sum of per-call stage timeouts
(435 s). Clients should keep the connection open up to ~8 minutes.

### 7.2 Case Chat — `POST /api/v1/cases/{case_id}/chat`

SSE chat grounded in a completed case run. Body `{"content": "..."}`.
Events: streaming token events then
`data: {"type": "done", "case_id": "...", "full_response": "...", "disclosure": {...}, "provenance": {...}}`
— the two Art. 50 objects as in §7.1 (added by WP-96, D-059; additive).
`provenance.modules` names the modules of the case's recorded `legal_areas`
(none recorded → `DEFAULT_MODULE`). Error events
`{"error": "case_chat_failed" | "service_unavailable"}` carry neither object.
The user message and assistant reply are persisted into the case's
`chat_history`.

### 7.3 Targeted re-evaluation — `POST /api/v1/cases/{case_id}/reevaluate`

Re-run one pipeline stage for an existing case. Body
`{"stage": "<stage name>", "context": "free-text hint"}`. SSE response;
records the re-evaluation in the case's `user_edits`.

---

## 8. Reference data: endpoint catalog

Every route requires `X-Disclaimer-Ack` unless noted. Path parameters are
UUIDs unless stated otherwise.

### 8.1 Ingestion & OCR

#### `POST /api/v1/ingest`

multipart/form-data: `file` (required) — PDF/JPG/PNG/TXT/HTML/EML.
Headers: `X-Disclaimer-Ack`, plus `X-Document-Tag` on dev instances.

```json
// 200
{"text": "normalized UTF-8 content of the document"}
```

Errors: `400` (too large / OCR failed), `403` (guards), `415` (bad MIME).

#### `GET /api/v1/ocr/assess?text=<url-encoded text>`

Assesses extracted-text quality.

```json
// 200
{"score": 0.82, "level": "good", "issues": [], "warnings": [],
 "ocr_artifacts_detected": false, "readable_words_pct": 91.2,
 "language_detected": "de", "recommendations": []}
```

Errors: `400` (empty or >100 000 chars).

### 8.2 Intake interviews

Multi-turn pre-analysis interview. State machine: active → done.

#### `POST /api/v1/intake/start`

```json
// request
{"session_id": "optional-client-id", "initial_text": "Bescheid erhalten…", "max_turns": 8}
```

max_turns must be 2–12. Returns the created session (see GET below):
`{"id", "session_id", "state": "active", "turn_count": 0, "messages": [...],
"question": "<first LLM question>"}`. Errors: `400`.

#### `POST /api/v1/intake/{intake_id}/message`

Body `{"message": "..."}` → updated session state; when the LLM decides the
interview is complete, state becomes `done` and the payload carries the
extracted `intake_result`. Errors: `400`, `409` (turn limit).

Every intake session response (start, message, get, restart, confirm) also
carries `resolved_modules` (WP-95; entry shape in §7.1) for the determined
`primary_area` and `secondary_areas` — `[]` while no area is determined.

#### `GET /api/v1/intake/{intake_id}` — current session or `404`.
#### `POST /api/v1/intake/{intake_id}/restart` — abandon & reset.
#### `POST /api/v1/intake/{intake_id}/confirm` — force-finalise, returns `IntakeResult`:

```json
{"legal_areas": ["sozialrecht"], "summary": "...",
 "key_facts": {...}, "open_questions": []}
```

### 8.3 Cases (analysis results)

#### `GET /api/v1/cases`

Most recent 100 completed case runs.

```json
[{"id": "<uuid>", "session_id": "<uuid>", "title": "...", "status": "completed",
  "created_at": "...", "updated_at": "...", "input_preview": "first 100 chars...",
  "legal_areas": [{"legal_area": "sozialrecht", "is_primary": true}]}]
```

#### `GET /api/v1/cases/{case_id}`

Full case: adds `input_text`, `final_output` (merged generation +
`adversarial_*` + `calculation_*` keys), `stages[]` (audit log entries),
`claims[]` each with `evidence_bindings[]` (`chunk_id`, `quote_excerpt`,
`binding_strength`), `chat_history`, `user_edits`. `404` if unknown.
Since core 3.2.0 the `calculation_check` stage's `output_snapshot` also holds
`result` (the module calculators' full result, without `legal_snapshot`) for
cases analysed from then on; it feeds the dossier (§8.11) and is not copied
into `final_output`, whose keys are unchanged. `user_edits.dossier` holds the
dossier confirmation state (§8.11).

#### `DELETE /api/v1/cases/{case_id}` → `{"status": "deleted", "id": "..."}`, `404` if unknown.

#### `POST /api/v1/cases/{case_id}/claims`

Body `{"claim_text": "...", "confidence_score": 0.8, "claim_type": "fact"}`.
Returns the created claim object. `claim_text` non-empty required; `400`
otherwise; `404` unknown case.

#### `PATCH /api/v1/cases/{case_id}/claims/{claim_id}`

Body: any of `{"claim_text", "confidence_score"}`. Returns the updated claim;
records the edit in `user_edits.edited_claims`. `404` unknown.

#### `POST /api/v1/cases/{case_id}/adjudicate`

```json
{"target_type": "claim", "target_id": "<claim uuid>", "status": "agreed", "note": "..."}
```

`target_type` ∈ {`claim`,`section`}; `status` ∈ {`agreed`,`disputed`}.
For sections, `target_id` is the section key (e.g. `ergebnis`). Returns the
adjudicated object; records in `user_edits.section_adjudications` for
sections. Errors: `400`, `404`.

#### `GET /api/v1/cases/{case_id}/export?format=json|markdown`

Downloads the full case. `format=json` (default) → `application/json`
attachment; `format=markdown` → `text/markdown` attachment with German
headings (Eingabetext, Ergebnisse, Ansprüche/Claims).
Header `Content-Disposition: attachment; filename="case_...".json|.md`.

### 8.4 Corpus management

Legal source ingestion (scrape → chunk → embed → upsert) runs as background
jobs with polling status. The job store is **in-memory**: after a restart old
job ids are gone (`404`).

#### `POST /api/v1/corpus/update` → `202`

Optional body `{"sources": ["sgb2", "sgbx", "weisung", "bsg", "bgb"]}`
(one-shot override; persisted selection unaffected). Unknown keys are ignored.

```json
// 202
{"job_id": "<uuid>", "status": "queued"}
```

#### `GET /api/v1/corpus/status/{job_id}`

```json
{"job_id": "...", "status": "queued|running|completed|failed",
 "substage": "scraping|embedding|null",
 "chunks_scraped": 120, "chunks_processed": 80, "chunks_embedded": 64,
 "chunks_upserted": 48}
```

Poll recommendation: every 2–5 s until `completed`/`failed`. Full corpus runs
take up to 30 min (`CORPUS_INGESTION_TIMEOUT_SEC`). `404` unknown job.

#### `GET /api/v1/corpus/health`

```json
{"total_chunks": 8631, "total_sources": 4, "is_healthy": true,
 "sources": [{"type": "sgb2", "chunk_count": 5120, "last_updated": "..."}],
 "warnings": ["Konfigurierte Quellen nicht im Corpus: bgb."]}
```

#### `GET /api/v1/corpus/available-sources`

Catalog of known sources with metadata:
`[{key, name, description, tooltip, has_scraper, recommended, active}]`.

#### `GET /api/v1/corpus/sources` → `{"sources": [...], "is_runtime_override": bool}`
#### `PUT /api/v1/corpus/sources` — persist selection. Body `{"sources": [...]}` → same shape as GET.

### 8.5 Conversations (chat-first workflow)

Conversations bundle chat messages with attached documents. If the **first**
user message follows document attachment, the full analysis pipeline executes
and its result becomes the assistant message; later messages use RAG chat.

#### `POST /api/v1/conversations` — multipart/form-data: optional `title`, optional `file`
Returns conversation detail (below). Upload errors → `400`; dev-tag guard → `403`.

#### `GET /api/v1/conversations` — list of summaries:
```json
[{"id": "...", "title": "...", "created_at": "...", "updated_at": "...",
  "message_count": 3, "document_count": 1}]
```

#### `GET /api/v1/conversations/{conversation_id}` — detail incl. `messages[]` and `documents[]`. `404` if unknown.

#### `DELETE /api/v1/conversations/{conversation_id}` → `{"status": "deleted", "id": "..."}`

#### `POST /api/v1/conversations/{conversation_id}/messages` — body `{"content": "...", "legal_areas": ["<area key>", ...]}`

`legal_areas` is optional (prompt set 3.0.0, additive): it selects the
module profile of the chat persona, the areas of a first-message pipeline
run and the modules named in `provenance.modules`. Validated like
`/analyze`: `422` `MODULE_UNKNOWN` / `MODULE_NOT_ENABLED` (same detail
shape), `400` when it is not a list of strings.

SSE response (`text/event-stream`). First-message-with-documents mode emits
pipeline stage events plus a final summary
`{"sections": [...], "final_output": {...}, "disclosure": {...}, "provenance": {...}}`
(the two Art. 50 objects added by WP-96, D-059; additive); otherwise chat/RAG
token events ending with
`{"type": "done", "full_response": "...", "disclosure": {...}, "provenance": {...}}`
(the two Art. 50 objects as in §7.1). Without `legal_areas`,
`provenance.modules` is `[DEFAULT_MODULE]` on both terminal events. Error event:
`{"error": "message_generation_failed", ...}`. `400` empty content, `404`
unknown conversation.

#### `POST /api/v1/conversations/{conversation_id}/documents` — multipart `file`
Processes and attaches a document; returns the document record
(`{"id", "original_filename", "created_at", ...}`). Dev-tag guard applies.

#### `GET /api/v1/conversations/{conversation_id}/documents` — list attached documents.

#### `DELETE /api/v1/conversations/{conversation_id}/documents/{document_id}` → `{"status": "deleted", "id": "..."}`; `404` unknown.

### 8.6 Documents (Widerspruch / Antrag generators)

#### `GET /api/v1/documents/generator-options/{case_run_id}`

Returns the generator options derived from a completed case: available
document types, deadline (Frist) information, reconciliation lines, and
user-data slots. `404` unknown case_run.

#### `POST /api/v1/documents/generate`

```json
{"case_run_id": "<uuid>",
 "doc_type": "widerspruch",            // optional; auto-selected if omitted
 "user_data": {"name": "...", "adresse": "..."}}
```

`doc_type` ∈ {`widerspruch`, `widerspruch_jahresfrist`, `ueberpruefungsantrag_44`,
`akteneinsichtsantrag_25`}. Returns a `GeneratedDocument`:

```json
{"doc_type": "widerspruch", "title": "Widerspruch gegen den Bescheid …",
 "rendered_text": "# Widerspruch\n\nSehr geehrte Damen und Herren, …",
 "slots": [{"key": "anspruch_hoehe", "value": "...", "verified": true,
            "needs_review": false}],
 "generation_metadata": {"selected_by": "auto", "frist_am": "2026-09-14"},
 "provenance": {"spec_version": "citizen-provenance-v1.1", "generator": "citizen",
                "app_version": "3.1.0", "model_profile": "eu-avv",
                "timestamp_utc": "2026-08-07T14:23:00Z", "deployment_mode": "dev",
                "modules": [{"id": "sozialrecht", "version": "1.2.0",
                             "parameter_set": "1.2.0+2026-01-01"}]}}
```

`provenance` is the Art. 50(2) machine-readable marker (§7.1); its `modules`
names the module whose template rendered the draft. There is no
`disclosure` field on documents: the disclosure was already delivered with
the analysis result that preceded generation.

Unverified values render as `[BITTE PRÜFEN: …]` inside `rendered_text`.
Errors: `400` (missing/invalid `case_run_id`, unknown `doc_type`), `404`.

### 8.7 Goldsets & evaluation (Prüfstand)

#### `GET /api/v1/goldset` — manifest + summarized case list (no document texts). Serves the goldset at `GOLDSET_PATH` (default: Sozialrecht v0.1.0) and stays the Sozialrecht alias until `/api/v2`; module goldsets: `GET /api/v1/modules/{module_id}/goldset` (§8.10).
#### `GET /api/v1/goldset/{case_id}` — full case incl. input document text, expected findings, citations, calculation, traps. `404` unknown id.
#### `POST /api/v1/goldset/{case_id}/analyze` — SSE stream, identical contract to `POST /api/v1/analyze`, using the goldset case's stored input text. Nothing is persisted (no CaseRun).

#### `GET /api/v1/eval/reports`

```json
{"reports": [{"report_id": "run-2026-08-25", "goldset_version": "0.2.0",
              "git_sha": "...", "run_timestamp": "...", "case_count": 10,
              "aggregate": {"issue_recall": 0.9, "citation_precision": 0.95}}]}
```

Reads `*.json` from the configured eval results directory; empty list if absent.

#### `GET /api/v1/eval/reports/{report_id}` — full report (per-case metrics:
issue_recall, citation_precision, calculation_exact_match, frist_exact_match,
assessment_match, quote_verification_rate, latency_ms, errors).
`report_id` is the filename stem restricted to `[A-Za-z0-9_-]`; `400` on other
characters, `404` unknown, `500` corrupt file.

### 8.8 Presets

#### `GET /api/v1/presets` — list of case-type presets:
```json
[{"id": "jobcenter-kuerzung", "name": "Jobcenter – Kürzung",
  "legal_areas": ["sozialrecht"], "description": "..."}]
```
#### `GET /api/v1/presets/{preset_id}` — single preset; `404` unknown.
#### `POST /api/v1/presets/suggest` — body `{"text": "<case description>"}` →
`{"preset_id": "...", "primary_area": "sozialrecht", "secondary_areas": [], "match": "llm", "resolved_modules": [...]}`
(LLM-assisted with deterministic fallback). `match` (prompt set 3.0.0,
additive) says which path produced the suggestion: `"llm"`, or
`"keyword_fallback"` when the model named no catalogue preset (it may
answer "no match"), failed, or returned unparseable output. `400` empty text.
#### `POST /api/v1/presets/apply` — body
`{"preset_id": "...", "session_id": "...", "initial_text": "..."}` →
`{"preset_id", "preset_name", "legal_areas", "primary_area", "enriched_text", "resolved_modules"}`.
`400` missing preset_id; `404` unknown preset. `resolved_modules` (WP-95,
shape in §7.1) covers the preset's `legal_areas` (or the primary area when
the preset lists none).

### 8.9 Meta

All meta endpoints except `meta/disclaimer/version` require the disclaimer
header.

| Endpoint | Response |
|---|---|
| `GET /api/v1/meta/disclaimer/version` *(no ack needed)* | `{"version": "v3.0.0"}` — `"v"` + version of `DISCLAIMER_DE.md`/`DISCLAIMER_EN.md` (3.0.0 since WP-96; was `v0.1.0`). A bump requires every client to re-acknowledge |
| `GET /api/v1/meta/disclaimer/text` | `{"text": "<HTML disclaimer>", "version": "v3.0.0"}` |
| `GET /api/v1/meta/disclosure` | `{"version": "1.0", "must_display_before": "results", "texts": {"de": "Diese Analyse wurde von einem KI-System erstellt …", "en": "This analysis was produced by an AI system …"}}` — Art. 50(1) notification; cacheable, does not vary by deployment mode |
| `GET /api/v1/meta/version` | `{"api_version": "3.1.0", "disclaimer_version": "v3.0.0", "disclosure_version": "1.0", "modules": {"andere": "0.1.1", …, "sozialrecht": "1.2.0"}}` — `modules` (WP-95) maps every **enabled** module id to its version, sorted by id |
| `GET /api/v1/meta/legal-timestamp` | `{"parameter_freshness": "2026-07-01", "corpus_freshness": "2026-08-01"}` (either may be `null`) |
| `GET /api/v1/meta/active-profile` | `{"profile": "eu-avv", "label": "...", "avv_status": "...", "pseudonymization": true}` |
| `GET /api/v1/meta/deployment-mode` | `{"mode": "dev", "synthetic_data_only": true, "dev": true, "dev_banner": "…" \| null}` |

### 8.10 Modules (legal-area catalog)

Read-only catalog of the installed legal-area modules (WP-95). Module data
comes from the filesystem and is always served; the database-backed fields
`corpus` and `installed_at` are `null` when the database is unreachable.
Enablement follows `ENABLED_MODULES`, else the tier rule of the deployment
mode (`dev`/`self`: `experimental` + `verified`; `provider`: `verified` only).

#### `GET /api/v1/modules`

```json
{"default_module": "sozialrecht",
 "modules": [
   {"id": "sozialrecht", "version": "1.4.0", "tier": "verified",
    "enabled": true, "is_default": true,
    "origin": "in_tree", "declared_tier": "verified",
    "title": {"de": "Sozialrecht", "en": "Social-benefits law"},
    "area_keys": ["sozialrecht"],
    "corpus": {"chunk_count": 1234, "source_types": ["sgb2", "sgbx", "…"],
               "present_source_types": ["sgb2", "…"], "missing_source_types": [],
               "is_ready": true},
    "installed_at": "2026-11-16T10:00:00+00:00"}]}
```

- Order: modules in the order of the area keys they own (default module
  first today).
- `area_keys`: the `legal_areas` values this module serves (its id plus
  legacy aliases, e.g. `erbrecht` → `["erbrecht", "schenkungsrecht"]`).
- `corpus`: readiness over the union of the area keys' corpus source types —
  same semantics as the `/analyze` pre-flight (`is_ready` is `false` when the
  module expects no source type, e.g. the catch-all).
- `installed_at`: when the running manifest was first synced into the
  database; `null` when no synced row describes the running manifest.
- `origin` (core 3.3.0, WP-112): `in_tree` — shipped and reviewed with the
  core; `entry_point` — an installed package registered in the
  `citizen.modules` entry-point group. Out-of-tree modules are served at
  `tier: "community"` whatever their manifest says (`declared_tier` keeps the
  manifest's value) and are enabled only when `ENABLED_MODULES` lists them.

#### `GET /api/v1/modules/{module_id}`

The summary fields above plus the public manifest parts:

```json
{"id": "sozialrecht", "…": "…",
 "core_api": ">=3.0,<4.0",
 "scope": {"summary_de": "…", "own_matter_only": true, "out_of_scope": ["…"]},
 "legacy_aliases": [],
 "capabilities": {"deadlines": true, "calculators": true, "regime_provider": true,
                  "document_templates": true, "goldset": true, "dossier": true},
 "parameter_domain": "sozialrecht",
 "deadlines": [{"id": "widerspruch_sgg_84", "label_de": "Widerspruchsfrist",
                "trigger": "bekanntgabe", "duration": {"days": 0, "months": 1, "years": 0},
                "basis": "§ 84 Abs. 1 SGG", "fristbeginn_basis": "…",
                "bekanntgabe_fiction": "sgbx_37_2", "rollover": "sgg_64_3",
                "missing_rechtsbehelfsbelehrung": {"duration": {"days": 0, "months": 0, "years": 1},
                                                   "basis": "§ 66 Abs. 2 SGG"},
                "severity": "critical", "applies_when": {"document_type": "verwaltungsakt"}}],
 "document_types": [{"id": "widerspruch", "title": "Widerspruch"}],
 "dossier_checklist": {"format": "citizen-module-dossier-v1.0",
                       "checklist": [{"id": "bescheid_vollstaendig", "label_de": "…",
                                      "why_de": "…", "topic": "kernunterlagen",
                                      "required": true}],
                       "questions": [{"id": "frist_bestaetigen", "text_de": "…",
                                      "topic": "fristen"}]},
 "compliance": null,
 "errata": [{"id": "E-2026-001", "published": "2026-11-17",
             "affected_versions": ">=1.0.0,<1.3.0", "fixed_in": "1.3.0",
             "core_versions": ">=3.0.0,<3.2.0", "severity": "critical",
             "component": "deadline", "summary_de": "…", "summary_en": "…",
             "action_de": "…", "action_en": "…", "references": ["DECISIONS.md D-065"]}],
 "updates": [{"serial": 1, "issued_at": "2027-01-15T09:00:00+00:00",
              "applied_at": "2027-01-16T07:12:03+00:00", "key_id": "0123456789abcdef",
              "module_version": "1.4.0",
              "parameters": [{"key": "…", "valid_from": "2027-01-01",
                              "erratum": null, "action": "created"}],
              "corpus_notices": [{"source_type": "sgb2", "summary_de": "…"}]}],
 "parameter_set": "1.4.0+2027-01-01.u1"}
```

File paths and code references of the manifest are not served (only the
`capabilities` flags). `dossier_checklist` is the module's `dossier.yaml`
content — every checklist item and question, each with an optional
`when: {"any_keyword": [...]}` selection rule (§8.11) — or `null` for a module
without dossier data. `compliance` is `null` unless the manifest
declares one (`special_regimes`, `referral`).

Added in core 3.3.0 (P11):

- `errata` (WP-110): the module's published corrections, oldest first —
  `[]` when it declares none. `affected_versions` is a module version range
  (comma-separated comparators); a stored case is affected when the module
  version recorded for it (`case_run_area.module_version`) lies in the range.
  `core_versions` (optional) names the core versions when the defect sat in
  the core. List the affected cases with the route below.
- `updates` (WP-111): signed update feeds applied to this deployment, newest
  first (`[]` none; `null` when the database is unreachable). Each lists the
  parameter identities it wrote (`action`: `created`, `updated`,
  `unchanged`) and its corpus change notices.
- `parameter_set`: the module's current parameter-set id, as in provenance
  `modules[].parameter_set` — `<version>+<newest valid_from>`, with
  `.u<serial>` appended once update feeds were applied; `null` for a module
  without parameters. `404` `MODULE_UNKNOWN` for an
id that is not installed; disabled modules are served (with
`"enabled": false`).

#### `GET /api/v1/modules/{module_id}/goldset`

The goldset declared by the module manifest, same `goldset`/`cases` shape as
`GET /api/v1/goldset`, plus the module and its evaluation gate:

```json
{"module_id": "sozialrecht", "module_version": "1.4.0",
 "gate": {"rule": "zero_regression", "baseline_report": "eval/results/….json"},
 "goldset": {"id": "…", "version": "0.2.0", "…": "…"},
 "cases": [{"id": "GS-001", "…": "…"}]}
```

May serve a newer goldset version than `/api/v1/goldset` (which follows
`GOLDSET_PATH`). `404` `MODULE_UNKNOWN`, `404` `goldset_not_declared`, `500`
unreadable goldset file.

#### `GET /api/v1/modules/{module_id}/errata/{erratum_id}/cases`

Stored cases that ran with a module version the erratum affects (core 3.3.0,
WP-110), oldest first, one entry per (case, area key):

```json
{"module_id": "sozialrecht", "module_version": "1.4.0",
 "erratum": {"id": "E-2026-001", "affected_versions": ">=1.0.0,<1.3.0", "…": "…"},
 "count": 1,
 "cases": [{"case_id": "…", "legal_area": "sozialrecht", "module_version": "1.2.0",
            "created_at": "2026-11-10T08:00:00+00:00", "title": "…"}]}
```

Matching is semver on the recorded `module_version`; cases stored before
core 3.0.0 recorded no module version and never match. Whether a matched
case is actually affected depends on the erratum's `summary_de`/`action_de`
(e.g. only letters posted before a date). `404` `MODULE_UNKNOWN`, `404`
`erratum_unknown`.

### 8.11 Appointment dossier (Mandatsvorbereitung, roadmap P10)

The dossier is what the person takes to an appointment with an advice
centre or a lawyer: a chronology of the facts, a checklist of documents to
bring, the deadline banner, deterministic calculation results, the
analysis' statements with verified quotes, questions for the appointment,
and an action draft as annex. JSON validates against the JSON Schema
`citizen-dossier-v1.0` (`app/dossier/citizen-dossier-v1.0.schema.json`); the
PDF is rendered locally from the same JSON and embeds it.

**Where the content comes from.** Deadlines come only from the Fristen core
evaluating the case modules' deadline specs — never from model output.
The chronology is a deterministic date extraction from the analysed text and
the documents attached to the case (conversation uploads with this
`case_run_id`), confirmed by the person. Checklist and questions are module
data (`dossier.yaml`, selected by keyword). Calculations are the module
calculators' engine fields only (no model commentary). `evidence` (claims)
and `drafts` are AI-derived; the dossier therefore carries `disclosure` and
`provenance` (`citizen-provenance-v1.1`) like every AI-output surface.

#### `GET /api/v1/cases/{case_id}/dossier/chronology`

Every chronology proposal with the person's current decision, plus the
confirmed facts:

```json
{"case_id": "<uuid>",
 "entries": [{"entry_id": "chr-1a2b3c4d5e6f", "date": "2026-07-06",
              "kind": "document_date", "label_de": "Datum des Schreibens",
              "status": "proposed",
              "source": {"document": "case_input", "label": "Analysierter Text",
                         "line": 2, "excerpt": "Essen, 06.07.2026"},
              "module_id": null, "note": null}],
 "facts": {}}
```

`status` ∈ {`proposed`, `confirmed`, `rejected`, `user_added`}; a corrected
entry also carries `original_date`. `kind`: core kinds `document_date`,
`period_start`, `period_end`, `mentioned`, `user_event`, plus module cue
kinds (Sozialrecht e.g. `antrag`, `termin`, `zugang`). `source.document` is
`case_input` or `conversation_document:<uuid>`. Entry ids are stable while
the source text is unchanged. `404` unknown case.

#### `PUT /api/v1/cases/{case_id}/dossier/chronology`

Replaces the whole confirmation state (send everything you want kept):

```json
{"entries": [{"entry_id": "chr-1a2b3c4d5e6f", "status": "confirmed"},
             {"entry_id": "chr-…", "status": "confirmed", "date": "2026-07-07",
              "label_de": "…", "note": "…"},
             {"entry_id": "chr-…", "status": "rejected"}],
 "added": [{"date": "2026-07-10", "label_de": "Brief erhalten", "kind": "zugang",
            "note": "optional"}],
 "facts": {"bescheid_datum": "2026-07-06", "aufgabe_zur_post": "2026-07-06",
           "bekanntgabe_tatsaechlich": null, "rbb_status": "korrekt",
           "ist_verwaltungsakt": true, "bundesland": "NW"}}
```

All keys optional. `rbb_status` ∈ {`korrekt`, `fehlerhaft`, `fehlt`};
`bundesland` is a two-letter Land code (`NW`, `BY`, …). Returns the same shape
as the GET. Stored in `case_run.user_edits.dossier`; other `user_edits` keys
are kept. `400` `invalid_chronology_update`, `404` unknown case.

**Deadline inputs.** `facts.bescheid_datum` wins; otherwise the confirmed
`document_date` entry gives a `computed` deadline, an unconfirmed one only a
`provisional` deadline, none at all `missing_input`. Unset facts take the
conservative reading and are listed per deadline in `assumptions`
(Rechtsbehelfsbelehrung correct, Aufgabe zur Post = letter date, treated as a
Verwaltungsakt, Bundesland = Fristen-core default).

#### `POST /api/v1/cases/{case_id}/dossier?format=json|pdf`

Builds the next revision (1, 2, …) from the current case data and
confirmation state, stores it, and returns it with `201`.

`format=json` (default):

```json
{"case_id": "<uuid>", "revision": 2, "schema_version": "citizen-dossier-v1.0",
 "content_sha256": "<sha256 of the dossier's canonical JSON>",
 "created_at": "…",
 "dossier": {
   "schema_version": "citizen-dossier-v1.0", "revision": 2, "generated_at": "…",
   "case": {"case_id": "…", "title": "…", "created_at": "…",
            "legal_areas": ["sozialrecht"],
            "modules": [{"id": "sozialrecht", "version": "1.3.0", "title_de": "Sozialrecht"}]},
   "notice": {"de": "…keine Rechtsberatung…", "disclaimer_version": "v3.0.0"},
   "sections": {
     "chronology": {"entries": [/* as above, without rejected */],
                    "counts": {"proposed": 2, "confirmed": 1, "user_added": 1, "rejected": 1}},
     "document_checklist": {"items": [{"id": "…", "module_id": "sozialrecht",
                                       "modules": ["sozialrecht"], "label_de": "…",
                                       "why_de": "…", "topic": "…", "required": true}]},
     "deadlines": {"facts_used": {"bescheid_datum": "2026-07-06", "…": "…"},
                   "items": [{"module_id": "sozialrecht", "spec_id": "widerspruch_sgg_84",
                              "label_de": "Widerspruchsfrist", "severity": "critical",
                              "basis": "§ 84 Abs. 1 SGG", "status": "computed",
                              "frist_typ": "monat", "bekanntgabe": "2026-07-10",
                              "frist_ende": "2026-08-10", "rollover_applied": false,
                              "oq1_flag": false, "oq1_alternate_ende": null,
                              "explanation_de": "…", "assumptions": ["…"], "inputs": {}}],
                   "earliest_frist_ende": "2026-08-10"},
     "calculations": {"status": "available", "summary": {"total_discrepancies": 1,
                      "total_amount_eur": 48.0, "direction": "zulasten"},
                      "items": [{"label": "…", "relevant_rule": "…", "deterministic_result": 338.0,
                                 "computation_detail": "…", "authority_values": {"authority": 290.0},
                                 "discrepancy_found": true, "discrepancy_amount_eur": 48.0,
                                 "discrepancy_direction": "zulasten"}]},
     "evidence": {"items": [{"claim_id": "…", "claim_text": "…", "claim_type": "fact",
                             "confidence_score": 0.9, "verification": "exakt",
                             "user_adjudication": {"status": "disputed"},
                             "bindings": [{"quote_excerpt": "…", "binding_strength": 0.95,
                                           "source": "SGB II > § 11b"}]}]},
     "questions": {"items": [{"id": "…", "module_id": "sozialrecht", "modules": ["sozialrecht"],
                              "text_de": "…", "topic": "…", "origin": "module"}]},
     "drafts": {"items": [{"module_id": "sozialrecht", "document_type": "widerspruch",
                           "title": "…", "rendered_text": "…", "review_slots": 3,
                           "warnings": ["…"]}]},
     "export": {"formats": ["json", "pdf"], "pdf_attachments": ["dossier.json", "provenance.json"]}},
   "warnings": ["…"],
   "disclosure": {"version": "1.0", "must_display_before": "results", "texts": {"…": "…"}},
   "provenance": {"spec_version": "citizen-provenance-v1.1", "…": "…"}}}
```

- Deadline `status` ∈ {`computed`, `provisional`, `not_applicable`,
  `missing_input`}; `frist_ende` is `null` unless a deadline runs.
  `not_applicable` with `frist_typ: "kein_va"`: the letter is no
  Verwaltungsakt (person-confirmed fact).
- `calculations.status`: `available` (line items), `summary_only` (cases
  analysed before core 3.2.0: counts only), `none`.
- `questions[].origin`: `module` or `disputed_claim` (one question per claim
  the person marked `disputed` via `/adjudicate`).
- Claim texts and quotes are depseudonymized with the case's PII mapping —
  the dossier is the person's own document.
- `drafts`: one draft from the first case module with document templates,
  chosen by the module's selection table from the critical deadline; unbound
  slots stay `[BITTE PRÜFEN: …]`.
- Modules without `dossier.yaml` add no checklist/questions; `warnings`
  names them.

`format=pdf`: `application/pdf` attachment
(`dossier_<case_id>_r<revision>.pdf`), print-ready A4, deadline banner first.
Provenance is in a footer line on every page, in the PDF metadata
(`keywords` = provenance JSON, `subject` = schema id + case id) and in two
embedded files: `dossier.json` (the full dossier) and `provenance.json`.

Both formats send headers `X-Dossier-Revision`, `X-Dossier-Sha256`,
`X-Dossier-Schema`. `404` unknown case; `422` other `format` values.

#### `GET /api/v1/cases/{case_id}/dossier?format=json|pdf`

The last built revision, same shape and headers as the POST, status `200`;
the PDF is rendered from the stored JSON. `404` unknown case; `404`
`dossier_not_built` (structured `detail`, with `action`) before the first
POST. Deleting the case deletes its dossiers.

### 8.12 Citations (roadmap P11, WP-114)

#### `POST /api/v1/citations/verify`

Finds German legal citations in a text and checks them against the ingested
corpus. Deterministic (regular expressions + database lookups), read-only,
no LLM, nothing stored — the response is not AI-generated and carries no
disclosure. Body `{"text": "<up to 200000 chars>", "verify": true}`:

```json
{"count": 2, "corpus_checked": true,
 "summary": {"source_not_ingested": 1, "verified": 1},
 "citations": [
   {"kind": "statute", "text": "§ 44 Abs. 1 Satz 2 SGB X", "span": [5, 29],
    "law": "SGB X", "source_type": "sgbx", "paragraphs": ["44"],
    "absatz": "1", "satz": "2", "nummer": null, "ff": false, "article": false,
    "identifier": null,
    "verification": {"status": "verified",
                     "paragraphs": [{"paragraph": "44", "status": "verified"}]}},
   {"kind": "ecli", "text": "ECLI:DE:BSG:2019:…", "span": [40, 72], "law": null,
    "…": "…", "identifier": "ECLI:DE:BSG:2019:…",
    "verification": {"status": "not_ingested"}}]}
```

- `kind`: `statute` (`§`, `§§`, `Art.`), `ecli`, `docket` (BSG docket
  numbers such as `B 4 AS 19/18 R`). `span` is `[start, end)` in characters.
- `paragraphs`: cited §/Art. numbers; ranges as `"11–11b"`. `absatz`/`satz`/
  `nummer` refer to the first cited §.
- `verification.status` — statutes: `verified`, `absatz_not_found`,
  `not_found` (law ingested, § absent: check the citation),
  `source_not_ingested`, `not_in_catalog` (law recognised, corpus carries no
  source; articles of the GG etc.), `no_law` (no recognised law after the §);
  decisions: `decision_found` (with `title`), `decision_not_found`,
  `not_ingested` (no case law ingested).
- `verify: false` or an unreachable database → `verification: null`,
  `corpus_checked: false`. `422` empty or oversized `text`.

---

## 9. Minimal client checklist

1. `GET /api/v1/meta/disclaimer/version` → remember value V.
2. Send `X-Disclaimer-Ack: V` on every subsequent request.
3. Fetch `GET /api/v1/meta/disclosure` (cache by `version`); before presenting
   any AI-generated result or document to a natural person, display
   `texts[lang]` to them (Art. 50(1)) and persist the `provenance` marker
   delivered with each AI-generated payload (Art. 50(2)).
4. On `DEPLOYMENT_MODE=dev` (check `meta/deployment-mode`), add
   `X-Document-Tag: synthetic` to every upload.
5. Optional: `GET /api/v1/modules` to offer only enabled modules as
   `legal_areas`; handle `422 MODULE_UNKNOWN` / `MODULE_NOT_ENABLED`.
6. For analysis: `POST /analyze` (or conversation first-message) and consume
   the SSE stream; tolerate `running`/`complete` pairs per stage and a terminal
   `final_output` summary event; handle `{"error": ...}` terminal events.
7. For corpus setup: check `corpus/health`; if unhealthy trigger
   `corpus/update` and poll `corpus/status/{job_id}`.
8. Treat any unexpected disconnect mid-SSE as a failed run and re-submit.
9. For the appointment dossier: `GET …/dossier/chronology`, let the person
   confirm/correct entries and facts (`PUT`), then `POST …/dossier` (JSON or
   PDF). Show `deadlines` first and never hide `provisional`/`missing_input`.

---

*Generated for Citizen v2.0.0 (D-024/D-025 refactor). Guard test
`tests/unit/test_api_documentation.py` keeps this catalog in sync with the
live OpenAPI schema.*
