# Citizen — Rechtlicher Hinweis, Haftungsausschluss, Statement und KI-VO-Klassifizierung

**Version:** 3.3.0 · **Stand:** 2026-11-27

**Autor:** www.github.com/playa77

**Repository:** https://github.com/playa77/citizen

Dieses Dokument fasst den rechtlichen Hinweis und Haftungsausschluss, das
Projektstatement sowie die Compliance-/KI-VO-Klassifizierung des Projekts in
einer einzigen deutschsprachigen Fassung zusammen (englische Fassung:
[DISCLAIMER_EN.md](DISCLAIMER_EN.md)). Es ersetzt die früheren eigenständigen
Dokumente `DISCLAIMER_DE.md` (v1.1.0), `STATEMENT.md` (v1.0.0) und
`COMPLIANCE.md` (v1.1.0). Teil D enthält seit Fassung 3.0.0 die
Ergänzungen der Rechtsgebiets-Module.

Es enthält rechtliche Hinweise und Haftungsausschlüsse. Es ersetzt oder ändert
die anwendbaren Open-Source-Lizenzbedingungen nicht, sofern dies nicht
ausdrücklich angegeben ist.

Diese Software wird unter der MIT-Lizenz und **unentgeltlich** bereitgestellt.
Durch die Bereitstellung, den Abruf oder die Nutzung entsteht kein Entgelt-,
Austausch- oder Dienstverhältnis.

Soweit dieses Dokument vertragliche Regelungen enthält, gelten diese nur im
gesetzlich zulässigen Umfang und vorbehaltlich zwingender gesetzlicher
Vorschriften.

Änderungen an diesem Dokument folgen semantischer Versionierung; die
Änderungshistorie befindet sich am Ende des Dokuments.

---

## Teil A — Warum es dieses Projekt gibt

### Was ist

Citizen ist heute ein Prototyp: ein rechtsgebietsneutraler Kern mit
Rechtsgebiets-Modulen. Das erste und bislang einzige ausgereifte Modul,
Sozialrecht, liest deutsche Sozialrechts-Bescheide ein, bindet jede Aussage an
den Gesetzestext, rechnet Berechnungen deterministisch nach und bestimmt
Fristen auf den Tag genau. Weitere Rechtsgebiete — Arbeits-, Erb-, Familien-,
Straf- und Vertragsrecht — liegen als experimentelle Module vor: Sie
ordnen Anliegen zu und beziehen die passenden Rechtsquellen ein, berechnen
aber noch keine Fristen und keine Beträge. Die experimentellen Module
Schuldnerrecht und Mietrecht bieten begrenzte, qualifizierte Frist- und
Rechenprüfungen mit ausdrücklichen Voraussetzungen und Grenzen (Teil D). Es gibt ein versioniertes Golden Set mit verifizierten Prüffällen,
an dem jede Änderung gemessen wird. Es gibt bekannte Grenzen, und sie stehen
im Repo statt unter dem Teppich. Das ist der ehrliche Ist-Zustand:
funktionierend, ungeschliffen, messbar — und noch kein Produkt.

### Was sein soll

Ein Mensch hält ein Schreiben in der Hand, von dem viel abhängt — einen
Bescheid, eine Kündigung, einen Strafbefehl — und bekommt innerhalb von
Minuten vier Antworten: **Was steht da drin? Stimmt das? Bis wann muss ich
reagieren? Was mache ich jetzt?** — nachvollziehbar belegt, auf den Cent
nachgerechnet, auf den Tag terminiert, in verständlicher Sprache. Und er
kommt vorbereitet zum Termin bei Anwältin, Anwalt oder Beratungsstelle: mit
geordnetem Sachverhalt, den Fristen, den Unterlagen und den richtigen Fragen.
Citizen ersetzt diese Beratung nicht, es macht sie wirksamer. Kostenlos.
Quelloffen. Ohne dass seine Daten Europa verlassen. Und dasselbe Werkzeug
liegt in jeder Beratungsstelle und macht aus einer Dreiviertelstunde
Erstprüfung zehn Minuten mit Paragraphenbeleg.

### Warum

Im Jahr 2025 wurden über eine halbe Million Widersprüche gegen
Jobcenter-Bescheide eingelegt. Rund jeder dritte war erfolgreich. In mehr als
42.000 Fällen hatte die Behörde das Gesetz nachweislich falsch angewandt.
Diese Quote ist seit Jahren stabil — sie ist kein Ausrutscher, sie ist ein
Systemzustand. Und sie trifft asymmetrisch: auf der einen Seite eine
Verwaltung, die millionenfach maschinell Bescheide erzeugt; auf der anderen
ein einzelner Mensch mit einer Monatsfrist, ohne Anwalt, oft ohne die Sprache
des Bescheids zu sprechen — im wörtlichen wie im übertragenen Sinn.

Ein Rechtsstaat ist ein Versprechen: dass Rechte nicht davon abhängen, wer man
ist und was man sich leisten kann. Dieses Versprechen ist nur so viel wert wie
seine Durchsetzbarkeit. Ein Recht, das man nicht kennt, eine Frist, die man
verpasst, eine Berechnung, die man nicht prüfen kann — das ist auf dem Papier
ein Recht und in der Wirklichkeit keines.

Dazu kommt heute ein zweiter Grund, der über das Sozialrecht hinausweist. Wir
stehen am Anfang eines Übergangs, in dem maschinelle Intelligenz zur
Grundinfrastruktur wird — und Übergänge haben eine tückische Eigenschaft:
**Sie frieren die Machtverteilung ein, die im Moment des Übergangs besteht.**
Verwaltungen werden ihre Seite automatisieren; das ist sicher. Wenn die
Bürgerseite nicht dieselbe Klasse von Werkzeugen bekommt, wird die bestehende
Asymmetrie nicht nur konserviert, sondern auf höherem Niveau festgeschrieben.
Citizen ist mein Beitrag zur Gegenthese: dieselbe Fähigkeit, dieselbe
Gründlichkeit, dieselbe Unermüdlichkeit — in der Hand der schwächsten Partei.
Es ist eine kleine, konkrete Antwort auf die große Frage, wem die Maschinen
dienen sollen: allen. Sonst niemandem.

Und ein dritter, nüchterner Grund, aus der Perspektive komplexer Systeme: Eine
Fehlerquote, die über Jahre stabil bei einem Drittel liegt, bedeutet, dass die
Rückkopplungsschleife des Systems beschädigt ist. Jeder fehlerhafte Bescheid,
dem niemand widerspricht, ist ein Fehlersignal, das nie ankommt. Werkzeuge,
die Widersprüche präziser, belegter und häufiger machen, sind deshalb kein
Angriff auf die Verwaltung — sie sind die Reparatur ihres Korrektivs. Eine
Verwaltung, deren Fehler zuverlässig gefunden werden, wird besser. Davon
profitieren am Ende beide Seiten des Schreibtischs.

Das Sozialrecht ist der Ausgangspunkt, nicht die Grenze. Dieselbe Asymmetrie —
ein formalisiertes Gegenüber, eine kurze Frist, ein Mensch ohne Fachwissen —
besteht im Mietrecht, im Arbeitsrecht, im Familienrecht und im
Strafverfahren. Deshalb wächst Citizen modular: Jedes Rechtsgebiet kommt als
eigenes Modul mit eigener Version, eigenem Golden Set und ausdrücklich
erklärten Grenzen hinzu und gilt erst nach Prüfung als ausgereift.

### Grundsätze

**Nachrechenbarkeit statt Vertrauen.** Was deterministisch geht — Fristen,
Beträge, Zitate — wird deterministisch gerechnet und verifiziert. Das
Sprachmodell ist Werkzeug, nicht Autorität.

**Ehrlichkeit über Grenzen.** Wenn ein Bescheid rechtmäßig ist, sagt Citizen
das. Falsche Hoffnung ist keine Hilfe, sie ist eine zweite Kränkung. Unsichere
Rechtsfragen werden als unsicher gekennzeichnet, nicht weggeglättet.

