# Compliance — Rechtsstatus und KI-VO-Klassifizierung von Citizen

**Version:** 1.1.0 · **Stand:** 2026-08-07
**Kanonische Fassung:** Deutsch · **Englischer Spiegel:** [COMPLIANCE-EN.md](COMPLIANCE-EN.md)
**Status:** Verbindliche Projekt-Klassifizierung (WP-60/WP-61, Roadmap v2.0.0).

> **Kein Rechtsrat.** Dieses Dokument ist eine Engineering-Planungsgrundlage,
> keine Rechtsberatung. Es dokumentiert die vom Projekt getragene Einordnung.
> Die in der Roadmap v2.0.0 §8 gesammelten offenen Rechtsfragen sind durch
> externe Beratung zu schließen, nicht durch dieses Dokument.

## 1. Zweck und Geltungsbereich

Dieses Dokument ist die **einzige maßgebliche Quelle** für die rechtliche
Klassifizierung von Citizen unter der KI-Verordnung (KI-VO, VO (EU) 2024/1689).
Für jede laufende Instanz beantwortet es:

1. Ist der Betreiber **Anbieter**, **Einsetzer** oder keines von beiden?
2. Greift die **Entwicklungsphasen-Freistellung** (Art. 2(8)) oder die
   persönliche Nutzung?
3. Welche Pflichten sind in dem jeweiligen Modus **aktiv** — und welche
   ausdrücklich **nicht**?

Gegenstand sind die Software Citizen und ihre erzeugten Ausgaben
(Analyse-Berichte, Aktionsdokument-Entwürfe, Chat-Antworten). Nicht behandelt
werden: die Offenlegung der KI-Autorschaft des Quellcodes (dazu `AI-USAGE.md`,
WP-63) und der rechtliche Hinweis an Nutzer (`DISCLAIMER_DE.md`).

## 2. Schnellantwort: Pflichten je Modus

Die Einordnung hängt an **einem einzigen Schalter**: `DEPLOYMENT_MODE`
(Entscheidung **D-019**, siehe `DECISIONS.md`). Drei Werte:

| Modus | Bedeutung | Rechtslage |
|---|---|---|
| `dev` | Nur der Autor, nur Testbetrieb, **nur synthetische Daten** | Entwicklungsphase, Art. 2(8) KI-VO — Pflichten nicht ausgelöst |
| `self` | Nur der Autor, an **eigenen realen Bescheiden** | Persönliche, nicht-berufliche Nutzung — Pflichten nicht ausgelöst |
| `provider` | Bereitgestellt, sodass **beliebige Dritte** eine Analyse erhalten können | Autor wird **Anbieter** (Art. 3(3)) — Art.-50-Pflichten aktiv |

Legende: **A** = aktiv (zu erfüllen) · **–** = nicht ausgelöst · **D** = dokumentarisch (immer relevant, aber keine Handlungspflicht)

| Pflicht | Rechtsgrundlage | `dev` | `self` | `provider` | Umsetzung |
|---|---|---|---|---|---|
| Anbieter/Einsetzer-Bestimmung | Art. 3(3)/(4) KI-VO | – | – | A | dieses Dokument (WP-60), D-019 |
| Entwicklungsphasen-Posture einhalten | Art. 2(8) KI-VO | A | – | – | WP-62 (Zugriffskontrolle, Synthetik-Guard, DEV-INSTANCE.md) |
| FOSS-Note: MIT befreit **nicht** von Art. 50 | Art. 2(12) KI-VO | D | D | D | dieses Dokument (WP-60) |
| Zweckbestimmung: antragstellerseitig, nicht behördenseitig | Annex III Nr. 5 Bst. a KI-VO | A | A | A | WP-61 (Self-Assessment, Purpose-Drift-Lint), D-020 |
| KI-Interaktionshinweis an jede natürliche Person | Art. 50(1) KI-VO | – | – | **A** | WP-64 |
| Maschinenlesbare Kennzeichnung aller KI-Ausgaben | Art. 50(2) KI-VO | – | – | **A** (Frist: **2026-12-02**, falls bis dahin `provider`) | WP-65 |
| Offenlegung bei veröffentlichtem Text (öffentliches Interesse) | Art. 50(4) KI-VO | – | – | – (nicht ausgelöst: Aktionsdokumente sind individuelle Korrespondenz, keine Veröffentlichung) | WP-65 (Begründung im Marker-Spez) |
| RDG-Einzelfallgrenze (strukturell, per Pipeline erzwungen) | § 2/§ 6/§ 8 RDG | – | – | A | WP-67, D-021 |
| DSGVO: DPIA (Art. 35) + AVV-Kette (Art. 28) | DSGVO | – (nur synthetische Daten) | – (eigene Daten) | **A** (vor dem ersten echten Fall) | WP-68 |
| Provider-Go/No-Go-Gate | — (aggregiert) | – | – | A (vor erstem Drittanbieter-Einsatz) | WP-69 |

