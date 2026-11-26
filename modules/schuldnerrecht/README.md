# Schuldnerrecht 0.2.0 — backend implementation

Experimental own-matter module; no default loading, no verified promotion.
Human reviews are deferred under D-071. The implementation includes:

- Two domestic court-response rules based on confirmed actual service. Foreign
  and public service, missing facts and missing region require further input.
  The initial Mahnbescheid period is not an absolute exclusion of opposition.
- Monthly attachment and P-account checks using 2025/2026 annual parameters.
  Qualified ordinary/titled limitation and conservative collection-cost checks
  use the documented date range. Missing legal qualifications produce no result.
- Five guarded action drafts, module-specific inference profile, public intake
  schema, appointment checklist/questions and DE/EN/de-LS plain-language copy.
- Twenty synthetic base/dossier cases, 28 plain cases, arithmetic fixtures and
  local deterministic reports in `goldset/reports/`.

## Deployment preparation

Use the existing configured project environment:

```bash
alembic upgrade head
python -m scripts.seed_module_parameters --module schuldnerrecht --dry-run
python -m scripts.seed_module_parameters --module schuldnerrecht
```

Select `schuldnerrecht` explicitly for requests. It follows existing tier rules
(enabled in dev/self, disabled in provider unless explicitly enabled). Inspect
`GET /api/v1/modules/schuldnerrecht` for capabilities, public intake schema and
current corpus readiness. Intake-form schema is not a replacement for existing
API envelopes or synthetic-document/privacy guards.

The corpus requires `bgb`, `zpo`, `inso`, `rdg`, `rvg`. Use existing explicit
corpus-source/update endpoints with those keys and a separately configured
embedding setup. No deployment corpus or live inference was populated/measured
by this implementation session. Do not bypass readiness checks.

## Offline verification

```bash
python -m scripts.validate_module modules/schuldnerrecht
python -m eval.dossier_eval --module schuldnerrecht
python -m eval.plain_eval --module schuldnerrecht
```

The pipeline evaluator `python -m eval.runner --module schuldnerrecht` is a
live inference/database operation, not an offline smoke check. Follow the
project's separate test-key and bounded-run rules before using it. Its results
are not replaced by deterministic fixture scores or a claimed human approval.