**Die Daten bleiben beim Menschen.** Pseudonymisierung vor jeder Verarbeitung,
Inferenz ausschließlich in Europa unter Auftragsverarbeitung, lokale
Datenhaltung. Behauptet wird nur, was technisch erzwungen ist.

**Vorbereitung statt Vertretung.** Citizen hilft Menschen in ihren eigenen
Rechtsangelegenheiten und bei der Vorbereitung auf eine Beratung. Es vertritt
niemanden und berät niemanden in fremden Angelegenheiten.

**Der Mensch entscheidet.** Citizen informiert, belegt, rechnet nach und
liefert Bausteine. Bewertet, entschieden und unterschrieben wird von Menschen —
vom Betroffenen selbst oder von Beratenden, die beraten dürfen.

**Offenheit als Prüfbarkeit.** MIT-Lizenz, öffentliches Golden Set,
versionierte Korrektur eigener Fehler. Ein Werkzeug, das Behördenfehler findet,
muss sich selbst dieselbe Prüfbarkeit gefallen lassen.

### Was das nicht ist

Keine Rechtsberatung — Rechtsinformation und Selbsthilfe. Kein Startup — es
gibt nichts an Menschen in Existenznot zu verdienen, und es wird hier auch
nicht versucht. Keine Kampfansage an Jobcenter-Mitarbeitende — die meisten
arbeiten unter Bedingungen, die Fehler erzeugen; dieses Werkzeug richtet sich
gegen Fehler, nicht gegen Menschen. Keine Kanzleisoftware — Abrechnung,
Akten- oder Mandantenverwaltung gibt es nicht und wird es nicht geben (D-034).
Und kein Werkzeug der anderen Seite: Citizen ist nicht dazu bestimmt, von
Behörden, Gerichten, Strafverfolgungs- oder Migrationsbehörden oder in deren
Auftrag eingesetzt zu werden (D-035).

### Einladung

Wer juristisch prüfen, Fälle validieren, Code beitragen oder das Werkzeug in
einer Beratungsstelle erproben will: Issues und Pull Requests sind offen. Die
beste Form der Kritik an diesem Projekt ist ein Golden-Set-Fall, den es falsch
beantwortet.

*Zahlen: Widerspruchs- und Klagestatistik der Bundesagentur für Arbeit 2025
(147.213 von 476.728 entschiedenen Widersprüchen revidiert; 42.303 Fälle
fehlerhafter Rechtsanwendung; Jobcenter Essen: 53,7 % Fehlerquote bei
erledigten Widersprüchen, Mai 2026).*

---

## Teil B — Rechtlicher Hinweis und Haftungsausschluss

### B.1 Charakter der Software

Dieses Repository enthält persönliche, maßgeschneiderte Software, die in erster
Linie für den eigenen Gebrauch, zur Dokumentation, zu Experimentierzwecken und
als persönliche Referenz des Autors entwickelt wurde.

Die Software wurde nicht für den produktiven Einsatz, die kommerzielle Nutzung,
den öffentlichen Betrieb, sicherheitskritische Systeme, Security-kritische
Systeme, medizinische Systeme, Finanzsysteme, die anwaltliche oder sonstige
professionelle Rechtsberatung oder sonstige Umgebungen entwickelt, getestet,
auditiert, zertifiziert oder freigegeben, in denen Fehler, Fehlfunktionen,
Datenverlust, fehlerhafte Ausgaben oder Sicherheitsprobleme Schäden
verursachen könnten.

Die öffentliche Verfügbarkeit dieses Repositorys stellt kein Produktangebot,
keine professionelle Dienstleistung, keine Rechtsdienstleistung, keine
Empfehlung, keine Garantie und keine Zusicherung dar, dass die Software für
einen bestimmten Zweck geeignet ist.

### B.2 Keine Rechtsberatung

Diese Software ist ein technisches Werkzeug ausschließlich zu Informations-,
Bildungs-, Experimentier- und persönlichen Referenzzwecken.

Sie stellt keine Rechtsberatung, keine professionelle Beratung, keine
anwaltliche Vertretung und keinen Ersatz für die Beratung durch einen
qualifizierten Rechtsanwalt oder sonstigen qualifizierten Berufsträger dar.

Der Autor wird nicht in konkreten fremden Angelegenheiten im Sinne des § 2
Abs. 1 des Rechtsdienstleistungsgesetzes (RDG) tätig. Die Software arbeitet
schematisch nach vorgegebenen Regeln, Verfahren und Prüfschritten; eine
rechtliche Prüfung des Einzelfalls durch den Autor findet nicht statt.
Nutzerinnen und Nutzer, die die Software auf eigene Dokumente und eigene
Angelegenheiten anwenden, besorgen ihre eigenen Rechtsangelegenheiten
(Selbsthilfe). Der Einsatz der Software im Rahmen der Beratung oder
Unterstützung Dritter ist ausschließlich solchen Stellen und Personen
gestattet, die hierzu nach dem RDG oder anderen Vorschriften befugt sind; die
Verantwortung für das Vorliegen dieser Befugnis und für die Beratung selbst
liegt allein bei diesen Stellen und Personen.

Durch den Zugriff auf die Software, ihre Installation, Ausführung oder Nutzung
entsteht kein Mandatsverhältnis, Treuhandverhältnis, Beratungsverhältnis,
anwaltliches Verhältnis oder sonstiges professionelles Rechtsverhältnis.

Sie dürfen sich nicht allein auf diese Software stützen, wenn Sie rechtliche
Entscheidungen treffen, Anträge stellen, Widersprüche oder Rechtsmittel
einlegen, mit Behörden kommunizieren, vertragliche Entscheidungen treffen,
gerichtliche oder außergerichtliche Strategien entwickeln oder sonstige
rechtlich relevante Handlungen vornehmen oder unterlassen.

Holen Sie stets qualifizierten Rechtsrat ein, bevor Sie Handlungen mit
rechtlichen Folgen vornehmen oder unterlassen.

### B.3 KI-generierte Inhalte und Genauigkeit

Ausgaben können durch künstliche Intelligenz, große Sprachmodelle,
automatisierte Abrufsysteme, Ranking-Systeme, Zitiersysteme oder sonstige
automatisierte Verfahren erzeugt werden.

Auch wenn die Software versucht, quellenbasierte Bindung, Retrieval
Augmentation, Quellenverweise, Zitierverfolgung oder ähnliche Mechanismen zu
verwenden, können Ausgaben ungenau, unvollständig, irreführend, veraltet,
halluziniert oder auf einer fehlerhaften Auslegung von Gesetzen, Verordnungen,
Verwaltungsvorschriften, Rechtsprechung, Verträgen, Richtlinien oder sonstigen
Materialien beruhen.

Der Autor übernimmt keine Gewährleistung oder Zusicherung dafür, dass
Ausgaben richtig, vollständig, aktuell, rechtlich zutreffend, verwertbar,
zuverlässig oder für einen bestimmten Zweck geeignet sind.

Sie sind allein dafür verantwortlich, alle Ausgaben vor ihrer Verwendung
eigenständig anhand offizieller, aktueller und maßgeblicher Quellen zu
überprüfen. Dazu gehört, soweit einschlägig, die Prüfung von Originalgesetzen,
Verordnungen, Verwaltungsvorschriften, Gerichtsentscheidungen, amtlichen
Veröffentlichungen, Fristen, Verfahrensanforderungen und professionellem
Rechtsrat.

### B.4 Datenverarbeitung, Datenschutz und Inferenzprofile

Die Datenhaltung der Software erfolgt lokal. Soweit die Software externe
Dienste zur Verarbeitung nutzt (insbesondere Sprachmodell- und
Embedding-Dienste), geschieht dies ausschließlich über konfigurierbare,
versionierte **Inferenzprofile**. Das jeweils aktive Profil kann über den
API-Endpunkt `GET /api/v1/meta/active-profile` abgefragt werden und wird in
erzeugten Dokumenten ausgewiesen.

