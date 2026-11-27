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

Adding a new legal area = shipping a module with a ``prompts`` profile
(``modules/<id>/prompts/profile.yaml``, WP-93); no core change.

Prompt-engineering conventions applied to every stage prompt:
  * XML-tagged sections (<rolle>, <kontext>, <aufgabe>, <regeln>,
    <ausgabeformat>) for unambiguous instruction boundaries.
  * Instructions consistently in German; JSON keys and enum values in
    English exactly as the downstream parsers expect them — except
    ``risk_level`` (German, user-visible; see 3.0.0).
  * One canonical output example per prompt; the format block is always
    the LAST section (recency effect improves format compliance).
  * Shared anti-hallucination and JSON-discipline blocks, defined once.
  * Explicit escape hatches for insufficient evidence instead of
    letting the model improvise.

Sampling temperatures per stage live in ``STAGE_TEMPERATURES`` and are
read by every LLM call site (not embedded in the prompt text).

Versioning / breaking changes
-----------------------------
3.0.1 (WP-97 gate fix)
  * P-04 claim rules: the "nicht belegbar" claim is one per response (not one
    per question) and only for *legal* questions — questions the document
    itself answers (Angaben, Daten, Fristen, Beträge) need no claim. Claim
    density restored to 1–3 per legal question (max 12). Raised because the
    3.0.0 wording turned four of twelve goldset cases into responses that
    cited nothing at all (WP-97 gate, D-062).

3.0.0 (prompt upgrade, docs/prompt-upgrade-proposal.md)
  * BREAKING (prompt texts): every stage prompt rewritten; shared blocks
    S-01…S-04 rewritten, S-07 (no computation) added; ``STRICT_SUFFIX``
    (S-05) is German and has no "return [] / {}" escape hatch (F-03).
  * BREAKING (internal API): ``AreaProfile`` gains ``result_categories``
    (required in every module profile) and ``is_multi_area``.
  * ``PROMPT_SET_VERSION`` / ``prompt_identity`` (CR-09);
    ``STAGE_TEMPERATURES`` is read by every call site (CR-04).
  * Convention exception, documented: ``risk_level`` (P-05) keeps the
    German values ``niedrig|mittel|hoch`` — they surface to users inside
    ``adversarial_pruefung`` and no code maps them (F-12, declined).

