# WP-1.6 — Prüfstand-View: Golden Set & Eval-Ergebnisse in der GUI

| Feld | Wert |
|---|---|
| Version | 1.0.0 |
| Datum | 2026-07-12 |
| Einordnung | M1-Erweiterung; Abhängigkeiten: WP-1.2 (Goldset — erledigt, v0.1.0), WP-1.3 (Eval-Harness — Deliverable b degradiert kontrolliert, solange offen) |
| Aufwand | 3–4 Agent-Tage |
| Zielgruppen | (1) Demo-Publikum: Beratungsstellen, NGOs, Förderer — sieht nie YAML. (2) Entwickler: Regressionssicht. Eine Oberfläche, zwei Lesetiefen. |

## Leitprinzip (nicht verhandelbar)

**Die YAML-Datei bleibt die einzige Quelle der Wahrheit.** Die GUI ist eine
Read-only-Renderschicht über dem unveränderlichen, versionierten Artefakt.
Kein Editieren von Fällen in der GUI (Änderung = neue Goldset-Version, wie
gehabt), keine Zweitpflege von Inhalten, kein Drift zwischen Datei und
Anzeige. Der Loader parst `goldset-vX.Y.Z.yaml` serverseitig und liefert
strukturiertes JSON an das Frontend; im Browser taucht an keiner Stelle
YAML-Syntax auf.

## Deliverable A — Goldset-Browser („Prüfstand")

Neue Route/Ansicht **„Prüfstand"** mit drei Ebenen:

**1. Kopfbereich — Rechtsstand & Vertrauensanker.**
Badges für Goldset-Version, Rechtsstand (2026-07-11), Fallanzahl,
Verifikationsdatum; darunter die `legal_baseline` als Karten in
Klartext-Deutsch: Regelbedarfstabelle, Freibetrags-Staffel (§ 11b) als
kleine Treppengrafik, Sanktionsregeln neues Recht, und das Fristen-Modell
als **horizontale Zeitstrahl-Grafik** (Aufgabe zur Post → +4 Tage
Bekanntgabefiktion → +1 Monat → Werktag-Rollover) — diese eine Grafik
ersetzt im Tacheles-Gespräch fünf Minuten Erklärung. Die `open_questions`
erscheinen als eigener, ehrlich beschrifteter Abschnitt („Bewusst offen
gelassene Rechtsfragen") — Transparenz über Grenzen ist vor diesem
Publikum ein Feature, kein Makel.

**2. Fall-Galerie.**
Zehn Karten: Titel, Kategorie (mit verständlichem Label, z. B. „Sanktion /
Meldeversäumnis" statt `minderung_meldeversaeumnis_32`), Schwierigkeit,
Gesamtbewertung als neutraler Farbcode (rot = „Fehler zulasten gefunden",
grün = „Bescheid hält der Prüfung stand", grau = „kein Verwaltungsakt").
Deutlicher Hinweis im Kopf: *synthetische, fiktive Fälle*.

**3. Fall-Detail (Zwei-Spalten-Ansicht).**
Links das Eingangsdokument, gerendert als Behördenbrief (Briefoptik, nicht
Code-Block). Rechts die erwarteten Befunde in der Sprache, die auch der
spätere Ergebnisreport spricht:
- **Befunde** als Ampelliste (Issue-Text, Bewertung, zugehörige §§ als Chips),
- **Berechnung** als Gegenüberstellung „Jobcenter hat gerechnet / korrekt
  wäre" mit hervorgehobener Differenz,
- **Frist** als Mini-Zeitstrahl mit konkreten Daten inkl. Rollover-Markierung,
- **Bekannte Fallen** als amber Callout-Boxen,
- **Nächste Schritte** als nummerierte Handlungsliste.

Damit ist die Detailansicht zugleich der Prototyp der späteren
Report-Optik (WP-3.2) — bewusste Wiederverwendung derselben Komponenten.

## Deliverable B — Eval-Ergebnis-Ansicht

Overlay auf Galerie und Detailansicht: letzter Eval-Lauf pro Fall
(bestanden/nicht bestanden je Metrik — Befunde erkannt, Zitate korrekt,
Rechnung centgenau, Frist taggenau), plus eine Aggregat-Kachel im
Kopfbereich („Letzter Lauf: Modell X, 9/10 Fälle vollständig bestanden,
Datum, Report-Version"). Datenquelle: die versionierten JSON-Reports aus
WP-1.3. Solange der Harness nicht existiert oder keine Läufe vorliegen:
sauberer Leerzustand („Noch keine Prüfläufe") statt Attrappe — keine
Fake-Zahlen, nirgends.

## Deliverable C — Demo-Modus („Diesen Fall live analysieren")

Der Button, der das Tacheles-Gespräch gewinnt: lädt `input_document.text`
eines Goldset-Falls per Klick als regulären Fall in die Analyse-Pipeline
und zeigt nach Abschluss eine **Vergleichsansicht** — erwartete Befunde
links, tatsächliche Pipeline-Ausgabe rechts, Übereinstimmungen und
Abweichungen markiert. Dramaturgie der Demo damit: „Das sollte gefunden
werden → schauen Sie zu, wie es gefunden wird." Kein Upload, kein
Vorbereitungsrisiko, reproduzierbar in jeder Besprechung.

## API-Vertrag (für den Coding-Agent)

```
GET /api/goldset            → Manifest + Fall-Liste (geparst, ohne YAML-Rohtext)
GET /api/goldset/{case_id}  → vollständiger Fall (strukturiert)
GET /api/eval/reports       → Liste versionierter Läufe (leer erlaubt)
GET /api/eval/reports/{id}  → Ergebnis je Fall/Metrik
POST /api/goldset/{case_id}/analyze → startet reguläre Pipeline mit dem Falltext
```
Goldset-Pfad und -Version per Konfiguration; `schema_version`-Check beim
Laden — inkompatible Datei ⇒ verständliche Fehlermeldung, kein Halbrendering.

## Nicht-Ziele (v1)

Kein Fall-Editor (Versionierungsdisziplin bleibt beim YAML-Artefakt), keine
Nutzerverwaltung, kein öffentlicher Static-Export der Prüfstand-Seite
(sinnvolle spätere Erweiterung als „Qualitätsnachweis" fürs Repo/Web —
Komponenten dafür wiederverwendbar halten).

## Akzeptanzkriterien (maschinell verifizierbar)

- [ ] goldset-v0.1.0.yaml wird vollständig gerendert: 10/10 Fälle, alle Befunde, Berechnungen, Fristen, Fallen — Vollständigkeits-Test vergleicht Feldanzahl YAML ↔ API-Response.
- [ ] Kein YAML-Rohtext im ausgelieferten Frontend (Response- und DOM-Scan-Test).
- [ ] `schema_version`-Mismatch erzeugt definierte Fehlermeldung (Test mit manipulierter Datei).
- [ ] Fristen-Zeitstrahl zeigt für GS-002/-003/-004/-010 den Rollover korrekt an (Snapshot-Tests).
- [ ] Demo-Modus: Roundtrip GS-001 → Pipeline → Vergleichsansicht ohne manuelle Zwischenschritte (E2E-Test; Pipeline-Ergebnisqualität ist ausdrücklich nicht Gegenstand dieses WPs).
- [ ] Eval-Leerzustand und Eval-Befüllung beide getestet (Fixture-Report).
- [ ] Sprachprüfung: alle sichtbaren Labels deutsch, keine Schema-Bezeichner (`snake_case`) im UI (Lint über Label-Katalog).
- [ ] Goldset-Versionswechsel per Konfigurationsänderung ohne Codeänderung.

## Changelog

- 1.0.0 (2026-07-12): Erstfassung — Prüfstand (Browser, Eval-Ansicht, Demo-Modus), Read-only-Prinzip festgeschrieben.
