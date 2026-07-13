# Citizen — Bescheid-Prüfung für deutsches Sozialrecht

**🇬🇧 English version: [README-EN.md](README-EN.md)**

## Rechtsinformation, keine Rechtsberatung — siehe [DISCLAIMER_DE.md](DISCLAIMER_DE.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com)

Citizen ist eine lokale, evidenzgebundene Analyse-Engine für deutsche
Rechtsbescheide — mit verifiziertem Schwerpunkt auf dem Sozialrecht
(Bürgergeld/Grundsicherungsgeld, SGB II/X). Die Software liest eingescannte
Behördenkorrespondenz ein und beantwortet vier Fragen: **Was steht da drin?
Stimmt das? Bis wann muss ich reagieren? Was mache ich jetzt?** Jede Aussage
wird an den Gesetzestext gebunden, jede Berechnung deterministisch
nachgerechnet, jede Frist auf den Tag genau bestimmt — und die Qualität wird
gegen ein öffentliches, versioniertes Golden Set gemessen statt behauptet.

**Warum es dieses Projekt gibt:** [STATEMENT.md](STATEMENT.md) ·
**Kurzfassung:** [One-Pager](docs/citizen-onepager.md)

## Rechtsgebiete

| Gebiet | Gesetze | Status |
|---|---|---|
| **Sozialrecht** (Bürgergeld / Jobcenter) | SGB I, II, III, IX, X, XII | ✅ **unterstützt** — goldset-verifiziert |
| **Erbrecht** | BGB (Erbrecht), ErbStG, HöfeO | ⚠️ experimentell |
| **Schenkungsrecht** | BGB (Schenkung), ErbStG | ⚠️ experimentell |
| **Familienrecht** | BGB (Familienrecht) | ⚠️ experimentell |
| **Mietrecht** | BGB (Mietrecht) | ⚠️ experimentell |
| **Arbeitsrecht** | BGB, KSchG, BUrlG, TVG | ⚠️ experimentell |
| **Vertragsrecht** | BGB (Schuldrecht) | ⚠️ experimentell |
| **Verwaltungsrecht** | VwVfG, SGG | ⚠️ experimentell |
| **Strafrecht** | StGB | ⚠️ experimentell |
| **Andere** | Auffangkategorie | ⚠️ experimentell |

Experimentelle Gebiete sind funktionsfähig, aber nicht verifiziert; sie sind
in Oberfläche und Ausgaben entsprechend gekennzeichnet.

## Kernfunktionen

* **Fall-Journey:** Upload → OCR-Bestätigung → Analyse → Fristen-Banner →
  Befund-Report → Aktionsdokumente. Echtzeit-Fortschritt per SSE.
