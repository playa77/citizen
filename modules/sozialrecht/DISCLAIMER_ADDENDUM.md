# Disclaimer addendum — module `sozialrecht`

Area-specific limits of the module (ARCHITECTURE.md § 7). The `## DE` and
`## EN` bodies are copied verbatim into Part D of `DISCLAIMER_DE.md` /
`DISCLAIMER_EN.md`; `tests/unit/test_disclaimer_addenda.py` enforces the
copy. Any change here requires the same change there and a
`DISCLAIMER_VERSION` bump (ARCHITECTURE.md § 6.3).

## DE

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

## EN

**Scope.** The module covers basic income support for jobseekers
(Bürgergeld/Grundsicherung, SGB II), the social administrative procedure
(SGB X) and social-court procedure (SGG). Pension insurance (SGB VI) and
health insurance (SGB V) in particular are not covered; for other social
benefits the module provides no verified results.

**Deadlines.** The objection deadline (§ 84 SGG), the statutory fiction of
notification (§ 37(2) SGB X), deadline ends on weekends and public holidays
(§ 64(3) SGG) and the one-year deadline where the notice on legal remedies is
missing or wrong (§ 66(2) SGG) are computed by a deterministic deadline
engine from the module's versioned deadline specs — never by the language
model. The computation relies on the data entered and on the statutory
notification fiction; if the notice actually arrived later or not at all, or
the date is uncertain, the deadline may differ. When in doubt, act before the
earliest possible deadline end.

**Amounts.** Recalculations (standard needs, allowances under § 11b SGB II,
asset allowances) are computed by the module's deterministic rules engine on
versioned legal parameters with validity periods. The parameter set used is
stated in the machine-readable provenance marker of every output
(`modules[].parameter_set`); later changes in the law are not reflected in it.

**Drafts.** Objection, objection within the one-year deadline, review request
(§ 44 SGB X) and file-inspection request (§ 25 SGB X) are building blocks:
unverified legal assertions appear as `[BITTE PRÜFEN]`; the person reviews,
completes and signs them personally.

**Special categories of data.** Benefit notices often contain health or
disability information (Art. 9 GDPR). The module is intended for the
person's own matter; processing is governed by B.4 and C.6.1.

**Advice.** A binding review of the individual case is provided by
independent social-benefit advice centers, welfare associations and lawyers
specialised in social law (Fachanwalt für Sozialrecht); people on low incomes
may be eligible for legal-advice aid (Beratungshilfe) and legal aid
(Prozesskostenhilfe).
