# Citizen — Module Catalog

<!-- Version: 1.3.0 | 2026-11-27 — WP-134 traffic backend.
     1.2.0 | 2026-11-27 — WP-133 consumer contract backend.
     1.1.0 | 2026-11-26 — M1 experimental foundation; owner directs backend continuation.
     1.0.2 | 2026-11-25 — D-069: peer modules; startup/session TODO blocks further module implementation.
     1.0.1 | 2026-11-16 — M0 status row: module 1.2.0 (D-063). 1.0.0 | 2026-11-16 -->
<!-- Companion to ARCHITECTURE.md (module contract) and docs/roadmap-v3.0.0.md
     (phase P13 delivers modules M1–M10). Decisions: D-036 (core + modules),
     D-038 (queue), D-069 (no default; startup selection/session restore first). -->

**Backend prerequisite completed; continuation authorized:** the owner's
2026-11-26 direction permits backend module implementation to proceed. GUI
selection/session work and combined acceptance remain separately owned and
unverified here. See [TODO.md](../TODO.md), step 1, and
[D-069](decisions/D-069-module-selection-and-session-restore.md).

All modules are peers, including `sozialrecht`. On first GUI/desktop launch,
present all modules for the user to choose which to load, with none
preselected. On later launches, also offer **Restore last session** or a new
selection. Restoration is explicit; unavailable saved modules must not be
silently replaced. Module maturity and deployment eligibility remain visible
but do not imply loading or selection. Planned modules are listed as planned
until implemented; the remaining modules are the next work after this TODO.

> **Status of the statutory anchors below:** planning inputs compiled from
> general knowledge of German law on 2026-11-16. Each anchor is a *hypothesis
> to verify* in the module's first work package (WP-13x.1, "scope & sources")
> against the current statute text before any deadline spec, parameter or
> template is written. Nothing in this catalog is legal advice.

---

## 1. Selection rule

Modules cover areas of German law that **affect natural persons in their own
matters**, where the person typically **receives a document** (Bescheid,
Kündigung, Mahnbescheid, Strafbefehl …) that carries a **deadline** and
often an **amount**. That is the shape the core is built for: OCR → evidence
binding → deterministic deadline → deterministic calculation → draft →
appointment dossier. Areas without that shape (company law, IP, public
procurement) are out of scope by definition, as are lawyer-side features
(D-034).

## 2. Overview and queue

| # | Module id | Title | Status | Queue rationale (necessity hypothesis — to be revised by user-need evidence, roadmap OQ-4) |
|---|---|---|---|---|
| M0 | `sozialrecht` | Sozialrecht (SGB II/X, SGG) | **verified · peer module** | first implemented module (WP-97); this gives it no startup/loading priority |
| M1 | `schuldnerrecht` | Schulden, Inkasso, Zwangsvollstreckung, Verbraucherinsolvenz | **experimental 0.2.0 · backend implemented** | Service-based court deadlines, qualified calculators, guarded drafts, intake/dossier and DE/EN/de-LS copy; deployment corpus/live evaluation pending; human review deferred (D-071) |
| M2 | `mietrecht` | Wohnraummietrecht | backend implemented 0.2.0; experimental, review pending | housing is existential; very high volume; strong deterministic layer (Kappungsgrenze, Mietpreisbremse, Nebenkosten); crossover with § 22 SGB II |
| M3 | `arbeitsrecht` | Individualarbeitsrecht | experimental backend 0.2.0 (WP-132, D-074) | 3-week Klagefrist is the most consequential short deadline citizens miss; crossover with SGB III Sperrzeit / SGB II |
| M4 | `vertragsrecht` | Verbraucher- und Vertragsrecht | experimental backend 0.2.0 (WP-133, D-075) | everyday volume (Widerruf, Gewährleistung, Abo-Fallen, Fluggastrechte) |
| M5 | `verkehrsrecht` | Bußgeld- und Verkehrsrecht | experimental backend 0.1.0 (WP-134, D-076) | high volume, compact rule set (BKatV), 2-week Einspruch; builds the OWiG procedure library reused by M10 |
| M6 | `familienrecht` | Familienrecht (Unterhalt, Trennung, Sorge/Umgang) | planned (legacy key experimental) | high stakes; Unterhalt math deterministic; crossover UVG / SGB II |
| M7 | `aufenthaltsrecht` | Aufenthalts-, Asyl- und Staatsangehörigkeitsrecht | planned | very high necessity for M0 clientele, but very short deadlines and multilingual need → scheduled after the plain-language/i18n layer (P12) |
| M8 | `steuerrecht` | Einkommensteuer privater Personen + AO-Verfahren | planned | Steuerbescheid Einspruch is common; StBerG constraint shapes scope (own matter only) |
| M9 | `erbrecht` | Erbrecht (incl. Schenkung, ErbSt) | planned (legacy key experimental) | Ausschlagungsfrist; Pflichtteil math; lower urgency than M1–M7 |
| M10 | `strafrecht` | Straf- und Strafverfahrensrecht (Beschuldigte und Verletzte) | planned (legacy key experimental) | highest stakes; referral-first design; reuses M5's OWiG/StPO procedure library; last by design |