Die Software sieht insbesondere folgende Profile vor:

- **eu-avv** (Standard für den Einsatz in Organisationen): Vor jeder externen
  Verarbeitung werden direkte Identifikatoren (insbesondere Namen, Anschriften,
  Kennnummern, Kontodaten, Kontaktdaten, Geburtsdaten) durch eine technisch
  erzwungene Pseudonymisierungsstufe ersetzt. Die Übermittlung erfolgt
  ausschließlich an in der Profilkonfiguration freigegebene Endpunkte in der
  Europäischen Union auf Grundlage eines Auftragsverarbeitungsvertrags. Ein
  technischer Egress-Guard blockiert Übermittlungen an nicht freigegebene
  Ziele sowie Übermittlungen erkannter Klartext-Identifikatoren.
- **extern-openrouter** (Selbsthilfe- und Entwicklungsbetrieb):
  Pseudonymisierte Eingabedaten können an externe Anbieter übermittelt werden,
  auch an Server außerhalb Ihres Landes oder Ihrer Rechtsordnung,
  einschließlich Regionen mit abweichenden Datenschutzgesetzen und
  Datenschutzstandards.
- **on-prem** (sofern konfiguriert): keine externe Übermittlung.

Die Pseudonymisierung erfasst direkte Identifikatoren nach dem dokumentierten
Regelwerk. Restrisiken — insbesondere eine mögliche Identifizierbarkeit aus
dem verbleibenden Fallkontext sowie Fehlerkennungen einzelner Angaben — können
nicht ausgeschlossen werden. Pseudonymisierte Daten bleiben personenbezogene
Daten im Sinne der DSGVO.

Der Autor kontrolliert Drittanbieter nicht und übernimmt — auch bei Bestehen
eines Auftragsverarbeitungsvertrags — keine Gewährleistung oder Garantie für
deren Sicherheitsmaßnahmen, Verfügbarkeit, Datenspeicherung, Löschpraktiken,
Verwendung zu Trainingszwecken, Vertraulichkeit, regulatorische Compliance
oder Einhaltung der DSGVO oder anderer Datenschutzgesetze. Die Auswahl,
Prüfung und vertragliche Einbindung externer Anbieter obliegt demjenigen, der
die Software betreibt.

Wer die Software als betroffene Person auf **eigene** Dokumente und Daten
anwendet, entscheidet hierüber eigenverantwortlich und informiert unter dem
jeweilig aktiven Profil. Wer mit der Software Daten **Dritter** verarbeitet
(insbesondere Beratungsstellen und sonstige Organisationen), ist selbst
Verantwortlicher im Sinne der DSGVO und allein dafür verantwortlich, sämtliche
Pflichten nach anwendbarem Datenschutzrecht, Geheimhaltungsrecht (insbesondere
dem Sozialgeheimnis nach § 35 SGB I, §§ 67 ff. SGB X), Berufsrecht,
Verbraucherschutzrecht und Informationssicherheitsrecht zu bestimmen und
einzuhalten — einschließlich Rechtsgrundlage, Information der Betroffenen,
erforderlicher Einwilligungen, Auftragsverarbeitungsverträge, technischer und
organisatorischer Maßnahmen, Verarbeitungsverzeichnis und, soweit
erforderlich, Datenschutz-Folgenabschätzung.

Besondere Kategorien personenbezogener Daten, vertrauliche Informationen,
privilegierte Informationen, Geschäftsgeheimnisse, Mandantendaten sowie
sonstige sensible Informationen dürfen nur eingegeben oder verarbeitet werden,
wenn die vorgenannten Voraussetzungen erfüllt sind.

Dieser Haftungsausschluss ist keine Datenschutzerklärung.

Sie sind allein verantwortlich für alle Daten, die Sie unter Verwendung der
Software eingeben, verarbeiten, übermitteln, speichern oder offenlegen.

### B.5 Keine Gewährleistung

Soweit gesetzlich zulässig, wird diese Software "wie besehen" und "wie
verfügbar" bereitgestellt, ohne Gewährleistung irgendeiner Art, weder
ausdrücklich noch stillschweigend, gesetzlich oder anderweitig.

Insbesondere übernimmt der Autor keine Gewährleistung oder Zusicherung dafür,
dass die Software:

- fehlerfrei, sicher, vollständig, richtig oder aktuell ist;
- unterbrechungsfrei funktioniert;
- mit bestimmten Systemen, Plattformen, Anbietern, Modellen, APIs oder
  Umgebungen kompatibel ist;
- frei von Viren, Schwachstellen oder schädlichen Bestandteilen ist;
- Ihre Anforderungen oder Erwartungen erfüllt;
- rechtlich richtige, vollständige oder verwertbare Ergebnisse erzeugt;
- Vertraulichkeit, Privilegien oder datenschutzrechtliche Compliance wahrt;
  oder
- für den produktiven, kommerziellen, professionellen, rechtlichen,
  security-kritischen oder sicherheitskritischen Einsatz geeignet ist.

Soweit gesetzlich zulässig, werden alle ausdrücklichen oder stillschweigenden
Gewährleistungen ausgeschlossen, insbesondere hinsichtlich Marktgängigkeit,
Eignung für einen bestimmten Zweck, Rechtsmängelfreiheit, Nichtverletzung von
Rechten Dritter und Freiheit von Sachmängeln.

### B.6 Haftungsbeschränkung

Die Software wird unentgeltlich bereitgestellt. Soweit gesetzlich zulässig,
richtet sich die Haftung daher zusätzlich nach den für unentgeltliche
Überlassungen und Zuwendungen geltenden gesetzlichen Maßstäben.

Soweit gesetzlich zulässig, haften der Autor, Mitwirkende, Maintainer und
verbundene Unternehmen, soweit vorhanden, nicht für Ansprüche, Schäden,
Verluste, Verbindlichkeiten, Kosten oder Aufwendungen, die aus oder im
Zusammenhang mit der Software, ihren Ausgaben oder ihrer Nutzung entstehen,
insbesondere nicht für:

- unmittelbare oder mittelbare Schäden;
- Neben-, Sonder-, Folge-, Straf- oder exemplarische Schäden;
- entgangenen Gewinn, entgangenen Umsatz, Betriebsunterbrechungen, Verlust von
  Geschäftschancen, Goodwill oder erwarteten Einsparungen;
- Verlust, Beschädigung, Offenlegung oder unbefugte Verarbeitung von Daten;
- Nutzungsausfall, Systemausfälle, Ausfallzeiten oder Sicherheitsvorfälle;
- fehlerhafte, unvollständige, veraltete oder irreführende Ausgaben;
- versäumte Fristen, fehlerhafte Anträge, abgelehnte Anträge, nachteilige
  behördliche Entscheidungen, Sanktionen, Bußgelder, Leistungskürzungen,
  Rückforderungen, Rechtsanwaltskosten, Prozesskosten oder nachteilige
  gerichtliche Entscheidungen;
- unbefugten Zugriff auf, Nutzung oder Veränderung Ihrer Übertragungen,
  Inhalte, Prompts, Dokumente oder Daten;
- Verhalten, Inhalte, Dienste, APIs, Modelle oder Systeme Dritter; oder
- Ansprüche Dritter.

Dies gilt unabhängig vom Rechtsgrund, insbesondere aus Vertrag, unerlaubter
Handlung, Fahrlässigkeit, Gefährdungshaftung, Gewährleistung, gesetzlicher
Pflicht, beruflicher Pflicht oder sonstigem Rechtsgrund, selbst wenn der Autor
auf die Möglichkeit solcher Schäden hingewiesen wurde.

Die vorstehenden Haftungsbeschränkungen gelten nur, soweit sie nach
anwendbarem zwingendem Recht zulässig sind.

Unberührt bleibt insbesondere die Haftung:

- für Vorsatz;
- für grobe Fahrlässigkeit, soweit ein Ausschluss gesetzlich unzulässig ist;
- für Schäden aus der Verletzung des Lebens, des Körpers oder der Gesundheit;
- nach zwingenden Vorschriften des Produkthaftungsrechts;
- bei arglistigem Verschweigen eines Mangels;
- aus einer ausdrücklich übernommenen Garantie; und
- in allen sonstigen Fällen, in denen die Haftung gesetzlich nicht
  ausgeschlossen oder beschränkt werden kann.

Soweit der Nutzer Verbraucher im Sinne von § 13 BGB ist, gelten die
vorstehenden Beschränkungen nur insoweit, als sie nicht gegen zwingende
verbraucherschützende Vorschriften verstoßen.

### B.7 Nutzerverantwortung und Nutzung auf eigenes Risiko

Sie sind allein dafür verantwortlich zu prüfen, ob die Software und ihre
Ausgaben für Ihren beabsichtigten Zweck geeignet sind.

Wenn Sie auf die Software zugreifen, sie klonen, herunterladen, installieren,
bauen, ausführen, ändern, bereitstellen, mit ihr interagieren oder sie
anderweitig nutzen, geschieht dies auf eigene Gefahr.

Sie tragen die alleinige Verantwortung für alle Entscheidungen, Anträge,
Widersprüche, Rechtsmittel, Kommunikationen, Einreichungen, rechtlichen
Schritte, behördlichen Schritte, geschäftlichen Entscheidungen oder sonstigen
Handlungen oder Unterlassungen, die auf Ausgaben dieser Software beruhen.

Sie sind selbst dafür verantwortlich, angemessene Vorsichtsmaßnahmen zu
treffen, insbesondere unabhängige rechtliche Prüfung, professionelle Beratung,
Code-Review, Sicherheitsprüfung, Tests, Backups, Quellenprüfung,
Fristenprüfung, Prüfung verfahrensrechtlicher Anforderungen sowie die
Einhaltung anwendbarer Gesetze und Vorschriften.

### B.8 Keine Support- oder Wartungspflicht

Der Autor ist nicht verpflichtet, Support, Wartung, Aktualisierungen,
Fehlerbehebungen, Sicherheitskorrekturen, Dokumentation, Antworten auf Issues,
Antworten auf Pull Requests oder sonstige Unterstützung bereitzustellen.

Durch die Veröffentlichung dieses Repositorys entsteht kein Dienstleistungs-,
Beratungs-, Treuhand-, Arbeits-, Gesellschafts-, Berufs- oder sonstiges
besonderes Rechtsverhältnis zwischen dem Autor und einem Nutzer.

### B.9 Drittkomponenten und Drittanbieter-Dienste

Dieses Repository kann Drittsoftware, Bibliotheken, Modelle, APIs, Dienste,
Werkzeuge, Daten oder Dokumentation enthalten, referenzieren, aufrufen oder von
ihnen abhängen.

Drittkomponenten und Drittanbieter-Dienste unterliegen ihren jeweiligen
eigenen Bedingungen, Lizenzen, Richtlinien und Datenschutzpraktiken. Sie sind
allein dafür verantwortlich, diese Bedingungen zu prüfen und einzuhalten.

Der Autor ist für Drittkomponenten und Drittanbieter-Dienste nicht
verantwortlich und übernimmt diesbezüglich keine Gewährleistung oder
Zusicherung.

### B.10 Anwendbares Recht und Gerichtsstand

Soweit gesetzlich zulässig, unterliegt dieser Haftungsausschluss dem Recht der
Bundesrepublik Deutschland unter Ausschluss des Übereinkommens der Vereinten
Nationen über Verträge über den internationalen Warenkauf.

Wenn Sie Verbraucher mit gewöhnlichem Aufenthalt in einem anderen Staat sind,
insbesondere in einem Mitgliedstaat der Europäischen Union oder in den
Vereinigten Staaten von Amerika, entzieht Ihnen diese Rechtswahl nicht den
Schutz zwingender Verbraucherschutzvorschriften oder sonstiger zwingender
Rechte dieses Staates.

Soweit gesetzlich zulässig, ist für Nutzer, die Kaufleute, juristische Personen
des öffentlichen Rechts oder öffentlich-rechtliche Sondervermögen sind, der
Gerichtsstand am Wohnsitz oder Sitz des Autors in Deutschland. Zwingende
gesetzliche Gerichtsstände bleiben unberührt.

### B.11 Salvatorische Klausel

Sollte eine Bestimmung dieses Haftungsausschlusses ganz oder teilweise
unwirksam, rechtswidrig oder undurchsetzbar sein oder werden, bleibt die
Wirksamkeit der übrigen Bestimmungen hiervon unberührt, soweit gesetzlich
zulässig.

Die unwirksame, rechtswidrige oder undurchsetzbare Bestimmung ist, soweit
gesetzlich zulässig, so auszulegen, zu beschränken oder zu ersetzen, dass der
mit ihr verfolgte Zweck in wirksamer und durchsetzbarer Weise möglichst weit
gehend erreicht wird.

### B.12 Kenntnisnahme

Durch den Zugriff auf die Software, ihre Installation, Ausführung, Interaktion
mit ihr oder sonstige Nutzung bestätigen Sie, dass Sie diesen
Haftungsausschluss gelesen und verstanden haben und die Software auf eigene
Gefahr nutzen.

Die Software ist als API implementiert. Analysen und andere geschützte
Operationen werden nur ausgeführt, wenn jede Anfrage die Bestätigung der
Kenntnisnahme mit der aktuell gültigen Fassungsnummer trägt (Header
`X-Disclaimer-Ack`, abfragbar über `GET /api/v1/meta/disclaimer/version`; sie
entspricht der Fassung dieses Dokuments mit vorangestelltem `v`, derzeit
`v3.3.0`);
bei Fassungsänderungen wird eine erneute Bestätigung verlangt. Die
bestätigte Fassung wird je Analyse-Lauf zusammen mit Zeitpunkt und
Anwendungsversion im lokalen Audit-Protokoll festgehalten. Maßgeblich ist
jeweils die bestätigte Fassung. Von der Software erzeugte Dokumente und
Berichte weisen die zugrunde liegenden Versionen im Fußbereich aus.

Wenn Sie mit diesem Haftungsausschluss nicht einverstanden sind, nutzen Sie
die Software nicht.

---

## Teil C — Compliance: Rechtsstatus und KI-VO-Klassifizierung

> **Kein Rechtsrat.** Dieser Teil ist eine Engineering-Planungsgrundlage,
> keine Rechtsberatung. Er dokumentiert die vom Projekt getragene Einordnung.
> Die offenen Rechtsfragen aus Roadmap v2.0.0 §8 sind durch externe Beratung
> zu schließen, nicht durch dieses Dokument.

### C.1 Zweck und Geltungsbereich

Dieser Teil ist die **einzige maßgebliche Quelle** für die rechtliche
Klassifizierung von Citizen unter der KI-Verordnung (KI-VO, VO (EU) 2024/1689).
Für jede laufende Instanz beantwortet er:

1. Ist der Betreiber **Anbieter**, **Einsetzer** oder keines von beiden?
2. Greift die **Entwicklungsphasen-Freistellung** (Art. 2(8)) oder die
   persönliche Nutzung?
3. Welche Pflichten sind in dem jeweiligen Modus **aktiv** — und welche
   ausdrücklich **nicht**?

Gegenstand sind die Software Citizen und ihre erzeugten Ausgaben
(Analyse-Berichte, Aktionsdokument-Entwürfe, Chat-Antworten). Nicht behandelt
werden die Offenlegung der KI-Autorschaft des Quellcodes (WP-63, geplant) —
der rechtliche Hinweis an Nutzer ist Teil B desselben Dokuments.

