## 2026-11-16 — P9 first batch: module contract, registry, Fristen split (WP-90/91/92; D-042…D-047)

WP-90 ratifies D-021 (RDG single-case invariant, carry-over C-1) in
`DECISIONS.md`. **Deferred:** the v2.0.0 baseline eval report
(`eval/goldsets/goldset-v0.2.0.yaml --save`) — no LLM API key is available
in this environment; the zero-regression reference for the P9 exit gate
(WP-97) must be produced before WP-93 touches the pipeline. Package version
stays 2.0.0.

### Added

- `app/modules/` (WP-91): `sdk.py` (stable import surface, `SDK_VERSION`
  "3.0"), `manifest.schema.json` (core_api 3.0), `registry.py` (discover →
  validate → enable → resolve, D-037 tier rule per `DEPLOYMENT_MODE`,
  legacy alias `schenkungsrecht → erbrecht` per D-038), `lint.py` (module
  code may import only `app.modules.sdk`).
- Settings `DEFAULT_MODULE` (default `sozialrecht`) and `ENABLED_MODULES`
  (unset → D-037 tier rule), mirrored in `.env.example` and conftest;
  startup refuses an invalid enabled manifest, an unknown
  `ENABLED_MODULES` id, or a `DEFAULT_MODULE` outside the enabled set.
- `modules/sozialrecht/module.yaml` (manifest only, tier `verified`,
  version 1.0.0) and `modules/sozialrecht/fristen.yaml` (WP-92).
- `app/fristen/` (WP-92): holiday calendar per Bundesland, Bekanntgabe
  fiction library (`sgbx_37_2` with OQ-1 ambiguity), rollover library
  (`sgg_64_3`), Rechtsbehelfsbelehrung-defect extension, and the generic
  evaluator for module deadline specs; `FristResult` gains additive
  `module_id`/`spec_id`.
- Tests: `tests/unit/test_modules_registry.py` (discovery, invalid
  manifest, per-mode enablement, aliases, missing default, import lint),
  `tests/unit/test_fristen_spec.py` (holidays per Land, month-end
  arithmetic, rollover, defective-RBB one-year deadline).

### Changed

- `app/services/fristen.py` reduced to a compatibility shim;
  `compute_widerspruchsfrist` now evaluates the sozialrecht spec through
  the generic evaluator — `tests/unit/test_fristen.py` passes unchanged.
- Dependencies: `jsonschema>=4.21,<5.0` (manifest validation, D-044) and
  `types-PyYAML>=6.0` in dev extras (mypy strict was red on main without
  it, D-047).
- `/api/v1` unchanged; `API_DOCUMENTATION.md` not modified; no migrations
  in this batch.

## 2026-11-16 — Re-founding on the free public path: module architecture + roadmap v3.0.0 (D-034…D-041)

Decisions: D-034 (free public path), D-035 (purpose widened, amends D-020),
D-036 (core + modules, Sozialrecht default), D-037 (enablement by
DEPLOYMENT_MODE), D-038 (module queue + legacy keys), D-039 (API stays
`/api/v1`; versioning scheme), D-040 (PENDING: UI location), D-041 (module
licensing). **Documentation and architecture only — no production code,
configuration, migration or API contract changed.** Package version stays
2.0.0; core 3.0.0 is cut at roadmap P9 exit.

### Added

- `ARCHITECTURE.md` (3.0.0-draft.1) — target architecture: domain-neutral core
  + legal-area modules; module contract (manifest, deadline specs as data,
  typed calculator SDK, tiers), core service responsibilities, data-model
  deltas, additive `/api/v1` target surface, versioning of core/modules/
  artefacts, per-module compliance, and the as-is coupling map that is the
  P9 work list.
- `docs/roadmap-v3.0.0.md` — P9 module architecture (Sozialrecht → module 1,
  zero-regression gate), P10 appointment dossier, P11 module platform, P12
  consumer UI + plain-language layer, P13 modules M1–M10, Track G funding/
  governance (Prototype Fund 2026-11-30, NLnet 2027-01-03), v2.0.0
  carry-over items C-1…C-5, open questions OQ-1…OQ-9.
- `docs/module-catalog.md` (1.0.0) — eleven module profiles (Sozialrecht +
  Schuldner-, Miet-, Arbeits-, Vertrags-, Verkehrs-, Familien-,
  Aufenthalts-, Steuer-, Erb-, Strafrecht) with scope, documents, deadline
  and calculator anchors (marked as hypotheses to verify), drafts, corpus,
  compliance specifics; module definition of done.

### Changed

- `README.md` — repositioned as citizen-side preparation assistant (free
  public path); new "Ausrichtung und Stand" table; "Rechtsgebiete" replaced by
  the module table (current tier + plan); planned features listed separately
  from shipped ones; architecture and directory sections reference the new
  documents. Current-state sections (Schnellstart, API, Konfiguration, Tests,
  Sicherheit) unchanged.
- `AGENTS.md` — points to the new authoritative documents; direction
  paragraph and rules for new work (no new area logic in core, additive API,
  no AGPL embedding); purpose statement updated to D-035.
- `docs/roadmap-v2.0.0.md` — status banner: superseded for new work by
  v3.0.0; body unchanged (still cited by `DISCLAIMER_*.md` and
  `devdocs/DEV-INSTANCE.md`).

### Not changed (deliberately)

- `DISCLAIMER_DE.md` / `DISCLAIMER_EN.md` and `DISCLAIMER_VERSION` — the
  widened purpose (D-035) enters compliance copy with DISCLAIMER v3.0.0 in
  roadmap WP-96, together with the version bump the ack gate requires.
- `API_DOCUMENTATION.md` — documents the shipped contract only; target routes
  live in `ARCHITECTURE.md` § 5 until implemented (G4 parity guard).

### Found during the sweep

- D-021 (RDG single-case invariant) is cited as built but was never appended
  to `DECISIONS.md` (only proposed in roadmap v2.0.0) → carry-over C-1.

## 2026-08-25 — Art. 50 EU AI Act disclosure & provenance fields (D-032/D-033)

Decisions: D-032 (R1, disclosure/provenance embedding + invariants G-50-A..G /
T-50-H..I), D-033 (R1, connection-leak fix exposed by the new tests).

### Added

- `app/services/disclosure.py` — `DisclosureInfo` / `ProvenanceMarker` models,
  canonical Art. 50(1) DE/EN texts (`DISCLOSURE_VERSION = "1.0"`), and the
  shared never-raises helper `build_disclosure_and_provenance(settings)`.
- `GET /api/v1/meta/disclosure` — canonical disclosure endpoint, guarded by a
  route-level `X-Disclaimer-Ack` dependency (middleware excludes all of
  `/api/v1/meta*`; editing it was out of scope). Declared via
  `response_model`, so openapi.json reflects the schema.
- `disclosure_version: "1.0"` key on `GET /api/v1/meta/version`.
- Analyze SSE terminal event now carries top-level `disclosure` + `provenance`
  (error events carry neither); conversation chat `done` event carries both;
  `GeneratedDocument` carries `provenance` (deliberately no `disclosure`) and
  `POST /api/v1/documents/generate` serializes it.
- `tests/unit/test_disclosure.py` — 13 tests covering G-50-A..G-50-G
  (endpoint shape/ack enforcement, version key, analyze terminal + error
  events, chat done event, documents provenance incl. cross-surface identity
  with a frozen clock, helper fallback behavior on a broken settings object,
  model JSON round-trips, openapi.json reflection).

### Fixed

- `GET /cases/{case_id}` (and therefore `POST /documents/generate`) leaked one
  pooled asyncpg connection per call until GC: `get_case_endpoint` ran its
  `legal_areas` query against the already-closed session (D-033).

### Changed

- `API_DOCUMENTATION.md` — new meta route row, updated `/meta/version`,
  analyze terminal event, conversation done event, documents response, and
  client checklist (display disclosure before results, persist provenance);
  route-parity guard stays green.
- Semantic-version headers bumped: meta.py 0.3.0→0.4.0, analyze.py
  0.3.0→0.4.0, document_generators.py 0.1.0→0.2.0, documents.py 0.1.0→0.2.0,
  cases.py →0.2.0; chat_reasoning.py gained its missing header (1.1.0).

## 2026-08-25 — Stale-document cleanup (D-031)

### Removed

- `LETSFIXSTUPIDDBDESIGN.md` — resolved DB-design outline (implemented as
  D-024/D-025/D-026); historical rationale preserved in DECISIONS.md history.
- `docs/design_document.md`, `docs/design_v1.0.0.md`,
  `docs/technical_specification.md`, `docs/GAP-REPORT.md`,
  `docs/ARCHITECTURE-ACTUAL.md`, `docs/wp-1.6-pruefstand-v1.0.0.md` —
  v1.0.0-era planning artifacts describing the removed web UI / Electron /
  SQLite state; all were banner-marked superseded and referenced only by each
  other.
- `docs/goldset-v0.1.0.yaml` — byte-identical orphan duplicate of
  `eval/goldsets/goldset-v0.1.0.yaml`; every code/config reference already
  points at `eval/goldsets/`.

### Changed

- README directory tree updated (docs/ now holds only
  `roadmap-v2.0.0.md`, kept because DISCLAIMER_DE/EN and
  devdocs/DEV-INSTANCE.md reference it live).

## 2026-08-25 — API-only refactor + PostgreSQL-only database (v2.0.0)

Decisions: D-024 (R3, Postgres-only), D-025 (R2, remove web UI + Electron),
D-026 (R2, testcontainers). Invariants G1–G5 / T1–T3 logged in DECISIONS.md.

### Removed

- `static/` (index.html, app.js, style.css) and all HTML-serving routes:
  StaticFiles mount, `GET /` FileResponse, desktop `__main__` block
  (`app/main.py`). `/health`, `/robots.txt`, `/docs`, `/redoc`,
  `/openapi.json` retained.
- `electron/` tree entirely (main/preload TS, package.json, PyInstaller spec)
  and `scripts/apprun.sh`.