**Legacy area keys (v2.0.0 `LEGAL_AREA_ALLOWED`) → modules** (D-038):
`schenkungsrecht` → alias of `erbrecht`; `vertragsrecht` → id kept for M4;
`verwaltungsrecht` → not a module: becomes the core procedural library
(VwVfG/VwGO Bekanntgabe, Widerspruch, Klagefrist) used by M0, M5, M7, M8;
`andere` → retained as an unverified catch-all that runs the core without
module engines (no deadlines asserted, no calculations), tier `experimental`.

The backend part of [TODO.md](../TODO.md), step 1 is verified. The owner has
directed backend continuation while GUI work remains separately owned. Their
queue is implementation sequencing, not catalog preference, preselection or
automatic loading; it may be revised when user-need evidence arrives.

---

## 3. Module profiles

Each profile lists: **scope** · **documents citizens receive** · **critical
deadlines** (→ `fristen.yaml`) · **deterministic calculators** (→
`calculators.py` + parameters) · **action drafts** (→ `documents/`) ·
**corpus** (→ `corpus.yaml`) · **dossier focus** · **compliance specifics** ·
**crossovers**.

### M0 — `sozialrecht` (existing; peer module)

- **Scope:** Bürgergeld / Grundsicherungsgeld (SGB II), Verfahren (SGB X),
  Sozialgerichtsverfahren (SGG); adjacent SGB I, III, IX, XII as corpus.
- **Documents:** Bewilligungs-, Änderungs-, Aufhebungs- und
  Erstattungsbescheide, Sanktions-/Leistungsminderungsbescheide, Anhörungen.
- **Deadlines (built):** Bekanntgabefiktion § 37 Abs. 2 SGB X; Widerspruch
  § 84 SGG; rollover § 64 SGG; Jahresfrist § 66 Abs. 2 SGG; non-VA detection.
- **Calculators (built):** § 11b SGB II cascade, Regelbedarf, Bedarf/Einkommen
  reconciliation, Aufrechnung, arithmetic checks; regime switch 2026-07-01.
- **Drafts (built):** Widerspruch (+ Jahresfrist variant), Überprüfungsantrag
  § 44 SGB X, Akteneinsicht § 25 SGB X.
- **P9 work:** extraction only, zero behaviour change (ARCHITECTURE.md § 8).

### M1 — `schuldnerrecht`

- **Scope:** Mahnverfahren, Inkasso, Zwangsvollstreckung gegen Privatpersonen,
  Pfändungsschutz (P-Konto), Verjährung von Forderungen, Weg in die
  Verbraucherinsolvenz (preparation for the Schuldnerberatung, not the
  insolvency filing itself).
