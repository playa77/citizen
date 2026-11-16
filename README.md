# Citizen — Bescheide verstehen, Fristen halten, gut vorbereitet zum Anwaltstermin

## Rechtsinformation, keine Rechtsberatung — siehe [DISCLAIMER_DE.md](DISCLAIMER_DE.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com)

Citizen ist eine freie (MIT), nicht-kommerzielle, lokale und evidenzgebundene
Analyse-Engine für Menschen, die ein Schreiben in **ihrer eigenen
Angelegenheit** bekommen haben — einen Bescheid, eine Kündigung, einen
Mahnbescheid. Die Software liest die Korrespondenz ein und beantwortet vier
Fragen: **Was steht da drin? Stimmt das? Bis wann muss ich reagieren? Was
mache ich jetzt?** Jede Aussage wird an den Gesetzestext gebunden, jede
Berechnung deterministisch nachgerechnet, jede Frist auf den Tag genau
bestimmt — und die Qualität wird gegen ein öffentliches, versioniertes Golden
Set gemessen statt behauptet.

Das Ziel: Wer zur Anwältin, zum Anwalt oder zur Beratungsstelle geht, bringt
dieselbe Informationsqualität mit, mit der dort effizient gearbeitet werden
kann — als strukturiertes **Mandatsvorbereitungs-Dossier**. Citizen bereitet
vor; es berät nicht. Entschieden wird von Menschen.

**Warum es dieses Projekt gibt:** [DISCLAIMER_DE.md](DISCLAIMER_DE.md),
Teil A („Projektstatement")

## Ausrichtung und Stand

| | |
|---|---|
| **Weg** | Freier öffentlicher Pfad: MIT, kostenlos, nicht-kommerziell, nicht als Kanzlei-Software gebaut (Entscheidung **D-034**) |
| **Architektur (Ziel)** | Domänenneutraler Kern + austauschbare **Rechtsgebiets-Module**; Sozialrecht ist Modul 1 und Standard (**D-036**) — siehe [ARCHITECTURE.md](ARCHITECTURE.md) |
| **Roadmap** | [docs/roadmap-v3.0.0.md](docs/roadmap-v3.0.0.md): Modul-Architektur → Dossier → Modul-Plattform → Bürger-Oberfläche → zehn weitere Module |
| **Stand des Codes** | v2.0.0: ein verifiziertes Gebiet (Sozialrecht), Logik noch fest verdrahtet; der Umbau zu Modulen ist Phase P9 der Roadmap |

## Rechtlicher Status

Die rechtliche Einordnung von Citizen unter der KI-Verordnung (VO (EU)
2024/1689) ist in [DISCLAIMER_DE.md](DISCLAIMER_DE.md), Teil C, dokumentiert
(kanonisch, deutsch; englischer Spiegel: [DISCLAIMER_EN.md](DISCLAIMER_EN.md),
Part C). Kurzfassung:

* **`dev`** — nur Entwicklungs-/Testbetrieb mit synthetischen Daten:
  Entwicklungsphasen-Freistellung (Art. 2(8) KI-VO), keine Pflichten ausgelöst.
* **`self`** — nur eigene, persönliche Nutzung: kein Bereitstellen an Dritte,
  keine Pflichten ausgelöst.
* **`provider`** — Dritte können Analysen erhalten: der Autor wird **Anbieter**
  (Art. 3(3) KI-VO); die Transparenzpflichten nach Art. 50
  (KI-Interaktionshinweis, maschinenlesbare Kennzeichnung) sowie die
  DSGVO- und RDG-Auflagen werden aktiv (siehe DISCLAIMER_DE.md, Teil C).

Der jeweils aktive Modus wird über die Einstellung `DEPLOYMENT_MODE` bestimmt
(Entscheidung **D-019** im [Entscheidungs-Ledger](DECISIONS.md)); im Modus
`dev` verweigert die Instanz ohne `CITIZEN_SYNTHETIC_DATA_ONLY=true` den Start.

## Rechtsgebiete und Module

Jedes Rechtsgebiet wird ein eigenes, versioniertes Modul (Gesetzeskorpus,
Parameter, Fristen, Rechenwerke, Entwürfe, Dossier-Checkliste,
Bürgersprache, Golden Set) hinter derselben API. Ohne weitere Einstellung
startet Citizen mit dem Modul **Sozialrecht**. Profile und Reihenfolge:
[docs/module-catalog.md](docs/module-catalog.md).

| # | Modul | Inhalt | Stand |
|---|---|---|---|
| M0 | `sozialrecht` | Bürgergeld/Grundsicherungsgeld (SGB II), SGB X, SGG | ✅ **unterstützt** — goldset-verifiziert, **Standardmodul** |
| M1 | `schuldnerrecht` | Mahnbescheid, Inkasso, Pfändung, P-Konto, Weg in die Verbraucherinsolvenz | 🗓️ geplant |
| M2 | `mietrecht` | Mieterhöhung, Betriebskosten, Mängel, Kündigung | ⚠️ experimentell → geplant als Modul |
| M3 | `arbeitsrecht` | Kündigung (3-Wochen-Frist), Lohn, Urlaub, Zeugnis | ⚠️ experimentell → geplant als Modul |
| M4 | `vertragsrecht` | Verbraucher- und Vertragsrecht, Widerruf, Gewährleistung, Fluggastrechte | ⚠️ experimentell → geplant als Modul |
| M5 | `verkehrsrecht` | Bußgeldbescheid, Punkte, Fahrverbot | 🗓️ geplant |
| M6 | `familienrecht` | Unterhalt, Trennung, Unterhaltsvorschuss | ⚠️ experimentell → geplant als Modul |
| M7 | `aufenthaltsrecht` | Aufenthaltstitel, Asylverfahren (Fristschutz), Einbürgerung | 🗓️ geplant |
| M8 | `steuerrecht` | Einkommensteuerbescheid, Einspruch (nur eigene Angelegenheit) | 🗓️ geplant |
| M9 | `erbrecht` | Erbfolge, Ausschlagung, Pflichtteil, Erbschaft- und Schenkungsteuer | ⚠️ experimentell → geplant als Modul |
| M10 | `strafrecht` | Beschuldigte und Verletzte: Strafbefehl, Anhörung, Rechte — Verweis auf Verteidigung zuerst | ⚠️ experimentell → geplant als Modul |

Experimentelle Gebiete sind heute funktionsfähig, aber nicht verifiziert
(nur Prompt-Profile, keine eigenen Fristen- oder Rechenwerke); sie sind in den
API-Ausgaben entsprechend gekennzeichnet. Die Altschlüssel `schenkungsrecht`,
`verwaltungsrecht` und `andere` werden beim Umbau auf Module abgebildet
(D-038).

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
  Fristen) — über die Goldset-API abrufbar (`/api/v1/goldset/...`), inklusive
  Demo-Modus (Prüffall live durch die Pipeline schicken) und
  Eval-Ergebnis-Endpunkten.