- SQLite backend everywhere: `_cosine_distance_sqlite()`,
  `load_sqlite_vec_extension()`, `IS_SQLITE` branches (`session.py`,
  `vector_backend.py`, `cache.py`, `corpus.py`, `main.py`), WAL/PRAGMA init,
  sqlite auto-stamp in `alembic/env.py`.
- Alembic migrations 007–010 and 011_sqlite (SQLite branch).
- Dependencies: `aiosqlite`, `sqlite-vec`, `jinja2` (unused anywhere).
  Added dev dep `testcontainers[postgres]`.
- `Settings.DATA_DIR` (dead Electron config).
- `docs/ui_testing_guide.md`.

### Changed

- `ChunkEmbedding.embedding` is now `pgvector.sqlalchemy.Vector(1536)` —
  the LargeBinary/raw-SQL `::vector` cast workaround (D-014) is gone;
  `_upsert_embedding()` uses a plain dialect insert.
- New migration `012_pg_collapse_sqlite_branch`: idempotently carries the
  schema content of deleted SQLite-only migrations 008–010 AND re-admits
  `disclaimer_ack` into the `pipeline_stage_log` CHECK constraint — that
  value was dropped by former migration 008 while `services/audit.py` still
  writes such rows, silently breaking every audit-trail insert on
  PostgreSQL. Single linear DAG: `001 → … → 006 → 011_pg → 012`.
- Startup migration targeting simplified to plain `alembic upgrade head`
  (subprocess mechanism retained per D-006); default `DATABASE_URL` is now a
  PostgreSQL URL.
- Tests run against real PostgreSQL: session-scoped pgvector testcontainer
  when no `DATABASE_URL` is set (D-026); integration suite gained an
  event-loop/pool isolation fixture.
- Test harness repaired where it had rotted behind production changes
  (no business logic changed): disclaimer ack now uses `DISCLAIMER_VERSION`
  instead of the package version; uploads send `X-Document-Tag`;
  pipeline stubs match current call signatures (`system_prompt`,
  `retrieve_chunks_by_norm_reference`, `retrieve_chunks_for_areas`,
  calculation stub); stage-sequence assertions follow `_STAGES`; corpus
  seeding uses asyncpg against `DATABASE_URL` instead of a hardcoded psql
  call; model tests know about `text_hash`.
- CI: unit job runs against the pgvector service container (no SQLite path).
- Docs: README architecture table/directory tree, DEPLOYMENT.md nginx +
  migration sections, AGENTS.md rewritten to API-only/PG-only reality,
  ARCHITECTURE-ACTUAL.md status banner.

### Added

- `API_DOCUMENTATION.md` — exhaustive client-facing API contract
  (base URLs, versioning, auth/gates, error catalog, SSE contracts,
  per-endpoint examples). Guarded by
  `tests/unit/test_api_documentation.py` (doc ↔ OpenAPI parity).

---



### Änderungen

- **README.md** — tote Links entfernt (`README-EN.md`, `docs/citizen-onepager.md`
  existieren nicht); nichtexistierenden Befehl `citizen-eval` durch den realen
  Harness-Aufruf `python -m eval.runner <goldset.yaml> [--save] [--baseline]`
  ersetzt (Kernfunktionen + Tests-Sektion); Quickstart-Curl auf
  `X-Disclaimer-Ack: v0.1.0` korrigiert (Default aus `app/core/config.py`);
  Zähler aktualisiert (12 Migrationen/zwei DAGs, 24 Servicemodule, 36
  Testdateien ~12.300 Zeilen); Verzeichnisbaum an Realität angepasst (`docs/`,
  neu: `devdocs/`, `electron/`, `scripts/`); drei fehlende Meta-Endpunkte in die
  API-Tabelle aufgenommen (`legal-timestamp`, `active-profile`,
  `deployment-mode`); Codequalität-Befehle auf CI-Umfang (`app/` nur)
  eingeschärft; Behauptung „Regressions-Gate in der CI" korrigiert (Gate läuft
  per `--baseline` im Harness, nicht als CI-Schritt); Absatz zu
  `docs/datenschutz/` entfernt (Verzeichnis existiert nicht).
- **`.gitignore`** — ungültige Zeile `docker-compose.yml  # take out before
  release` entfernt (Gitignore kennt keine Inline-Kommentare; Datei ist ohnehin
  getrackt und Kernbestandteil des Deployments); `node_modules/` ergänzt
  (Electron-Paket); Versionskopf aktualisiert.

### Hinweis

- Keine Code-, API- oder Schema-Änderungen. Alle Korrekturen gegen verifizierte
  Quellen: `.github/workflows/ci.yml`, `app/api/routes/meta.py`,
  `eval/runner.py`, `alembic/versions/`, `app/core/config.py`,
  `tests/conftest.py`. Purpose-Drift-Lint nach README-Änderung grün
  (`python scripts/check_purpose_drift.py` → Exit 0).

---

## 2026-08-25 — Docs reconciliation + disclaimer consolidation (v2.0.0 docs)

Decisions: D-029 (R2, disclaimer merge), D-030 (R1, docs sweep). No
production code changed.

### Disclaimer consolidation (D-029)

- `DISCLAIMER_DE.md` / `DISCLAIMER_EN.md` rewritten as v2.0.0 consolidated
  documents — Part A project statement, Part B legal notice/disclaimer,
  Part C AI Act classification.
- Deleted `STATEMENT.md`, `COMPLIANCE.md`, `COMPLIANCE-EN.md` (content merged).
- Content aligned with implementation: acknowledgment logging described as it
  actually works (`X-Disclaimer-Ack` version + audit row per run; no checksum
  exists), active profile via `GET /meta/active-profile`, `DEPLOYMENT_MODE`
  switch documented as implemented, UI references removed (D-025),
  never-created `AI-USAGE.md` marked planned.

### Documentation drift fixes (D-030) — code treated as authoritative

- **README.md** — API-only wording throughout (no browser UI); documents
  routes corrected (`GET /documents/generator-options/{id}`,
  `POST /documents/generate`; the listed `POST /cases/{id}/documents` does
  not exist); architecture table: no tsvector (ILIKE keyword fallback),
  8 migrations; config table: `PIPELINE_TIMEOUT_SEC=480`,
  `RETRIEVAL_MODE=per_question`, rate limiter not mounted (`RATE_LIMIT_
  REQUESTS=0`); directory tree: 37 test files (~12.6k lines); security
  section: no IP processing, no-checksum acknowledgment, rate limiting off;
  corpus source hosts incl. bsg.bund.de; links point at the merged
  disclaimers.
- **`.env.example`** — rewritten to mirror `app/core/config.py` (all settings,
  current defaults). Removed phantom `CORS_ORIGINS` (field deleted from
  Settings in WP-00.5); corrected `PIPELINE_TIMEOUT_SEC`, stage timeouts,
  `TOP_K_RETRIEVAL`, `MAX_COSINE_DISTANCE`, `MAX_CHUNKS_FOR_FINAL`,
  fallback models; added missing `INFERENCE_PROFILE`, `DEPLOYMENT_MODE`,
  retrieval/corpus/cache/OCR-quality knobs.
- **DEPLOYMENT.md** — dropped nonexistent `SECRET_KEY` env var; nginx SSE
  proxy timeouts 300s → 540s per D-017 timeout chain; health example shows
  v2.0.0.
- **devdocs/DEV-INSTANCE.md** — dev banner described as the
  `GET /api/v1/meta/deployment-mode` payload field (no UI left to render it);
  references to deleted `COMPLIANCE.md` and never-created
  `devdocs/PROVIDER-GO-NOGO.md` fixed.
