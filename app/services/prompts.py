"""Area-aware prompt registry.

The pipeline historically used one hard-coded SGB-focused system prompt
per stage. As Citizen broadens to a general German legal AI assistant,
prompts are keyed by ``legal_area`` and combined when a case spans
multiple areas (e.g. Erbrecht + Familienrecht).

Architecture (v1.x)
-------------------
Prompts are no longer duplicated string constants. Each legal area is
described once by an :class:`AreaProfile` (persona, statutes, document
examples, terminology anchors, adversary examples, hierarchy example).
Stage templates (``_build_*``) render a profile into a system prompt.
Multi-area cases merge profiles into ONE coherent persona with a single
output-format block, instead of concatenating whole prompts (which
produced conflicting, duplicated JSON-format instructions in v0.x).

Adding a new legal area = adding one AreaProfile + one REGISTRY entry.

Prompt-engineering conventions applied to every stage prompt:
  * XML-tagged sections (<rolle>, <kontext>, <aufgabe>, <regeln>,
    <ausgabeformat>) for unambiguous instruction boundaries.
  * Instructions consistently in German; JSON keys and enum values in
    English exactly as the downstream parsers expect them.
  * One canonical output example per prompt; the format block is always
    the LAST section (recency effect improves format compliance).
  * Shared anti-hallucination and JSON-discipline blocks, defined once.
  * Explicit escape hatches for insufficient evidence instead of
    letting the model improvise.

Recommended sampling temperatures per stage are exported via
``STAGE_TEMPERATURES`` (metadata for the router; NOT embedded in the
prompt text itself).

Versioning / breaking changes
-----------------------------
1.0.0 (this file)
  * BREAKING: retires the v0.x byte-for-byte regression contract
    (``get_prompts([])`` still falls back to the Sozialrecht set, but
    the prompt *contents* are rewritten). The golden-string tests in
    ``tests/unit/test_promets.py`` (sic) and
    ``tests/unit/test_reasoning.py`` must be re-baselined.
  * FIX: Erbrecht cases previously received Sozialrecht-hardcoded
    personas for adversarial_review, claim_construction, verification
    and output. All eight stages are now area-parameterized.
  * FIX: multi-area composition merges profiles instead of
    concatenating prompts; exactly one format block per prompt.
  * FIX: "verdragen" -> "verdrängen" in the lex-specialis rule.
  * CHORE: removed unused ``typing.Any`` import.

0.3.0
  * Last release of the duplicated-constant architecture.
"""

# Semantic Version: 1.0.0

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

# ---------------------------------------------------------------------------
# Stage metadata — recommended sampling temperatures
# ---------------------------------------------------------------------------
# Extraction-like stages want near-determinism; drafting stages get a
# little headroom. Consumed by the LLM router; never sent to the model.

STAGE_TEMPERATURES: dict[str, float] = {
    "classification": 0.1,
    "decomposition": 0.2,
    "triage": 0.2,
    "grounded_answer": 0.2,
    "adversarial_review": 0.3,
    "claim_construction": 0.2,
    "verification": 0.1,
    "output": 0.3,
}


# ---------------------------------------------------------------------------
# Area profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AreaProfile:
    """Everything a stage template needs to know about a legal area."""

    key: str
    # "deutsches Sozialrecht" — grammatically usable after "Experte für ..."
    display_name: str
    # Statute scope, e.g. "insbesondere SGB II, SGB X und SGB XII"
    statutes: str
    # Typical inbound documents, continues "z. B. ..."
    document_examples: str
    # Few-shot terminology anchors for issue naming
    issue_terms: tuple[str, ...]
    # Formal vs. material question examples for decomposition/triage
    formal_examples: str
    material_examples: str
    # Which law answers the derived questions, continues "mit ..."
    answerable_with: str
    # Canonical evidence hierarchy example, e.g. "SGB II > § 31 > Abs. 1"
    hierarchy_example: str
    # Opposing parties for the adversarial review, continues "z. B. ..."
    adversary_examples: str


SOZIALRECHT_PROFILE = AreaProfile(
    key="sozialrecht",
    display_name="deutsches Sozialrecht",
    statutes="insbesondere SGB I, SGB II, SGB III, SGB IX, SGB X und SGB XII",
    document_examples=(
        "eines Jobcenter-Bescheids, einer Anhörung, einer Aufforderung zur "
        "Mitwirkung, einer Einladung, einer Eingliederungsvereinbarung oder "
        "eines Schreibens des Sozialamts oder einer anderen Sozialbehörde"
    ),
    issue_terms=(
        "Meldefristverletzung",
        "Mitwirkungspflicht",
        "Eingliederungsvereinbarung",
        "Bewilligungsbescheid",
        "Aufhebungs- und Erstattungsbescheid",
        "Kosten der Unterkunft",
        "Sanktion nach § 31 SGB II",
        "Anhörung nach § 24 SGB X",
        "Gesundheitsprüfung",
    ),
    formal_examples="Anhörung, Begründung, Frist, Zuständigkeit",
    material_examples="Anspruch, Sanktion, Mitwirkung, Unterkunftskosten",
    answerable_with=("deutschem Sozialrecht, insbesondere SGB II, SGB X oder SGB XII"),
    hierarchy_example="SGB II > § 31 > Abs. 1",
    adversary_examples="das Jobcenter, das Sozialamt oder eine andere Behörde",
)