- **Documents:** Inkasso-Schreiben, Mahnbescheid, Vollstreckungsbescheid,
  Pfändungs- und Überweisungsbeschluss, Ladung zur Vermögensauskunft.
- **Deadlines:** Widerspruch gegen Mahnbescheid 2 weeks (§ 692 Abs. 1 Nr. 3
  ZPO; late Widerspruch possible until Vollstreckungsbescheid, § 694 ZPO);
  Einspruch gegen Vollstreckungsbescheid 2 weeks (§§ 700, 339 ZPO);
  Verjährung (§§ 195, 199 BGB; titulierte Forderungen § 197 BGB).
- **Calculators:** Pfändungsfreigrenzen (§ 850c ZPO, annual table effective
  1 July → parameter set), P-Konto Sockelbetrag and Erhöhungsbeträge
  (§§ 899, 902 ZPO; § 850k for conversion), Verjährungseintritt, Inkassokosten plausibility
  (statutory caps, RDG/RVG — anchor to verify).
- **Drafts:** Widerspruch gegen Mahnbescheid (form guidance; no blanket
  mandatory-form claim for natural persons, §§ 692, 702 ZPO), Bestreiten/Verjährungseinrede an Inkassounternehmen,
  Antrag auf P-Konto-Bescheinigung (§ 903 ZPO), DSGVO-Auskunft (Art. 15) an
  Auskunfteien.
- **Corpus:** ZPO (8. Buch), BGB (Verjährung, Verzug), InsO §§ 304 ff., RDG
  (Inkasso), RVG (VV), Pfändungsfreigrenzenbekanntmachung.
- **Dossier focus:** Gläubigerliste with amounts/titles/status — the exact
  input a Schuldnerberatung needs for the § 305 InsO Bescheinigung.
- **Compliance:** Schuldnerberatungsstellen are the primary human
  counterpart; referral targets in manifest.
- **Crossovers:** M0 (Aufrechnung, SGB-II-Leistungen unpfändbar), M2
  (Mietschulden).

### M2 — `mietrecht`

**Backend implementation (2026-11-27):** 0.2.0 implements explicit qualified
deadlines, calculators, guarded drafts, intake/dossier and multilingual copy.
Regional data is positive-only and incomplete nationally; all16 state source
statuses and exact unsupported coverage are recorded in
[`sources/coverage.yaml`](../modules/mietrecht/sources/coverage.yaml).
Unknown/expired coverage yields no amount. Twenty synthetic cases and offline
dossier/plain reports do not establish live inference quality or deployment
corpus population. Human review/promotion remain deferred under D-071.
See [D-073](decisions/D-073-wp131-tenancy-implementation.md).

- **Scope:** Wohnraummiete from the tenant's side: Mieterhöhung,
  Betriebskosten, Mängel/Minderung, Kündigung, Kaution, Räumung.
- **Documents:** Mieterhöhungsverlangen, Betriebskostenabrechnung,
  Kündigung, Abmahnung, Modernisierungsankündigung, Räumungsklage.
- **Deadlines:** Zustimmung zur Mieterhöhung by end of the second calendar
  month after receipt (§ 558b Abs. 2 BGB); Einwendungen gegen
  Betriebskostenabrechnung 12 months (§ 556 Abs. 3 BGB); Kündigungsfristen
  (§ 573c BGB); Widerspruch Sozialklausel (§ 574b BGB); Schonfristzahlung
  (§ 569 Abs. 3 Nr. 2 BGB).
- **Calculators:** Kappungsgrenze (§ 558 Abs. 3 BGB, 20 % / 15 % by
  Landesverordnung → parameter), Mietpreisbremse (§ 556d BGB, Gebietsliste
  → parameter), Betriebskosten-Umlage plausibility (BetrKV,
  HeizkostenV), Minderungsquote ranges (case-law-based → evidence, not
  asserted), Kündigungsfrist.