- **docs/** — historical status banners added to `technical_specification.md`,
  `design_document.md`, `design_v1.0.0.md`, `GAP-REPORT.md`,
  `wp-1.6-pruefstand-v1.0.0.md` (v1.0.0-era planning artifacts superseded by
  D-024/D-025); ARCHITECTURE-ACTUAL.md already carried one.
- **LETSFIXSTUPIDDBDESIGN.md** — marked RESOLVED via D-024/D-025/D-026 with a
  pointer to current truth.
- **AGENTS.md** — `.env.example` now documented as mirroring config.py;
  purpose-drift scan set description updated post-merge (lint code
  untouched; `DISCLAIMER_*.md` outside its default targets = logged gap).
- **.gitignore** — added runtime state `.corpus_sources.json` (written by
  `services/corpus.py`) and `docker-compose.override.yml` (carries DB
  credentials per DEPLOYMENT.md); removed trailing space after
  `.secret_salt`.

### Known discrepancies reported, NOT changed (code behavior frozen)

- `app/api/routes/meta.py` `_DISCLAIMER_TEXT` (served by
  `/api/v1/meta/disclaimer/text`) claims "uploaded documents are not stored"
  and "IPs are logged anonymously" — both false (uploads persist in
  PostgreSQL; IPs are never touched). Fixing requires a code change.
- Purpose-drift lint default targets include files that no longer exist;
  adding `DISCLAIMER*.md` would change lint behavior and was out of scope.

---

## 2026-08-07 — WP-62: Dev-instance Art. 2(8) hardening (Roadmap v2.0.0)

### Änderungen

- **`app/core/config.py`** — neue Einstellungen `DEPLOYMENT_MODE`
  (`dev`/`self`/`provider`, Standard `dev`, per `Literal` validiert) und
  `CITIZEN_SYNTHETIC_DATA_ONLY` (Standard `false`). Damit liegt der
  `DEPLOYMENT_MODE`-Schalter aus D-019 bereits in WP-62 vor (die Roadmap
  erlaubt das, da WP-66 noch nicht umgesetzt ist).
- **`app/services/dev_guard.py`** (neu) — Startup-Assertion: verweigert den
  Start bei `DEPLOYMENT_MODE=dev` ohne `CITIZEN_SYNTHETIC_DATA_ONLY=true`
  (`DevGuardError`). Ingest-Guard: bei aktiver dev-Posture werden
  Dokument-Uploads ohne `X-Document-Tag: synthetic`/`goldset` mit HTTP 403
  abgelehnt (`synthetic_data_only`).
- **`app/main.py`** — ruft die Startup-Assertion im Lifespan auf (Start wird
  verweigert, wenn die dev-Posture nicht explizit gesetzt ist); neue
  Middleware `DevNoIndexMiddleware`; neue Route `/robots.txt` (im Modus `dev`
  `Disallow: /`).
- **`app/middleware/dev_headers.py`** (neu) — setzt `X-Robots-Tag: noindex,
  nofollow` auf allen Antworten im Modus `dev`.
- **`app/api/routes/meta.py`** — neuer Endpoint `GET /api/v1/meta/deployment-mode`
  (Modus, `synthetic_data_only`, Banner-Text) für UI und Auditoren.
- **`app/api/routes/ingest.py`** und **`app/api/routes/conversations.py`** —
  Ingest-Guard an allen Dokument-Upload-Pfaden (`/api/v1/ingest`,
  `POST /api/v1/conversations` mit Datei, `POST /api/v1/conversations/{id}/documents`).
- **`static/index.html`** — dauerhafter, nicht schließbarer Entwicklungs-Banner
  `ENTWICKLUNGSINSTANZ — Testbetrieb mit synthetischen Daten. Keine Nutzung für
  reale Fälle. Ausgaben sind nicht belastbar.` im Modus `dev` (Version 1.3.0).
- **`devdocs/DEV-INSTANCE.md`** (neu) — Betriebsdokumentation der dev-Instanz:
  Zweck, Zugriffskontrolle (primär WireGuard/Tailscale; Fallback mTLS oder
  Basic Auth + IP-Allowlist), synthetische-Daten-Posture, Noindex, Banner,
  ausdrückliches Keine-reale-Nutzung-Statement.
- **`.env.example`** — neue Einstellungen `DEPLOYMENT_MODE` und
  `CITIZEN_SYNTHETIC_DATA_ONLY` dokumentiert.
- **`tests/conftest.py`** — setzt `DEPLOYMENT_MODE=dev` und
  `CITIZEN_SYNTHETIC_DATA_ONLY=true`, damit die bestehende Suite gegen die
  dev-Posture läuft.
- **`tests/unit/test_dev_guard.py`** (neu) — Unit-Tests für Startup-Assertion,
  Ingest-Guard, Konfig-Defaults und Route-Level-Enforcement.
- **`DECISIONS.md`** — D-023 (R2) protokolliert: `DEPLOYMENT_MODE` wird in
  WP-62 vorgezogen; Standard `dev` + `CITIZEN_SYNTHETIC_DATA_ONLY=false`
  erzwingt eine explizite Operator-Entscheidung.

### Exit-Kriterien (WP-62)

- Die dev-Instanz ist nicht öffentlich nutzbar (Runbook in DEV-INSTANCE.md).
- Sie kann keine echten Daten aufnehmen (Startup-Assertion + Ingest-Guard).
- Sie ist nicht indexierbar (`X-Robots-Tag` + `robots.txt`).
- Sie trägt eine dokumentierte No-Real-Use-Posture (Banner + DEV-INSTANCE.md).

### Hinweis

- R2: Setzt einen Startup-Guard und einen Ingest-Guard; bestehende
  API-Verträge bleiben erhalten (neue Header-Auflage nur auf dev-Instanzen
  mit aktiver Synthetik-Posture). Bis WP-66 gilt der Schalter bereits
  technisch; die WP-66-Erweiterungen (UI-Header-Anzeige, Log-Zeile) folgen.

---

## 2026-08-07 — WP-61: Annex III high-risk self-assessment (Roadmap v2.0.0)

### Änderungen

- **`COMPLIANCE.md`** — Abschnitt 4.4 zur vollständigen
  Annex-III-Nr.-5-Bst.-a-Selbstbewertung ausgebaut (Erfassungsbereich,
  deklarierte Zweckbestimmung D-020, vier Gründe gegen den Tatbestand,
  Drift-Schutz, Bedingtheit). Version 1.0.0 → 1.1.0.
- **`COMPLIANCE-EN.md`** — englischer Spiegel der Selbstbewertung.
  Version 1.0.0 → 1.1.0.
- **`DECISIONS.md`** — D-020 (R1) aus Roadmap v2.0.0 §1 protokolliert.
- **`scripts/check_purpose_drift.py`** (neu) — Dokumentations-Lint gegen
  Zweckbestimmungs-Abdrift. Scannt `README*.md`, `STATEMENT.md`,
  `COMPLIANCE*.md` und `docs/pitch*` auf behördenseitige Formulierungen
  (konfigurierbare Deny-Phrase-Liste, case-insensitive) und meldet jeden
  Treffer mit Datei, Zeile und Spalte. Exit-Codes: 0 = sauber, 1 = Zweckdrift,
  2 = Fehler.
- **`.github/workflows/ci.yml`** — neuer CI-Schritt „Purpose-drift check
  (WP-61)": Die CI schlägt fehl, wenn ein gescanntes Dokument Citizen als
  behördenseitiges Werkzeug beschreibt.
- **`tests/unit/test_purpose_drift.py`** (neu) — Unit-Tests für den Lint
  (sauberes Repo, Treffer mit Datei/Zeile, englische Deny-Phrasen, fehlende
  Datei, `--extra-deny`, case-insensitive, ungültige Deny-Phrase-Datei).

### Selbstbewertung (Kurzfassung)

- Anhang III Nr. 5 Bst. a KI-VO erfasst die behördenseitige Bewertung der
  Anspruchsberechtigung von Personen zu Sozialleistungen. Citizen ist nach
  seiner Zweckbestimmung (D-020) antragstellerseitige Selbsthilfe und
  Beratungsassistenz — kein Werkzeug von Behörden zur Leistungsbewertung.
  Ergebnis: **keine Hochrisiko-Einstufung** bei deklarierter
  Zweckbestimmung. Die Bewertung ist konditional und wird durch den
  Purpose-Drift-Lint in der CI technisch gegen Abdrift gesichert.

### Hinweis

- R1 (Dokumentation + Lint-Skript + CI-Schritt; kein Laufzeit- oder
  API-Verhalten geändert). Der `DEPLOYMENT_MODE`-Schalter wird weiterhin in
  WP-66 implementiert.

---

## 2026-08-07 — WP-60: Compliance baseline document and classification (Roadmap v2.0.0)

### Änderungen

- **`COMPLIANCE.md`** (neu, Deutsch, kanonisch) — alleinige Quelle für die
  rechtliche Klassifizierung von Citizen unter der KI-VO (VO (EU) 2024/1689):
  Anbieter/Einsetzer-Bestimmung über den Schalter `DEPLOYMENT_MODE`
  (dev/self/provider, D-019), Entwicklungsphasen-Posture (Art. 2(8)),
  FOSS-Freistellung mit Art.-50-Ausnahme (Art. 2(12)), Pflichten-Matrix je
  Modus, Frist 2026-12-02 für Art. 50(2), Kurzverortung DSGVO (Art. 35/28)
  und RDG (§ 2/§ 6/§ 8).
- **`COMPLIANCE-EN.md`** (neu) — englischer Spiegel der kanonischen Datei.
- **`DECISIONS.md`** — D-019 (R2) und D-022 (R1) aus Roadmap v2.0.0 §1
  protokolliert.
- **`README.md`** — Abschnitt „Rechtlicher Status" mit Verweis auf
  `COMPLIANCE.md`.

### Klassifizierung (Kurzfassung)

- `dev` (Autor, Testbetrieb, nur synthetische Daten): Entwicklungsphase nach
  Art. 2(8) KI-VO — keine Pflichten ausgelöst.
- `self` (Autor, eigene reale Bescheide): persönliche, nicht-berufliche
  Nutzung — keine Pflichten ausgelöst.
- `provider` (Dritte können Analysen erhalten): Autor wird Anbieter
  (Art. 3(3)); Art. 50(1)/(2) aktiv (WP-64/WP-65; Kennzeichnungsfrist
  2026-12-02), DSGVO-DPIA/AVV (WP-68) und RDG-Invariante (WP-67) sind
  Voraussetzung, Go/No-Go-Gate (WP-69) steht davor.

### Hinweis

- Reine Dokumentation (R1). Der `DEPLOYMENT_MODE`-Schalter wird in WP-66
  implementiert; bis dahin gilt für die laufende Instanz die Einordnung
  `dev`. Keine Code-Änderungen in diesem Work Package.

---

## 2026-07-20 — Critical Retrieval & Model Fallback Fixes (v0.4.5)

### Problem

Prüfstand goldset cases GS-002 through GS-005 exposed two critical failure
patterns that fundamentally broke the pipeline:

**Problem A — Model Exhaustion.** GS-002, GS-004 failed with `Combined triage
failed: All models exhausted: ['deepseek/deepseek-v4-pro']`. GS-003 after corpus
enlargement failed identically at the grounded answer stage. Root cause: every
LLM call in `reasoning.py` passed `model=triage_model` to `chat_completion()`,
which in `router.py` creates a single-model chain with no fallback. With
`MAX_RETRIES=1`, any transient error (timeout, 429, 503) killed the pipeline.
The fallback models were ineffective — `FALLBACK_MODEL_1` was identical to
`PRIMARY_MODEL` (deduplicated away) and `FALLBACK_MODEL_2` was `/openrouter/free`
(an invalid model ID). Effective chain for every call: `[deepseek-v4-pro]` with
exactly one attempt.

**Problem B — Retrieval Failure.** GS-003 and GS-005 completed but the LLM
reported "die einschlägigen Vorschriften... sind in den bereitgestellten Chunks
nicht enthalten" — even after ALL 16 source types were ingested into the corpus.
This was a critical trust-killer for the project. Two bugs in
`_extract_norm_references()` were the root cause:

1. **Parenthetical stripping destroyed § references.** The line
   `re.sub(r'\s*\([^)]*\)', '', cleaned)` removed parentheticals from the text
   before running the §-reference regex. This destroyed legal citations inside
   parentheses like `(§ 32 SGB II)` — an extremely common pattern in German
   legal documents.

2. **Greedy regex captured trailing words as statute name.** The statute regex
   used `{0,3}` for extra word groups, causing greedy capture like `"SGB II für
   die"` instead of `"SGB II"`. When checked against `_STATUTE_TO_SOURCE_TYPE`,
   the garbage statute name didn't match any entry → reference silently dropped.
   Combined with Bug 1, GS-005's §-references (including all critical norms
   like § 32 SGB II, § 39 SGB II) were effectively invisible to the retrieval
   engine.

### Changes

- **`app/services/retrieval.py`**: Removed parenthetical-stripping line (Bug 1).
  Changed `{0,3}` → `{0,1}` in the statute regex to prevent greedy capture of
  trailing prose (Bug 2). Both `_NORM_REF_RE` and `_extract_norm_references()`
  were affected.

- **`app/core/pipeline.py`**: Added §-reference direct lookup
  (`retrieve_chunks_by_norm_reference`) to the single-area retrieval path (both
  combined and per_question modes). Previously §-lookup only ran in the
  multi-area path — single-area analysis (empty `legal_areas`) could never find
  §-referenced chunks.

- **`app/core/config.py`**: Changed `FALLBACK_MODEL_1` from
  `deepseek/deepseek-v4-pro` (same as PRIMARY) to `deepseek/deepseek-chat`.
  Changed `FALLBACK_MODEL_2` from `/openrouter/free` (invalid) to
  `anthropic/claude-3.5-sonnet`. Increased `MAX_RETRIES` 1→3.
  `MAX_COSINE_DISTANCE` 0.55→0.65 (similarity ≥ 0.35). `TRIAGE_TIMEOUT_SEC`
  45→60. `FINAL_TIMEOUT_SEC` 150→180. `MAX_CHUNKS_FOR_FINAL` 6→12.

- **`app/services/reasoning.py`**: Changed 6 LLM call sites (triage ×2,
  grounded_answer ×2, grounded_answer_stream ×2) from `model=` (single-model
  chain, no fallback) to `models=` (full client fallback chain when
  TRIAGE_MODEL/FINAL_MODEL is None). Increased `max_retries` from 1 to 3 on all
  6 call sites.

### Verification

- §-reference extraction test: previously found 0 correct refs from GS-005 text
  (all dropped by parenthetical stripping or greedy regex). After fix: correctly
  extracts all 3 refs including the parenthetical `§ 32 SGB II`.
- Health endpoint returns `{"status":"ok","version":"v1.0.0"}` on VPS.
- 797 unit tests pass. 13 pre-existing failures (middleware needs DB, config
  timeout assertion had stale 120s value) — 2 test files updated to match new
  defaults.

## 2026-07-19 — Timeout Stack Overhaul: Hard Wall-Clock Enforcement + Realistic Budgets (v0.4.4)

### Problem

After the v0.4.3 fix, the Prüfstand pipeline reached the generation stage but
then failed with `Pipeline execution exceeded 120s timeout`. Two root causes:

1. **Pipeline budget was mathematically impossible to satisfy.** The pipeline
   timeout (120s) was smaller than the sum of per-call LLM timeouts:
   triage(20s) + grounded_answer(75s) + adversarial_review(75s) +
   calculation(45s) = 215s. The pipeline was designed to fail.

2. **Per-call httpx timeouts never fired on streaming responses.** OpenRouter
   streams tokens via chunked transfer encoding — headers arrive in ~1s, body
   streams slowly. httpx's read timeout resets with each chunk received, so
   the 75s per-call timeout never triggered. The only effective timeout was
   the pipeline-level `asyncio.wait_for(120s)`.

### Changes

- **`app/core/router.py`**: Wrapped `chat_completion`'s HTTP call in
  `asyncio.wait_for(timeout)` to enforce a HARD wall-clock timeout regardless
  of httpx streaming behavior. Added elapsed-time check inside
  `chat_completion_stream`'s token loop that raises `httpx.TimeoutException`
  when wall-clock time exceeds the timeout. (D-017)

- **`app/core/config.py`**: Increased timeout values to realistic levels:
  - `PIPELINE_TIMEOUT_SEC`: 120 → 480 (8 min)
  - `TRIAGE_TIMEOUT_SEC`: 20 → 45
  - `FINAL_TIMEOUT_SEC`: 75 → 150
  - `EMBEDDING_TIMEOUT_SEC`: 15 → 30
  - `CALCULATION_TIMEOUT_SEC`: 45 → 90
  - Removed duplicate `CALCULATION_TIMEOUT_SEC` definition (was at both line 93
    and line 107).

- **nginx** (`/etc/nginx/sites-enabled/workbench.gronowski.cc`): Increased
  `proxy_read_timeout` and `proxy_send_timeout` from 300s → 540s for both
  `/api/v1/analyze` and `/api/v1/goldset` locations.

- **Production `.env`**: Updated `PIPELINE_TIMEOUT_SEC=480`,
  `TRIAGE_TIMEOUT_SEC=45`, `FINAL_TIMEOUT_SEC=150`, `EMBEDDING_TIMEOUT_SEC=30`.

### Verification

- `tests/unit/test_router.py` + `test_vector_backend_aliasing.py`: 31 passed
- `ruff check` + `mypy` clean on changed files (only pre-existing E501 warnings)
- Production GS-001 pipeline completed end-to-end: normalization →
  classification → decomposition → retrieval (6 chunks, 1.9s) → construction
  (81.6s grounded_answer) → verification → generation → adversarial_review
  (15.6s) → calculation_check (117s). Total ~215s, well under 480s budget.
  All 8 `final_output` sections populated.

### Timeout Chain (after fix)

```
nginx (540s) > pipeline (480s) > sum of per-call (45+150+150+90 = 435s)
```

---

## 2026-07-19 — Prüfstand Pipeline Failure: pgvector Aliasing + SSE Error Swallowing (v0.4.3)

### Problem

The Prüfstand goldset demo analysis never produced output for any golden case.
Every run showed `Pipeline abgeschlossen, aber keine Ausgabe erhalten.` instead
of results. Two bugs combined to cause this:

1. **pgvector column aliasing mismatch (primary):** The SQLite backend in
   `app/db/vector_backend.py` aliases dotted `extra_columns` (e.g.
   `"lc.text_content"` → `"lc.text_content AS lc_text_content"`), so the row
   dict key is `lc_text_content`. The pgvector backend did NOT alias — it just
   did `cols.extend(extra_columns)`, producing row dict key `text_content`
   (no `lc_` prefix). But `app/services/retrieval.py` accesses
   `row["lc_text_content"]` in all retrieval functions. On PostgreSQL
   (production): `KeyError: 'lc_text_content'` at retrieval stage. On SQLite
   (tests): works fine. This is why tests passed but production failed — a
   classic dialect-specific bug.

2. **Prüfstand SSE error swallowing (secondary — the "blackbox"):** The
   Prüfstand demo's SSE handler in `static/app.js` threw
   `new Error(event.detail)` inside the same `try` block as `JSON.parse`, and
   the `catch` only re-threw errors whose message contained the literal string
   `'Pipeline'`. Since real backend errors (e.g.
   `"Stage 'retrieval' failed: 'lc_text_content'"`) don't contain 'Pipeline',
   they were silently logged to console and the user saw the generic
   "keine Ausgabe erhalten" message instead of the actual failure reason.

### Changes

- **`app/db/vector_backend.py`** — `_cosine_distance_pgvector()` now aliases
  dotted `extra_columns` the same way the SQLite backend does: columns without
  ` AS ` get ` AS {col.replace(".", "_")}` appended; columns with ` AS ` pass
  through unchanged. This ensures both backends produce identical row-dict key
  structure.
- **`static/app.js`** — Restructured the Prüfstand demo SSE handler
  (`startDemoAnalysis`) to separate JSON parsing from event handling. `JSON.parse`
  errors are caught and logged without swallowing subsequent events. Pipeline
  error events (`event.error`) now propagate immediately via `throw new
  Error(event.detail || event.error || 'Pipeline fehlgeschlagen')` outside the
  parse try/catch. Same fix applied to the drain-buffer section. The main
  analyze endpoint already handled this correctly.
- **`tests/unit/test_vector_backend_aliasing.py`** — New regression test file
  (6 tests) verifying: (a) pgvector aliases dotted columns, (b) multiple
  columns aliased, (c) pre-aliased columns pass through, (d) no extra columns
  case, (e) SQLite reference aliasing, (f) cross-dialect consistency — both
  backends produce the same aliased SQL for the same input.

### Verification

- 6 new regression tests pass (`pytest tests/unit/test_vector_backend_aliasing.py`)
- Full unit suite: 800 passed, 6 new tests pass, 10 pre-existing failures
  unrelated to this fix (text_hash column, disclaimer version, stale mock
  signature — all fail identically on unmodified code)
- `ruff check` + `ruff format --check` + `mypy` all clean on changed files

---

## 2026-07-19 — Corpus Update: Fix btree index size limit with text_hash (v0.4.2)

### Problem

Corpus ingestion on PostgreSQL failed with `ProgramLimitExceededError: index
row size 2728 exceeds maximum 2704 for btree` on large legal chunks (e.g., BGB
§ 309 with 8643+ chars). The unique constraint on
`(source_id, hierarchy_path, text_content)` created a btree index entry larger
than PostgreSQL's v4 btree maximum row size of ~2704 bytes.

### Changes

- **`app/db/models.py`** — Added `text_hash: Mapped[str]` column (String(64)) to
  `LegalChunk`. Changed `UniqueConstraint` from
  `(source_id, hierarchy_path, text_content)` to
  `(source_id, hierarchy_path, text_hash)`.
- **`app/services/corpus.py`** — `_get_or_create_legal_chunk()` now computes
  `text_hash = hashlib.md5(text_content.encode("utf-8")).hexdigest()` and queries
  on `text_hash` instead of `text_content`. The hash is passed to the
  `LegalChunk` constructor.
- **`app/main.py`** — Updated PostgreSQL migration target from
  `006_add_intake_and_legal_areas` to `011_pg_legal_chunk_text_hash`.
- **Migrations:**
  - `alembic/versions/011_pg_legal_chunk_text_hash.py` — PostgreSQL migration
    using built-in `md5()` function for backfill.
  - `alembic/versions/011_sqlite_legal_chunk_text_hash.py` — SQLite migration
    using `hashlib.md5()` and `batch_alter_table` for constraint changes.

### Verification

All lint/format checks pass.

---

# Changelog

All notable changes to the Citizen project are documented in this file.
Newest entries first. Dates in ISO 8601.

---

## 2026-07-19 — Corpus Update: pgvector Upsert Fix (v0.4.1)

### Problem

After the batch embedding fix (v0.4.0), embeddings generated successfully but
the DB upsert stage failed with `DatatypeMismatchError: column "embedding" is
of type vector but expression is of type bytea`. Root cause: the
`ChunkEmbedding.embedding` ORM column is mapped as `LargeBinary` (BYTEA) for
dialect portability, but the actual PostgreSQL column is pgvector `Vector`
type. The ORM `insert()` sent data as `$3::BYTEA`, which PostgreSQL rejected.
This was a pre-existing bug masked by the 900s timeout — the embedding stage
never completed before, so the upsert stage was never reached.

### Changes

- **`app/services/corpus.py`** — Rewrote `_upsert_embedding()` PostgreSQL path
  to use raw SQL with explicit `(:vec)::vector` cast, matching the proven
  pattern in `vector_backend.py`. Serializes the embedding as a pgvector
  literal string `"[0.1, 0.2, ...]"` and casts with `::vector`. SQLite path
  unchanged (ORM insert with `struct.pack` blob). Added verbose debug logging
  to both paths. Added INFO log at start of `upsert_chunks` showing backend
  and total. Added try/except per chunk with detailed error logging
  (source_type, hierarchy_path, text_content_len).

### Verification

- All 27 corpus/router unit tests pass.
- VPS deployment: 939 chunks (sgb2 + sgbx) scraped → embedded in ~2s →
  upserted to pgvector in ~5s. Clean logs, no errors.

---

## 2026-07-19 — Corpus Update: Batch Embedding API + Granular Progress (v0.4.0)

### Problem

Corpus updates with ~8582 text blocks timed out after 900s. Root cause:
`get_embeddings_batch()` sent N individual HTTP requests at concurrency=2
(8582/2 × ~0.3s ≈ 1287s > 900s). The frontend showed only a static
"8582 Textblöcke werden verarbeitet" with an indeterminate progress bar —
no per-chunk progress during embedding or upsert stages.

### Changes

- **`app/core/router.py`** — Rewrote `get_embeddings_batch()` to use the
  OpenRouter batch embedding API (`input: [str, ...]` in a single request).
  Added private `_embed_batch_api()` helper that sends a batch and parses
  the `data` array (sorted by `index` field). New parameters:
  `batch_size` (default `settings.EMBEDDING_BATCH_SIZE` = 64),
  `concurrency` (default `settings.EMBEDDING_BATCH_CONCURRENCY` = 4),
  `progress_cb` (async callback `(done, total) -> None` invoked after each
  batch). With batch_size=64, 8582 chunks → 134 batch requests instead of
  8582 individual requests (~64x reduction in HTTP round-trips).
- **`app/core/config.py`** — Added `EMBEDDING_BATCH_SIZE: int = 64` and
  `EMBEDDING_BATCH_CONCURRENCY: int = 4`. Increased
  `CORPUS_INGESTION_TIMEOUT_SEC` from 900 (15 min) to 1800 (30 min) as a
  safety net.
- **`app/services/corpus.py`** — `generate_embeddings()` and
  `upsert_chunks()` now accept an optional `progress_cb` parameter.
  `upsert_chunks` calls the callback every 25 chunks.
- **`app/api/routes/corpus.py`** — `_run_corpus_update()` passes async
  callbacks that update `_job_store[job_id]` with `chunks_embedded` and
  `chunks_upserted` counters during the respective stages.
- **`static/app.js`** — `updateCorpusProgress()` and
  `updateSettingsProgress()` now show `done / total (pct%)` during
  embedding and upsert stages, with a determinate progress bar (width
  set to percentage) instead of the indeterminate animation.
- **Tests** — Updated `test_router.py` batch test to return a proper
  batch response (3 embeddings with `index` fields). Added
  `test_progress_callback_invoked` test. Updated `test_corpus_endpoint.py`
  and `test_corpus.py` mock signatures to accept new kwargs.

### Impact

- 8582 chunks: ~134 batch requests at concurrency=4 → ~17s (was ~1287s).
- Progress updates: ~134 (embedding) + ~343 (upsert) = ~477 updates
  (was 3 total — ~159x more granular).
- Zero regressions: all 795 pre-existing-passing unit tests still pass.

---

## 2026-07-19 — Frontend: Chat UI Restyled to Uniform Light Theme (v1.2.0)

### Changes

- **Chat mode (`#chat-mode`) restyled to the app's uniform light theme.** Previously
  the chat mode used a divergent dark theme (`--chat-bg: #1a1a2e`, `--chat-surface:
  #16213e`) with its own layout. The chat now matches Analyze/Settings/Prüfstand:
  - **CSS variables remapped**: All `--chat-*` variables in `:root` now alias the
    uniform `--color-*` tokens (e.g. `--chat-bg: var(--color-background)`,
    `--chat-surface: var(--color-surface)`, `--chat-primary: var(--color-primary)`).
    The legacy dark values are retained as a commented block for traceability. This
    is the lowest-risk way to flip the whole chat to light theme — every existing
    `var(--chat-*)` reference automatically becomes light-themed.
  - **Wrapped chat content in `<main>`** with the same `max-width: 900px; margin: 0
    auto; padding: var(--spacing-xl) var(--spacing-lg)` as the other modes. The
    `<main>` doubles as a two-column flex shell (sidebar + chat-main) with `display:
    flex; gap: var(--spacing-md); min-height: 0;`.
  - **Sidebar and chat-main restyled as `.section`-style surfaces**: white background
    (`var(--color-surface)`), light border (`var(--color-border)`), border-radius
    (`var(--border-radius-lg)`), and box-shadow (`var(--shadow-sm)`). They now look
    like the white card surfaces in Analyze/Settings.
  - **`.chat-header` restyled as a slim in-panel toolbar** (the shared `app-header`
    already provides branding + mode toggle). The `#chat-header` ID is preserved for
    JS. The toolbar has a light surface and a bottom border separating it from the
    messages area.
  - **`.btn-chat-primary` aliased to the standard `.btn-primary` look** (teal
    background, white text, hover lift + shadow). Previously it was a dark-blue
    chat-only button.
  - **Message bubbles restyled**: user bubble uses `var(--color-primary)` (teal) with
    white text; assistant bubble uses `var(--color-surface)` (white) with dark text
    and a light border; system messages use a light teal-tinted background.
  - **Input area restyled**: `.chat-input-container` uses light gray background
    (`var(--color-background)`) with a light border; `.chat-input` uses dark text on
    transparent background.
  - **Doc chips, typing indicator, pipeline progress, collapsible result sections,
    error inline, drag highlight** — all auto-flipped to light theme via the variable
    remap, plus targeted fixes for hardcoded `rgba()` assumptions (code block
    backgrounds, system message borders, error borders, drag-over highlight).
  - **Responsive rules updated**: `#chat-mode main` gets tighter padding on mobile
    (`var(--spacing-md)`) so the chat surface gets more horizontal space.
- **Shared footer now visible in chat mode.** `setAppFooterVisible(false)` changed
  to `setAppFooterVisible(true)` in `switchMode()` for the chat branch (`app.js`).
  The comment above `setAppFooterVisible()` was updated to explain why: the chat
  surface is now light-themed, so a footer bar below it is visually consistent
  rather than clashing with a dark surface.
- **Case Chat (`#case-chat-section`) restyled to the same light theme.** The case
  chat is embedded in the Analyze mode and previously used the same dark `--chat-*`
  variables. It now matches the light theme via the variable remap, plus:
  - **`.case-chat-layout` height fixed**: was `height: 100vh` which overflowed the
    analyze-mode section (it took the full viewport height, ignoring the shared
    header and footer). Now `height: 600px; min-height: 400px;` so it fits inside
    its section with internal scrolling in the messages area. Mobile gets `500px`.
  - **`.case-sidebar` and `.case-main` restyled as `.section`-style surfaces**
    (white, bordered, rounded, shadowed). Their `height: 100vh` was also fixed to
    `height: 100%` so they fill the `.case-chat-layout` container instead of the
    viewport.
- **Version bump**: `static/index.html` → 1.2.0, `static/style.css` → 1.2.0,
  `static/app.js` → 1.2.0.

### Verification

- All chat-mode element IDs preserved (19 IDs in `#chat-mode`, 14 IDs in
  `#case-chat-section`) — verified via grep.
- All JS-toggled classes (`hidden`, `active`, `open`, `drag-over`, `uploading`)
  still work — the `#chat-mode.drag-over .chat-messages` descendant selector
  still matches with the new `<main>` wrapper.
- No `var(--chat-*)` reference points at a dark color — all `--chat-*` variables in
  `:root` now alias `--color-*` tokens or use light-theme literals.
- `setAppFooterVisible(true)` is now called for all four modes (analyze, chat,
  settings, pruefstand).
- No backend Python code, routes, or API contracts were modified.

---

## 2026-07-19 — Frontend: Uniform Shared Header/Footer (v1.1.0)

### Changes

- **Shared app header**: Extracted the per-mode `<header>` blocks (previously duplicated
  in `#analyze-mode`, `#settings-mode`, `#pruefstand-mode` with divergent structure and
  styling) into a single shared `<header class="app-header">` as the first child of `#app`.
  All four modes now render the identical dark-gradient header with the `rechtsstand`
  indicator, `profile-banner`, and 4-button `mode-toggle` (Analysieren / Prüfstand /
  Chat / Einstellungen). Eliminates the root cause of header divergence. (D-011)
- **Shared app footer**: Consolidated the per-mode footers into a single
  `<footer id="app-footer">` with `id="footer-profile"`. Version text bumped to
  `Citizen v1.1.0`. Footer is hidden in chat mode (the chat surface has its own
  disclaimer line; a second footer bar below the dark chat surface would be visually
  inconsistent).
- **Dynamic subtitle**: The shared header's `#app-subtitle` now updates via `switchMode()`
  in `app.js` based on the active mode. German strings preserved exactly:
  - Analyze: `Legal Reasoning Engine — SGB II Bürgergeld (SGB X, SGG)`
  - Prüfstand: `Prüfstand — Goldset & Evaluierung`
  - Chat: `Citizen Chat — Konversation & RAG`
  - Settings: `Einstellungen`
- **CSS cleanup**: Removed divergent `#pruefstand-mode` container/header/main/footer/
  subtitle overrides that gave Prüfstand a light "paper" header. Prüfstand now inherits
  the uniform app shell. The warm-paper design tokens and `.pruefstand-*` component
  styles (badges, gallery, cards) are preserved — those are content styles, not layout
  chrome. Added `#app` flex layout so the shared header/footer flank the active mode
  container; chat-mode flex/height adjusted to work within that shell.
- **app.js cleanup**: Removed the `footerProfilePruefstand` element ref and its
  references in `fetchActiveProfile()`. Removed the per-header mode-button wiring
  (`#settings-mode .mode-btn, #pruefstand-mode .mode-btn` query) since those buttons
  no longer exist. Added `MODE_SUBTITLES`, `setModeSubtitle()`, and
  `setAppFooterVisible()` helpers in `switchMode()`.
- **Version bump**: `static/index.html` → 1.1.0, `static/style.css` → 1.1.0,
  `static/app.js` → 1.1.0.

### Verification

Verified locally with Playwright (no backend, static file server):
- No duplicate IDs in the DOM (excluding the pre-existing `analyze-btn` dupe from v1.0.0).
- Shared header renders identically across all 4 modes: same dark gradient
  (`linear-gradient(135deg, #1a5f7a 0%, #124859 100%)`), same text color, same box-shadow.
- `rechtsstand-indicator` and `profile-banner` elements present and visible in all modes
  (including Prüfstand, where they were previously missing).
- All 4 mode buttons present with correct German labels; mode switching works.
- Subtitle updates correctly per mode.
- Footer visible in analyze/pruefstand/settings, hidden in chat mode.
- Chat-mode layout is full-height with no page scroll (body height == viewport height).
- Responsive: at 640px width, `.header-top` switches to `flex-direction: column`
  and `.mode-toggle` centers.

## 2026-07-19 — Production Bugfixes

### Fixes

- **Embedding API 404**: `.env.example` had `EMBEDDING_MODEL=text-embedding-3-small` (missing `openai/` prefix). OpenRouter requires the full provider-prefixed model name. Fixed to `openai/text-embedding-3-small`. (D-008)
- **Prüfstand tab UI crash**: `fetchGoldset()` called `handleApiError()` on non-OK responses, which triggered `showDisclaimerModal()` → hid the entire `#app` container. Fixed by handling errors gracefully within the Prüfstand view without cascading to the disclaimer modal. (D-009)
- **Goldset SSE timeout**: The nginx config only had 180s `proxy_read_timeout` for `/api/v1/analyze`. The Prüfstand demo endpoint (`/api/v1/goldset/{case_id}/analyze`) fell through to the generic `/` location with default 60s timeout, cutting off SSE streams before the deepseek-r1 pipeline (5+ LLM calls) could complete. Added a dedicated `/api/v1/goldset` nginx location with 300s timeout and `proxy_buffering off`. Updated DEPLOYMENT.md. (D-010)
- **No progress indicator**: Demo progress stages showed static icons (○/◉/✓) with no animation to indicate active work. Added CSS `@keyframes demo-pulse` animation on the active stage icon for a visible pulsing indicator.

## 2026-07-13 — Release v1.0.0

### Production Deployment (2026-07-13)
- Deployed to VPS (37.60.240.152) at https://workbench.gronowski.cc
- PostgreSQL 16 + pgvector via Docker Compose, nginx reverse proxy, Let's Encrypt TLS
- Fixed missing dependencies: `asyncpg>=0.29.0`, `pgvector>=0.3.0` (D-001, D-002)
- Fixed migration DAG branch targeting: PostgreSQL targets `006`, SQLite targets `heads` (D-004)
- Applied missing schema columns from SQLite-branch migrations 008–010: `regime`, `notes`, `pii_mapping` (D-005)
- Fixed alembic startup deadlock: migrations now run in subprocess instead of `asyncio.to_thread` (D-006)
- Created DEPLOYMENT.md and DECISIONS.md

### Citizen v1.0.0
Local-first, evidence-constrained legal reasoning engine for German social law (SGB II).

- **21 work packages** across 6 phases (WP-00 through WP-54)
- **9-stage pipeline**: normalization, classification, decomposition, retrieval, construction,
  verification, generation, adversarial review, calculation check
- **37 API endpoints** across 14 route modules
- **802 unit tests** (0 failures, 0 mypy errors)
- **13 shared UI components** (Prüfstand + Result Report + Demo)
- **Key deterministic kernels**: Fristen engine (85 tests), calculation engine (200 tests),
  quote verification, intertemporal regime selection, OCR quality gate
- **Safety guardrails**: pseudonymization gate, egress guard with inference profiles,
  document generator guardrail (verified + confirmed claims only)
- **Goldset-driven eval**: v0.1.0 (10 cases) → v0.2.0 (12 cases with PII annotations)
- **4 retrieval levers**: tightened threshold, per-question mode, §-reference direct lookup,
  always-on hybrid RRF fusion

### Versioning
- **Canonical version**: `pyproject.toml` → `v1.0.0`
- **Frontend**: `index.html` (v1.0.0), `app.js` (v1.0.0), `style.css` (v1.0.0)
- **Database**: 13 ORM models, 10 migrations (001–010)

---

## 2026-07-13 — WP-50/51: Test suite + mypy hardening

### WP-50: Test audit
- Full suite: **802 passed, 3 skipped, 0 failures**
- Fixed 44 test errors from WP-00.5 client consolidation migration
- All `_get_client` references migrated to `app.core.router.get_shared_client`

### WP-51: mypy strict
- **0 mypy errors** across entire `app/` package
- 18 files fixed: added missing generic type parameters (`dict` → `dict[str, Any]`, `Pattern` → `Pattern[str]`),
  renamed shadowed variables, added return type annotations, dialect-dependent import `# type: ignore` annotations
- Installed `types-PyYAML` stub package
- 0 ruff errors (pre-existing only)

---

## 2026-07-13 — WP-20: Retrieval remediation (levers 1-4)

### WP-20: Retrieval improvements
- **Lever 1**: Tightened `MAX_COSINE_DISTANCE` 0.95 → 0.55 (was effectively no filter)
- **Lever 2**: Switched default `RETRIEVAL_MODE` from "combined" to "per_question"
- **Lever 3**: Added `retrieve_chunks_by_norm_reference()` — extracts § references from
  input text, queries `legal_chunk.hierarchy_path` directly, returns exact matches with `distance=0.0`
- **Lever 4**: Added `_rrf_fuse()` — Reciprocal Rank Fusion for always-on hybrid
  vector+keyword search (was fallback-only); keyword search now runs alongside every vector query
- **Files**: `app/core/config.py`, `app/services/retrieval.py`

---

## 2026-07-13 — WP-12: Deterministic quote verification

### WP-12: Quote verification
- Enhanced `app/services/verification.py` (v0.1.0 → v0.2.0):
  - Added hyphenation-normalized matching as third strategy (exact → whitespace → hyphenation)
  - Changed `verified` bool to `verification_status` string: `"exakt"`, `"normalisiert"`, `"unverifiziert"`
  - Backward-compatible: `verified` computed field preserved alongside `verification_status`
- Added `compute_quote_verification_rate()` to `eval/metrics.py`
- Added `quote_verification_rate` to `CaseMetrics`, aggregate, regression gate
- 55 unit tests (47 verification + 8 eval metrics)

---

## 2026-07-13 — WP-23: Calculation engine expansion

### WP-23: Calculation engine
- Extended `app/services/rules_engine.py` (v0.1.0 → v0.2.0):
  - Added `_OLD_FREIBETRAG_BRACKETS` for pre-2023-07-01 (pre-Bürgergeld)
  - Added `_select_bracket_table()` — regime-aware bracket selection
  - Added `compute_bedarf()` — total Bedarf: Regelbedarf + KdU + Mehrbedarfe
  - Added `ReconciliationLineItem` dataclass
  - Added `reconcile_bedarf_einkommen()` — full Bedarf-vs-Einkommen reconciliation
  - Added `detect_additionsfehler()` — arithmetic error detection (GS-010)
  - Added `aggregate_months()` — multi-month aggregation
  - Extended `process_extraction()` with reconciliation + additionsfehler checks
- Added `compute_reconciliation_exact_match()` to `eval/metrics.py`
- 200 total tests (67 new)

---

## 2026-07-13 — WP-24: Intertemporal law selection

### WP-24: Regime selection
- Created `app/services/regime.py` (193 lines):
  - `legal_regime(date)` — maps dates to 4 regime tags (a.F._vor_2023, a.F._2023, a.F._2025, n.F._2026)
  - `regime_transition_dates()` — returns key reform dates
  - `regime_for_period_range()` — handles period-splitting across 2026-07-01 boundary
  - `regime_banner()` — human-readable German regime description
- Modified `app/services/parameter_store.py`: `param()` accepts optional `regime` kwarg
- Modified `app/core/pipeline.py`: `PipelineState.legal_regime_banner`, injected into
  construction/generation prompts
- 40 tests

---

## 2026-07-13 — WP-30: Pseudonymization gate

### WP-30: Pseudonymization
- Created `app/services/pseudonymization.py` (923 lines):
  - Hybrid detection: regex for structured IDs (BG-Nummer, Aktenzeichen, SV-Nummer, Steuer-ID,
    IBAN, phone, email, street+number, PLZ, birth dates) + spaCy NER + first-name gazetteer +
    salutation heuristics
  - `PiiMapping` dataclass with `to_dict()`/`from_dict()` for DB serialization
  - `pseudonymize()`, `depseudonymize()`, `depseudonymize_tolerant()`
  - Correctly preserves: city names, Bundesländer, authority names, dates, EUR amounts, §§ references
- Added `pii_mapping` JSONB column to `CaseRun` (migration 010)
- Added `PSEUDONYMIZATION_ENABLED: bool = True` config setting
- Integrated into pipeline: pseudonymize before LLM calls, depseudonymize after
- 46 tests

---

## 2026-07-13 — WP-32: Goldset v0.2.0

### WP-32: Goldset v0.2.0
- Created `eval/goldsets/goldset-v0.2.0.yaml`: 12 cases
  - All 10 v0.1.0 cases with PII annotations (person, address, bg_nummer entries)
  - GS-011: OCR-degraded text with 7 PII types (IBAN, phone, email, address)
  - GS-012: Over-redaction trap (5 negative controls + 3 PII annotations)
- All PII metric functions already present in `eval/metrics.py`
- `eval/runner.py` already had PII fields + `--pii-gate on|off` CLI arg
- 92 goldset/eval/pseudonymization tests

---

## 2026-07-13 — WP-40: Action document generators

### WP-40: Document generators
- Created `app/services/document_generators.py` (839 lines):
  - 4 generators: Widerspruch, Widerspruch (Jahresfrist), § 44 Überprüfungsantrag, § 25 Akteneinsicht
  - `DocumentSlot` / `GeneratedDocument` dataclasses
  - `validate_slot_claim()` guardrail: only verified + user-confirmed claims usable
  - `select_generator()` — Frist-aware selection: open → Widerspruch, lapsed + fehlerhafte RBB →
    Jahresfrist, lapsed → § 44, kein VA → Akteneinsicht
  - Mandatory footer: disclaimer + generation metadata (version, profile, date)
- Created `app/api/routes/documents.py`: `POST /api/v1/documents/generate`,
  `GET /api/v1/documents/generator-options/{id}`
- 52 tests

---

## 2026-07-13 — WP-42: OCR confirmation gate

### WP-42: OCR quality gate
- Recalibrated `app/services/ocr_quality.py` scoring: 30% char integrity, 30% readable words,
  25% German word match, 15% structure
- Garbage/artifact penalties applied as multipliers
- Fixed pipeline test mock for OCR_QUALITY settings
- 12 tests

---

## 2026-07-13 — WP-41: Result Report & Case Journey Redesign

### WP-41: Result Report (Analyze Mode)
- **Frontend HTML** (`static/index.html`):
  - Replaced single `#result-report-content` placeholder div with 9 structured container IDs inside `#result-report-section`:
    `#deadline-banner`, `#result-summary`, `#findings-list`, `#calculation-diff`, `#frist-timeline`, `#traps-list`, `#next-steps`, `#doc-actions`, `#report-footer`
  - Each container is a stable anchor populated individually by JS; empty regions collapse via `:empty { display: none }`
  - Case header with `#report-case-actions` for back/chat buttons
- **Frontend JS** (`static/app.js`):
  - Rewrote `renderResultReport(output, caseRunId)` to populate each container by ID using shared components instead of building one monolithic HTML string
  - Render order per design doc §11.1: DeadlineBanner → SummaryBlock → ClaimList → CalcDiffTable → FristTimeline → TrapCallouts → NextSteps → DocActions → Footer
  - `renderClaimItem(finding, context)` now accepts the context flag (`'report' | 'pruefstand' | 'demo'`) per design doc §2.1 component contract; defaults to `'report'` for backward compatibility
  - Extracted `renderSummaryBlock`, `renderDocActions`, `renderReportFooter` helper functions
  - Fixed broken `elements.resultsSection` references (pointed to non-existent `#results-section`, would throw TypeError in `handleRemoveFile`, `handleUseText`, `handleUpload`, `handleAnalyze`, `handleCaseDelete`) — repointed to `#result-report-section`
  - SSE progress display (`#progress-section`, progress bar, stage indicators) unchanged
- **Frontend CSS** (`static/style.css`):
  - Added WP-41 report styles (additive, appended at end — no modifications to existing rules):
    - `.report-result` container + `.report-region` section spacing with `:empty` collapse
    - `.report-case-header` / `.report-case-title` / `.report-case-actions` layout
    - `.report-section-heading` uppercase label styling
    - `.report-summary` block with green/red/gray verdict variants (`.report-summary-green/red/gray`)
    - `.report-calc-summary` recessed summary line
    - `.report-doc-buttons` / `.report-doc-btn` / `.report-doc-status` / `.report-doc-output` / `.report-doc-rendered` / `.report-doc-text` / `.report-doc-warnings` document generation panel
    - `.report-footer` / `.report-footer-disclaimer` footer styling
    - `.report-error` error state
    - DeadlineBanner red-state pulse animation (`@keyframes report-deadline-pulse`, 2.2s, gated behind `prefers-reduced-motion: no-preference`) per design doc §3.2
    - Responsive rules at `max-width: 639px` for narrow screens
  - All shared components use `.c-` prefix (`.c-deadline-banner`, `.c-claim-list`, `.c-claim-item`, `.c-calc-diff`, `.c-frist-timeline`, `.c-trap-callout`, `.c-next-steps`, `.c-section-chip`); report-specific layout uses `.report-` prefix

---

## 2026-07-13 — WP-14: Prüfstand View (Goldset Browser, Eval Overlay, Demo Mode)

### WP-14: Prüfstand View
- **Backend** (`app/api/routes/goldset.py`, `app/api/routes/eval_reports.py`):
  - `GET /api/v1/goldset` — returns goldset manifest + 10 case summaries as structured JSON
  - `GET /api/v1/goldset/{case_id}` — returns full case detail (input document, findings, citations, calc diff, frist, traps, next steps)
  - `POST /api/v1/goldset/{case_id}/analyze` — triggers the standard 9-stage pipeline on a goldset case's input text, streams SSE
  - `GET /api/v1/eval/reports` — lists versioned eval report summaries (empty array if no reports)
  - `GET /api/v1/eval/reports/{report_id}` — returns full eval report JSON
  - YAML is parsed server-side via `eval/goldset_loader.py`; no YAML raw text ever appears in API responses
  - Goldset path and eval results dir configurable via `GOLDSET_PATH` / `EVAL_RESULTS_DIR` settings
  - File-mtime caching on goldset loads to avoid re-parsing on every request
  - Fixed 4 UP038 lint errors (use `int | float` instead of `(int, float)` in isinstance calls)
- **Frontend HTML** (`static/index.html`):
  - 4th mode toggle button "Prüfstand" in header alongside Analyze, Chat, Settings
  - `#pruefstand-mode` container with header, gallery, detail, and demo comparison sections
  - Version bumped to 1.0.0
- **Frontend JS** (`static/app.js`):
  - `fetchGoldset()` — loads goldset manifest, renders header + gallery
  - `fetchGoldsetCase(caseId)` — loads case detail, renders two-column layout
  - `fetchEvalReports()` — loads eval reports, renders aggregate tile or "Noch keine Prüfläufe" empty state
  - `startDemoAnalysis(caseId)` — POSTs to pipeline endpoint, streams SSE, renders comparison view
  - `renderPruefstandHeader(data)` — badges, baseline cards (Regelbedarf, § 11b Treppengrafik, Sanktionen, FristTimeline), open questions
  - `renderCaseGallery(cases)` — responsive grid of cards with verdict color bars
  - `renderCaseDetail(case)` — two-column: LetterRender (Behördenbrief) left, findings/calc/frist/traps/steps right
  - `renderEvalOverlay(reports)` — latest eval tile or clean empty state
  - `renderDemoComparison(caseData, pipelineResult)` — expected vs actual side-by-side
  - `renderFristTimelineSVG(frist, isFull)` — inline SVG timeline with 4 stations, delta labels, rollover arc
  - `renderDeadlineBanner(frist)` — 5-state hero (normal, amber, red, lapsed, kein VA)
  - `renderCalcDiffTable(rows)` — Jobcenter vs Korrekt vs Differenz with ▲/▼/— glyphs
  - `renderClaimItem(finding)` — traffic-light finding with § chips
  - Formatting helpers: `formatDate()`, `formatDateTime()`, `formatEuro()` (German locale)
  - Version bumped to 1.0.0
- **Frontend CSS** (`static/style.css`):
  - Warm-paper design tokens per `devdocs/design_v1.0.0.md` (additive — no regression to existing vars)
  - Component classes prefixed `c-` per design spec §15.2: `c-letter-render`, `c-deadline-banner`, `c-frist-timeline`, `c-claim-list`, `c-claim-item`, `c-section-chip`, `c-calc-diff`, `c-trap-callout`, `c-next-steps`, `c-eval-overlay`
  - § 11b Treppengrafik (step graphic) for Freibeträge baseline card
  - Responsive: gallery 1-col <640px, 2-col tablet, auto-fill desktop; detail stacks <768px
  - Version bumped to 1.0.0
- **Design system** (`devdocs/design_v1.0.0.md`):
  - 13-component shared library spec (DeadlineBanner, FristTimeline, ClaimList, ClaimItem, SectionChip, CalcDiffTable, NextSteps, TrapCallout, LetterRender, ExperimentalBadge, EvalOverlay, SummaryBlock, ConfidenceRibbon)
  - Warm-paper light theme as v1.0.0 default (D-2)
  - 4 locked decisions: +4-day Bekanntgabefiktion (D-1, goldset-authoritative), warm-paper default (D-2), Chat parked (D-3), spec persisted (D-4)

## 2026-07-12 — WP-21: Deterministic Fristen engine

### WP-21: Fristen engine
- `app/services/fristen.py` — pure, deterministic Widerspruchsfrist calculator:
  - `compute_widerspruchsfrist()` — main public function with 7 rule-stages:
    1. Non-VA check (§ 31 SGB X → `frist_typ="kein_va"`)
    2. Bekanntgabe fiction (§ 37 Abs. 2 SGB X, post-2025 reform: +4 days)
    3. Jahresfrist for missing/wrong RBB (§ 66 Abs. 2 SGG)
    4. 1-month Monatsfrist (§ 84 Abs. 1 SGG + § 188 Abs. 2 BGB)
    5. Workday rollover (§ 64 Abs. 3 SGG)
    6. OQ-1 flag (ambiguous 4-day fiction on weekends/holidays)
    7. Bundesland-specific holiday table (fixed + movable holidays 2024-2027)
  - `FristResult` dataclass with `bekanntgabe`, `frist_ende`, `frist_typ`,
    `rollover_applied`, `oq1_flag`, `oq1_alternate_ende`, `explanation_de`
  - Holiday tables: all fixed holidays per Bundesland, movable holidays
    (Karfreitag, Ostermontag, Christi Himmelfahrt, Pfingstmontag, Fronleichnam)
    computed from Easter dates 2024-2027
- `tests/unit/test_fristen.py` — 85 test cases covering all code paths,
  edge cases, and all 10 goldset cases (GS-001 through GS-010)
- `eval/metrics.py` — `compute_frist_exact_match()` now calls the Fristen engine
  against goldset widerspruchsfrist expectations instead of returning None
- `eval/runner.py` — Fristen column added to eval table output; `frist_exact_match`
  included in per-case metrics and aggregate computation

## 2026-07-12 — WP-22: Legal parameter store completion

### WP-22: Legal parameter store
- `app/db/models.py`: Added `regime` (String(50)) and `notes` (Text) columns to `LegalParameter`
- `alembic/versions/009_add_regime_and_notes_to_legal_parameter.py`: Migration adding both columns
- `app/services/parameter_store.py`: Added synchronous `param()` function backed by in-memory cache; added `reload_parameter_cache()` called at startup; extended `get_parameter_numeric()` / `get_parameter_json()` to return `"status": "verification_required"` for proposed rows with notes
- `app/main.py`: Lifespan now imports `async_session_factory` and calls `reload_parameter_cache()` after migrations
- `scripts/seed_legal_parameters.py`: Seeds 27 parameters (SGB II) — Regelbedarf 2024/2025, §11b brackets, Vermögensfreibeträge a.F., Vermögensfreibeträge n.F. (OQ-3/proposed), Sanktionen a.F. and n.F.
- `app/api/routes/meta.py`: Added `GET /api/v1/meta/legal-timestamp` returning `parameter_freshness` and `corpus_freshness`
- `static/index.html`: Added "Rechtsstand" indicator in analyze mode header
- `static/app.js`: Added `fetchRechtsstand()` — calls legal-timestamp endpoint, formats DD.MM.YYYY, applies warning (>90d) or stale (>180d) style
- `static/style.css`: Added `.rechtsstand*` styles and `.header-actions` wrapper

## 2026-07-12 — Phase 0 (Ground Truth) complete

### WP-11: Eval harness
- `eval/pipeline_adapter.py` — `PipelineOutput` dataclass + `run_pipeline_for_case()` adapter that drains SSE generator
- `eval/extractors.py` — deterministic norm reference, citation, assessment, calculation, and issue extractors (regex-based, no LLM)
- `eval/metrics.py` — `compute_issue_recall`, `compute_citation_precision`, `compute_calculation_exact_match`, `compute_frist_exact_match` (N/A until WP-21), `compute_assessment_match`
- `eval/runner.py` — CLI entry point (`python -m eval.runner`), per-case + aggregate tables, JSON report save, regression gate integration
- `eval/regression_gate.py` — per-case monotonic gate (D-6): strict on deterministic metrics, warn-only on LLM metrics
- Results stored as versioned JSON in `eval/results/`, not DB (YAGNI until WP-14 Prüfstand)

### WP-00: Repo inventory & gap report
- `devdocs/ARCHITECTURE-ACTUAL.md` — full module, pipeline, DB, LLM, config, and frontend map
- `devdocs/GAP-REPORT.md` — 13 gaps found vs roadmap §1 assumptions (G-001 through G-013)

### WP-00.5: Client consolidation + STAGE_NAME_ALLOWED fix
- Replaced 4 separate `OpenRouterClient` singletons with single shared factory in `router.py`
- Added `contextvars.ContextVar("case_id")` for future egress guard (WP-31)
- Updated 5 service modules (`reasoning.py`, `chat_reasoning.py`, `intake.py`, `case_chat.py`, `calculation.py`)
- Consolidated `main.py` shutdown to single `close_client()`
- Fixed `STAGE_NAME_ALLOWED` in `models.py` — removed `disclaimer_ack`, added `adversarial_review` and `calculation_check`
- Created `alembic/versions/008_fix_stage_name_allowed.py` migration

### WP-01: Baseline v0.1.0
- Tagged `v0.1.0` (canonical version from `pyproject.toml`)
- Created `.github/workflows/ci.yml` — lint, type-check, unit + integration tests on Python 3.11/3.12
- Created `devdocs/DECISIONS.md` — 10 ratified decisions, 3 open

### WP-02: Scope cut — Sozialrecht-only
- Added `LEGAL_AREA_TIER` dict in `models.py` + frontend
- Experimental badge on all non-Sozialrecht areas in intake UI
- Updated subtitle: "SGB II Bürgergeld (SGB X, SGG)"
- `.experimental-badge` CSS styling (amber, uppercase, tooltip)

### WP-10: Goldset integration
- Copied `goldset-v0.1.0.yaml` (10 cases) into `eval/goldsets/`
- Created `eval/goldset_loader.py` — Pydantic-typed YAML loader with audit function
- Validates against `LEGAL_AREA_ALLOWED`, case ID uniqueness, known assessment values
- Added `PyYAML` to project dependencies

---

## 2026-07-12 — v1.0.0 UI/UX design direction approved

### Added
- `devdocs/design_v1.0.0.md` — comprehensive UI/UX design specification for the v1.0.0
  release. Covers four work packages: WP-02 (Scope Cut / Experimental Badge), WP-14
  (Prüfstand View), WP-41 (Result Report & Case Journey Redesign), WP-42 (OCR
  Confirmation Gate). Defines a 13-component shared library, color token system, the
  FristTimeline showpiece, DeadlineBanner 5-state hero, ClaimList, CalcDiffTable,
  OCR confidence gate, accessibility and responsive strategy.

### Decisions locked (design review)
- **D-1: Bekanntgabefiktion = +4 days** (strict goldset conformity). The goldset is the
  executable specification for all legal behavior — § 37 Abs. 2 SGB X is rendered as posting_date
  + 4 days. FristTimeline renders "+4 Tage Fiktion".
- **D-2: Warm-paper light theme** is the v1.0.0 default. Dark theme preserved as
  `[data-theme="dark"]` opt-in toggle. Unifies the current split light (Analyze) /
  dark (Chat) personality.
- **D-3: Chat mode parked but accessible.** Removed from primary mode toggle
  (Analysieren · Prüfstand · Einstellungen); reachable via secondary menu / direct route.
  Existing sessions preserved. No regression.
- **D-4: Design spec persisted** to `devdocs/design_v1.0.0.md` as implementation
  reference.

### Notes
- No code changes yet — this is design/strategy only. Implementation pending alignment
  on component build order.
- Typography direction: Source Serif 4 (headings) + Atkinson Hyperlegible (body) +
  IBM Plex Mono (numbers/§ chips). All Google Fonts, full German diacritic support.
- The existing `style.css` (v0.3.0, 2845 lines) will be refactored incrementally — no
  big-bang rewrite (regression risk). New component classes prefixed `c-`, tokens in
  `:root`.

---

## 2026-07-12 — WP-31: Inference profile layer + egress guard

### WP-31: Inference profiles + egress guard
- `config/inference_profiles.yaml` — versioned inference profiles (eu-avv, extern-openrouter, on-prem)
  with per-stage model/temperature overrides, host allowlists, compliance settings
- `app/services/inference_profiles.py` — `InferenceProfile` dataclass, `load_profiles()`,
  `get_active_profile()`, `validate_profile()`, and `reset_profile_cache()`
- `app/core/router.py` — `EgressBlockedError` exception, `_egress_check()` function with
  host allowlist enforcement + PII scan (casefolded + diacritics-normalized matching),
  wired into `chat_completion()`, `chat_completion_stream()`, and `get_embedding()`
- `app/core/config.py` — `INFERENCE_PROFILE` (default: `"eu-avv"`) and `AVV_OVERRIDE` settings
- `app/services/pseudonymization.py` — `get_known_values()` helper for egress guard
- `app/core/router.py` — `set_pii_context()` / `get_pii_context()` contextvars for
  passing PiiMapping to the egress guard
- `app/main.py` — startup validation: loads active profile, validates, logs warnings
- `app/api/routes/meta.py` — `GET /api/v1/meta/active-profile` endpoint with profile
  name, label, avv_status, pseudonymization
- Frontend: profile banner in header (green for signed, amber for not-signed), profile
  info in footer, `fetchActiveProfile()` JS function
- `tests/unit/test_inference_profiles.py` — 19 tests: YAML loading, profile resolution,
  AVV gate (blocked/allowed/override), disabled profile, validate warnings
- `tests/unit/test_egress_guard.py` — 21 tests: host allowlist, PII scan (block/pass/empty),
  casefold/diacritics matching, no cleartext in errors, client integration