ERBRECHT_PROFILE = AreaProfile(
    key="erbrecht",
    display_name="deutsches Erbrecht und Erbschaftsteuerrecht",
    statutes=(
        "insbesondere BGB (Erbrecht), ErbStG, Höfeordnung, Schenkungsrecht "
        "und FamFG für Erbschaftsverfahren"
    ),
    document_examples=(
        "eines Testaments, eines Erbvertrags, eines Erbscheinsantrags, "
        "eines Finanzamtsbescheids zur Erbschaftsteuer, eines Schreibens "
        "des Nachlassgerichts oder eines Familienrechtsstreits mit "
        "erbrechtlichen Bezügen"
    ),
    issue_terms=(
        "gesetzliche Erbfolge",
        "Testamentsauslegung",
        "Pflichtteilsanspruch",
        "Erbquote",
        "Vorausvermächtnis",
        "Annahme und Ausschlagung der Erbschaft",
        "Erbschaftsteuer-Freibetrag",
        "Steuerklasse",
        "Bewertung des land- und forstwirtschaftlichen Vermögens",
        "Höfeordnung",
        "Hofesübergabe",
    ),
    formal_examples="Testamentsform, Eröffnungstermin, Anfechtungsfrist",
    material_examples=(
        "Erbquote, Pflichtteil, Freibetrag, Steuerklasse, Bewertung "
        "landwirtschaftlicher Betriebe"
    ),
    answerable_with=(
        "deutschem Erbrecht, Erbschaftsteuerrecht oder Schenkungsrecht "
        "(insbesondere BGB, ErbStG, Höfeordnung, FamFG)"
    ),
    hierarchy_example="BGB > § 1922",
    adversary_examples=(
        "Miterben, Pflichtteilsberechtigte, das Finanzamt oder das " "Nachlassgericht"
    ),
)


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

_NO_INVENTION = (
    "- Erfinde niemals Tatsachen, Fristen, Paragraphen, Aktenzeichen, "
    "Gerichtsentscheidungen oder Behördenhandlungen.\n"
    "- Nenne nichts, das im vorgelegten Material keine erkennbare "
    "Grundlage hat.\n"
    "- Benenne Unsicherheit ausdrücklich, statt Lücken durch Annahmen zu "
    "füllen."
)

_JSON_OBJECT_ONLY = (
    "Antworte ausschließlich mit einem einzigen gültigen JSON-Objekt.\n"
    "- Kein Text vor oder nach dem JSON.\n"
    "- Keine Markdown-Zäune (```), keine Kommentare, keine zusätzlichen "
    "Schlüssel.\n"
    "- JSON-Schlüssel exakt wie angegeben (englisch); alle Textinhalte auf "
    "Deutsch.\n"
    "- Zeilenumbrüche innerhalb von Strings als \\n kodieren."
)

_JSON_ARRAY_ONLY = (
    "Antworte ausschließlich mit einem einzigen gültigen JSON-Array.\n"
    "- Kein Text vor oder nach dem JSON.\n"
    "- Keine Markdown-Zäune (```), keine Kommentare, keine zusätzlichen "
    "Schlüssel.\n"
    "- JSON-Schlüssel exakt wie angegeben (englisch); alle Textinhalte auf "
    "Deutsch.\n"
    "- Zeilenumbrüche innerhalb von Strings als \\n kodieren."
)


def _terms(profile: AreaProfile) -> str:
    return ", ".join(f'"{t}"' for t in profile.issue_terms)


def _multi_area_rules(profile: AreaProfile) -> str:
    """Extra rules injected when a profile spans multiple areas."""
    if " sowie " not in profile.display_name:
        return ""
    return (
        "- Der Fall berührt mehrere Rechtsgebiete: Berücksichtige ALLE "
        "relevanten Aspekte aus jedem Gebiet.\n"
        "- Achte besonders auf Querverbindungen zwischen den Gebieten und "
        "auf Vorrangregeln (speziellere Normen verdrängen allgemeinere).\n"
        "- Wenn Gebiete unterschiedliche Bewertungen nahelegen, benenne "
        "diesen Konflikt ausdrücklich.\n"
    )


# ---------------------------------------------------------------------------
# Stage 2 — Issue Classification
# ---------------------------------------------------------------------------