* **Eval-Harness:** `python -m eval.runner` führt die echte Pipeline gegen das
  Goldset aus und misst Befund-Erkennung, Zitatpräzision,
  Halluzinationsrate, Rechen- und Fristgenauigkeit. Versionierte Reports;
  Regressions-Gate per `--baseline`.
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
  Egress-Guard blockiert alles andere). Das aktive Profil wird über die
  Meta-API ausgewiesen und in Dokumenten angegeben.
* **Adversariale Rechtsprüfung:** Mehrperspektivische Gegenprüfung
  („Rechtsprüfungsrat") aus Verteidigungs-, Behörden- und Gerichtssicht.
* **Lokale OCR-Pipeline:** Vollständig lokale Dokumentaufnahme
  (PDF/JPG/PNG/TXT/HTML/EML, bis 25 MB) mit deterministischer
  Fallback-Kette (`pdfplumber` → `PyMuPDF` → `Tesseract`) und
  verpflichtender Nutzer-Bestätigung des erkannten Textes vor der Analyse.
* **Hierarchischer Gesetzeskorpus:** Automatisierter Abruf von 16
  Quelltypen (gesetze-im-internet.de, arbeitsagentur.de, bsg.bund.de),
  gechunkt auf vier Ebenen (Gesetz → § → Absatz → Satz), zur Laufzeit
  auswählbar; „Rechtsstand"-Anzeige mit Aktualitätswarnung.
* **First-Run-Bestätigung:** Analyse erst nach ausdrücklicher Kenntnisnahme
  des rechtlichen Hinweises (Header `X-Disclaimer-Ack` mit der aktuellen
  Fassungsnummer); API-seitig durchgesetzt.
* **Audit-Trail:** Jeder Lauf, jede Pipeline-Stufe, jeder Befund und jede
  Evidenzbindung wird in PostgreSQL persistiert.
* **API-only:** Kein Web-UI, kein GUI-Client in diesem Repository — die
  versionierte REST-API unter `/api/v1` ist die einzige externe Schnittstelle
  (D-025), dokumentiert in [API_DOCUMENTATION.md](API_DOCUMENTATION.md).
  Eine Bürger-Oberfläche ist geplant (Roadmap P12); wo sie liegt, ist offen
  (D-040).

### Geplant (Roadmap v3.0.0 — noch nicht implementiert)

* **Modul-System:** Rechtsgebiete als versionierte Pakete, ein-/ausschaltbar
  (`DEFAULT_MODULE`, `ENABLED_MODULES`), neue Endpunkte `/api/v1/modules`.
* **Mandatsvorbereitungs-Dossier:** Chronologie, Dokumenten-Checkliste,
  Fristen, Rechenergebnisse, belegte Fundstellen, Fragenliste für den Termin,
  Entwürfe — als druckfertiges PDF und als maschinenlesbares JSON.
* **Bürgersprache:** verständliche Erklärung je Befund, Leichte Sprache für
  Fristen, mehrere Sprachen — wie jede andere Ausgabe gegen das Golden Set
  geprüft.
* **Signierte Aktualisierungen** für Parameter und Gesetzesstände, ohne
  Telemetrie und ohne gehosteten Dienst.

## Architektur

| Ebene | Technologie |
|---|---|
| **Backend** | FastAPI, Uvicorn (SSE-Streaming) |
| **Datenbank** | PostgreSQL 16 + `pgvector` (Vektorsuche, ILIKE-Keyword-Fallback) |
| **ORM / Migrationen** | SQLAlchemy 2.0 (async), Alembic (8 Migrationen, eine lineare DAG — PostgreSQL-only, D-024) |
| **LLM-Anbindung** | Versionierte Inferenzprofile (`eu-avv` Standard, `extern-openrouter`, `on-prem`-Slot); Modell je Pipeline-Stufe konfigurierbar; Fallback-Kette |
| **OCR** | pdfplumber → PyMuPDF → Tesseract (deutsch) |
| **Tooling** | ruff (Format & Lint), mypy (strict), pytest (Unit + Integration) |
| **Module (Ziel)** | Kern + Rechtsgebiets-Module mit Manifest, versioniert und getrennt vom Kern — siehe [ARCHITECTURE.md](ARCHITECTURE.md) |

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
  -H "X-Disclaimer-Ack: v3.0.0" \
  -H "Content-Type: application/json" -d '{}'

# 7. API nutzen — geschützte Endpunkte verlangen den Header
#    X-Disclaimer-Ack mit der aktuellen Fassungsnummer
#    Interaktive Doku: http://localhost:8000/docs
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
| **documents** | `GET` | `/api/v1/documents/generator-options/{case_run_id}` | Verfügbare Aktionsdokumente + Fristdaten je Fall |
| **documents** | `POST` | `/api/v1/documents/generate` | Aktionsdokument erzeugen (Widerspruch, § 44, § 25) |
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
| **meta** | `GET` | `/api/v1/meta/legal-timestamp` | Rechtsstand-Frischedaten (Parameter & Korpus) |
| **meta** | `GET` | `/api/v1/meta/active-profile` | Aktives Inferenzprofil (Name, AVV-Status, Pseudonymisierung) |
| **meta** | `GET` | `/api/v1/meta/deployment-mode` | Aktiver Betriebsmodus (`dev`/`self`/`provider`, D-019) + Dev-Banner |
| **health** | `GET` | `/health` | Liveness-Probe |

Vollständige, interaktive Dokumentation nach dem Start unter `/docs`
(Swagger) und `/redoc`.

## Verzeichnisstruktur

```
citizen/
├── alembic/                              # 8 Migrationen (eine lineare PG-DAG)
├── app/
│   ├── api/routes/                       # 12 Routenmodule (analyze, cases,
│   │                                     #  conversations, corpus, documents,
│   │                                     #  eval_reports, goldset, ingest,
│   │                                     #  intake, meta, ocr, presets)
│   ├── core/                             # config, pipeline (SSE), router
│   ├── db/                               # 14 ORM-Modelle, Session, Vektor-Backend
│   ├── middleware/                       # Disclaimer-Durchsetzung, Noindex-Header
│   ├── fristen/                          # Fristen-Kern (Kalender, Fiktionen, Spec-Evaluator)
│   ├── modules/                          # Modul-Registry, SDK, Inhalts-Loader,
│   │                                     #  Bereichstabellen, Verfahrensbibliothek
│   ├── services/                         # 22 Kern-Servicemodule, u.a.:
│   │                                     #  calculation (Harness), parameter_store,
│   │                                     #  prompts (Stufen-Templates), pseudonymization,
│   │                                     #  inference_profiles, verification,
│   │                                     #  document_generators, retrieval
│   └── utils/                            # image, pdf, text, tokens
├── modules/                              # Rechtsgebiets-Module: sozialrecht (Standard,
│                                         #  verified: Fristen, Rechner, Parameter, Vorlagen,
│                                         #  Goldsets) + 7 Stub-Module (experimental)
├── eval/                                 # Eval-Harness, Reports
├── tests/                                # 37 Testdateien (~12.600 Zeilen)
├── docs/                                 # Roadmap v3.0.0 (aktuell), Modul-Katalog,
│                                         #  Roadmap v2.0.0 (abgelöst; von
│                                         #  DISCLAIMER_*.md referenziert)
├── devdocs/                              # Betriebsdokumentation (Dev-Instanz)
├── scripts/                              # Wartungs-Skripte (Purpose-Drift-Lint,
│                                         #  Parameter-Seeding, Benchmark)
├── API_DOCUMENTATION.md                  # Vollständiger API-Vertrag (D-025)
├── ARCHITECTURE.md                       # Ziel-Architektur: Kern + Module
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
| **Betriebsmodus** | `DEPLOYMENT_MODE` | `dev` | Posture (`dev`/`self`/`provider`, D-019); `dev` verlangt zusätzlich `CITIZEN_SYNTHETIC_DATA_ONLY=true` |
| **Pipeline** | `ENABLE_CALCULATION_CHECK` | `True` | Deterministische SGB-II-Rechenprüfung |
| | `PIPELINE_TIMEOUT_SEC` | `480` | Hartes Pipeline-Timeout (Timeout-Kette D-017) |
| **Retrieval** | `RETRIEVAL_MODE` | `per_question` | Embedding-Strategie (`per_question` / `combined`) |
| | `TOP_K_RETRIEVAL` | `10` | Max. Chunks je Anfrage |
| **Korpus** | `CORPUS_SOURCES` | `["sgb2", "sgbx"]` | Standardquellen (zur Laufzeit änderbar) |
| | `GOLDSET_PATH` | `modules/sozialrecht/goldset/goldset-v0.1.0.yaml` | Goldset der Prüfstand-API |
| **Rate-Limit** | `RATE_LIMIT_REQUESTS` / `_WINDOW` | `0` / `60` | In-Memory-Limiter existiert, ist aber nicht eingebunden (`0` = deaktiviert) |
| **OCR** | `ENABLE_OCR_LLM_SYNTHESIS` | `False` | LLM-Synthese der Dual-OCR-Ergebnisse |

Vollständige Liste in `.env.example`.

## Tests ausführen

```bash
# Unit-Tests (ohne Datenbank)
pytest tests/unit/ -v

# Integrationstests (PostgreSQL 16 + pgvector erforderlich)
alembic upgrade head
pytest tests/integration/ -v

# Eval gegen das Goldset (echte Pipeline; DB + API-Schlüssel nötig)
python -m eval.runner modules/sozialrecht/goldset/goldset-v0.2.0.yaml --save
# mit Regressions-Gate gegen einen Baseline-Report (Exit 1 bei Verschlechterung):
python -m eval.runner modules/sozialrecht/goldset/goldset-v0.2.0.yaml \
  --baseline eval/results/<baseline>.json --save

# Codequalität (CI-Umfang)
ruff check app/
ruff format --check app/
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
* **Protokollierte Kenntnisnahme:** Geschützte Endpunkte verlangen den
  Header `X-Disclaimer-Ack` mit der aktuellen Fassungsnummer des rechtlichen
  Hinweises; die bestätigte Fassung wird je Analyse-Lauf im lokalen
  Audit-Protokoll festgehalten.
* **Datenminimierung:** IP-Adressen werden weder verarbeitet noch gespeichert;
  automatisch erzeugtes `.secret_salt` beim ersten Start; Logs enthalten
  Platzhalter statt personenbezogener Klartextdaten.
* **Kein Rate-Limiting aktiv:** Der in `app/middleware/rate_limit.py`
  vorhandene Sliding-Window-Limiter ist standardmäßig nicht eingebunden
  (`RATE_LIMIT_REQUESTS=0`); Deployments hinter nginx können dort eigene
  Limits setzen.

## Lizenz

MIT-Lizenz — siehe [LICENSE](LICENSE).

**Rechtlicher Hinweis:** Diese Software liefert automatisierte
Rechtsinformation. Sie stellt keine Rechtsberatung dar — maßgeblich ist
[DISCLAIMER_DE.md](DISCLAIMER_DE.md) in der jeweils bestätigten Fassung.