- **Drafts:** Antwort auf Mieterhöhungsverlangen, Belegeinsicht/Einwendungen
  Betriebskosten, Mängelanzeige mit Fristsetzung, Widerspruch nach § 574 BGB.
- **Corpus:** BGB §§ 535–580a, BetrKV, HeizkostenV, Landes-Mietpreis- und
  Kappungsgrenzenverordnungen (sourcing per Land = open question).
- **Compliance:** Mietervereine operate under § 7 RDG — natural adopter.
- **Crossovers:** M0 (Kosten der Unterkunft § 22 SGB II, Mietschuldenübernahme
  § 22 Abs. 8 SGB II), M1.

### M3 — `arbeitsrecht`

**Backend implemented (WP-132, 2026-11-27):** experimental 0.2.0 on core
3.7.0 / module API 3.5. Qualified critical dismissal deadlines, explicit
knowledge-date registration reminders, five statutory calculator modes,
guarded drafts, public intake and DE/EN/de-LS dossier copy. Eighteen synthetic
cases and offline reports accompany the module. §38 individualized timing
exceptions and non-working-day backwards targets require review; no automatic
exclusion-clause validity or generic severance entitlement. Deployment ingestion,
live evaluation and human promotion are not claimed. See
[D-074](decisions/D-074-wp132-employment-implementation.md).

- **Scope:** individual employment law from the employee's side:
  Kündigung, Abmahnung, Lohn, Urlaub, Arbeitszeugnis, Aufhebungsvertrag.
- **Documents:** Kündigung, Abmahnung, Aufhebungsvertrag, Lohnabrechnung,
  Arbeitszeugnis, Arbeitsvertrag.