2.0.0 (WP-93)
  * BREAKING (internal API): area profiles moved out of the core into
    module data (``modules/*/prompts/profile.yaml``); ``SOZIALRECHT_PROFILE``,
    ``ERBRECHT_PROFILE``, ``SOCIALRECHT_PROMPTS``, ``ERBRECHT_PROMPTS`` and
    ``REGISTRY`` are removed. ``DEFAULT_PROMPTS`` (the ``DEFAULT_MODULE``
    set) replaces ``SOCIALRECHT_PROMPTS``; ``get_prompts`` is unchanged in
    signature and output. Prompt *texts* are byte-identical to 1.0.0.

1.0.0
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

# Semantic Version: 3.0.0

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

# ---------------------------------------------------------------------------
# Prompt identity (CR-09, F-14)
# ---------------------------------------------------------------------------

#: Version of the prompt set as a whole (every stage, shared block, endpoint
#: and calculator prompt). Bumped on any change to prompt text.
PROMPT_SET_VERSION = "3.6.0"


def prompt_digest(text: str) -> str:
    """SHA-256 hex digest of a rendered prompt."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_identity(stage: str, text: str) -> dict[str, str]:
    """Identity of one rendered prompt: stage id, set version, digest.

    Recorded in stage audit payloads and eval reports so that outputs can be
    traced to the exact instruction text that produced them.
    """
    return {"id": stage, "version": PROMPT_SET_VERSION, "sha256": prompt_digest(text)}


# ---------------------------------------------------------------------------
# Stage metadata — sampling temperatures and output caps (CR-04, CR-03)
# ---------------------------------------------------------------------------
# Every LLM call site reads its temperature here (until prompt set 3.0.0
# this table was metadata nobody read and every call ran at 0.1, F-04).
# Extraction-like stages want near-determinism; verbatim quoting (the
# grounded answer) stays low; the adversarial review gets headroom to argue
# both sides. JSON retries always run at 0.0, independently of this table.

STAGE_TEMPERATURES: dict[str, float] = {
    "classification": 0.1,
    "decomposition": 0.2,
    "triage": 0.1,
    "grounded_answer": 0.1,
    "adversarial_review": 0.3,
    "claim_construction": 0.2,
    "verification": 0.1,
    "output": 0.3,
    "calc_extraction": 0.0,
    "calc_explanation": 0.1,
    "chat": 0.1,
    "case_chat": 0.1,
    "intake": 0.1,
    "preset_suggest": 0.1,
    "ocr_synthesis": 0.1,
}


def stage_temperature(stage: str) -> float:
    """Sampling temperature for *stage* (``KeyError`` on unknown stages)."""
    return STAGE_TEMPERATURES[stage]


def stage_max_tokens(stage: str) -> int | None:
    """Output-token cap for *stage* from ``STAGE_MAX_TOKENS``, ``None`` = uncapped."""
    from app.core.config import settings

    return settings.STAGE_MAX_TOKENS.get(stage)


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
    # Closed vocabulary for the opening sentence of ``ergebnis`` (P-04/P-08),
    # "Begriff – Definition"; the core appends "Einordnung offen" (3.0.0).
    result_categories: tuple[str, ...] = ()
    # True only for profiles produced by _merge_profiles (CR-10, F-15);
    # replaces the substring test on " sowie " in the display name.
    is_multi_area: bool = False


# Concrete profiles are module data (``modules/<id>/prompts/profile.yaml``,
# WP-93) and are loaded through the module area tables below.


def profile_from_mapping(data: dict[str, object]) -> AreaProfile:
    """Build an :class:`AreaProfile` from a module prompt-profile mapping."""
    terms = data.get("issue_terms") or ()
    if not isinstance(terms, list | tuple):
        raise TypeError("prompt profile 'issue_terms' must be a list")
    categories = data.get("result_categories")
    if not isinstance(categories, list | tuple) or not categories:
        raise TypeError("prompt profile 'result_categories' must be a non-empty list")
    return AreaProfile(
        key=str(data["key"]),
        display_name=str(data["display_name"]),
        statutes=str(data["statutes"]),
        document_examples=str(data["document_examples"]),
        issue_terms=tuple(str(t) for t in terms),
        formal_examples=str(data["formal_examples"]),
        material_examples=str(data["material_examples"]),
        answerable_with=str(data["answerable_with"]),
        hierarchy_example=str(data["hierarchy_example"]),
        adversary_examples=str(data["adversary_examples"]),
        result_categories=tuple(str(c) for c in categories),
    )


#: Template slots of one (possibly merged) area profile, as a mapping.
_Slots = dict[str, Any]

#: Domain-neutral result category appended to every profile's
#: ``result_categories`` (no area literal: any module can be "offen").
_OPEN_CATEGORY = "Einordnung offen – die bereitgestellten Quellen reichen nicht aus"


def _slots(profile: AreaProfile) -> _Slots:
    return asdict(profile)


# ---------------------------------------------------------------------------
# Shared blocks (S-01 … S-07)
# ---------------------------------------------------------------------------

_NO_INVENTION = (
    "- Nenne keine Tatsache, kein Datum, keine Frist, keinen Geldbetrag, keine Norm, "
    "kein Aktenzeichen, keine Gerichtsentscheidung und keine Behördenhandlung, die "
    "weder im Dokument noch in den bereitgestellten Quellen steht.\n"
    "- Fehlt eine Angabe, benenne die Lücke („im Dokument nicht angegeben“). Fülle sie "
    "nicht durch Annahmen.\n"
    "- Kennzeichne eine unbelegte Aussage als unbelegt, statt sie abzuschwächen."
)

_JSON_OBJECT_ONLY = (
    "Antworte ausschließlich mit einem einzigen JSON-Objekt.\n"
    "- Erstes Zeichen „{“, letztes Zeichen „}“; kein Text davor oder danach, keine "
    "Markdown-Zäune, keine Kommentare.\n"
    "- Genau die angegebenen Schlüssel (englisch): keiner fehlt, keiner kommt hinzu.\n"
    '- Ohne Inhalt: "" für Text, [] für Listen; null nur, wo das Format es zeigt.\n'
    "- Alle Textwerte auf Deutsch; Zeilenumbrüche in Strings als \\n."
)

#: S-02 for prompts outside this module (intake P-09, presets P-10).
JSON_OBJECT_ONLY = _JSON_OBJECT_ONLY

_JSON_ARRAY_ONLY = (
    "Antworte ausschließlich mit einem einzigen JSON-Array.\n"
    "- Erstes Zeichen „[“, letztes Zeichen „]“; kein Text davor oder danach, keine "
    "Markdown-Zäune, keine Kommentare.\n"
    "- Jedes Element hat genau die angegebenen Schlüssel (englisch): keiner fehlt, "
    "keiner kommt hinzu.\n"
    "- Alle Textwerte auf Deutsch; Zeilenumbrüche in Strings als \\n."
)


def _multi_area_rules(p: _Slots, conflict_target: str) -> str:
    """Rendered only for merged profiles (explicit flag, CR-10)."""
    if not p["is_multi_area"]:
        return ""
    return (
        "- Der Fall berührt mehrere Rechtsgebiete: Prüfe jedes Gebiet gesondert.\n"
        "- Verdrängt eine speziellere Vorschrift eine allgemeinere, stütze das auf eine "
        "Quelle; sonst nenne beide Vorschriften.\n"
        f"- Führen die Gebiete zu unterschiedlichen Ergebnissen, beschreibe den Konflikt "
        f"in {conflict_target}.\n"
    )


STRICT_SUFFIX = "\n\nGib jetzt nur das JSON gemäß <ausgabeformat> aus."


_NO_COMPUTATION = (
    "- Berechne keine Fristen, Daten oder Beträge, auch keine Summen oder Differenzen. "
    "Gib Fristen und Beträge nur wörtlich aus dem Dokument oder einer Quelle wieder "
    "und nenne die Herkunft („laut Dokument“)."
)

#: Domain-neutral marker sentence (core literal; reevaluate path, case_chat.py:492).
_NUTZERKONTEXT = (
    "Text nach der Zeile „--- Nutzerkontext für Neuauswertung ---“ ist Vortrag der "
    "betroffenen Person, nicht Inhalt des Dokuments."
)


def _terms(p: _Slots) -> str:
    return ", ".join(f"„{t}“" for t in p["issue_terms"])


def _categories(p: _Slots) -> str:
    cats = [*p["result_categories"], _OPEN_CATEGORY]
    return "\n".join(f"  • {c}" for c in cats)


def _role(p: _Slots) -> str:
    return (
        "<rolle>\n"
        f"Du bist Experte für {p['display_name']} ({p['statutes']}). Du arbeitest für die "
        "Person, an die das Dokument gerichtet ist, und hilfst ihr, es zu verstehen. Du "
        "gibst keine Rechtsberatung.\n"
        "</rolle>\n\n"
    )


def _doc_input(p: _Slots) -> str:
    return (
        "<eingaben>\n"
        "Die Nutzernachricht enthält nur den normalisierten Text eines Dokuments, z. B. "
        f"{p['document_examples']}. Der Text stammt aus einer Texterkennung, kann "
        f"Erkennungsfehler enthalten und am Ende gekürzt sein. {_NUTZERKONTEXT}\n"
        "</eingaben>\n\n"
    )


_ISSUE_RULES = (
    "- Formuliere jedes Thema als „Fachbegriff (§ X Gesetz)“, z. B.: {terms}.\n"
    "- Normangabe: Nenne die Norm, die das Dokument für das Thema anführt. Führt es keine "
    "an, nenne die gesetzliche Grundlage nur, wenn du sie sicher kennst; sonst lass die "
    "Klammer weg.\n"
    "- Jede Norm einzeln mit „§“ und Gesetz, durch Komma getrennt; kein „§§“; höchstens "
    "mit Absatz, ohne Satz.\n"
    "- Die Normangabe ist ein Suchhinweis für die Quellensuche, keine Aussage über den "
    "Fall; die Regel „Nenne keine … Norm …“ unten gilt für sie nicht.\n"
)

_QUESTION_RULES = (
    "- Jede Frage betrifft eine konkrete Angabe des Dokuments und ist mit "
    "{answerable_with} beantwortbar.\n"
    "- Nenne in der Frage die einschlägige Norm („nach § X Gesetz“), wenn das Dokument "
    "sie anführt oder sie sicher feststeht.\n"
    "- Formuliere prüfbare Ja/Nein- oder W-Fragen, keine Ratgeberfragen.\n"
    "- Mindestens eine formelle Frage (z. B. {formal_examples}) und eine materielle Frage "
    "(z. B. {material_examples}), wenn das Dokument beides hergibt.\n"
    "- Ist das Dokument unklar, nimm die Unsicherheit in die Frage auf („Falls …, …“).\n"
)

# ---------------------------------------------------------------------------
# Stage templates P-01 … P-08
# ---------------------------------------------------------------------------


def _render_classification(p: _Slots) -> str:
    return (
        _role(p) + _doc_input(p) + "<aufgabe>\n"
        "Liste 1 bis 8 rechtliche Themen, die das Dokument anspricht oder die für seine "
        "Prüfung unmittelbar erheblich sind, wichtigstes zuerst.\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        + _ISSUE_RULES.format(terms=_terms(p))
        + "- Fasse überlappende Themen zusammen.\n"
        "- Ist der Text kein rechtlich erhebliches Schreiben oder unlesbar, gib genau ein "
        "Thema „Dokument nicht einordenbar“ zurück.\n"
        + _multi_area_rules(p, "einem eigenen Thema")
        + _NO_INVENTION
        + "\n</regeln>\n\n"
        "<ausgabeformat>\n"
        '{ "issues": ["Fachbegriff (§ X Gesetz)", "Fachbegriff"] }\n\n'
        + _JSON_OBJECT_ONLY
        + "\n</ausgabeformat>"
    )


def _render_decomposition(p: _Slots) -> str:
    return (
        _role(p) + _doc_input(p) + "<aufgabe>\n"
        "Formuliere 3 bis 5 Rechtsfragen, die geklärt werden müssen, um das Dokument für "
        "die betroffene Person rechtlich einzuordnen.\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        + _QUESTION_RULES.format(**p)
        + "- Ist der Text kein rechtlich erhebliches Schreiben oder unlesbar, gib eine leere "
        "Liste zurück.\n"
        + _multi_area_rules(p, "einer eigenen Rechtsfrage")
        + _NO_INVENTION
        + "\n</regeln>\n\n"
        "<ausgabeformat>\n"
        '{ "questions": ["Frage 1", "Frage 2", "Frage 3"] }\n\n'
        + _JSON_OBJECT_ONLY
        + "\n</ausgabeformat>"
    )


def _render_triage(p: _Slots) -> str:
    return (
        _role(p) + _doc_input(p) + "<aufgabe>\n"
        "1. issues: Liste 1 bis 8 rechtliche Themen, die das Dokument anspricht oder die für "
        "seine Prüfung unmittelbar erheblich sind, wichtigstes zuerst.\n"
        "2. questions: Leite aus den Themen 3 bis 5 Rechtsfragen ab.\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        + _ISSUE_RULES.format(terms=_terms(p))
        + _QUESTION_RULES.format(**p)
        + "- Fasse überlappende Themen und Fragen zusammen.\n"
        "- Ist der Text kein rechtlich erhebliches Schreiben oder unlesbar: issues = "
        "[„Dokument nicht einordenbar“], questions = [].\n"
        + _multi_area_rules(p, "einer eigenen Rechtsfrage")
        + _NO_INVENTION
        + "\n</regeln>\n\n"
        "<ausgabeformat>\n"
        '{ "issues": ["Fachbegriff (§ X Gesetz)"], "questions": ["Frage 1", "Frage 2", '
        '"Frage 3"] }\n\n' + _JSON_OBJECT_ONLY + "\n</ausgabeformat>"
    )


_CLAIM_EVIDENCE_RULES = (
    "- evidence_chunk_id: die chunk_id aus der eckigen Klammer der Kopfzeile, ohne "
    "Klammern, Zeichen für Zeichen.\n"
    "- evidence_hierarchy: die Hierarchie aus derselben Kopfzeile, unverändert.\n"
    "- evidence_quote: ein zusammenhängender Abschnitt aus dem Text dieses Chunks, 1 bis 2 "
    "Sätze, Zeichen für Zeichen kopiert. Keine Auslassungszeichen, keine Umformulierung, "
    "keine Zusammenfügung zweier Stellen, nicht die Kopfzeile, nicht das „...“ eines "
    "gekürzten Chunks.\n"
    "- Das Zitat muss die Aussage des Claims tragen; thematische Nähe genügt nicht.\n"
)

_CONFIDENCE_RULE = (
    "- confidence_score: 0.8–1.0 nur, wenn die Quelle die Aussage ohne Auslegung trägt; "
    "0.5–0.7, wenn Auslegung oder fehlende Tatsachen entscheiden; höchstens 0.4, wenn "
    "die Quelle sie nur teilweise trägt.\n"
)

_UNSOURCED_CLAIM = (
    "- Trägt keine Quelle eine Antwort auf eine rechtliche Frage: höchstens ein solcher "
    "Claim insgesamt (nicht je Frage) mit claim_text „Mit den bereitgestellten Quellen "
    "nicht belegbar: <Frage in Kurzform>“, claim_type "
    '"interpretation", confidence_score 0.2{empty_fields}. Fragen, die das Dokument '
    "selbst beantwortet (Angaben, Daten, Fristen, Beträge), brauchen keinen Claim.\n"
)

_RESULT_RULE = (
    "- ergebnis: beginnt mit genau einem Satz „Vorläufige Einordnung: <Begriff>.“; den "
    "Begriff vor dem Gedankenstrich wählst du aus:\n{categories}\n"
    "  Verwende diese Begriffe nur in diesem Satz und nie verneint. Danach höchstens 3 "
    "Sätze Begründung.\n"
)

_DRAFT_RULE = (
    "- entwurf: Schreiben der betroffenen Person an die absendende Stelle, sachlich und "
    "höflich. Rechtsbehauptungen nur aus belegten Claims; bei unsicherer Rechtslage als "
    "Bitte um Überprüfung oder Begründung. Platzhalter: [Name], [Anschrift], [Datum], "
    "[Aktenzeichen], [Begründung ergänzen].\n"
)


def _render_grounded_answer(p: _Slots) -> str:
    return (
        "<rolle>\n"
        f"Du bist Experte für {p['display_name']} ({p['statutes']}). Du bereitest für die "
        "Person, an die das Dokument gerichtet ist, eine belegte Einschätzung und einen "
        "Antwortentwurf vor. Du gibst keine Rechtsberatung und vertrittst niemanden.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        "Die Nutzernachricht hat diese Abschnitte:\n"
        f"- „## DOKUMENT“: normalisierter Text, z. B. {p['document_examples']}; kann "
        "gekürzt sein.\n"
        "- „## IDENTIFIZIERTE THEMEN“, „## RECHTSFRAGEN“: aus einer Vorstufe. Normangaben "
        "darin sind Suchhinweise, keine Belege.\n"
        "- „## RECHTSQUELLEN (CHUNKS)“: Blöcke mit der Kopfzeile „CHUNK [chunk_id] "
        "Hierarchie:“ und dem Text, getrennt durch „---“. Ein Block, der auf „...“ endet, "
        "ist gekürzt.\n"
        f"{_NUTZERKONTEXT}\n"
        "</eingaben>\n\n"
        "<aufgabe>\n"
        "1. claims: Beantworte jede rechtliche Frage mit 1 bis 3 Claims, insgesamt höchstens "
        "12.\n"
        "2. sections: Schreibe die sieben Abschnitte nur auf Grundlage der Claims und des "
        "Dokuments.\n"
        "Widerspricht eine Abschnittsregel einer Claim-Regel, gilt die Claim-Regel.\n"
        "</aufgabe>\n\n"
        "<regeln_claims>\n"
        '- claim_type: "interpretation" (rechtliche Bewertung) oder "recommendation" '
        '(Schritt, der aus einer belegten Bewertung folgt). Verwende "fact" nicht; '
        "Tatsachen aus dem Dokument gehören in sachverhalt.\n"
        "- question: die Rechtsfrage wörtlich aus „## RECHTSFRAGEN“.\n"
        + _CLAIM_EVIDENCE_RULES
        + _CONFIDENCE_RULE
        + _UNSOURCED_CLAIM.format(empty_fields=', "" in allen evidence-Feldern')
        + _multi_area_rules(p, "sections.unsicherheiten")
        + _NO_INVENTION
        + "\n"
        + _NO_COMPUTATION
        + "\n</regeln_claims>\n\n"
        "<regeln_abschnitte>\n"
        "- Schreibe für Personen ohne juristische Vorbildung: kurze Sätze, Fachbegriffe "
        "beim ersten Auftreten erklärt.\n"
        "- sachverhalt: nur Angaben aus dem Dokument; unklare Angaben als unklar "
        "kennzeichnen.\n"
        "- rechtliche_wuerdigung: nur Aussagen belegter Claims; jede Norm einzeln als "
        "„§ X Abs. Y Satz Z Gesetz“ (nur vorhandene Teile) in Klammern hinter der Aussage, "
        "kein „§§“.\n"
        + _RESULT_RULE.format(categories=_categories(p))
        + "- handlungsempfehlung: nummerierte Schritte; jeder folgt aus einem Claim oder "
        "einer Angabe des Dokuments (z. B. Rechtsbehelfsbelehrung).\n"
        + _DRAFT_RULE
        + "- unsicherheiten: nicht belegbare Fragen, fehlende Angaben, gekürzte Eingaben.\n"
        "- adversarial_pruefung: höchstens 3 Sätze zu den stärksten Gegenargumenten; wird "
        "durch eine nachgelagerte Prüfung ersetzt.\n"
        "</regeln_abschnitte>\n\n"
        "<ausgabeformat>\n"
        "{\n"
        '  "claims": [\n'
        "    {\n"
        '      "claim_text": "...",\n'
        '      "confidence_score": 0.6,\n'
        '      "claim_type": "interpretation",\n'
        '      "question": "...",\n'
        '      "evidence_chunk_id": "...",\n'
        f'      "evidence_hierarchy": "{p["hierarchy_example"]}",\n'
        '      "evidence_quote": "..."\n'
        "    }\n"
        "  ],\n"
        '  "sections": {\n'
        '    "sachverhalt": "...",\n'
        '    "rechtliche_wuerdigung": "...",\n'
        '    "ergebnis": "Vorläufige Einordnung: ... .",\n'
        '    "handlungsempfehlung": "1. ...",\n'
        '    "entwurf": "...",\n'
        '    "unsicherheiten": "...",\n'
        '    "adversarial_pruefung": "..."\n'
        "  }\n"
        "}\n\n" + _JSON_OBJECT_ONLY + "\n</ausgabeformat>"
    )


def _render_adversarial_review(p: _Slots) -> str:
    return (
        "<rolle>\n"
        f"Du bist Experte für {p['display_name']} und prüfst die Claims einer "
        "automatisierten Voranalyse kritisch. Du arbeitest für die Person, an die das "
        "Dokument gerichtet ist: Sie soll die Schwächen ihrer Position kennen, bevor sie "
        "antwortet. Verteidige die Claims nicht.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        "Die Nutzernachricht enthält „## DOKUMENT“, „## IDENTIFIZIERTE THEMEN“, "
        "„## RECHTSFRAGEN“, „## RECHTSQUELLEN (CHUNKS)“ wie die Voranalyse und „## CLAIMS“: "
        "Zeilen „[i] (claim_type, confidence, Prüfstatus) claim_text“ mit Beleg "
        "„CHUNK [chunk_id] Hierarchie: Zitat“. Prüfstatus „unverifiziert“ heißt: Das Zitat "
        "steht nicht im Chunk.\n"
        "</eingaben>\n\n"
        "<aufgabe>\n"
        "Erstelle für jeden Claim genau einen Eintrag in reviews:\n"
        "- defense_argument: Sicht der betroffenen Person – Fehler der Gegenseite, "
        "Schutzvorschriften, stützende Angaben des Dokuments.\n"
        f"- authority_argument: Sicht der Gegenseite (z. B. {p['adversary_examples']}) – "
        "stärkstes Gegenargument mit Rechtsgrundlage aus den Chunks, Ermessens- oder "
        "Beurteilungsspielraum.\n"
        "- judicial_assessment: neutrale Sicht – Ist der Claim belegt? Ist die Rechtslage "
        "eindeutig? Erfolgsaussicht qualitativ, ohne Garantie.\n"
        f"- procedural_issues: Verfahrensfragen (z. B. {p['formal_examples']}).\n"
        "- risk_level, recommended_strategy: nach den Regeln.\n"
        "Fasse danach alle Claims in overall_assessment zusammen.\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- Argumentiere nur mit Dokument, Claims und Chunks.\n"
        "- claim_index: die Zahl i aus „## CLAIMS“; ein Eintrag pro Claim, aufsteigend.\n"
        '- risk_level (Risiko, dass die Position aus dem Claim nicht trägt): "hoch", wenn '
        "der Claim unverifiziert oder nicht belegbar ist oder ein belegtes Gegenargument "
        'ihn entkräftet; "mittel", wenn Auslegung oder fehlende Tatsachen entscheiden; '
        'sonst "niedrig".\n'
        "- recommended_strategy: ein konkreter Schritt der betroffenen Person.\n"
        "- Jedes Textfeld in reviews höchstens 2 Sätze.\n"
        "- Formuliere die Gegenseite so stark, wie die Quellen es zulassen; übertreibe keine "
        "Erfolgsaussicht.\n"
        "- procedural_errors_found: nur Fehler, die das Dokument selbst zeigt; mögliche "
        "Fehler gehören in procedural_issues oder key_risks.\n"
        "- key_risks: 3 bis 5; recommended_next_steps: 3 bis 5 Schritte der betroffenen "
        "Person; summary: höchstens 4 Sätze.\n"
        '- confidence_in_defense (0.0–1.0): über 0.7 nur, wenn die meisten Claims "niedrig" '
        'sind; unter 0.3, wenn die meisten "hoch" sind.\n'
        "- Schreibe nicht in der Ich-Form einer Anwältin oder eines Anwalts.\n"
        + _multi_area_rules(p, "overall_assessment.key_risks")
        + _NO_INVENTION
        + "\n"
        + _NO_COMPUTATION
        + "\n</regeln>\n\n"
        "<ausgabeformat>\n"
        "{\n"
        '  "reviews": [\n'
        "    {\n"
        '      "claim_index": 0,\n'
        '      "defense_argument": "...",\n'
        '      "authority_argument": "...",\n'
        '      "judicial_assessment": "...",\n'
        '      "procedural_issues": "...",\n'
        '      "risk_level": "mittel",\n'
        '      "recommended_strategy": "..."\n'
        "    }\n"
        "  ],\n"
        '  "overall_assessment": {\n'
        '    "summary": "...",\n'
        '    "key_risks": ["..."],\n'
        '    "recommended_next_steps": ["..."],\n'
        '    "confidence_in_defense": 0.5,\n'
        '    "procedural_errors_found": []\n'
        "  }\n"
        "}\n\n" + _JSON_OBJECT_ONLY + "\n</ausgabeformat>"
    )


def _render_claim_construction(p: _Slots) -> str:
    return (
        "<rolle>\n"
        f"Du bist Experte für {p['display_name']} ({p['statutes']}). Du arbeitest "
        "evidenzgebunden für die Person, an die das zugrunde liegende Dokument gerichtet "
        "ist.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        "Die Nutzernachricht enthält eine Liste von Rechtsfragen und danach Rechtsquellen "
        "als Blöcke „[Hierarchie]: Text“, getrennt durch „---“. Der Quellenteil kann am "
        "Ende gekürzt sein. Das Dokument selbst erhältst du nicht.\n"
        "</eingaben>\n\n"
        "<aufgabe>\n"
        "Beantworte jede Rechtsfrage mit 1 oder 2 Claims. Ein Claim ist eine einzelne "
        "prüfbare Aussage.\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- claim_text nennt die tragende Vorschrift („nach § X Abs. Y Gesetz“), wie sie in "
        "der Hierarchie der Quelle steht.\n"
        '- claim_type: "interpretation" oder "recommendation"; "fact" nicht verwenden, '
        "weil dir das Dokument fehlt.\n"
        "- question: die Rechtsfrage wörtlich.\n"
        + _CONFIDENCE_RULE
        + _UNSOURCED_CLAIM.format(empty_fields="")
        + _multi_area_rules(p, "einem eigenen Claim")
        + _NO_INVENTION
        + "\n</regeln>\n\n"
        "<ausgabeformat>\n"
        '[ { "claim_text": "...", "confidence_score": 0.6, "claim_type": "interpretation", '
        '"question": "..." } ]\n\n' + _JSON_ARRAY_ONLY + "\n</ausgabeformat>"
    )


def _render_verification(p: _Slots) -> str:
    return (
        "<rolle>\n"
        f"Du bist Experte für {p['display_name']} und prüfst unabhängig, ob "
        "Rechtsquellen die Claims einer automatisierten Voranalyse tragen.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        "Die Nutzernachricht enthält nummerierte Claims „n. [claim_type] claim_text“ und "
        "danach Rechtsquellen als Blöcke „[Hierarchie]: Text“. Der Quellenteil kann am Ende "
        "gekürzt sein.\n"
        "</eingaben>\n\n"
        "<aufgabe>\n"
        "Prüfe für jeden Claim, ob eine Quelle die Aussage ausdrücklich trägt.\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- Genau ein Element pro Claim, in derselben Reihenfolge.\n"
        "- claim_text und claim_type unverändert übernehmen.\n"
        "- verified true nur, wenn eine Quelle die gesamte Aussage ausdrücklich trägt; "
        "Plausibilität genügt nicht. Trägt sie nur einen Teil: verified false.\n"
        "- confidence_score: wie vollständig die Quelle den Claim trägt; bei verified false "
        "höchstens 0.4.\n"
        "- reasoning: ein Satz; nennt die tragende Hierarchie oder den nicht getragenen "
        "Teil.\n"
        "- Erfinde keine Quellen, Normen oder Tatsachen.\n"
        + _multi_area_rules(p, "reasoning")
        + "</regeln>\n\n"
        "<ausgabeformat>\n"
        '[ { "claim_text": "...", "confidence_score": 0.4, "claim_type": "interpretation", '
        '"verified": false, "reasoning": "..." } ]\n\n' + _JSON_ARRAY_ONLY + "\n</ausgabeformat>"
    )


def _render_output(p: _Slots) -> str:
    return (
        "<rolle>\n"
        f"Du bist Experte für {p['display_name']}. Du fasst geprüfte Claims für die Person "
        "zusammen, an die das zugrunde liegende Dokument gerichtet ist. Du gibst keine "
        "Rechtsberatung.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        "Die Nutzernachricht enthält Zeilen „- [claim_type] (verified=…, confidence=…) "
        "claim_text“. Dokument und Rechtsquellen erhältst du nicht.\n"
        "</eingaben>\n\n"
        "<aufgabe>\n"
        "Schreibe die sechs Abschnitte nur auf Grundlage der Claims.\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- Claims mit verified=False erscheinen nur in unsicherheiten.\n"
        "- sachverhalt: nur Tatsachen, die in den Claims stehen; sonst „im Dokument nicht "
        "angegeben“.\n"
        "- rechtliche_wuerdigung: nur Normen, die in den Claims stehen, jede einzeln als "
        "„§ X Abs. Y Satz Z Gesetz“ (nur vorhandene Teile) in Klammern hinter der "
        "Aussage.\n"
        + _RESULT_RULE.format(categories=_categories(p))
        + "- handlungsempfehlung: nummerierte Schritte, jeder aus einem Claim.\n"
        + _DRAFT_RULE
        + "- unsicherheiten: nicht verifizierte Claims und fehlende Angaben.\n"
        + _multi_area_rules(p, "unsicherheiten")
        + _NO_INVENTION
        + "\n"
        + _NO_COMPUTATION
        + "\n</regeln>\n\n"
        "<ausgabeformat>\n"
        '{ "sachverhalt": "...", "rechtliche_wuerdigung": "...", "ergebnis": '
        '"Vorläufige Einordnung: ... .", "handlungsempfehlung": "1. ...", "entwurf": "...", '
        '"unsicherheiten": "..." }\n\n' + _JSON_OBJECT_ONLY + "\n</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# Chat prompts P-11 / P-12 (CR-05, F-05): rendered from the area profile
# ---------------------------------------------------------------------------

_CHAT_COMMON_RULES = (
    "- Antworte auf Deutsch, kurz und in Alltagssprache; erkläre Fachbegriffe.\n"
    "- Trenne erkennbar: was im Dokument steht, was die Quellen dazu sagen, was offen "
    "bleibt.\n"
    "- Belege jede Rechtsaussage mit einer bereitgestellten Quelle und nenne die Norm als "
    "„§ X Abs. Y Satz Z Gesetz“. Kennzeichne Aussagen ohne solchen Beleg mit „(ohne "
    "Quellenbeleg)“.\n"
    "- Fehlt eine Angabe für die Antwort, nenne sie konkret.\n"
    "- Stelle Vermutungen nicht als Tatsachen dar; versprich kein Ergebnis.\n"
    + _NO_COMPUTATION
    + "\n"
    "- Bei drohendem Fristablauf oder hohem Risiko: empfiehl fachkundige Beratung "
    "(Beratungsstelle, Rechtsanwalt).\n"
)


def _chat_role(p: _Slots, what: str) -> str:
    return (
        "<rolle>\n"
        f"Du bist ein Assistent für {p['display_name']} ({p['statutes']}). Du hilfst einer "
        f"Person, {what}, damit sie ihre eigene Antwort vorbereiten kann. Du gibst keine "
        "Rechtsberatung und vertrittst niemanden.\n"
        "</rolle>\n\n"
    )


def _render_chat(p: _Slots) -> str:
    return (
        _chat_role(p, "an sie gerichtete Schreiben zu verstehen") + "<eingaben>\n"
        "Auf diese Anweisungen können folgen: „Dem Nutzer liegen folgende Dokumente vor:“ "
        "(ggf. gekürzt) und „Relevante Rechtsquellen aus dem lokalen Corpus:“ (Blöcke "
        "„[Chunk n] Hierarchie“). Danach folgt der Gesprächsverlauf.\n"
        "</eingaben>\n\n"
        "<regeln>\n"
        + _CHAT_COMMON_RULES
        + "- Nenne bei Rechtsaussagen den Block („[Chunk n]“). Zitiere wörtlich nur kurze "
        "Stellen.\n"
        f"- Betrifft eine Frage ein anderes Rechtsgebiet als {p['display_name']}, sage, "
        "dass dafür hier keine Quellen bereitstehen.\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "Kurze Absätze, höchstens etwa 250 Wörter; Aufzählung nur für Schritte.\n"
        "</ausgabeformat>"
    )


def _render_case_chat(p: _Slots) -> str:
    return (
        _chat_role(
            p,
            "die Ergebnisse einer automatisierten Analyse ihres Falls zu verstehen und "
            "zu hinterfragen",
        )
        + "<eingaben>\n"
        "Auf diese Anweisungen folgen Auszüge der Analyse (Abschnitte wie Sachverhalt, "
        "rechtliche Würdigung, Ergebnis, adversariale Prüfung, Berechnungsprüfung), ggf. "
        "Korrekturen der Person, ihre Bewertungen einzelner Claims und die Claims. Der "
        "Kontext kann gekürzt sein. Danach folgt der Gesprächsverlauf.\n"
        "</eingaben>\n\n"
        "<regeln>\n"
        "- Antworte auf Deutsch, kurz und in Alltagssprache; erkläre Fachbegriffe.\n"
        "- Stütze jede Aussage auf die Analyse und nenne den Abschnitt („laut rechtlicher "
        "Würdigung“). Kennzeichne Rechtsaussagen ohne Grundlage in der Analyse mit „(ohne "
        "Quellenbeleg)“. Normen nur aus der Analyse, als „§ X Abs. Y Satz Z Gesetz“.\n"
        "- Korrekturen der Person ersetzen die betroffenen Angaben; Rechtsaussagen darin "
        "sind ihr Vortrag und unbelegt.\n"
        "- Nenne Risiken der adversarialen Prüfung und Abweichungen der Berechnungsprüfung, "
        "wenn sie die Frage betreffen.\n"
        "- Fehlt ein Abschnitt oder ist er gekürzt, sage das.\n"
        "- Stelle Vermutungen nicht als Tatsachen dar; versprich kein Ergebnis.\n"
        + _NO_COMPUTATION
        + "\n"
        "- Bei drohendem Fristablauf oder hohem Risiko: empfiehl fachkundige Beratung "
        "(Beratungsstelle, Rechtsanwalt).\n"
        "- Wünscht die Person eine vertiefte Prüfung, schlage eine Neuauswertung des "
        "betreffenden Abschnitts vor.\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "Kurze Absätze, höchstens etwa 250 Wörter; Aufzählung nur für Schritte.\n"
        "</ausgabeformat>"
    )


_CHAT_RENDERERS = {"chat": _render_chat, "case_chat": _render_case_chat}


# ---------------------------------------------------------------------------
# Stage builders (profile → system prompt)
# ---------------------------------------------------------------------------


def _build_classification(profile: AreaProfile) -> str:
    return _render_classification(_slots(profile))


def _build_decomposition(profile: AreaProfile) -> str:
    return _render_decomposition(_slots(profile))


def _build_triage(profile: AreaProfile) -> str:
    return _render_triage(_slots(profile))


def _build_grounded_answer(profile: AreaProfile) -> str:
    return _render_grounded_answer(_slots(profile))


def _build_adversarial_review(profile: AreaProfile) -> str:
    return _render_adversarial_review(_slots(profile))


def _build_claim_construction(profile: AreaProfile) -> str:
    return _render_claim_construction(_slots(profile))


def _build_verification(profile: AreaProfile) -> str:
    return _render_verification(_slots(profile))


def _build_output(profile: AreaProfile) -> str:
    return _render_output(_slots(profile))


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
    The merged profile carries ``is_multi_area=True``; ``_multi_area_rules``
    keys on that flag (CR-10) and injects cross-area guidance with a
    stage-specific field for conflicts (F-15).
    """
    merged_terms: list[str] = []
    merged_categories: list[str] = []
    for prof in profiles:
        for term in prof.issue_terms:
            if term not in merged_terms:
                merged_terms.append(term)
        for category in prof.result_categories:
            if category not in merged_categories:
                merged_categories.append(category)

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
        result_categories=tuple(merged_categories),
        is_multi_area=True,
    )


# ---------------------------------------------------------------------------
# Registry — area key → profile (module data, WP-93)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _profile_registry() -> dict[str, AreaProfile]:
    """Area key → profile, from the modules owning each key.

    Keys sharing one module profile (a legacy alias, or a stub that
    inherits another module's profile) map to the *same* object, so the
    multi-area composer collapses them exactly as v2.0.0 did.
    """
    from app.modules.areas import area_tables

    tables = area_tables()
    by_module: dict[str, AreaProfile] = {
        module_id: profile_from_mapping(data) for module_id, data in tables.module_profiles.items()
    }
    return {key: by_module[str(data["key"])] for key, data in tables.prompt_profiles.items()}


class ModuleSelectionRequired(ValueError):
    """Legal inference needs an explicit scope with a usable module profile."""


SELECTION_REQUIRED_TEXT = (
    "Bitte wählen Sie ein verfügbares Rechtsmodul mit Analyseprofil aus. "
    "Ohne diese Auswahl wird keine rechtliche Analyse oder KI-Antwort erstellt."
)


def require_inference_scope(legal_areas: list[str] | None) -> None:
    """Validate availability and profiles before retrieval or inference (D-070)."""
    from app.modules.runtime import resolve_request_areas

    resolve_request_areas(list(legal_areas or []))
    if not legal_areas or not _resolve_profiles(legal_areas):
        raise ModuleSelectionRequired(SELECTION_REQUIRED_TEXT)


# ---------------------------------------------------------------------------
# Multi-area prompt composer
# ---------------------------------------------------------------------------


@lru_cache(maxsize=32)
def _cached_multi_area_set(profile_keys: tuple[str, ...]) -> dict[str, str]:
    registry = _profile_registry()
    by_key = {prof.key: prof for prof in registry.values()}
    profiles = [by_key[key] for key in profile_keys]
    return _build_prompt_set(_merge_profiles(profiles))


# Public-facing combined-area lookup, used by the pipeline.
def get_prompts(legal_areas: list[str] | None = None) -> dict[str, str]:
    """Return the prompt set appropriate for a case covering *legal_areas*.

    Parameters
    ----------
    legal_areas :
        Explicit area keys. Empty/unknown scope or a module without a profile
        raises ``ModuleSelectionRequired``; no other module is borrowed.

    Returns
    -------
    dict[str, str]
        Mapping of stage name to system prompt. Keys:
        ``classification``, ``decomposition``, ``triage``,
        ``grounded_answer``, ``adversarial_review``,
        ``claim_construction``, ``verification``, ``output``.
    """
    profiles = _resolve_profiles(legal_areas)
    if not profiles:
        raise ModuleSelectionRequired(SELECTION_REQUIRED_TEXT)
    if len(profiles) == 1:
        return dict(_build_prompt_set(profiles[0]))
    return dict(_cached_multi_area_set(tuple(prof.key for prof in profiles)))


def _resolve_profiles(legal_areas: list[str] | None) -> list[AreaProfile]:
    """Unique profiles of *legal_areas*, in request order (empty: none known).

    Keys sharing a module profile collapse onto it.
    """
    from app.modules.areas import PROCEDURAL_OWNER, area_tables

    registry = _profile_registry()

    owners = area_tables().owner
    unique_profiles: list[AreaProfile] = []
    for area in legal_areas or []:
        profile = registry.get(area)
        if profile is None and owners.get(area) != PROCEDURAL_OWNER:
            raise ModuleSelectionRequired(SELECTION_REQUIRED_TEXT)
        if profile is not None and profile not in unique_profiles:
            unique_profiles.append(profile)
    return unique_profiles


def get_chat_prompt(kind: str, legal_areas: list[str] | None = None) -> str:
    """System prompt of a chat surface (``"chat"`` P-11, ``"case_chat"`` P-12).

    Area resolution follows :func:`get_prompts`; absent/unusable profiles
    raise ``ModuleSelectionRequired`` before legal inference.
    """
    profiles = _resolve_profiles(legal_areas)
    if not profiles:
        raise ModuleSelectionRequired(SELECTION_REQUIRED_TEXT)
    elif len(profiles) == 1:
        profile = profiles[0]
    else:
        profile = _merge_profiles(profiles)
    return _CHAT_RENDERERS[kind](_slots(profile))