Die Einordnung gilt für den Kern und für jedes aktivierte Rechtsgebiets-Modul;
gebietsspezifische Grenzen ergänzt Teil D. Welche Module eine Ausgabe erzeugt
haben, weist deren maschinenlesbare Provenienz-Kennzeichnung aus
(`citizen-provenance-v1.1`, Feld `modules`).

### C.2 Schnellantwort: Pflichten je Modus

Die Einordnung hängt an **einem einzigen Schalter**: `DEPLOYMENT_MODE`
(Entscheidung **D-019**, siehe `DECISIONS.md`). Drei Werte:

| Modus | Bedeutung | Rechtslage |
|---|---|---|
| `dev` | Nur der Autor, nur Testbetrieb, **nur synthetische Daten** | Entwicklungsphase, Art. 2(8) KI-VO — Pflichten nicht ausgelöst |
| `self` | Nur der Autor, an **eigenen realen Bescheiden** | Persönliche, nicht-berufliche Nutzung — Pflichten nicht ausgelöst |
| `provider` | Bereitgestellt, sodass **beliebige Dritte** eine Analyse erhalten können | Autor wird **Anbieter** (Art. 3(3)) — Art.-50-Pflichten aktiv |

Legende: **A** = aktiv (zu erfüllen) · **–** = nicht ausgelöst · **D** =
dokumentarisch (immer relevant, aber keine Handlungspflicht)

| Pflicht | Rechtsgrundlage | `dev` | `self` | `provider` | Umsetzung |
|---|---|---|---|---|---|
| Anbieter/Einsetzer-Bestimmung | Art. 3(3)/(4) KI-VO | – | – | A | dieser Teil (WP-60), D-019 |
| Entwicklungsphasen-Posture einhalten | Art. 2(8) KI-VO | A | – | – | WP-62 (Zugriffskontrolle, Synthetik-Guard, DEV-INSTANCE.md) |
| FOSS-Note: MIT befreit **nicht** von Art. 50 | Art. 2(12) KI-VO | D | D | D | dieser Teil (WP-60) |
| Zweckbestimmung: bürgerseitig in eigener Angelegenheit; nicht seitens Behörden, Gerichten, Strafverfolgungs- oder Migrationsbehörden | Anhang III Nr. 5 Bst. a, Nr. 6, Nr. 7, Nr. 8 Bst. a KI-VO | A | A | A | WP-61/WP-96 (Self-Assessment, Purpose-Drift-Lint mit Modul-Deny-Phrasen), D-020, D-035 |
| KI-Interaktionshinweis an jede natürliche Person | Art. 50(1) KI-VO | – | – | **A** | D-032 (`GET /api/v1/meta/disclosure`, eingebettet in jede KI-Ausgabe) |
| Maschinenlesbare Kennzeichnung aller KI-Ausgaben | Art. 50(2) KI-VO | – | – | **A** (Frist: **2026-12-02**, falls bis dahin `provider`) | D-032; `citizen-provenance-v1.1` mit Modulangabe auf allen KI-Ausgabeflächen (WP-96, D-059) |
| Offenlegung bei veröffentlichtem Text (öffentliches Interesse) | Art. 50(4) KI-VO | – | – | – (nicht ausgelöst: Aktionsdokumente sind individuelle Korrespondenz, keine Veröffentlichung) | WP-65 (Begründung im Marker-Spez) |
| RDG-Einzelfallgrenze (strukturell, per Pipeline erzwungen) | § 2/§ 6/§ 8 RDG | – | – | A | WP-67, D-021 |
| DSGVO: DPIA (Art. 35) + AVV-Kette (Art. 28) | DSGVO | – (nur synthetische Daten) | – (eigene Daten) | **A** (vor dem ersten echten Fall) | WP-68 |
| Provider-Go/No-Go-Gate | — (aggregiert) | – | – | A (vor erstem Drittanbieter-Einsatz) | WP-69 |

**Schnellantwort in einem Satz:** Eine Instanz im Modus `dev` oder `self` hat
keine Pflichten aus der KI-VO und keine DSGVO-/RDG-Auslöser; eine Instanz im
Modus `provider` hat die in der Matrix mit **A** markierten Pflichten aktiv,
bevor der erste echte Drittfall verarbeitet werden darf — insbesondere
Art. 50(1), Art. 50(2), die RDG-Invariante, DPIA/AVV und das Go/No-Go-Gate.

### C.3 Der Schalter: DEPLOYMENT_MODE

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

**Technischer Umsetzungsstand:** Der Schalter ist implementiert —
`DEPLOYMENT_MODE` in `app/core/config.py` (Standard `dev`, per `Literal`
validiert). Im Modus `dev` verweigert die Instanz den Start ohne explizit
gesetztes `CITIZEN_SYNTHETIC_DATA_ONLY=true` (`app/services/dev_guard.py`)
und lehnt Dokument-Uploads ohne `X-Document-Tag: synthetic|goldset` mit
HTTP 403 ab. Die Härtung der erreichbaren Instanz ist in
`devdocs/DEV-INSTANCE.md` dokumentiert.

### C.4 Klassifizierung im Einzelnen

#### C.4.1 Anbieter und Einsetzer (Art. 3(3)/(4))

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

#### C.4.2 Entwicklungsphase (Art. 2(8))

Die KI-VO gilt nicht für KI-Systeme, die ausschließlich zum Zweck der
wissenschaftlichen Forschung und Entwicklung entwickelt und in Betrieb
genommen werden. Der Modus `dev` liegt in dieser Phase: erreichbar zum
Testen, bereitgestellt für niemanden. Damit diese Einordnung trägt, muss die
dev-Instanz drei Bedingungen erfüllen (Runbook in `devdocs/DEV-INSTANCE.md`):
(1) Zugriff nur durch den Autor (VPN/mTLS oder Basic-Auth + IP-Allowlist),
(2) ausschließlich synthetische Daten (Startup-Assertion + Ingest-Guard),
(3) keine Indexierung (`robots.txt`, `X-Robots-Tag: noindex`) und ein
dauerhaft über `GET /api/v1/meta/deployment-mode` abrufbarer
Entwicklungs-Banner, den Clients ausweisen müssen.

#### C.4.3 FOSS-Freistellung (Art. 2(12)) — und die Ausnahme für Art. 50

Citizen steht unter der MIT-Lizenz. Für KI-Systeme, die unter freien und
Open-Source-Lizenzen veröffentlicht werden, gilt der größte Teil der KI-VO
nicht — **Art. 50 (Transparenzpflichten) ist ausdrücklich ausgenommen** und
bleibt anwendbar. Die Lizenz ändert deshalb nichts daran, dass im Modus
`provider` die Art.-50-Pflichten gelten (KI-Interaktionshinweis,
maschinenlesbare Kennzeichnung). Im Modus `dev`/`self` greift Art. 50 nicht,
weil **kein Bereitstellen an Dritte** vorliegt — nicht wegen der Lizenz.

#### C.4.4 Selbstbewertung: Keine Hochrisiko-Einstufung (Anhang III Nr. 5 Bst. a, Nr. 6, Nr. 7, Nr. 8 Bst. a)

**Ergebnis.** Citizen ist **kein Hochrisiko-KI-System** im Sinne des Anhangs
III KI-VO — insbesondere nicht nach Nr. 5 Bst. a (Sozialleistungen), Nr. 6
(Strafverfolgung), Nr. 7 (Migration, Asyl und Grenzkontrolle) und Nr. 8
Bst. a (Rechtspflege) — bei der hier deklarierten Zweckbestimmung (D-035,
Erweiterung von D-020) und unter den in diesem Abschnitt dokumentierten
Schutzvorkehrungen gegen Zweckbestimmungs-Abdrift. Die Einordnung gilt für
jedes Rechtsgebiets-Modul.

**Erfassungsbereich der Tatbestände.** Alle vier Tatbestände knüpfen an die
Verwendung auf der Seite der entscheidenden, ermittelnden oder
rechtsprechenden Stelle an:

- **Nr. 5 Bst. a:** KI-Systeme, die von Behörden oder in deren Auftrag zur
  **Bewertung der Anspruchsberechtigung** natürlicher Personen zu
  Sozialleistungen und Sozialdiensten eingesetzt werden.
- **Nr. 6:** KI-Systeme, die von Strafverfolgungsbehörden oder in deren
  Auftrag eingesetzt werden, etwa zur Bewertung von Beweismitteln oder zur
  Risikobewertung natürlicher Personen.
- **Nr. 7:** KI-Systeme, die von den zuständigen Behörden in den Bereichen
  Migration, Asyl und Grenzkontrolle oder in deren Auftrag eingesetzt werden.
- **Nr. 8 Bst. a:** KI-Systeme, die von einer Justizbehörde oder in deren
  Auftrag zur Ermittlung und Auslegung von Sachverhalten und Rechtsvorschriften
  und zur Anwendung des Rechts auf konkrete Sachverhalte eingesetzt werden.

**Deklarierte Zweckbestimmung (D-035).** Die Zweckbestimmung von Citizen ist
**bürgerseitige Selbsthilfe und Terminvorbereitung natürlicher Personen in
ihren eigenen Rechtsangelegenheiten**, über die aktivierten
Rechtsgebiets-Module hinweg, sowie **Assistenz für Beratungsstellen** im
Rahmen ihrer eigenen RDG-Befugnis. Das System unterstützt die betroffene
Person selbst oder deren Beratende dabei, ein Schreiben zu verstehen, zu
prüfen, darauf zu reagieren und einen Beratungstermin vorzubereiten. Es ist
ausdrücklich **nicht** dazu bestimmt, von einer Behörde, einem Gericht, einer
Strafverfolgungs- oder Migrationsbehörde oder in deren Auftrag eingesetzt zu
werden, um natürliche Personen zu bewerten, über sie zu entscheiden oder
Maßnahmen gegen sie durchzusetzen.

**Warum die Tatbestände nicht erfüllt sind.**

1. **Keine Bestimmung für die entscheidende Stelle:** Weder das Produkt noch
   seine Dokumentation noch ein Modul beschreibt Citizen als Werkzeug einer
   Behörde, eines Gerichts oder einer Strafverfolgungs- oder
   Migrationsbehörde. Die Zweckbestimmung ist in README, Teil A dieses
   Dokuments, dem Rechtshinweis und in jedem Modul-Manifest
   (`scope.own_matter_only`) verankert.
2. **Kein Entscheidungssystem:** Citizen erzeugt Rechtsinformation und
   Bausteine, die der menschlichen Adjudikation bedürfen (D-021); es trifft
   keine Entscheidung über natürliche Personen und wird nicht dazu
   bereitgestellt, eine solche zu treffen oder vorzubereiten.
3. **Bereitstellungsform:** Selbst im Modus `provider` wird die Software
   Betroffenen und Beratungsstellen bereitgestellt — nicht Stellen, die über
   Leistungen, Strafverfolgung, Aufenthalt oder Rechtsstreitigkeiten
   entscheiden.
4. **Klassifizierung nach Zweckbestimmung:** Die KI-VO stellt für die
   Hochrisiko-Einordnung auf die Zweckbestimmung ab. Solange diese
   bürgerseitig bleibt, greifen die Tatbestände nicht.

**Drift-Schutz (Guardrails).** Damit diese Bewertung trägt:

- **D-020/D-035** verpflichten auf die bürgerseitige Zweckbestimmung und
  verbieten in Dokumentation und Texten jede Beschreibung als Werkzeug einer
  Behörde, eines Gerichts, einer Strafverfolgungs- oder Migrationsbehörde.
- **`scripts/check_purpose_drift.py`** (WP-61, erweitert durch WP-96) scannt
  README, `DISCLAIMER_*.md`, `ARCHITECTURE.md`, `docs/*.md` sowie die
  Texte (`copy/`) und Ergänzungen (`DISCLAIMER_ADDENDUM.md`) jedes Moduls auf
  Formulierungen aus Sicht der entscheidenden Stelle. Neben der
  Standardliste gelten die Deny-Phrasen, die jedes Modul in seinem Manifest
  erklärt (z. B. Strafrecht: Strafverfolgungs-Framing, Anhang III Nr. 6) —
  für den gesamten Scan-Umfang. Bei Treffern schlägt die CI fehl; bewusste
  Zitate brauchen einen sichtbaren Ausnahme-Marker in derselben Zeile.
- **Modul-Stufen:** Im Modus `provider` sind standardmäßig nur geprüfte
  Module (`verified`) aktiviert (D-037); experimentelle Module erst nach
  ausdrücklicher Freigabe.
- **Änderungsmanagement:** Veränderungen an Zweckbestimmung, Zielgruppe oder
  Bereitstellungsform sowie jedes neue Modul und jede geänderte
  Modul-Ergänzung erfordern eine Fassungsänderung dieses Dokuments
  (Abschnitt C.7, Teil D) und eine erneute Prüfung dieser Selbstbewertung.

**Bedingung.** Diese Bewertung ist konditional: Sie gilt nur für die hier
deklarierte Zweckbestimmung. Wird Citizen oder eines seiner Module künftig
als Werkzeug einer Behörde, eines Gerichts, einer Strafverfolgungs- oder
Migrationsbehörde beschrieben oder diesen bereitgestellt, ist die Einstufung
neu zu prüfen — die Pflichten für Hochrisiko-KI-Systeme (Kapitel III KI-VO)
würden ausgelöst.

### C.5 Fristen und Auslöse-Ereignisse

| Ereignis / Frist | Wirkung |
|---|---|
| **Bereitstellung für Dritte** (`DEPLOYMENT_MODE=provider`) | Schaltet die Art.-50-Pflichten sowie die DSGVO- und RDG-Auflagen an (siehe Abschnitt C.2) |
| **2026-12-02** (Ende der Übergangsfrist für Art. 50(2)) | **Nur bindend, wenn** bis dahin `provider` gilt: Die maschinenlesbare Kennzeichnung muss bis dahin umgesetzt sein (WP-65). Andernfalls gilt sie als Tor für die spätere Bereitstellung. |
| **Erster echter Drittfall** | Verarbeitung erst nach: Purpose-Guard grün (WP-61), Hinweis live (WP-64), Kennzeichnung live (WP-65), RDG-Invariante getestet (WP-67), DPIA + AVV-Kette vorhanden (WP-68), Go/No-Go-Gate signiert (WP-69). |

### C.6 Benachbarte Rechtsregime

#### C.6.1 DSGVO

Die DSGVO ist für den Betrieb das am stärksten unterschätzte Regime.
Bescheide von Leistungsberechtigten enthalten regelmäßig **besondere
Kategorien** personenbezogener Daten (Art. 9 DSGVO: Gesundheit, Behinderung);
die Betroffenen sind verletzliche Personen. Je nach Rechtsgebiet kommen
weitere Kategorien hinzu (z. B. Art. 10 DSGVO, Daten über Straftaten, im
Strafrecht); die Module erklären sie im Manifest
(`compliance.special_regimes`) und in Teil D. Daraus folgt:

- **`provider`:** Eine **Datenschutz-Folgenabschätzung (DPIA, Art. 35)** ist
  sehr wahrscheinlich verpflichtend; eine **AVV-Kette** (Art. 28) muss vor
  dem ersten echten Fall stehen: Autor als Auftragsverarbeiter → EU-Inferenz
  als Unterauftragsverarbeiter (Profil `eu-avv`) → Beratungsstelle als
  Verantwortliche. Umsetzung: WP-68.
- **`self`:** Der Autor verarbeitet eigene Daten; keine DPIA/AVV-Pflicht. Die
  vorhandenen Schutzmechanismen (Pseudonymisierung, Egress-Guard) bleiben
  aktiv (Defense-in-Depth).
