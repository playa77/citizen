# Citizen — Project Statement

*Version 1.0.0 · Juli 2026 · Dieses Dokument erklärt, warum es dieses Projekt gibt.
Was es technisch ist, steht im [README](README.md).*

---

## Was ist

Citizen ist heute ein Prototyp: eine Analyse-Pipeline, die deutsche
Sozialrechts-Bescheide einliest, jede Aussage an den Gesetzestext bindet,
Berechnungen deterministisch nachrechnet und Fristen auf den Tag genau bestimmt.
Es gibt ein versioniertes Golden Set mit verifizierten Prüffällen, an dem jede
Änderung gemessen wird. Es gibt bekannte Grenzen, und sie stehen im Repo statt
unter dem Teppich. Das ist der ehrliche Ist-Zustand: funktionierend, ungeschliffen,
messbar — und noch kein Produkt.

## Was sein soll

Ein Mensch hält einen Bescheid in der Hand, von dem seine Existenz abhängt, und
bekommt innerhalb von Minuten vier Antworten: **Was steht da drin? Stimmt das?
Bis wann muss ich reagieren? Was mache ich jetzt?** — nachvollziehbar belegt,
auf den Cent nachgerechnet, auf den Tag terminiert, in verständlicher Sprache.
Kostenlos. Quelloffen. Ohne dass seine Daten Europa verlassen. Und dasselbe
Werkzeug liegt in jeder Sozialberatungsstelle und macht aus einer
Dreiviertelstunde Erstprüfung zehn Minuten mit Paragraphenbeleg.

## Warum

Im Jahr 2025 wurden über eine halbe Million Widersprüche gegen
Jobcenter-Bescheide eingelegt. Rund jeder dritte war erfolgreich. In mehr als
42.000 Fällen hatte die Behörde das Gesetz nachweislich falsch angewandt. Diese
Quote ist seit Jahren stabil — sie ist kein Ausrutscher, sie ist ein
Systemzustand. Und sie trifft asymmetrisch: auf der einen Seite eine Verwaltung,
die millionenfach maschinell Bescheide erzeugt; auf der anderen ein einzelner
Mensch mit einer Monatsfrist, ohne Anwalt, oft ohne die Sprache des Bescheids zu
sprechen — im wörtlichen wie im übertragenen Sinn.

Ein Rechtsstaat ist ein Versprechen: dass Rechte nicht davon abhängen, wer man
ist und was man sich leisten kann. Dieses Versprechen ist nur so viel wert wie
seine Durchsetzbarkeit. Ein Recht, das man nicht kennt, eine Frist, die man
verpasst, eine Berechnung, die man nicht prüfen kann — das ist auf dem Papier
ein Recht und in der Wirklichkeit keines. 

Dazu kommt heute ein zweiter Grund, der über das Sozialrecht hinausweist. Wir
stehen am Anfang eines Übergangs, in dem maschinelle Intelligenz zur
Grundinfrastruktur wird — und Übergänge haben eine tückische Eigenschaft: **Sie
frieren die Machtverteilung ein, die im Moment des Übergangs besteht.**
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
dem niemand widerspricht, ist ein Fehlersignal, das nie ankommt. Werkzeuge, die
Widersprüche präziser, belegter und häufiger machen, sind deshalb kein Angriff
auf die Verwaltung — sie sind die Reparatur ihres Korrektivs. Eine Verwaltung,
deren Fehler zuverlässig gefunden werden, wird besser. Davon profitieren am
Ende beide Seiten des Schreibtischs.

## Grundsätze

**Nachrechenbarkeit statt Vertrauen.** Was deterministisch geht — Fristen,
Beträge, Zitate — wird deterministisch gerechnet und verifiziert. Das
Sprachmodell ist Werkzeug, nicht Autorität.

**Ehrlichkeit über Grenzen.** Wenn ein Bescheid rechtmäßig ist, sagt Citizen
das. Falsche Hoffnung ist keine Hilfe, sie ist eine zweite Kränkung. Unsichere
Rechtsfragen werden als unsicher gekennzeichnet, nicht weggeglättet.

**Die Daten bleiben beim Menschen.** Pseudonymisierung vor jeder Verarbeitung,
Inferenz ausschließlich in Europa unter Auftragsverarbeitung, lokale
Datenhaltung. Behauptet wird nur, was technisch erzwungen ist.

**Der Mensch entscheidet.** Citizen informiert, belegt, rechnet nach und liefert
Bausteine. Bewertet, entschieden und unterschrieben wird von Menschen — vom
Betroffenen selbst oder von Beratenden, die beraten dürfen.

**Offenheit als Prüfbarkeit.** MIT-Lizenz, öffentliches Golden Set, versionierte
Korrektur eigener Fehler. Ein Werkzeug, das Behördenfehler findet, muss sich
selbst dieselbe Prüfbarkeit gefallen lassen.

## Was das nicht ist

Keine Rechtsberatung — Rechtsinformation und Selbsthilfe. Kein Startup — es gibt
nichts an Menschen in Existenznot zu verdienen, und es wird hier auch nicht
versucht. Keine Kampfansage an Jobcenter-Mitarbeitende — die meisten arbeiten
unter Bedingungen, die Fehler erzeugen; dieses Werkzeug richtet sich gegen
Fehler, nicht gegen Menschen.

## Einladung

Wer juristisch prüfen, Fälle validieren, Code beitragen oder das Werkzeug in
einer Beratungsstelle erproben will: Issues und Pull Requests sind offen. Die
beste Form der Kritik an diesem Projekt ist ein Golden-Set-Fall, den es falsch
beantwortet.

---

*Zahlen: Widerspruchs- und Klagestatistik der Bundesagentur für Arbeit 2025
(147.213 von 476.728 entschiedenen Widersprüchen revidiert; 42.303 Fälle
fehlerhafter Rechtsanwendung; Jobcenter Essen: 53,7 % Fehlerquote bei erledigten
Widersprüchen, Mai 2026). Änderungen an diesem Dokument folgen semantischer
Versionierung.*