**Schnellantwort in einem Satz:** Eine Instanz im Modus `dev` oder `self` hat
keine Pflichten aus der KI-VO und keine DSGVO-/RDG-Auslöser; eine Instanz im
Modus `provider` hat die in der Matrix mit **A** markierten Pflichten aktiv,
bevor der erste echte Drittfall verarbeitet werden darf — insbesondere
Art. 50(1), Art. 50(2), die RDG-Invariante, DPIA/AVV und das Go/No-Go-Gate.

## 3. Der Schalter: DEPLOYMENT_MODE

`DEPLOYMENT_MODE` ist die technische Verkörperung der
Anbieter/Einsetzer-Einordnung. Drei Werte, ein klarer Schwellenwert:

* **`dev`** — der Autor entwickelt und testet; es werden ausschließlich
  synthetische Daten (Goldset, Testdaten) verarbeitet. Die Instanz ist für
  niemanden bereitgestellt. Trägt die Entwicklungsphasen-Freistellung des
  Art. 2(8).
* **`self`** — der Autor nutzt die Software auf eigenen realen Bescheiden.
  Das ist persönliche, nicht-berufliche Nutzung; es wird keinem Dritten etwas
  bereitgestellt.
* **`provider`** — die Software ist so bereitgestellt, dass beliebige Dritte
  (z. B. Nutzer einer Sozialberatungsstelle) eine Analyse erhalten können.
  Ab diesem Ereignis ist der Autor **Anbieter** im Sinne des Art. 3(3).

Der Schalter ist bewusst **explizit** und wird nicht aus Betriebsdetails
(z. B. ob Authentifizierung konfiguriert ist) abgeleitet (D-019): Der
Pflichtenübergang ist ein einziges, prüfbares Ereignis, kein schleichender
Zustand.

**Technischer Umsetzungsstand:** Der Schalter wird in WP-66 in
`app/core/config.py` implementiert. Bis dahin gilt für die laufende Instanz
die Einordnung des Modus `dev` (Entwicklungs- und Testbetrieb durch den
Autor; Härtung der erreichbaren Instanz siehe WP-62).

## 4. Klassifizierung im Einzelnen

### 4.1 Anbieter und Einsetzer (Art. 3(3)/(4))

- **Anbieter** (Art. 3(3)): wer ein KI-System entwickelt oder entwickeln
  lässt und es unter eigenem Namen **in Verkehr bringt oder in Betrieb
  nimmt**.
- **Einsetzer** (Art. 3(4), engl. deployer): wer das System — außer in
  persönlicher, nicht-beruflicher Tätigkeit — **beruflich einsetzt**.

In `dev`/`self` ist der Autor keines von beiden: Er bringt nichts in Verkehr
und nimmt es für Dritte nicht in Betrieb. In `provider` ist der Autor
Anbieter. Eine einsetzende Sozialberatungsstelle ist **Einsetzer** im Sinne
des Art. 3(4) und — datenschutzrechtlich — **Verantwortliche** im Sinne des
Art. 4 Nr. 7 DSGVO.

### 4.2 Entwicklungsphase (Art. 2(8))

Die KI-VO gilt nicht für KI-Systeme, die ausschließlich zum Zweck der
wissenschaftlichen Forschung und Entwicklung entwickelt und in Betrieb
genommen werden. Der Modus `dev` liegt in dieser Phase: erreichbar zum
Testen, bereitgestellt für niemanden. Damit diese Einordnung trägt, muss die
dev-Instanz drei Bedingungen erfüllen (Härtung in WP-62): (1) Zugriff nur
durch den Autor (VPN/mTLS oder Basic-Auth + IP-Allowlist), (2) ausschließlich
synthetische Daten (Startup-Assertion + Ingest-Guard), (3) keine
Indexierung (robots.txt, `noindex`) und ein dauerhafter
Entwicklungs-Banner.

### 4.3 FOSS-Freistellung (Art. 2(12)) — und die Ausnahme für Art. 50