- **`dev`:** Nur synthetische Daten; keine Verarbeitung personenbezogener
  Daten. Der Synthetik-Guard (WP-62) verhindert, dass echte Daten in die
  dev-Instanz gelangen.

#### C.6.2 RDG

Ein System, das den konkreten Bescheid einer einzelnen Person prüft, bewegt
sich nahe der Grenze zur **Rechtsdienstleistung in konkreter fremder
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
- Jedes Modul ist auf die **eigene Angelegenheit** der Person beschränkt
  (`scope.own_matter_only` im Modul-Manifest, D-035); Unterstützung in
  fremden Angelegenheiten leisten ausschließlich Beratungsstellen im Rahmen
  ihrer eigenen RDG-Befugnis.

### C.7 Gültigkeit und Änderungsdienst

- Dieser Teil stammt aus Roadmap v2.0.0 (WP-60/WP-61) und wurde mit
  Roadmap v3.0.0 (WP-96) für den modularen Aufbau neu gefasst. Er ist mit den
  Entscheidungen D-019, D-020, D-022, D-035 und D-059 (sowie D-021) im
  Entscheidungs-Ledger verankert.
- Änderungen an Zweckbestimmung, Bereitstellungsform oder Zielgruppe
  erfordern eine Überprüfung und Fassungsänderung dieses Dokuments
  (semantische Versionierung).
- Offene Rechtsfragen, die sich technisch nicht schließen lassen, sind in
  Roadmap v2.0.0 §8 gesammelt; Roadmap v3.0.0 führt die verbleibenden
  Compliance-Lücken (§ 2).

#### Referenzen

- `docs/roadmap-v2.0.0.md` — Phasen P6–P8, Pflichten-Matrix (§5)
- `docs/roadmap-v3.0.0.md` — Phase P9, WP-96 (Compliance für Module)
- `ARCHITECTURE.md` — § 7 (Compliance-Architektur je Modul)
- `DECISIONS.md` — D-019, D-020, D-021, D-022, D-035, D-037, D-059
- `modules/*/DISCLAIMER_ADDENDUM.md` — Quellen der Modul-Ergänzungen (Teil D)
- `README.md` — Abschnitt „Rechtlicher Status"
- `devdocs/DEV-INSTANCE.md` — Dev-Instanz-Betriebsführung (Art. 2(8))
- `scripts/check_purpose_drift.py` — Purpose-Drift-Lint (WP-61/WP-96)

---

## Teil D — Modul-Ergänzungen

### D.1 Grundregeln

Citizen besteht aus einem Kern und Rechtsgebiets-Modulen. Die Teile A bis C
gelten für jedes Modul. Dieser Teil ergänzt sie um die gebietsspezifischen
Grenzen, die ein Modul in seiner Datei `DISCLAIMER_ADDENDUM.md` erklärt; die
Ergänzungen sind hier wörtlich übernommen. Für das gesamte Dokument
einschließlich aller Ergänzungen gilt **eine** Fassungsnummer: Ändert sich
eine Ergänzung oder kommt ein Modul hinzu, ändert sich die Fassung dieses
Dokuments und damit die per `X-Disclaimer-Ack` zu bestätigende Fassung.

- **Stufen.** `verified`: geprüftes Modul mit deterministischen Engines und
  einem Golden Set, an dem jede Änderung gemessen wird. `experimental`: Modul
  ohne Fristen-Engine, ohne Berechnungen und ohne Golden Set; seine Ausgaben
  sind allgemeine, KI-erzeugte Rechtsinformation, deren Qualität nicht
  gemessen wird. Experimentelle Module sind im Modus `provider`
  standardmäßig nicht aktiviert (D-037).
- **Geltungsbereich.** Jedes Modul erklärt Umfang und Ausschlüsse in seinem
  Manifest (`scope`), abrufbar über `GET /api/v1/modules/{module_id}`.
  Welche Module eine Ausgabe erzeugt haben, weist deren
  Provenienz-Kennzeichnung aus.
- **Fristen und Beträge** stammen ausschließlich aus deterministischen
  Engines auf versionierten Parametern eines Moduls, nie aus dem
  Sprachmodell. Ein Modul ohne solche Engines berechnet weder Fristen noch
  Beträge.

### D.2 Sozialrecht (`sozialrecht`, Stufe `verified`)

**Geltungsbereich.** Das Modul behandelt Bürgergeld/Grundsicherung für
Arbeitsuchende (SGB II), das Sozialverwaltungsverfahren (SGB X) und das
sozialgerichtliche Verfahren (SGG). Nicht erfasst sind insbesondere die
Rentenversicherung (SGB VI) und die Krankenversicherung (SGB V); zu anderen
Sozialleistungen liefert das Modul keine geprüften Ergebnisse.

**Fristen.** Widerspruchsfrist (§ 84 SGG), Bekanntgabefiktion (§ 37 Abs. 2
SGB X), Fristende an Wochenenden und Feiertagen (§ 64 Abs. 3 SGG) und
Jahresfrist bei fehlender oder fehlerhafter Rechtsbehelfsbelehrung (§ 66
Abs. 2 SGG) berechnet eine deterministische Fristen-Engine aus den
versionierten Fristspezifikationen des Moduls — nie das Sprachmodell. Die
Berechnung beruht auf den eingegebenen Daten und der gesetzlichen
Bekanntgabefiktion; ist der Bescheid tatsächlich später oder gar nicht
zugegangen oder ist das Datum unsicher, kann die Frist abweichen. Im Zweifel
vor dem frühesten in Betracht kommenden Fristende handeln.

**Beträge.** Nachberechnungen (Regelbedarfe, Freibeträge nach § 11b SGB II,
Vermögensfreibeträge) rechnet das deterministische Regelwerk des Moduls auf
versionierten Rechtsparametern mit Gültigkeitszeiträumen. Welcher
Parameterstand verwendet wurde, weist die maschinenlesbare
Provenienz-Kennzeichnung jeder Ausgabe aus (`modules[].parameter_set`);
spätere Gesetzesänderungen sind darin nicht berücksichtigt.

**Entwürfe.** Widerspruch, Widerspruch unter Jahresfrist, Überprüfungsantrag
(§ 44 SGB X) und Akteneinsichtsantrag (§ 25 SGB X) sind Bausteine: nicht
geprüfte Rechtsbehauptungen erscheinen als `[BITTE PRÜFEN]`; die Person
prüft, ergänzt und unterzeichnet selbst.

**Besondere Daten.** Leistungsbescheide enthalten häufig Gesundheits- oder
Behinderungsangaben (Art. 9 DSGVO). Das Modul ist für die eigene
Angelegenheit der Person bestimmt; für die Verarbeitung gelten B.4 und C.6.1.

**Beratung.** Eine verbindliche Prüfung des Einzelfalls leisten unabhängige
Sozialberatungsstellen, Sozialverbände sowie Fachanwältinnen und
Fachanwälte für Sozialrecht; bei geringem Einkommen kommen Beratungshilfe
und Prozesskostenhilfe in Betracht.

### D.3 Strafrecht (`strafrecht`, Stufe `experimental`)

**Status.** Experimentelles Modul (Stufe `experimental`): keine
Fristen-Engine, keine Berechnungen, kein Golden Set. Ausgaben sind
ausschließlich allgemeine, KI-erzeugte Rechtsinformation zur eigenen
Angelegenheit der betroffenen Person (beschuldigte, angeklagte oder verletzte
Person).

**Kurze Fristen.** Im Strafverfahren laufen teils sehr kurze Fristen, die
das Modul nicht berechnet — etwa zwei Wochen für den Einspruch gegen einen
Strafbefehl (§ 410 Abs. 1 StPO) und eine Woche für Berufung oder Revision
(§ 314 Abs. 1, § 341 Abs. 1 StPO). Wer ein Schreiben von Polizei,
Staatsanwaltschaft oder Gericht erhalten hat, sollte unverzüglich
anwaltlichen Rat einholen; in Fällen notwendiger Verteidigung (§ 140 StPO)
wird eine Pflichtverteidigung bestellt, die auch beantragt werden kann.