* **Evidenzgebundene Ausgaben:** Jede Tatsachen- und Rechtsaussage wird über
  `pgvector`-Ähnlichkeitssuche an Gesetzes-Chunks gebunden — mit
  Konfidenzwert, wörtlichem Belegzitat und deterministischer
  Zitat-Verifikation (String-Prüfung gegen den Quell-Chunk; nicht
  verifizierbare Bindungen werden sichtbar als „unverifiziert" markiert).
* **Deterministische Fristen-Engine:** Bekanntgabefiktion (§ 37 Abs. 2 SGB X,
  4 Tage), Widerspruchsfrist (§ 84 SGG), Fristberechnung mit
  Werktag-Rollover (§ 64 SGG), Feiertagskalender je Bundesland, Jahresfrist
  bei fehlerhafter Rechtsbehelfsbelehrung (§ 66 Abs. 2 SGG), Erkennung von
  Nicht-Verwaltungsakten. Vollständig LLM-frei und unit-getestet.
* **Deterministisches Rechenwerk (SGB II):** Vollständige § 11b-Kaskade
  (Brutto-Bemessung, Netto-Absetzung), Bedarf-/Einkommensabgleich,
  Gegenüberstellung „Jobcenter hat gerechnet / korrekt wäre" mit
  centgenauer Differenz. Alle gesetzlichen Beträge stammen aus einem
  versionierten Parameterspeicher mit Geltungszeiträumen.
* **Intertemporale Rechtsauswahl:** Automatische Auswahl alter/neuer
  Rechtslage je Leistungszeitraum (u.a. Reform zum 01.07.2026,
  „Grundsicherungsgeld"), inklusive zeitraumgetrennter Prüfung bei
  Rechtswechseln innerhalb eines Antrags.
* **Golden Set & Prüfstand:** Versioniertes Set verifizierter Prüffälle
  (synthetische Bescheide mit erwarteten Befunden, Berechnungen und
  Fristen) — im UI als „Prüfstand" klickbar aufbereitet, inklusive
  Demo-Modus („Diesen Fall live analysieren") und Eval-Ergebnisansicht.
* **Eval-Harness:** `citizen-eval` führt die echte Pipeline gegen das
  Goldset aus und misst Befund-Erkennung, Zitatpräzision,
  Halluzinationsrate, Rechen- und Fristgenauigkeit. Versionierte Reports,
  Regressions-Gate in der CI.
* **Aktionsdokumente:** Widerspruch, Überprüfungsantrag (§ 44 SGB X) und
  Akteneinsichtsantrag (§ 25 SGB X) als Baustein-Entwürfe — jede
  Rechtsbehauptung im Dokument ist an verifizierte, vom Nutzer bestätigte
  Befunde gebunden; Unbelegtes erscheint als `[BITTE PRÜFEN]`-Platzhalter.
  Unterschrieben wird vom Menschen.
* **Pseudonymisierung & Inferenzprofile:** Direkte Identifikatoren (Namen,
  Adressen, Kennnummern, Kontodaten …) werden vor jeder externen
  Verarbeitung lokal durch typisierte Platzhalter ersetzt und erst in den
  fertigen Dokumenten wieder eingesetzt. Externe Inferenz läuft
  ausschließlich über versionierte Profile (`eu-avv` als Standard für
  Organisationen: nur freigegebene EU-Endpunkte mit AVV; technischer
  Egress-Guard blockiert alles andere). Das aktive Profil wird in UI und
  Dokumenten ausgewiesen.
* **Adversariale Rechtsprüfung:** Mehrperspektivische Gegenprüfung
  („Rechtsprüfungsrat") aus Verteidigungs-, Behörden- und Gerichtssicht.
* **Lokale OCR-Pipeline:** Vollständig lokale Dokumentaufnahme
  (PDF/JPG/PNG/TXT/HTML/EML, bis 25 MB) mit deterministischer
  Fallback-Kette (`pdfplumber` → `PyMuPDF` → `Tesseract`) und
  verpflichtender Nutzer-Bestätigung des erkannten Textes vor der Analyse.
* **Hierarchischer Gesetzeskorpus:** Automatisierter Abruf von 16
  Quelltypen (gesetze-im-internet.de, arbeitsagentur.de), gechunkt auf vier
  Ebenen (Gesetz → § → Absatz → Satz), zur Laufzeit auswählbar;
  „Rechtsstand"-Anzeige mit Aktualitätswarnung.
* **First-Run-Bestätigung:** Analyse erst nach ausdrücklicher, lokal
  protokollierter Kenntnisnahme des rechtlichen Hinweises (Version +
  Prüfsumme); API-seitig durchgesetzt.
* **Audit-Trail:** Jeder Lauf, jede Pipeline-Stufe, jeder Befund und jede
  Evidenzbindung wird in PostgreSQL persistiert.
* **Browserbasierte Oberfläche:** Vanilla HTML/JS/CSS, dunkles Theme,
  deutschsprachig; Modi: Analyse (Fall-Journey), Prüfstand, Einstellungen.

## Architektur

| Ebene | Technologie |
|---|---|
| **Backend** | FastAPI, Uvicorn (SSE-Streaming) |
| **Datenbank** | PostgreSQL 16 + `pgvector` + `tsvector` |
| **ORM / Migrationen** | SQLAlchemy 2.0 (async), Alembic (10 Migrationen) |
| **Frontend** | Vanilla HTML/JS/CSS |
| **LLM-Anbindung** | Versionierte Inferenzprofile (`eu-avv` Standard, `extern-openrouter`, `on-prem`-Slot); Modell je Pipeline-Stufe konfigurierbar; Fallback-Kette |
| **OCR** | pdfplumber → PyMuPDF → Tesseract (deutsch) |
| **Tooling** | ruff (Format & Lint), mypy (strict), pytest (Unit + Integration) |

## Datenbankschema (14 Tabellen)

| # | Tabelle | Zweck |
|---|---|---|
| 1 | `legal_source` | Wurzeldatensatz eines Rechtsdokuments |
| 2 | `legal_chunk` | Hierarchische Gesetzeseinheit (Gesetz→§→Absatz→Satz), mit `legal_area` |
| 3 | `chunk_embedding` | Dichter Vektor (1536d, Cosinus) |
| 4 | `case_run` | Analyse-Sitzung mit Verlauf, Nutzerkorrekturen und PII-Mapping |
| 5 | `pipeline_stage_log` | Unveränderliches Audit je Pipeline-Stufe |
| 6 | `claim` | Atomare Rechtsaussage mit Nutzer-Adjudikation |
| 7 | `evidence_binding` | Verknüpfung Claim ↔ LegalChunk mit Stärke & Zitat |
| 8 | `cache_entry` | Key-Value-Cache (Embeddings, Triage) |
| 9 | `legal_parameter` | Versionierte Rechtsparameter (Regelbedarf, Freibeträge …) mit Geltungszeitraum und Rechtslage |
| 10 | `conversation` | Mehrschrittige Chat-Sitzung |
| 11 | `conversation_message` | Einzelnachricht (user/assistant/system) |
| 12 | `conversation_document` | An Konversation angehängtes Dokument |
| 13 | `intake_session` | Mehrschrittiges Aufnahme-Interview |
| 14 | `case_run_area` | m:n case_run ↔ legal_area |

## 16 unterstützte Gesetzes-Quelltypen

sgb1, sgb2, sgb3, sgb9, sgb12, sgbx, bgb, vwvfg, sgg, weisung, bsg, erbstg,
hoefev, kschg, burlg, tvg

## Voraussetzungen

### Docker-Deployment (empfohlen)

* [Docker](https://docs.docker.com/engine/install/) & [Docker Compose](https://docs.docker.com/compose/install/)
* API-Zugang gemäß gewähltem Inferenzprofil (EU-Anbieter mit AVV für
  `eu-avv`, OpenRouter-Key für `extern-openrouter`)

### Lokale Entwicklung

| Abhängigkeit | Installation (Ubuntu/Debian) |
|---|---|
| Python 3.11+ | `sudo apt install python3.11 python3.11-venv` |
| Tesseract OCR 5.x | `sudo apt install tesseract-ocr libtesseract-dev tesseract-ocr-deu` |
| PostgreSQL 16 + pgvector | `sudo apt install postgresql-16 postgresql-16-pgvector` |
| API-Schlüssel | je nach Inferenzprofil (siehe `.env.example`) |

---

## Schnellstart: Docker Compose

```bash
# 1. Repository klonen
git clone https://github.com/playa77/citizen.git
cd citizen

# 2. Umgebungsdatei anlegen
cp .env.example .env

# 3. .env bearbeiten — mindestens:
#    INFERENCE_PROFILE=eu-avv                (oder extern-openrouter)
#    + Zugangsdaten des gewählten Profils (siehe .env.example)

# 4. Stack bauen und starten
docker compose up -d --build

# 5. Nach Health-Check Migrationen ausführen
docker compose exec citizen-app alembic upgrade head

# 6. Gesetzeskorpus laden (Abruf + Embedding)
#    Hinweis: erfordert bestätigten Disclaimer; Version siehe
#    GET /api/v1/meta/disclaimer/version
curl -X POST http://localhost:8000/api/v1/corpus/update \
  -H "X-Disclaimer-Ack: v1.1.0" \
  -H "Content-Type: application/json" -d '{}'

# 7. App öffnen — beim ersten Start wird die Bestätigung des
#    rechtlichen Hinweises verlangt
#    http://localhost:8000
```

Stoppen:
```bash
docker compose down
```

---

## API-Endpunkte (Auswahl)

| Gruppe | Methode | Pfad | Beschreibung |
|---|---|---|---|
| **ingest** | `POST` | `/api/v1/ingest` | Dokument hochladen und per OCR erfassen |
| **analyze** | `POST` | `/api/v1/analyze` | Vollständige Pipeline ausführen (SSE) |
| **cases** | `GET` | `/api/v1/cases` | Alle Fall-Läufe auflisten |
| **cases** | `GET` | `/api/v1/cases/{id}` | Fall mit Befunden und Evidenz abrufen |
| **cases** | `DELETE` | `/api/v1/cases/{id}` | Fall löschen |
| **cases** | `POST` | `/api/v1/cases/{id}/chat` | Fallgebundener Chat (SSE) |
| **cases** | `POST` | `/api/v1/cases/{id}/reevaluate` | Gezielte Neubewertung einzelner Befunde (SSE) |
| **cases** | `POST` | `/api/v1/cases/{id}/claims` | Befund ergänzen |
| **cases** | `PATCH` | `/api/v1/cases/{id}/claims/{cid}` | Befund bearbeiten |
| **cases** | `POST` | `/api/v1/cases/{id}/adjudicate` | Nutzer-Adjudikation (bestätigen/markieren/korrigieren) |
| **cases** | `GET` | `/api/v1/cases/{id}/export` | Fall exportieren (JSON/Markdown) |
| **documents** | `POST` | `/api/v1/cases/{id}/documents` | Aktionsdokumente erzeugen (Widerspruch, § 44, § 25) |
| **goldset** | `GET` | `/api/v1/goldset` | Goldset-Manifest und Fallliste (Prüfstand) |
| **goldset** | `GET` | `/api/v1/goldset/{case_id}` | Vollständiger Prüffall |
| **goldset** | `POST` | `/api/v1/goldset/{case_id}/analyze` | Prüffall live durch die Pipeline schicken (Demo-Modus) |
| **eval** | `GET` | `/api/v1/eval/reports` | Versionierte Eval-Läufe auflisten |
| **eval** | `GET` | `/api/v1/eval/reports/{id}` | Ergebnisse je Fall/Metrik |
| **conversations** | `GET`,`POST` | `/api/v1/conversations` | Konversationen auflisten/anlegen |
| **conversations** | `GET`,`DELETE` | `/api/v1/conversations/{id}` | Konversation abrufen/löschen |
| **conversations** | `POST` | `/api/v1/conversations/{id}/messages` | Chat-Nachricht senden (SSE) |
| **conversations** | `POST`,`GET` | `/api/v1/conversations/{id}/documents` | Dokumente anhängen/auflisten |
| **corpus** | `POST` | `/api/v1/corpus/update` | Gesetzestexte abrufen + einbetten |
| **corpus** | `GET` | `/api/v1/corpus/status/{job_id}` | Fortschritt der Aktualisierung |
| **corpus** | `GET` | `/api/v1/corpus/health` | Korpus-Zustand (Chunks, Warnungen, Rechtsstand) |
| **corpus** | `GET` | `/api/v1/corpus/available-sources` | Alle Quelltypen auflisten |
| **corpus** | `GET`,`PUT` | `/api/v1/corpus/sources` | Laufzeit-Quellauswahl lesen/setzen |
| **intake** | `POST` | `/api/v1/intake/start` | Aufnahme-Interview starten |
| **intake** | `GET` | `/api/v1/intake/{id}` | Interview-Status abrufen |
| **intake** | `POST` | `/api/v1/intake/{id}/message` | Interview-Antwort senden (SSE) |
| **intake** | `POST` | `/api/v1/intake/{id}/confirm` | Interview-Ergebnis bestätigen |
| **presets** | `GET` | `/api/v1/presets` | Pipeline-Presets auflisten |
| **presets** | `POST` | `/api/v1/presets/suggest` | Preset aus Szenario vorschlagen |
| **presets** | `POST` | `/api/v1/presets/apply` | Preset-Konfiguration anwenden |
| **meta** | `GET` | `/api/v1/meta/disclaimer/version` | Disclaimer-Version |
| **meta** | `GET` | `/api/v1/meta/disclaimer/text` | Vollständiger Disclaimer-Text |
| **meta** | `GET` | `/api/v1/meta/version` | API- und Disclaimer-Versionen |
| **health** | `GET` | `/health` | Liveness-Probe |

Vollständige, interaktive Dokumentation nach dem Start unter `/docs`
(Swagger) und `/redoc`.

## Verzeichnisstruktur

```
citizen/
├── alembic/                              # 10 Migrationen
├── app/
│   ├── api/routes/                       # 12 Routenmodule (analyze, cases,
│   │                                     #  conversations, corpus, documents,
│   │                                     #  eval_reports, goldset, ingest,
│   │                                     #  intake, meta, ocr, presets)
│   ├── core/                             # config, pipeline (SSE), router
│   ├── db/                               # 14 ORM-Modelle, Session, Vektor-Backend
│   ├── middleware/                       # Disclaimer-Durchsetzung, Rate-Limit
│   ├── services/                         # 23 Servicemodule, u.a.:
│   │                                     #  fristen, rules_engine, regime,
│   │                                     #  parameter_store, pseudonymization,
│   │                                     #  inference_profiles, verification,
│   │                                     #  document_generators, retrieval
│   └── utils/                            # image, pdf, text, tokens
├── eval/                                 # Goldsets, Eval-Harness, Reports
├── static/                               # Frontend (Analyse, Prüfstand, Einstellungen)
├── tests/                                # 33 Testdateien (~11.700 Zeilen)
├── docs/                                 # STATEMENT, One-Pager, Datenschutz-Vorlagen
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

## Wichtige Konfiguration

| Kategorie | Einstellung | Standard | Beschreibung |
|---|---|---|---|
| **Inferenz** | `INFERENCE_PROFILE` | `eu-avv` | Aktives Inferenzprofil (`eu-avv` / `extern-openrouter` / `on-prem`) |
| | Profildefinitionen | `config/inference_profiles.yaml` | Endpunkte, AVV-Status, Modell je Stufe, Egress-Allowlist |
| **Pipeline** | `ENABLE_CALCULATION_CHECK` | `True` | Deterministische SGB-II-Rechenprüfung |
| | `PIPELINE_TIMEOUT_SEC` | `120` | Hartes Pipeline-Timeout |
| **Retrieval** | `RETRIEVAL_MODE` | `combined` | Embedding-Strategie |
| | `TOP_K_RETRIEVAL` | `10` | Max. Chunks je Anfrage |
| **Korpus** | `CORPUS_SOURCES` | `["sgb2", "sgbx"]` | Standardquellen (zur Laufzeit änderbar) |
| **Rate-Limit** | `RATE_LIMIT_REQUESTS` / `_WINDOW` | `60` / `60` | Anfragen je Zeitfenster (Sekunden) |
| **OCR** | `ENABLE_OCR_LLM_SYNTHESIS` | `False` | LLM-Synthese der Dual-OCR-Ergebnisse |

Vollständige Liste in `.env.example`.

## Tests ausführen

```bash
# Unit-Tests (ohne Datenbank)
pytest tests/unit/ -v

# Integrationstests (laufende Datenbank erforderlich)
alembic upgrade head
pytest tests/integration/ -v

# Eval gegen das Goldset (Beispiel)
citizen-eval run --goldset v0.2.0 --profile eu-avv \
  --accept-disclaimer v1.1.0 --report eval/reports/

# Codequalität
ruff check app/ tests/
ruff format --check app/ tests/
mypy app/
```

## Sicherheit & Datenschutz

* **Datenhaltung lokal:** Dokumente, Fälle, Befunde, Mappings und Audit-Trail
  verbleiben in der lokalen Datenbank.
* **Pseudonymisierung vor Inferenz:** Direkte Identifikatoren werden lokal
  ersetzt, bevor Daten das System verlassen, und erst in den fertigen
  Artefakten reinjiziert. Rechtlich tragende Angaben (Daten, Beträge, §§)
  bleiben erhalten.
* **EU-Inferenz unter AVV (`eu-avv`, Standard):** Übermittlung ausschließlich
  an freigegebene EU-Endpunkte; ein technischer Egress-Guard blockiert
  nicht freigegebene Ziele und erkannte Klartext-Identifikatoren.
* **Protokollierte Kenntnisnahme:** Erst-Start-Bestätigung des rechtlichen
  Hinweises mit Version und Prüfsumme; Durchsetzung auf API-Ebene
  (`X-Disclaimer-Ack` bzw. In-App-Bestätigung).
* **Datenminimierung:** IP-Adressen werden nie im Klartext gespeichert;
  automatisch erzeugtes `.secret_salt` beim ersten Start; Logs enthalten
  Platzhalter statt personenbezogener Klartextdaten.
* **Rate-Limiting:** Sliding-Window-Limiter standardmäßig aktiv.

Vorlagen für Datenschutzbeauftragte (AVV-Checkliste, Verzeichnis von
Verarbeitungstätigkeiten) liegen unter `docs/datenschutz/`.

## Lizenz

MIT-Lizenz — siehe [LICENSE](LICENSE).

**Rechtlicher Hinweis:** Diese Software liefert automatisierte
Rechtsinformation. Sie stellt keine Rechtsberatung dar — maßgeblich ist
[DISCLAIMER_DE.md](DISCLAIMER_DE.md) in der jeweils bestätigten Fassung.