- **Deadlines:** Kündigungsschutzklage 3 weeks after receipt (§ 4 KSchG) —
  severity `critical`, banner-mandatory; Arbeitsuchendmeldung (§ 38 SGB III,
  crossover); vertragliche/tarifliche Ausschlussfristen (extracted from the
  user's own contract, flagged for review).
- **Calculators:** Kündigungsfrist (§ 622 BGB), Abfindung nach § 1a KSchG
  (0.5 Monatsverdienst je Beschäftigungsjahr), Urlaubsanspruch/-abgeltung
  (BUrlG), Mindestlohn check (MiLoG → parameter).
- **Drafts:** Geltendmachung offener Ansprüche, Zeugnisberichtigung,
  Checkliste Kündigungsschutzklage (Rechtsantragstelle preparation).
- **Corpus:** BGB §§ 611a–630, KSchG, BUrlG, TzBfG, EntgFG, MiLoG, MuSchG,
  ArbZG, ArbGG (procedure).
- **Compliance:** Gewerkschaften (§ 7 RDG) as adopters; Aufhebungsvertrag →
  Sperrzeit warning is information, not advice.
- **Crossovers:** M0 / SGB III (Sperrzeit § 159 SGB III).

### M4 — `vertragsrecht`

**Backend implemented (WP-133, 2026-11-27):** experimental 0.2.0 on core
3.8.0 / module API 3.6. Qualified withdrawal, ordinary-goods limitation,
evidentiary-presumption and regular-limitation dates; exact segmented interest,
withdrawal and flight-band checks; guarded drafts, intake/dossier and DE/EN/de-LS
copy. EGBGB/EUR-Lex article sources preserve nested identities. Source checks
and fixtures do not prove deployment ingestion; EUR-Lex publisher challenge
prevented a raw ingestion smoke test. Twenty synthetic cases and offline
reports are included. §477 is not a filing deadline; special regimes and
missing qualifications require review. See [D-075](decisions/D-075-wp133-contract-implementation.md).
Human review/promotion and live inference remain deferred under D-071.


- **Scope:** consumer and everyday contract law: Widerruf, Gewährleistung,
  Kündigung von Dauerschuldverhältnissen, unerlaubte Telefonwerbung/
  Abofallen, Fluggastrechte.
- **Documents:** Rechnungen, Mahnungen, Vertragsbestätigungen, Ablehnungen
  von Gewährleistungs- oder Erstattungsansprüchen.
- **Deadlines:** Widerruf 14 days (§ 355 Abs. 2 BGB) and maximal Widerrufsfrist
  (§ 356 Abs. 4 BGB); Mängelverjährung (§ 438 BGB); Beweislastumkehr
  (§ 477 BGB); regelmäßige Verjährung (§§ 195, 199 BGB).
- **Calculators:** Verzugszinsen (§ 288 BGB over Basiszinssatz § 247 BGB →
  parameter), Widerrufsfrist end, Fluggast-Ausgleich (Art. 7 VO (EG)
  261/2004 distance bands).
- **Drafts:** Widerrufserklärung, Mängelrüge mit Nachfristsetzung, Kündigung,
  Fluggast-Anspruchsschreiben.
- **Corpus:** BGB Schuldrecht AT/BT (§§ 241–853 selection), EGBGB
  (Informationspflichten), VO (EG) 261/2004 via EUR-Lex.
- **Compliance:** Verbraucherzentralen are the natural institutional adopter.

### M5 — `verkehrsrecht`

**Backend implemented (WP-134, 2026-11-27):** experimental 0.1.0 on core
3.9.0/module API 3.7. Critical qualified actual-service objection, StPO
rollover, selected speed table, current-regime limitation/ban/register checks,
guarded drafts, intake/dossier and DE/EN/de-LS copy. Twenty synthetic cases;
human review/promotion and live inference remain deferred. Paragraph corpus
support is partial: annexes/tables are not ingested; selected table entries
are parameters. Accident settlement remains stage 2. See
[D-076](decisions/D-076-wp134-traffic-implementation.md).


- **Scope:** Bußgeldverfahren (traffic), Fahreignungsregister (Punkte),
  Fahrverbot; stage 2: Verkehrsunfall-Schadensregulierung.
- **Documents:** Anhörungsbogen, Zeugenfragebogen, Bußgeldbescheid,
  Punkte-Mitteilung, (stage 2) Schreiben der Haftpflichtversicherung.
- **Deadlines:** Einspruch gegen Bußgeldbescheid 2 weeks after Zustellung
  (§ 67 OWiG); Verfolgungsverjährung (§ 26 Abs. 3 StVG); Fahrverbot
  Antrittsfrist (current § 25 Abs. 2–3 StVG; former paragraph 2a is stale).
- **Calculators:** Regelsatz/Punkte/Fahrverbot lookup (BKatV +
  Bußgeldkatalog → parameter set), Verjährungsprüfung, Punktestand/
  Tilgungsfristen (§ 29 StVG).
- **Drafts:** Einspruch, Antrag auf Akteneinsicht incl. Messdaten (§ 49 OWiG),
  Antwort auf Anhörungsbogen (rights information: no duty to testify).
- **Corpus:** OWiG, StVG, StVO, BKatV, FeV.
- **Builds:** core OWiG procedure library (Zustellung, Einspruch, Akteneinsicht)
  reused by M10.

### M6 — `familienrecht`

- **Scope:** Trennung/Scheidung preparation, Kindes- und Ehegattenunterhalt,
  Sorge- und Umgangsrecht (information only), Unterhaltsvorschuss.
- **Documents:** Unterhaltsaufforderung, Auskunftsverlangen, Beschlüsse des
  Familiengerichts, Jugendamt-Schreiben, UVG-Bescheide.
- **Deadlines:** Beschwerde 1 month (§ 63 FamFG); Auskunfts- and
  Verzugszeitpunkte for Unterhalt (§ 1613 BGB) — when maintenance can be
  claimed retroactively.
- **Calculators:** Kindesunterhalt (Mindestunterhalt § 1612a BGB via
  Mindestunterhaltsverordnung → parameter; Düsseldorfer Tabelle as
  guideline → parameter, reuse terms = open question), Kindergeldanrechnung
  (§ 1612b BGB), Selbstbehalt, UVG amounts.
- **Drafts:** Auskunftsverlangen, Stellungnahme-Gliederung, UVG-Antrag
  preparation.
- **Corpus:** BGB Buch 4, FamFG, UVG, MindUhV.
- **Compliance:** data of third parties (children, ex-partner) — strict
  minimisation; Art. 9 data likely; Kindeswohl topics are referral-first.
- **Crossovers:** M0 (Unterhalt als Einkommen, § 33 SGB II Anspruchsübergang).

### M7 — `aufenthaltsrecht`

- **Scope:** Aufenthaltstitel (Verlängerung, Fiktionswirkung), Asylverfahren
  (information + deadline protection), Einbürgerung (preparation).
- **Documents:** Bescheide der Ausländerbehörde, BAMF-Bescheide, Ladungen,
  Anhörungsschreiben, Duldungen.
- **Deadlines:** Klagefrist 1 month (§ 74 Abs. 1 VwGO); Widerspruch where the
  Land retains it (per-Land parameter); AsylG Klagefristen 2 weeks / 1 week
  incl. Eilantrag (§ 74 AsylG, § 36 Abs. 3 AsylG) — severity `critical`,
  mandatory referral banner; Fortgeltungsfiktion requires application before
  expiry (§ 81 Abs. 4 AufenthG).
- **Calculators:** Lebensunterhaltssicherung (§ 2 Abs. 3 AufenthG, crossover
  M0 parameters), Fristen for Titel expiry, Einbürgerung residence period
  (StAG → parameter).
- **Drafts:** Antrag auf Verlängerung (checklist), Akteneinsicht,
  Fristverlängerungsbitte; **no** asylum-claim content drafting.
- **Corpus:** AufenthG, AsylG, AufenthV, BeschV, FreizügG/EU, StAG, VwGO.
- **Compliance:** Annex III(7) AI Act covers authority-side migration use —
  claimant-side purpose must be lint-enforced with module deny phrases;
  Art. 9 data; strongest duty-of-care profile. **Depends on P12 i18n**
  (at minimum EN, AR, FA, UK, TR, RU copy) — hence queued after the UI.
- **Crossovers:** M0 (AsylbLG vs. SGB II), M3.

### M8 — `steuerrecht`

- **Scope:** Einkommensteuer natural persons (employees, pensioners, small
  side income), Steuerbescheid check, Einspruch, Aussetzung der Vollziehung.
- **Documents:** Einkommensteuerbescheid, Schätzungsbescheid, Anfragen des
  Finanzamts, Vorauszahlungsbescheide.
- **Deadlines:** Bekanntgabefiktion (§ 122 Abs. 2 AO); Einspruch 1 month
  (§ 355 AO); Jahresfrist bei fehlerhafter Belehrung (§ 356 Abs. 2 AO);
  Abgabefristen (§ 149 AO → parameter).
- **Calculators:** ESt-Tarif (§ 32a EStG → parameter per year), Pauschbeträge,
  Bescheid-vs-Erklärung diff. **gettsim (AGPL) is never embedded**; law-derived
  reimplementation in MIT, or optional AGPL sidecar (D-041).
- **Drafts:** Einspruch, Antrag auf Aussetzung der Vollziehung (§ 361 AO),
  Antrag auf schlichte Änderung (§ 172 AO).
- **Corpus:** EStG, AO, SolZG, FGO.
- **Compliance:** **StBerG** — Hilfeleistung in Steuersachen for others is
  reserved (Steuerberater, Lohnsteuerhilfevereine). Module scope is strictly
  own-matter self-help; advice-center use is **not** a supported mode for this
  module (manifest `third_party_assistance: false`).

### M9 — `erbrecht`

- **Scope:** gesetzliche Erbfolge, Testament (reading, not drafting),
  Ausschlagung, Pflichtteil, Erbschein, Erbschaftsteuer, Schenkung.
- **Documents:** Testamentseröffnungsprotokoll, Schreiben des Nachlassgerichts,
  Pflichtteilsforderungen, ErbSt-Erklärungsaufforderungen.
- **Deadlines:** Ausschlagung 6 weeks / 6 months (§ 1944 BGB); Anzeigepflicht
  ErbSt (§ 30 ErbStG); Pflichtteil-Verjährung (§§ 195, 199, 2332 BGB).
- **Calculators:** gesetzliche Erbquoten (§§ 1924 ff., 1931, 1371 BGB),
  Pflichtteil (§ 2303 BGB), ErbSt Freibeträge/Steuersätze (§§ 16, 19 ErbStG
  → parameter).
- **Drafts:** Auskunftsverlangen Pflichtteil (§ 2314 BGB), Ausschlagung
  preparation (form requirement: Nachlassgericht/notary — tool prepares only).
- **Corpus:** BGB Buch 5, ErbStG, HöfeO (existing v2.0.0 sources: `bgb`,
  `erbstg`, `hoefev`), FamFG (Nachlass).
- **Legacy:** absorbs `schenkungsrecht`; existing erbrecht presets/prompts
  are the starting material.

### M10 — `strafrecht`

- **Scope:** two own-matter roles: **Beschuldigte** (Anhörung, Strafbefehl,
  Ladung) and **Verletzte** (Strafanzeige, Nebenklage information,
  Opferentschädigung — crossover SGB XIV). Referral-first by design.
- **Documents:** Vorladung/Anhörung als Beschuldigter, Strafbefehl,
  Anklageschrift, Einstellungsbescheid, Urteil.
- **Deadlines:** Einspruch gegen Strafbefehl 2 weeks (§ 410 StPO); Berufung
  and Revision 1 week (§§ 314, 341 StPO); Beschwerde gegen Einstellung
  (§ 172 StPO) — all severity `critical`.
- **Calculators:** Tagessatz plausibility (§ 40 StGB), Verjährung
  (§§ 78 ff. StGB) — information only.
- **Drafts:** Einspruch gegen Strafbefehl (form-only, no reasoning),
  Antrag auf Pflichtverteidigerbestellung (§ 140 StPO) preparation; rights
  information (§ 136 StPO: right to remain silent).
- **Corpus:** StGB, StPO, JGG, SGB XIV, OWiG (shared with M5).
- **Compliance:** Art. 10 DSGVO (criminal-offence data) — local-only default,
  no external inference without explicit per-case consent (to decide in
  WP-139.1); Annex III(6) AI Act concerns law-enforcement use — module deny
  phrases; every output leads with Verteidiger/Opferberatung referral.

---

## 4. Module definition of done (applies to every module before `verified`)

1. Manifest valid; scope and out-of-scope written; statutory anchors verified
   against current statute text (dated).
2. Corpus scope ingested; Rechtsstand visible via `/corpus/health`.
3. Parameters seeded with `source_quote` and validity periods. No named-person
   approval gate; human parameter review is deferred under D-071.
4. Every deadline spec has golden date tests incl. holiday/rollover edge cases.
5. Every calculator is pure, parameter-backed, unit-tested to the cent.
6. Every draft renders unbound assertions as `[BITTE PRÜFEN]`.
7. Intake schema + dossier checklist + lawyer-question list.
8. Plain-language copy (Bürgersprache DE + EN minimum; Leichte Sprache for
   critical-deadline copy) implemented and automatically checked. Human review
   is deferred until all modules are implemented (D-071); keep draft status.
9. Goldset ≥ 15 synthetic cases, eval report published, gate thresholds met.
10. Disclaimer addendum + deny phrases; purpose-drift lint green.
11. Promotion recorded as a D-entry; module CHANGELOG at `1.0.0`.

---

*Changes to this catalog follow semantic versioning: adding/removing a module
or reordering the queue is MINOR; correcting an anchor is PATCH.*