Citizen steht unter der MIT-Lizenz. Für KI-Systeme, die unter freien und
Open-Source-Lizenzen veröffentlicht werden, gilt der größte Teil der KI-VO
nicht — **Art. 50 (Transparenzpflichten) ist ausdrücklich ausgenommen** und
bleibt anwendbar. Die Lizenz ändert deshalb nichts daran, dass im Modus
`provider` die Art.-50-Pflichten gelten (KI-Interaktionshinweis,
maschinenlesbare Kennzeichnung). Im Modus `dev`/`self` greift Art. 50 nicht,
weil **kein Bereitstellen an Dritte** vorliegt — nicht wegen der Lizenz.

### 4.4 Selbstbewertung: Keine Hochrisiko-Einstufung (Anhang III Nr. 5 Bst. a)

**Ergebnis.** Citizen ist **kein Hochrisiko-KI-System** im Sinne des Anhangs III
Nr. 5 Bst. a KI-VO — bei der hier deklarierten Zweckbestimmung (D-020) und
unter den in diesem Abschnitt dokumentierten Schutzvorkehrungen gegen
Zweckbestimmungs-Abdrift.

**Erfassungsbereich des Tatbestands.** Anhang III Nr. 5 Bst. a erfasst
KI-Systeme, die von Behörden oder in deren Auftrag zur **Bewertung der
Anspruchsberechtigung** von natürlichen Personen zu Sozialleistungen und
Sozialdiensten eingesetzt werden. Tatbestandsmerkmal ist die behördenseitige
Verwendung zur Leistungsentscheidung.

**Deklarierte Zweckbestimmung (D-020).** Die Zweckbestimmung von Citizen ist
**antragstellerseitige Selbsthilfe und Beratungsassistenz**: das System
unterstützt die betroffene Person selbst oder deren Beratende dabei, einen
Bescheid zu verstehen, zu prüfen und zu reagieren. Es ist ausdrücklich **nicht**
dazu bestimmt, von einer Behörde oder in deren Auftrag zur Bewertung der
Anspruchsberechtigung eingesetzt zu werden.

**Warum der Tatbestand nicht erfüllt ist.**

1. **Keine behördenseitige Bestimmung:** Weder das Produkt noch seine
   Dokumentation oder UI-Kopien beschreiben Citizen als behördenseitiges
   Werkzeug. Die Zweckbestimmung ist in README, STATEMENT, diesem Dokument und
   dem Rechtshinweis verankert.
2. **Kein Entscheidungssystem:** Citizen erzeugt Rechtsinformation und
   Bausteine, die der menschlichen Adjudikation bedürfen (D-021); es trifft
   keine Entscheidung über Anspruchsberechtigung und wird nicht dazu
   bereitgestellt, eine solche zu treffen.
3. **Bereitstellungsform:** Selbst im Modus `provider` wird die Software
   Betroffenen und Beratungsstellen bereitgestellt — nicht Behörden zur
   Leistungsbewertung.
4. **Klassifizierung nach Zweckbestimmung:** Die KI-VO stellt für die
   Hochrisiko-Einordnung auf die Zweckbestimmung ab. Solange diese
   antragstellerseitig bleibt, greift der Tatbestand des Anhangs III Nr. 5
   Bst. a nicht.

**Drift-Schutz (Guardrails).** Damit diese Bewertung trägt:

- **D-020** verpflichtet auf die antragstellerseitige Zweckbestimmung und
  verbietet behördenseitige Beschreibungen in Dokumentation, Pitch und
  UI-Kopien.
- **`scripts/check_purpose_drift.py`** (WP-61) scannt `README*.md`,
  `STATEMENT.md`, `COMPLIANCE*.md` und `docs/pitch*` auf behördenseitige
  Formulierungen (konfigurierbare Deny-Phrase-Liste) und lässt die CI bei
  Treffern fehlschlagen. Der Lint ist die technische Durchsetzung der
  Zweckbestimmung gegen Abdrift.
- **Änderungsmanagement:** Veränderungen an Zweckbestimmung, Zielgruppe oder
  Bereitstellungsform erfordern eine Fassungsänderung dieses Dokuments
  (Abschnitt 7) und eine erneute Prüfung dieser Selbstbewertung.

**Bedingung.** Diese Bewertung ist konditional: Sie gilt nur für die hier
deklarierte Zweckbestimmung. Wird Citizen künftig als behördenseitiges Werkzeug
beschrieben oder Behörden zur Leistungsbewertung bereitgestellt, ist die
Einstufung neu zu prüfen — die Pflichten für Hochrisiko-KI-Systeme (Kapitel III
KI-VO) würden ausgelöst.