def _build_classification(p: AreaProfile) -> str:
    return (
        "<rolle>\n"
        f"Du bist ein sorgfältiger, evidenzorientierter Experte für "
        f"{p.display_name} ({p.statutes}).\n"
        "</rolle>\n\n"
        "<kontext>\n"
        f"Dir wird der normalisierte Text eines Dokuments vorgelegt, z. B. "
        f"{p.document_examples}.\n"
        "</kontext>\n\n"
        "<aufgabe>\n"
        "Identifiziere die rechtlichen Themen bzw. Problemfelder, die in dem "
        "Dokument tatsächlich angesprochen werden oder für die rechtliche "
        "Bewertung naheliegend relevant sind. Liefere 1 bis 8 Themen, "
        "geordnet nach Relevanz (wichtigstes zuerst).\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        f"- Verwende präzise deutsche Fachbegriffe, z. B.: {_terms(p)}.\n"
        "- Fasse inhaltlich überlappende Themen zu einem Begriff zusammen; "
        "keine Wiederholungen.\n"
        "- Ist das Dokument unklar, benenne das nächstliegende Thema "
        "allgemein, ohne Tatsachen zu unterstellen.\n"
        f"{_multi_area_rules(p)}"
        f"{_NO_INVENTION}\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "JSON-Objekt mit genau einem Schlüssel:\n"
        '{ "issues": ["Thema 1", "Thema 2"] }\n\n'
        f"{_JSON_OBJECT_ONLY}\n"
        "</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# Stage 3 — Question Decomposition
# ---------------------------------------------------------------------------


def _build_decomposition(p: AreaProfile) -> str:
    return (
        "<rolle>\n"
        f"Du bist ein sorgfältiger, evidenzorientierter Experte für "
        f"{p.display_name} ({p.statutes}).\n"
        "</rolle>\n\n"
        "<kontext>\n"
        f"Dir wird der normalisierte Text eines Dokuments vorgelegt, z. B. "
        f"{p.document_examples}.\n"
        "</kontext>\n\n"
        "<aufgabe>\n"
        "Leite genau 3 bis 5 konkrete Rechtsfragen ab, die beantwortet "
        "werden müssen, um die Angelegenheit rechtlich einzuordnen.\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- Jede Frage muss sich konkret auf den vorgelegten Dokumenttext "
        "beziehen.\n"
        f"- Jede Frage muss mit {p.answerable_with} beantwortbar sein.\n"
        "- Formuliere prüfbare Rechtsfragen, keine allgemeinen "
        "Ratgeberfragen.\n"
        "- Unterscheide, soweit erkennbar, zwischen formellen Fragen "
        f"(z. B. {p.formal_examples}) und materiellen Fragen "
        f"(z. B. {p.material_examples}).\n"
        "- Ist das Dokument unklar, formuliere die Unsicherheit in der "
        "Rechtsfrage selbst, statt etwas zu unterstellen.\n"
        f"{_multi_area_rules(p)}"
        f"{_NO_INVENTION}\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "JSON-Objekt mit genau einem Schlüssel:\n"
        '{ "questions": ["Frage 1", "Frage 2"] }\n\n'
        f"{_JSON_OBJECT_ONLY}\n"
        "</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# Combined Stages 2+3 — Triage (WP-006)
# ---------------------------------------------------------------------------


def _build_triage(p: AreaProfile) -> str:
    return (
        "<rolle>\n"
        f"Du bist ein sorgfältiger, evidenzorientierter Experte für "
        f"{p.display_name} ({p.statutes}).\n"
        "</rolle>\n\n"
        "<kontext>\n"
        f"Dir wird der normalisierte Text eines Dokuments vorgelegt, z. B. "
        f"{p.document_examples}.\n"
        "</kontext>\n\n"
        "<aufgabe>\n"
        "Erledige BEIDE der folgenden Teilaufgaben in einem einzigen "
        "Durchlauf:\n\n"
        "1. Themenidentifikation: Identifiziere alle rechtlichen Themen "
        "bzw. Problemfelder, die in dem Dokument tatsächlich angesprochen "
        "werden oder für die rechtliche Bewertung naheliegend relevant "
        "sind. Verwende präzise deutsche Fachbegriffe, z. B.: "
        f"{_terms(p)}. Liefere 1 bis 8 Themen, geordnet nach Relevanz.\n\n"
        "2. Fragenableitung: Leite aus den Themen genau 3 bis 5 konkrete, "
        "beantwortbare Rechtsfragen ab. Jede Frage muss sich auf den "
        f"Dokumenttext beziehen und mit {p.answerable_with} beantwortbar "
        "sein. Berücksichtige, soweit relevant, formelle Fragen (z. B. "
        f"{p.formal_examples}) und materielle Fragen (z. B. "
        f"{p.material_examples}).\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- Fasse inhaltlich überlappende Themen und Fragen zusammen; keine "
        "Dopplungen.\n"
        "- Ist das Dokument unklar, formuliere die Unsicherheit in der "
        "Rechtsfrage selbst, statt etwas zu unterstellen.\n"
        f"{_multi_area_rules(p)}"
        f"{_NO_INVENTION}\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "JSON-Objekt mit genau diesen zwei Schlüsseln:\n"
        '{ "issues": ["Thema A", "Thema B"], '
        '"questions": ["Frage 1", "Frage 2"] }\n\n'
        f"{_JSON_OBJECT_ONLY}\n"
        "</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# Stage 7 — Adversarial Review
# ---------------------------------------------------------------------------


def _build_adversarial_review(p: AreaProfile) -> str:
    return (
        "<rolle>\n"
        "Du bist der Rechtsprüfungsrat — ein Gremium aus mehreren "
        "Rechtsexpertinnen und -experten für "
        f"{p.display_name}, das eine umfassende adversariale Prüfung des "
        "Falles aus allen Perspektiven durchführt. Deine Aufgabe ist "
        "NICHT, die Claims zu verteidigen: Du prüfst jeden Claim kritisch, "
        "gegnerisch und neutral. Ein Claim kann stark, teilweise tragfähig, "
        "unsicher oder unbegründet sein.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        "1. Der normalisierte Text des Ausgangsdokuments.\n"
        "2. Eine Liste identifizierter rechtlicher Themen.\n"
        "3. Eine Liste konkreter Rechtsfragen.\n"
        "4. Eine Liste rechtlicher Claims (Aussagen) mit Konfidenzwerten.\n"
        "5. Rechtsquellen-Chunks aus dem Corpus.\n"
        "</eingaben>\n\n"
        "<aufgabe>\n"
        "Prüfe JEDEN Claim aus allen fünf Perspektiven:\n\n"
        "1. Verteidigerperspektive (Anwalt der Nutzerseite):\n"
        "- Welche Gegenargumente sprechen gegen die Position der "
        "Gegenseite?\n"
        "- Welche Rechtsfehler hat die Gegenseite möglicherweise begangen?\n"
        "- Welche Schutzvorschriften kommen der Nutzerseite zugute?\n"
        "- Welche Tatsachen aus dem Dokument stützen die Nutzerposition?\n\n"
        "2. Gegnerperspektive (die andere Partei, z. B. "
        f"{p.adversary_examples}):\n"
        "- Was würde die Gegenseite zur Verteidigung ihrer Position "
        "vorbringen?\n"
        "- Auf welche der bereitgestellten Rechtsgrundlagen würde sie sich "
        "stützen?\n"
        "- Welche Ermessens-, Beurteilungs- oder Nachweisspielräume hätte "
        "sie?\n"
        "- Welche Schwächen oder Lücken in der Nutzerposition würde sie "
        "angreifen?\n\n"
        "3. Richterliche Perspektive (neutrale Instanz):\n"
        "- Wie würde ein neutrales Gericht diesen Fall wahrscheinlich "
        "beurteilen?\n"
        "- Ist die Rechtslage eindeutig oder bestehen "
        "Auslegungsspielräume?\n"
        "- Ist der Claim anhand der bereitgestellten Chunks ausreichend "
        "belegt?\n"
        "- Wie hoch ist die Erfolgsaussicht qualitativ einzuschätzen "
        "(keine Garantie, keine verbindliche Rechtsberatung)?\n\n"
        "4. Verfahrensprüfung:\n"
        "- Wurden formelle Verfahrensvorschriften eingehalten?\n"
        "- Liegen formelle Fehler vor (z. B. fehlende Anhörung, "
        "unzureichende Begründung, Fristversäumnis, falsche Zuständigkeit, "
        "fehlende Bestimmtheit, unklare Rechtsbehelfsbelehrung, "
        "Formmängel)?\n"
        "- Ist die angegriffene Entscheidung formell angreifbar?\n"
        "- Welche Verfahrensfehler sind nur möglich, aber nicht sicher "
        "feststellbar?\n\n"
        "5. Risikobewertung:\n"
        "- Welche rechtlichen Risiken bestehen für die Nutzerseite?\n"
        "- Wie hoch ist das Risiko einer negativen Entscheidung?\n"
        "- Wie stark ist die Verteidigungsposition insgesamt?\n"
        "- Welche fehlenden Tatsachen oder Unterlagen könnten entscheidend "
        "sein?\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- Argumentiere ausschließlich auf Grundlage des Dokuments und der "
        "bereitgestellten Chunks.\n"
        "- Wird ein Claim durch die Chunks nicht ausreichend gestützt, "
        "sage das ausdrücklich und bewerte das Risiko entsprechend höher.\n"
        "- Formuliere die Gegnerperspektive ernsthaft und stark, auch wenn "
        "dies der Nutzerposition schadet.\n"
        "- Halte die richterliche Perspektive strikt neutral; übertreibe "
        "keine Erfolgsaussicht.\n"
        "- Bewerte Risiken ehrlich: Gestehe eine schwache "
        "Verteidigungsposition ein, wenn die Fakten dagegen sprechen.\n"
        "- Gib 3 bis 5 key_risks und 3 bis 5 recommended_next_steps an.\n"
        "- confidence_in_defense: 0.0 (sehr schwach) bis 1.0 (sehr stark).\n"
        "- procedural_errors_found darf leer sein, wenn keine "
        "Verfahrensfehler erkennbar sind. Mögliche, aber nicht sicher "
        "feststellbare Fehler gehören in procedural_issues oder key_risks, "
        "nicht in procedural_errors_found.\n"
        "- Jeder Eintrag in reviews MUSS einen claim_index (0-basiert) "
        "haben, der auf den ursprünglichen Claim verweist.\n"
        '- risk_level ist ausschließlich einer der Werte "niedrig", '
        '"mittel" oder "hoch".\n'
        f"{_multi_area_rules(p)}"
        f"{_NO_INVENTION}\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "JSON-Objekt mit genau dieser Struktur:\n"
        "{\n"
        '  "reviews": [\n'
        "    {\n"
        '      "claim_index": 0,\n'
        '      "defense_argument": "Argument aus Verteidigersicht",\n'
        '      "authority_argument": "Argument der Gegenseite",\n'
        '      "judicial_assessment": "Einschätzung des Gerichts",\n'
        '      "procedural_issues": "Verfahrensfehler oder -bedenken",\n'
        '      "risk_level": "niedrig",\n'
        '      "recommended_strategy": "Empfohlene Strategie"\n'
        "    }\n"
        "  ],\n"
        '  "overall_assessment": {\n'
        '    "summary": "Gesamtbewertung aller Claims aus adversarialer '
        'Sicht",\n'
        '    "key_risks": ["Risiko 1 – Beschreibung"],\n'
        '    "recommended_next_steps": ["Schritt 1 – Beschreibung"],\n'
        '    "confidence_in_defense": 0.65,\n'
        '    "procedural_errors_found": ["Formeller Fehler 1"]\n'
        "  }\n"
        "}\n\n"
        f"{_JSON_OBJECT_ONLY}\n"
        "</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# Combined Stages 5+6+7+8 — Grounded Answer Generation (WP-007)
# ---------------------------------------------------------------------------


def _build_grounded_answer(p: AreaProfile) -> str:
    return (
        "<rolle>\n"
        f"Du bist ein sorgfältiger Experte für {p.display_name} "
        f"({p.statutes}). Du arbeitest strikt evidenzgebunden.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        f"1. Der normalisierte Text eines Dokuments, z. B. "
        f"{p.document_examples}.\n"
        "2. Eine Liste identifizierter rechtlicher Themen.\n"
        "3. Eine Liste konkreter Rechtsfragen.\n"
        "4. Eine Sammlung von Gesetzes- und Rechtsprechungs-Chunks aus "
        "einer Vektordatenbank (jeweils mit chunk_id).\n"
        "</eingaben>\n\n"
        "<arbeitsprinzip>\n"
        "- Tatsachen dürfen nur aus dem Dokument übernommen werden.\n"
        "- Rechtliche Aussagen dürfen nur auf den bereitgestellten Chunks "
        "beruhen.\n"
        "- Empfehlungen dürfen nur aus belegten Tatsachen und belegten "
        "rechtlichen Bewertungen folgen.\n"
        "- Kann eine Frage mit den bereitgestellten Quellen nicht sicher "
        "beantwortet werden, benenne diese Unsicherheit ausdrücklich.\n"
        "</arbeitsprinzip>\n\n"
        "<aufgabe>\n"
        "A) Claims erstellen: Formuliere für jede Rechtsfrage 1 bis 3 "
        "rechtliche Aussagen (Claims). Jeder Claim hat exakt diese "
        "Felder:\n"
        '- "claim_text" (str): die Aussage selbst, auf Deutsch\n'
        '- "confidence_score" (float 0.0–1.0): deine Sicherheit auf '
        "Grundlage der bereitgestellten Evidenz\n"
        '- "claim_type" (str): "fact" | "interpretation" | '
        '"recommendation"\n'
        '- "question" (str): die Rechtsfrage, auf die sich der Claim '
        "bezieht\n"
        '- "evidence_chunk_id" (str): die ID des Chunks, aus dem die '
        "Evidenz stammt\n"
        '- "evidence_hierarchy" (str): die Hierarchie der Rechtsquelle '
        f'(z. B. "{p.hierarchy_example}")\n'
        '- "evidence_quote" (str): das EXAKTE wörtliche Zitat aus dem '
        "Chunk\n\n"
        "B) Abschnitte generieren: Erstelle die folgenden 7 Abschnitte auf "
        "Deutsch:\n"
        '- "sachverhalt": Zusammenfassung des Sachverhalts\n'
        '- "rechtliche_wuerdigung": Rechtliche Würdigung mit Zitaten der '
        "einschlägigen Vorschriften\n"
        '- "ergebnis": Ergebnis / Fazit\n'
        '- "handlungsempfehlung": Konkrete Handlungsempfehlungen\n'
        '- "entwurf": Entwurf eines Antwortschreibens\n'
        '- "unsicherheiten": Verbleibende Unsicherheiten oder fehlende '
        "Informationen\n"
        '- "adversarial_pruefung": Vorläufige adversariale Einschätzung '
        "(wird später durch die detaillierte Rechtsprüfung ersetzt)\n"
        "</aufgabe>\n\n"
        "<regeln_claims>\n"
        "- Verwende NUR die bereitgestellten Chunks als Rechtsquellen.\n"
        "- Kopiere evidence_quote WÖRTLICH aus dem Chunk-Text (copy-paste, "
        "keine Paraphrasierung, keine Glättung).\n"
        "- evidence_quote muss die konkrete rechtliche Aussage stützen; "
        "ein nur thematisch ähnlicher Chunk reicht nicht aus.\n"
        "- evidence_chunk_id MUSS exakt eine chunk_id aus den "
        "bereitgestellten Chunks sein.\n"
        "- evidence_hierarchy MUSS zur angegebenen Quelle passen, soweit "
        "sie im Chunk angegeben ist.\n"
        "- Reicht die Evidenz nicht aus: setze confidence_score niedrig "
        "(<= 0.4) und sage im claim_text ausdrücklich, dass die Frage mit "
        "den bereitgestellten Quellen nicht sicher beantwortet werden "
        "kann.\n"
        "- Ist gar kein geeigneter Chunk vorhanden: erstelle keinen "
        "substantiven rechtlichen Claim, sondern nur eine vorsichtige "
        "Aussage zur fehlenden Belegbarkeit mit niedrigem "
        "confidence_score und leeren Strings für evidence_chunk_id, "
        "evidence_hierarchy und evidence_quote.\n"
        "- Übernimm keine Tatsache aus dem Dokument als sicher, wenn sie "
        "dort nur behauptet, unklar oder streitig erscheint; kennzeichne "
        "sie vorsichtig.\n"
        "- Trenne sauber zwischen Tatsachen aus dem Dokument (fact), "
        "rechtlicher Auslegung (interpretation) und Handlungsempfehlung "
        "(recommendation).\n"
        "- Empfehlungen dürfen nur aus zuvor belegten rechtlichen "
        "Bewertungen folgen.\n"
        "- Eine hohe confidence_score ist nur zulässig, wenn "
        "Dokumenttatsachen und Rechtsquelle klar zusammenpassen.\n"
        f"{_multi_area_rules(p)}"
        f"{_NO_INVENTION}\n"
        "</regeln_claims>\n\n"
        "<regeln_abschnitte>\n"
        "- Schreibe verständlich für eine betroffene Person, aber "
        "rechtlich präzise.\n"
        "- Die rechtliche_wuerdigung muss auf den Claims und deren "
        "evidence_quote beruhen; führe keine zusätzlichen Rechtsquellen "
        "ein. Zitiere Vorschriften im Format '§ X Abs. Y Satz Z', soweit "
        "diese Angaben vorliegen.\n"
        "- Mache deutlich, wenn eine Einschätzung unsicher ist oder "
        "weitere Informationen fehlen.\n"
        "- Nenne keine konkreten Fristen, die nicht aus dem Dokument oder "
        "den bereitgestellten Quellen hervorgehen. Eine im Dokument "
        "genannte Frist darfst du wiedergeben, musst aber kenntlich "
        "machen, dass sie aus dem Dokument stammt.\n"
        "- Der Entwurf ist höflich, sachlich und behördentauglich. Er "
        "behauptet keine falschen Tatsachen; bei fehlenden Informationen "
        "nutze Platzhalter wie [Datum], [Aktenzeichen], [Name] oder "
        "[konkrete Begründung ergänzen].\n"
        "- Der Entwurf enthält keine rechtlichen Behauptungen, die nicht "
        "durch die Claims gestützt sind. Bei unsicherer Rechtslage "
        "formuliere ihn als Prüfungs- oder Begründungsverlangen statt als "
        "sichere Rechtsbehauptung.\n"
        "- Stelle nicht dar, dass dies verbindliche anwaltliche Beratung "
        "sei.\n"
        "</regeln_abschnitte>\n\n"
        "<ausgabeformat>\n"
        "JSON-Objekt mit genau dieser Struktur:\n"
        "{\n"
        '  "claims": [\n'
        "    {\n"
        '      "claim_text": "...",\n'
        '      "confidence_score": 0.82,\n'
        '      "claim_type": "interpretation",\n'
        '      "question": "...",\n'
        '      "evidence_chunk_id": "...",\n'
        f'      "evidence_hierarchy": "{p.hierarchy_example}",\n'
        '      "evidence_quote": "..."\n'
        "    }\n"
        "  ],\n"
        '  "sections": {\n'
        '    "sachverhalt": "...",\n'
        '    "rechtliche_wuerdigung": "...",\n'
        '    "ergebnis": "...",\n'
        '    "handlungsempfehlung": "...",\n'
        '    "entwurf": "...",\n'
        '    "unsicherheiten": "...",\n'
        '    "adversarial_pruefung": "..."\n'
        "  }\n"
        "}\n\n"
        f"{_JSON_OBJECT_ONLY}\n"
        "</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# Stage 5 — Claim Construction (legacy, used when COMBINE_FINAL_STAGES=False)
# ---------------------------------------------------------------------------


def _build_claim_construction(p: AreaProfile) -> str:
    return (
        "<rolle>\n"
        f"Du bist ein sorgfältiger Experte für {p.display_name} "
        f"({p.statutes}). Du arbeitest strikt evidenzgebunden.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        "1. Eine Liste konkreter Rechtsfragen.\n"
        "2. Eine Sammlung von Rechtsquellen-Chunks aus dem Corpus.\n"
        "</eingaben>\n\n"
        "<aufgabe>\n"
        "Konstruiere für jede Frage 1 bis 3 rechtliche Claims. Ein Claim "
        "ist eine einzelne prüfbare Aussage, die eine Rechtsfrage ganz "
        "oder teilweise beantwortet. Jeder Claim hat exakt diese Felder:\n"
        '- "claim_text" (str): die Aussage selbst, auf Deutsch\n'
        '- "confidence_score" (float 0.0–1.0)\n'
        '- "claim_type" (str): "fact" | "interpretation" | '
        '"recommendation"\n'
        '- "question" (str): die Frage, auf die sich der Claim bezieht\n'
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- Stütze Claims so weit wie möglich auf die bereitgestellten "
        "Chunks.\n"
        "- Beantworten die Chunks eine Frage nicht ausreichend, formuliere "
        "einen vorsichtigen Claim mit niedrigem confidence_score "
        "(<= 0.4).\n"
        "- Verwende hohe confidence_score-Werte nur, wenn die "
        "bereitgestellten Quellen die Aussage klar tragen.\n"
        "- Trenne Tatsachenbehauptungen, rechtliche Auslegung und "
        "Empfehlungen.\n"
        "- Empfehlungen dürfen nur aus rechtlich gestützten Claims "
        "folgen.\n"
        f"{_multi_area_rules(p)}"
        f"{_NO_INVENTION}\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "JSON-Array von Claim-Objekten:\n"
        '[ { "claim_text": "...", "confidence_score": 0.8, '
        '"claim_type": "fact", "question": "..." } ]\n\n'
        f"{_JSON_ARRAY_ONLY}\n"
        "</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# Stage 6 — Verification (legacy, used when COMBINE_FINAL_STAGES=False)
# ---------------------------------------------------------------------------


def _build_verification(p: AreaProfile) -> str:
    return (
        "<rolle>\n"
        "Du bist ein strenger, unabhängiger Qualitätsprüfer für eine "
        f"evidenzgebundene Reasoning-Engine im Bereich {p.display_name}. "
        "Du erhältst Claims und die Quellen-Chunks, auf denen sie beruhen "
        "sollen.\n"
        "</rolle>\n\n"
        "<aufgabe>\n"
        "Prüfe für jeden Claim, ob die angegebenen Quellen die Aussage "
        "wirklich tragen:\n"
        "- Unterstützt der Quellentext die Aussage ausdrücklich oder mit "
        "hoher rechtlicher Plausibilität?\n"
        "- Geht der Claim zu weit, verallgemeinert er unzulässig oder "
        "ergänzt er Tatsachen, Paragraphen oder Rechtsfolgen, die nicht "
        "belegt sind?\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- Wird der Claim nur teilweise unterstützt: senke den "
        "confidence_score deutlich und erkläre kurz warum.\n"
        "- Wird der Claim nicht unterstützt: setze verified auf false und "
        "senke den confidence_score auf höchstens 0.4.\n"
        "- Ändere den claim_text nicht inhaltlich; prüfe ihn nur.\n"
        "- Erfinde keine neuen Quellen, Paragraphen, Tatsachen oder "
        "Begründungen.\n"
        f"{_multi_area_rules(p)}"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "JSON-Array; jedes Element hat exakt diese Felder:\n"
        '- "claim_text" (str): der ursprüngliche Claim\n'
        '- "confidence_score" (float 0.0–1.0): angepasste Konfidenz\n'
        '- "claim_type" (str): "fact" | "interpretation" | '
        '"recommendation"\n'
        '- "verified" (bool): ob die Quelle den Claim trägt\n'
        '- "reasoning" (str): kurze Begründung auf Deutsch\n\n'
        '[ { "claim_text": "...", "confidence_score": 0.7, '
        '"claim_type": "fact", "verified": true, "reasoning": "..." } ]\n\n'
        f"{_JSON_ARRAY_ONLY}\n"
        "</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# Stage 8 — Output Generation (legacy)
# ---------------------------------------------------------------------------


def _build_output(p: AreaProfile) -> str:
    return (
        "<rolle>\n"
        f"Du bist ein sorgfältiger Experte für {p.display_name}. Dir wird "
        "eine Liste verifizierter Claims übergeben.\n"
        "</rolle>\n\n"
        "<aufgabe>\n"
        "Erstelle daraus eine strukturierte rechtliche Einschätzung in "
        "genau 6 Abschnitten (JSON-Schlüssel englisch, Inhalte deutsch):\n"
        '- "sachverhalt" (str): Zusammenfassung des Sachverhalts\n'
        '- "rechtliche_wuerdigung" (str): Rechtliche Würdigung mit '
        "Zitaten der einschlägigen Vorschriften\n"
        '- "ergebnis" (str): Ergebnis / Fazit\n'
        '- "handlungsempfehlung" (str): Konkrete Handlungsempfehlungen\n'
        '- "entwurf" (str): Entwurf eines Antwortschreibens\n'
        '- "unsicherheiten" (str): Unsicherheiten oder fehlende '
        "Informationen\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- Verwende ausschließlich die verifizierten Claims als "
        "Grundlage.\n"
        "- Stelle unsichere oder nicht belegte Punkte ausdrücklich als "
        "unsicher dar.\n"
        "- Zitiere Vorschriften nur, wenn sie in den Claims belastbar "
        "enthalten sind, im Format '§ X Abs. Y Satz Z', soweit diese "
        "Angaben vorliegen.\n"
        "- Die rechtliche Würdigung ist verständlich, aber nicht "
        "vereinfachend verfälschend.\n"
        "- Die Handlungsempfehlung enthält konkrete nächste Schritte, "
        "behauptet aber keine verbindliche anwaltliche Beratung.\n"
        "- Der Entwurf ist höflich, sachlich und behördentauglich; bei "
        "fehlenden Informationen nutze Platzhalter wie [Datum], "
        "[Aktenzeichen], [Name] oder [konkrete Begründung ergänzen].\n"
        f"{_multi_area_rules(p)}"
        f"{_NO_INVENTION}\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "JSON-Objekt mit genau diesen sechs Schlüsseln:\n"
        '{ "sachverhalt": "...", "rechtliche_wuerdigung": "...", '
        '"ergebnis": "...", "handlungsempfehlung": "...", '
        '"entwurf": "...", "unsicherheiten": "..." }\n\n'
        f"{_JSON_OBJECT_ONLY}\n"
        "</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# Prompt-set assembly
# ---------------------------------------------------------------------------

_STAGE_BUILDERS = {
    "classification": _build_classification,
    "decomposition": _build_decomposition,
    "triage": _build_triage,
    "grounded_answer": _build_grounded_answer,
    "adversarial_review": _build_adversarial_review,
    "claim_construction": _build_claim_construction,
    "verification": _build_verification,
    "output": _build_output,
}


def _build_prompt_set(profile: AreaProfile) -> dict[str, str]:
    return {stage: build(profile) for stage, build in _STAGE_BUILDERS.items()}


def _merge_profiles(profiles: list[AreaProfile]) -> AreaProfile:
    """Merge several area profiles into one coherent multi-area persona.

    Unlike the v0.x approach (concatenating whole prompts), the merge
    happens at the profile level, so every stage prompt keeps a single
    role, a single rule set and exactly one output-format block.
    ``_multi_area_rules`` detects the merged persona (via " sowie " in
    the display name) and injects cross-area guidance.
    """
    merged_terms: list[str] = []
    for prof in profiles:
        for term in prof.issue_terms:
            if term not in merged_terms:
                merged_terms.append(term)

    return AreaProfile(
        key="+".join(prof.key for prof in profiles),
        display_name=" sowie ".join(prof.display_name for prof in profiles),
        statutes="; ".join(prof.statutes for prof in profiles),
        document_examples="; oder ".join(prof.document_examples for prof in profiles),
        issue_terms=tuple(merged_terms),
        formal_examples="; ".join(prof.formal_examples for prof in profiles),
        material_examples="; ".join(prof.material_examples for prof in profiles),
        answerable_with=" oder ".join(prof.answerable_with for prof in profiles),
        hierarchy_example=profiles[0].hierarchy_example,
        adversary_examples="; ".join(prof.adversary_examples for prof in profiles),
    )


# ---------------------------------------------------------------------------
# Registry — area → prompts
# ---------------------------------------------------------------------------

_PROFILE_REGISTRY: dict[str, AreaProfile] = {
    "sozialrecht": SOZIALRECHT_PROFILE,
    "erbrecht": ERBRECHT_PROFILE,
    # Shares the Erbrecht profile (ErbStG / BGB-Schenkung overlap).
    "schenkungsrecht": ERBRECHT_PROFILE,
    # Shares the Erbrecht profile because of succession overlap.
    "familienrecht": ERBRECHT_PROFILE,
}

SOCIALRECHT_PROMPTS: dict[str, str] = _build_prompt_set(SOZIALRECHT_PROFILE)
ERBRECHT_PROMPTS: dict[str, str] = _build_prompt_set(ERBRECHT_PROFILE)

# All areas currently registered (public, kept for API compatibility).
REGISTRY: dict[str, dict[str, str]] = {
    "sozialrecht": SOCIALRECHT_PROMPTS,
    "erbrecht": ERBRECHT_PROMPTS,
    "schenkungsrecht": ERBRECHT_PROMPTS,
    "familienrecht": ERBRECHT_PROMPTS,
}


# ---------------------------------------------------------------------------
# Multi-area prompt composer
# ---------------------------------------------------------------------------


@lru_cache(maxsize=32)
def _cached_multi_area_set(profile_keys: tuple[str, ...]) -> dict[str, str]:
    profiles = [_PROFILE_REGISTRY[key] for key in profile_keys]
    return _build_prompt_set(_merge_profiles(profiles))


# Public-facing combined-area lookup, used by reasoning.py.
def get_prompts(legal_areas: list[str] | None = None) -> dict[str, str]:
    """Return the prompt set appropriate for a case covering *legal_areas*.

    Parameters
    ----------
    legal_areas :
        A list of legal-area keys (e.g. ``["sozialrecht"]``,
        ``["erbrecht", "familienrecht"]``). Unknown / empty values fall
        back to the Sozialrecht prompt set (default-area behaviour
        preserved from v0.x; prompt *contents* are v1.x).

    Returns
    -------
    dict[str, str]
        Mapping of stage name to system prompt. Keys:
        ``classification``, ``decomposition``, ``triage``,
        ``grounded_answer``, ``adversarial_review``,
        ``claim_construction``, ``verification``, ``output``.
    """
    if not legal_areas:
        return dict(SOCIALRECHT_PROMPTS)

    # Resolve to unique profiles, preserving request order (aliases such
    # as schenkungsrecht/familienrecht collapse onto their base profile).
    unique_profiles: list[AreaProfile] = []
    for area in legal_areas:
        profile = _PROFILE_REGISTRY.get(area)
        if profile is not None and profile not in unique_profiles:
            unique_profiles.append(profile)

    if not unique_profiles:
        return dict(SOCIALRECHT_PROMPTS)

    if len(unique_profiles) == 1:
        return dict(_build_prompt_set(unique_profiles[0]))

    return dict(_cached_multi_area_set(tuple(prof.key for prof in unique_profiles)))