**Zweckbindung.** Das Modul ist kein Werkzeug der Strafverfolgung (Anhang III
Nr. 6 KI-VO): Es ist nicht dazu bestimmt, von Polizei, Staatsanwaltschaft
oder Gerichten oder in deren Auftrag eingesetzt zu werden.

**Besondere Daten.** Angaben zu Straftaten und strafrechtlichen
Verurteilungen unterliegen Art. 10 DSGVO; für die Verarbeitung gelten B.4
und C.6.1.

### D.4 Weitere experimentelle Module

Für die Module `arbeitsrecht`, `erbrecht` (einschließlich des Altschlüssels
`schenkungsrecht`), `familienrecht`, `vertragsrecht` und
`andere` (Auffangbereich) gelten D.1 und die Teile A bis C ohne
gebietsspezifische Ergänzung. Sie berechnen weder Fristen noch Beträge; wer
eine Frist zu wahren hat, lässt sie anwaltlich oder durch eine
Beratungsstelle prüfen. Das allgemeine Verwaltungsverfahren
(`verwaltungsrecht`) ist kein eigenes Modul, sondern Teil der
Verfahrensbibliothek des Kerns.

---

### D.5 Schulden und Vollstreckung (`schuldnerrecht`)

**Geltungsbereich.** Dieses experimentelle Modul unterstützt Sie in Ihrer
eigenen Schuldenangelegenheit. Es berechnet gerichtliche Reaktionszeiträume
nur bei bestätigter Inlandszustellung und eindeutigem Dokumenttyp. Der
Zwei-Wochen-Zeitraum beim Mahnbescheid ist keine absolute Ausschlussfrist;
lassen Sie auch danach mögliche Schritte unverzüglich prüfen. Bei Auslands-
oder öffentlicher Zustellung ist eine gesonderte Prüfung nötig.

Pfändungsschutz, Verjährung und Inkassokosten werden nur im ausdrücklich
qualifizierten Regelungsbereich und mit passenden Parametern geprüft.
Unterhaltsvollstreckung, gerichtliche Sonderfreibeträge und ungeklärte
Hemmungs- oder Neubeginnfälle sind nicht von der Rechenprüfung erfasst.
Ergebnisse und Schreiben bleiben prüfbedürftig. Das Modul erstellt keinen
Insolvenzantrag und ersetzt keine Bescheinigung einer geeigneten Stelle.
Bei gerichtlichen Schreiben oder Kontopfändung suchen Sie zeitnah eine
Schuldnerberatung oder anwaltliche Beratung auf.

---

### D.6 Wohnraummiete (`mietrecht`)

**Geltungsbereich.** Dieses experimentelle Modul unterstützt Sie bei Ihrer
eigenen Wohnraummietsache als mietende Person. Es prüft Fristen und Beträge
nur mit bestätigten Tatsachen und passenden versionierten Parametern.
Briefdatum und Modellschätzungen ersetzen weder Zugang noch Zustellung.
Örtliche Mietpreis- und Kappungsgrenzenverordnungen haben unterschiedliche
Gebiete, Zeiträume und Ausnahmen. Ungeklärte örtliche Geltung wird nicht als
bundesweite Erlaubnis oder als Negativnachweis behandelt.

Rechenprüfungen bestätigen weder die Wirksamkeit einer Mieterhöhung noch die
Berechtigung einzelner Betriebskosten. Das Modul legt keine Minderungsquote
fest. Ändern Sie Zahlungen nicht allein aufgrund einer automatischen
Einschätzung. Verträge, Ausnahmen, Härtegründe und Nachweise müssen im
Einzelfall geprüft werden. Entwürfe bleiben prüfbedürftig und werden nicht
versandt. Bei Kündigung, Räumungsklage oder drohendem Wohnungsverlust suchen
Sie unverzüglich Mietberatung oder anwaltliche Hilfe. Eine Schonfristzahlung
beseitigt eine ordentliche Kündigung nicht automatisch; ein fehlender Hinweis
auf den Härtewiderspruch kann gesonderte spätere Möglichkeiten eröffnen.

---

## Änderungshistorie

- **3.3.0 (2026-11-27):** Mietrecht: qualifizierte Frist- und Rechenprüfungen, örtliche Quellenlücken und Entwürfe. Erneute Kenntnisnahme erforderlich.

- **3.2.0 (2026-11-26):** Schuldnerrecht: begrenzte Frist- und Rechenprüfungen, Entwürfe und klare Ausnahmen. Erneute Kenntnisnahme erforderlich.
- **3.1.0 (2026-11-26):** Experimentelles Modul `schuldnerrecht` mit Terminvorbereitung und gebietsspezifischer Ergänzung; noch keine Fristen- oder Betragsberechnung. Erneute Kenntnisnahme erforderlich.
- **3.0.0 (2026-11-16):** Erweiterte Zweckbestimmung (D-035) für den
  modularen Aufbau (Kern + Rechtsgebiets-Module): Teil A (Statement) und
  Teil C (Compliance) neu gefasst — bürgerseitige Selbsthilfe und
  Terminvorbereitung in eigenen Rechtsangelegenheiten über alle aktivierten
  Module; Selbstbewertung C.4.4 auf Anhang III Nr. 6, Nr. 7 und Nr. 8 Bst. a
  KI-VO erweitert; Drift-Schutz um Modul-Deny-Phrasen und den erweiterten
  Scan-Umfang ergänzt; Umsetzungsstand Art. 50 nachgetragen (Provenienz
  v1.1 mit Modulangabe auf allen KI-Ausgabeflächen); RDG-Beschränkung auf
  die eigene Angelegenheit je Modul. Neuer Teil D (Modul-Ergänzungen:
  Grundregeln, Sozialrecht, Strafrecht, weitere experimentelle Module).
  B.12: Fassungsnummer der Kenntnisnahme entspricht der Dokumentfassung
  (`v3.0.0`). Major-Fassung, weil sich die Zweckbestimmung ändert; erneute
  Bestätigung erforderlich.
- **2.0.0 (2026-08-25):** Zusammenführung der bisher eigenständigen Dokumente
  `DISCLAIMER_DE.md` (v1.1.0), `STATEMENT.md` (v1.0.0) und `COMPLIANCE.md`
  (v1.1.0) in eine einzige Fassung (Teil A Statement, Teil B Rechtlicher
  Hinweis, Teil C Compliance). Inhaltliche Anpassungen an die aktuelle
  Implementierung (API-only-Refaktor D-025): Kenntnisnahme-Mechanik in B.12
  an die tatsächliche Protokollierung angepasst (Fassungsnummer per
  `X-Disclaimer-Ack`, Audit-Protokoll je Lauf; keine Prüfsumme);
  Inferenzprofil-Anzeige über `GET /meta/active-profile`; technischer
  Umsetzungsstand des `DEPLOYMENT_MODE`-Schalters (implementiert inkl.
  Startup-/Ingest-Guards) nachgetragen; UI-Bezüge entfernt; Verweis auf
  `AI-USAGE.md` (WP-63) als geplant gekennzeichnet.
- **1.1.0 (2026-07-12/13):** Rechtlicher Hinweis: Versionierung und
  Änderungshistorie eingeführt; Unentgeltlichkeit klargestellt; RDG-Klarstellung
  (§ 2); Inferenzprofile/Pseudonymisierung neu gefasst (§ 4);
  Haftungsmaßstäbe für unentgeltliche Überlassung (§ 6); App-seitige
  Erst-Bestätigung (§ 12). Compliance: kanonische Klassifizierung (WP-60/WP-61)
  mit Pflichten-Matrix, Self-Assessment Anhang III und Drift-Schutz erstmals
  veröffentlicht.
- **1.0.0 (2026-05-09 / Juli 2026):** Ursprüngliche Fassungen des Rechtshinweises
  (seinerzeit unversioniert) und des Projektstatements.