## 5. Fristen und Auslöse-Ereignisse

| Ereignis / Frist | Wirkung |
|---|---|
| **Bereitstellung für Dritte** (`DEPLOYMENT_MODE=provider`) | Schaltet die Art.-50-Pflichten sowie die DSGVO- und RDG-Auflagen an (siehe Abschnitt 2) |
| **2026-12-02** (Ende der Übergangsfrist für Art. 50(2)) | **Nur bindend, wenn** bis dahin `provider` gilt: Die maschinenlesbare Kennzeichnung muss bis dahin umgesetzt sein (WP-65). Andernfalls gilt sie als Tor für die spätere Bereitstellung. |
| **Erster echter Drittfall** | Verarbeitung erst nach: Purpose-Guard grün (WP-61), Hinweis live (WP-64), Kennzeichnung live (WP-65), RDG-Invariante getestet (WP-67), DPIA + AVV-Kette vorhanden (WP-68), Go/No-Go-Gate signiert (WP-69). |

## 6. Benachbarte Rechtsregime

### 6.1 DSGVO

Die DSGVO ist für den Betrieb das am stärksten unterschätzte Regime.
Bescheide von Leistungsberechtigten enthalten regelmäßig **besondere
Kategorien** personenbezogener Daten (Art. 9 DSGVO: Gesundheit,
Behinderung); die Betroffenen sind verletzliche Personen. Daraus folgt:

- **`provider`:** Eine **Datenschutz-Folgenabschätzung (DPIA, Art. 35)**
  ist sehr wahrscheinlich verpflichtend; eine **AVV-Kette** (Art. 28) muss
  vor dem ersten echten Fall stehen: Autor als Auftragsverarbeiter →
  EU-Inferenz als Unterauftragsverarbeiter (Profil `eu-avv`) →
  Beratungsstelle als Verantwortliche. Umsetzung: WP-68.
- **`self`:** Der Autor verarbeitet eigene Daten; keine DPIA/AVV-Pflicht.
  Die vorhandenen Schutzmechanismen (Pseudonymisierung, Egress-Guard)
  bleiben aktiv (Defense-in-Depth).
- **`dev`:** Nur synthetische Daten; keine Verarbeitung personenbezogener
  Daten. Der Synthetik-Guard (WP-62) verhindert, dass echte Daten in die
  dev-Instanz gelangen.

### 6.2 RDG

Ein System, das den konkreten Bescheid einer einzelnen Person prüft,
bewegt sich nahe der Grenze zur **Rechtsdienstleistung in konkreter fremder
Angelegenheit** (§ 2 RDG). Die Projektposition (D-021):

- Jede Ausgabe ist **Rechtsinformation plus Bausteine**, die der menschlichen
  Adjudikation bedürfen; keine Ausgabe präsentiert sich als abgeschlossene
  rechtliche Bewertung des Einzelfalls.
- Unadjudizierte Rechtsbehauptungen erscheinen in Aktionsdokumenten als
  `[BITTE PRÜFEN]`-Platzhalter — technisch erzwungen, nicht nur deklariert
  (WP-67).
- Für den Einsatz in Beratungsstellen wird der Rahmen des § 6/§ 8 RDG
  (unentgeltliche Rechtsdienstleistung / anerkannte Beratungsstellen)
  dokumentiert (WP-67).

## 7. Gültigkeit und Änderungsdienst

- Dieses Dokument ist Teil der Roadmap v2.0.0 (WP-60/WP-61) und mit den
  Entscheidungen D-019, D-020 und D-022 (sowie, in seinem Work Package,
  D-021) im Entscheidungs-Ledger verankert.
- Änderungen an Zweckbestimmung, Bereitstellungsform oder Zielgruppe
  erfordern eine Überprüfung und Fassungsänderung dieses Dokuments
  (semantische Versionierung).
- Offene Rechtsfragen, die sich technisch nicht schließen lassen, sind in
  Roadmap v2.0.0 §8 gesammelt.

## Referenzen

- `docs/roadmap-v2.0.0.md` — Phasen P6–P8, Pflichten-Matrix (§5)
- `DECISIONS.md` — D-019, D-020, D-021, D-022
- `DISCLAIMER_DE.md` / `DISCLAIMER_EN.md` — rechtlicher Hinweis für Nutzer
- `README.md` — Abschnitt „Rechtlicher Status"
- `AI-USAGE.md` — Offenlegung der KI-Autorschaft des Quellcodes (WP-63)
- `scripts/check_purpose_drift.py` — Purpose-Drift-Lint (WP-61)
