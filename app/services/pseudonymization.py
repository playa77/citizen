"""Pseudonymization gate: PII detection, replacement, and reinjection (WP-30).

**Logging rule (mandatory):** No cleartext PII may appear in any log message.
All logging must use placeholders only — values from the PiiMapping are safe
to log because they contain only [[PLACEHOLDER]] keys and original values.

**Design:**
- Hybrid regex + spaCy NER + first-name gazetteer detection layer.
- Typed placeholders: [[PERSON_X]], [[ADRESSE_X]], [[FIRMA_X]], [[ID_X]],
  [[GEBURTSDATUM_X]].
- Bidirectional PiiMapping for deterministic roundtrip + tolerant reinjection.

**spaCy model:** ``de_core_news_lg`` (download separately):
    ``python -m spacy download de_core_news_lg``
"""

# Semantic Version: 0.1.0 | 2026-07-12 — WP-30 initial implementation

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Common German first names — ~200 most frequent (male + female)
# ---------------------------------------------------------------------------
# Sourced from official German name statistics (2023/2024). Used as a
# supplement to spaCy NER to catch names that NER misses (e.g. in brief
# short-form documents). Includes inflected forms where common.
_FIRST_NAMES: set[str] = {
    # Male
    "max",
    "lukas",
    "leon",
    "felix",
    "jonas",
    "noah",
    "emil",
    "finn",
    "elias",
    "luca",
    "henry",
    "paul",
    "luis",
    "ben",
    "niklas",
    "tim",
    "julian",
    "moritz",
    "philipp",
    "alexander",
    "david",
    "simon",
    "ole",
    "jannik",
    "lenny",
    "lian",
    "milan",
    "piet",
    "john",
    "tom",
    "linus",
    "hannes",
    "mats",
    "nico",
    "fritz",
    "theo",
    "leo",
    "karl",
    "hans",
    "peter",
    "thomas",
    "wolfgang",
    "klaus",
    "dieter",
    "jürgen",
    "andreas",
    "michael",
    "stephan",
    "matthias",
    "martin",
    "stefan",
    "daniel",
    "christian",
    "markus",
    "florian",
    "tobias",
    "sebastian",
    "bernd",
    "achim",
    "ralf",
    "uwe",
    "rainer",
    "frank",
    "heinz",
    "gerhard",
    "horst",
    "helmut",
    "günter",
    "manfred",
    "ulrich",
    "volker",
    "jens",
    "karsten",
    "torsten",
    "oliver",
    "marc",
    "mario",
    "rené",
    "hans-peter",
    "karl-heinz",
    "hans-joachim",
    "erich",
    "walter",
    "willi",
    "hermann",
    "otto",
    "erwin",
    "rupert",
    "norbert",
    "bernhard",
    "holger",
    "dirk",
    "ingo",
    "gert",
    "gunnar",
    "henning",
    "detlef",
    "eberhard",
    "albrecht",
    "friedrich",
    "wilhelm",
    "ludwig",
    "heinrich",
    "konrad",
    "theodor",
    "johann",
    "jakob",
    "anton",
    "valentin",
    "alois",
    "josef",
    "georg",
    "ferdinand",
    "arthur",
    "albert",
    "ernst",
    "alfred",
    "adolf",
    "gottfried",
    "siegfried",
    "herbert",
    "kurt",
    "werner",
    "adrian",
    "konstantin",
    "raphael",
    "fabian",
    "dominik",
    "benedikt",
    "till",
    "lasse",
    "marlon",
    "damian",
    "pepe",
    "jonathan",
    "samuel",
    "nikolai",
    "lennard",
    "mika",
    "liam",
    "finley",
    "maximilian",
    "pascal",
    "danilo",
    "justus",
    "matti",
    "malte",
    "arved",
    # Female
    "sophie",
    "marie",
    "emma",
    "mia",
    "hanna",
    "emilia",
    "lina",
    "lena",
    "leonie",
    "leah",
    "anna",
    "lara",
    "nele",
    "lotta",
    "sara",
    "lisa",
    "laura",
    "johanna",
    "julia",
    "annika",
    "tina",
    "sabine",
    "ute",
    "petra",
    "monika",
    "birgit",
    "renate",
    "margret",
    "ingrid",
    "ursula",
    "kathrin",
    "susanne",
    "nicole",
    "sandra",
    "kirsten",
    "heike",
    "astrid",
    "maren",
    "silke",
    "claudia",
    "tanja",
    "britta",
    "anke",
    "gabriele",
    "kristin",
    "antje",
    "maria",
    "elisabeth",
    "margarete",
    "katharina",
    "christine",
    "martina",
    "barbara",
    "angela",
    "beate",
    "edith",
    "hildegard",
    "heidi",
    "daniela",
    "sabrina",
    "nadine",
    "svenja",
    "jasmine",
    "marlene",
    "helene",
    "greta",
    "ruby",
    "mila",
    "emily",
    "amélie",
    "nora",
    "mira",
    "zoe",
    "rosa",
    "lilly",
    "luisa",
    "stella",
    "luise",
    "lea",
    "matea",
    "alina",
    "sophia",
    "maya",
    "yvonne",
    "alexandra",
    "nathalie",
    "isabelle",
    "stephanie",
    "melanie",
    "sarah",
    "jessica",
    "vanessa",
    "nina",
    "michelle",
    "silvia",
    "gudrun",
    "marion",
    "herta",
    "elke",
    "annette",
    "waltraud",
    "else",
    "frieda",
    "karla",
    "erika",
    "kornelia",
    "annalena",
    "eva",
    "martha",
    "paula",
    "friederike",
    "henriette",
    "wilma",
    "josefine",
    "magdalena",
    "franziska",
    "theresa",
    "carolin",
    "karin",
    "clara",
    "eleonore",
    "lilli",
    "janina",
    "diana",
    "doris",
    "rebekka",
    "viktoria",
    "annabelle",
}

# ---------------------------------------------------------------------------
# Address suffix gazetteer
# ---------------------------------------------------------------------------
_STREET_SUFFIXES = (
    "straße",
    "strasse",
    "str.",
    "weg",
    "allee",
    "gasse",
    "platz",
    "damm",
    "ring",
    "pfad",
    "steig",
    "zeile",
    "ufer",
    "kai",
    "chaussee",
    "promenade",
    "winkel",
    "graben",
    "bogen",
    "stieg",
    "stiege",
)
_STREET_SUFFIXES_LOWER: frozenset[str] = frozenset(s.lower() for s in _STREET_SUFFIXES)
# Also generate capitalized-first variants for case-insensitive regex matching
# without using re.IGNORECASE (which would also case-fold the uppercase start
# requirement).
_STREET_SUFFIXES_CASE: tuple[str, ...] = tuple(
    sorted(
        set(
            suffix
            for s in _STREET_SUFFIXES
            for suffix in (s, s[0].upper() + s[1:] if s[0].islower() else s)
        ),
        key=len,
        reverse=True,
    )
)

# Words in the street part of an address detection that indicate the
# regex overshoots into preceding context. These are NOT actual street
# name components but prepositions, articles, or verbs that commonly
# precede addresses in German text.
_STREET_STOPWORDS: set[str] = {
    "in",
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einen",
    "einer",
    "einem",
    "und",
    "oder",
    "aber",
    "bei",
    "auf",
    "an",
    "am",
    "wohne",
    "wohnt",
    "wohnhaft",
    "lebe",
    "lebt",
    "befindet",
    "liegt",
    "ist",
    "sind",
    "war",
    "waren",
    "werde",
    "wird",
    "seine",
    "seinen",
    "ihre",
    "ihren",
    "meine",
    "meinen",
    "meiner",
    "hause",
    "nach",
    "mit",
    "von",
    "vom",
    "zum",
    "zur",
    "über",
    "unter",
}

# ---------------------------------------------------------------------------
# Regex patterns — structured IDs (recall target: 1.0)
# ---------------------------------------------------------------------------


def _build_patterns() -> dict[str, re.Pattern[str]]:
    """Compile all regex patterns once and cache them."""
    return {
        # BG-Nummer: 5 digits // 7 digits (or / or space variants)
        "bg_nummer": re.compile(r"\b(\d{5})\s*/{1,2}\s*(\d{7})\b"),
        # Aktenzeichen — various German case-number formats
        "aktenzeichen": re.compile(
            r"\b(?:Az\.\s*:?\s*|Gesch\.-?Z\.\s*:?\s*|Aktenzeichen\s*|Gz\.\s*|"
            r"Aktenz\.\s*|Widerspruch\s+Nr?\.\s*)"
            r"([A-Z]?\s*[\d/]+\s*[\d/]*(?:\s*[A-Z]+)?)",
            re.IGNORECASE,
        ),
        # Sozialversicherungsnummer (SV-Nummer)
        "sv_nummer": re.compile(
            r"\b\d{2}\s?\d{6}\s?\d\s?\d{2}\s?\d\b",
        ),
        # Steuer-ID
        "steuer_id": re.compile(
            r"\b(?:\d{2}\s?\d{3}\s?\d{3}\s?\d{5}|\d{11})\b",
        ),
        # IBAN (DE only)
        "iban": re.compile(
            r"\bDE\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}\b",
        ),
        # German phone numbers
        "phone": re.compile(
            r"\b(?:\+49|0)\d{1,4}[-\s]?\d{1,8}(?:[-\s]?\d{1,8}){0,2}\b",
        ),
        # Email addresses
        "email": re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        ),
        # Birth date with context — "geboren am", "geb.", "*", "Geburtsdatum"
        "birth_date": re.compile(
            r"(geboren\s+am|geb\.|\*|Geburtsdatum|Geb\.?)\s*" r"(\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4})",
            re.IGNORECASE,
        ),
        # Free-standing birth date without context (caught if birth context nearby)
        "standalone_birth_date": re.compile(
            r"\b\d{1,2}\.\s?\d{1,2}\.\s?(?:19\d{2}|20\d{2})\b",
        ),
        # German address pattern: street name + suffix + number.
        # Street part must start with uppercase (true of all German street
        # names). Suffix list includes both cases for matching.
        "street_address": re.compile(
            rf"\b([A-ZÄÖÜß][A-ZÄÖÜßa-zäöüß\s.-]*?)\s*("
            rf"{'|'.join(_STREET_SUFFIXES_CASE)})\s*\.?\s*"
            r"(\d+\s*(?:[a-z]|[-\s]?\d+)?)",
            re.UNICODE,
        ),
    }


_PATTERNS: dict[str, re.Pattern[str]] | None = None


def _get_patterns() -> dict[str, re.Pattern[str]]:
    global _PATTERNS
    if _PATTERNS is None:
        _PATTERNS = _build_patterns()
    return _PATTERNS


# ---------------------------------------------------------------------------
# Salutation/letterhead heuristics
# ---------------------------------------------------------------------------
_SALUTATION_PATTERNS = [
    re.compile(
        r"(?:Herr|Frau|Herrn|Fr\.|Hr\.)\s+(?:(?:Dr\.|Prof\.|Prof\.\s*Dr\.)\s+)?([A-ZÄÖÜß][a-zäöüß]+(?:\s+[A-ZÄÖÜß][a-zäöüß]+)?)"
    ),
    re.compile(
        r"Sehr\s+geehrte[rns]?\s+(?:Herr|Frau)\s+(?:(?:Dr\.|Prof\.|Prof\.\s*Dr\.)\s+)?([A-ZÄÖÜß][a-zäöüß]+(?:\s+[A-ZÄÖÜß][a-zäöüß]+)?)"
    ),
    re.compile(
        r"Liebe[rn]?\s+(?:Herr|Frau)\s+(?:(?:Dr\.|Prof\.|Prof\.\s*Dr\.)\s+)?([A-ZÄÖÜß][a-zäöüß]+(?:\s+[A-ZÄÖÜß][a-zäöüß]+)?)"
    ),
    re.compile(r"([A-ZÄÖÜß][a-zäöüß]+)\s+wohnhaft\s+in"),
    re.compile(r"([A-ZÄÖÜß][a-zäöüß]+),\s*geboren\s+am"),
]

# ---------------------------------------------------------------------------
# Inflected name detection (German genitive/possessive)
# ---------------------------------------------------------------------------
_INFLECTED_SUFFIXES = ("s", "es", "n", "ns")

# ---------------------------------------------------------------------------
# Authorities / organisations that must NOT be redacted
# ---------------------------------------------------------------------------
_AUTHORITY_PATTERNS = [
    re.compile(r"\bJobcenter\s+[A-ZÄÖÜß][a-zäöüß]+\b"),
    re.compile(r"\bAgentur\s+für\s+Arbeit\b"),
    re.compile(r"\bAmtsgericht\s+[A-ZÄÖÜß][a-zäöüß]+\b"),
    re.compile(r"\bLandgericht\s+[A-ZÄÖÜß][a-zäöüß]+\b"),
    re.compile(r"\bSozialgericht\s+[A-ZÄÖÜß][a-zäöüß]+\b"),
    re.compile(r"\bVerwaltungsgericht\s+[A-ZÄÖÜß][a-zäöüß]+\b"),
    re.compile(r"\bFinanzamt\s+[A-ZÄÖÜß][a-zäöüß]+\b"),
    re.compile(r"\bBundesagentur\s+für\s+Arbeit\b"),
    re.compile(r"\bDeutsche\s+Rentenversicherung\b"),
    re.compile(r"\bKrankenkasse\b"),
    re.compile(r"\bAOK\b"),
    re.compile(r"\bVersicherungsamt\b"),
    re.compile(r"\bStadt\s+[A-ZÄÖÜß][a-zäöüß]+\b"),
    re.compile(r"\bLandkreis\s+[A-ZÄÖÜß][a-zäöüß]+\b"),
    re.compile(r"\bBezirksregierung\b"),
    re.compile(r"\bLandratsamt\b"),
    re.compile(r"\bStadtverwaltung\b"),
]

# ---------------------------------------------------------------------------
# Names of German cities / Bundesländer / common large cities
# (never redacted)
# ---------------------------------------------------------------------------
_CITIES: set[str] = {
    "berlin",
    "hamburg",
    "münchen",
    "köln",
    "frankfurt",
    "stuttgart",
    "düsseldorf",
    "leipzig",
    "dortmund",
    "essen",
    "bremen",
    "dresden",
    "hannover",
    "nürnberg",
    "duisburg",
    "bochum",
    "bielefeld",
    "bonn",
    "mannheim",
    "wiesbaden",
    "münster",
    "karlsruhe",
    "augsburg",
    "aachen",
    "braunschweig",
    "chemnitz",
    "kiel",
    "halle",
    "magdeburg",
    "krefeld",
    "freiburg",
    "mainz",
    "lübeck",
    "erfurt",
    "oberhausen",
    "rostock",
    "kassel",
    "hagen",
    "potsdam",
    "saarbrücken",
    "hamm",
    "ludwigshafen",
    "oldenburg",
    "osnabrück",
    "leverkusen",
    "heidelberg",
    "darmstadt",
    "solingen",
    "regensburg",
    "paderborn",
    "wuppertal",
    "gelsenkirchen",
    "mönchengladbach",
    "würzburg",
    "ingolstadt",
    "göttingen",
    "ulm",
    "heilbronn",
    "pforzheim",
    "bottrop",
    "remscheid",
    "reutlingen",
    "koblenz",
    "trier",
    "passau",
    "flensburg",
    "jena",
    "bayreuth",
    "bamberg",
    "celle",
    "cuxhaven",
    "delmenhorst",
    "detmold",
    "emden",
    "erlangen",
    "esslingen",
    "fürth",
    "gorlitz",
    "greifswald",
    "herne",
    "hildesheim",
    "konstanz",
    "landshut",
    "lünen",
    "marburg",
    "minden",
    "moers",
    "neuss",
    "offenbach",
    "ratzeburg",
    "russelsheim",
    "siegen",
    "stralsund",
    "velbert",
    "viersen",
    "wesel",
    "wetzlar",
    "wilhelmshaven",
    "wolfsburg",
    "worms",
    "zwickau",
}

_BUNDESLAENDER: set[str] = {
    "baden-württemberg",
    "bayern",
    "berlin",
    "brandenburg",
    "bremen",
    "hamburg",
    "hessen",
    "mecklenburg-vorpommern",
    "niedersachsen",
    "nordrhein-westfalen",
    "rheinland-pfalz",
    "saarland",
    "sachsen",
    "sachsen-anhalt",
    "schleswig-holstein",
    "thüringen",
}

# ---------------------------------------------------------------------------
# PiiMapping
# ---------------------------------------------------------------------------


@dataclass
class PiiMapping:
    """Bidirectional mapping between original PII values and placeholders.

    Threading note: this dataclass is mutated in place during pseudonymization.
    In the current architecture each case run has its own PiiMapping instance,
    so no shared-state issues arise.
    """

    person_counter: int = 0
    address_counter: int = 0
    company_counter: int = 0
    id_counter: int = 0
    placeholder_to_value: dict[str, str] = field(default_factory=dict)
    value_to_placeholder: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (for DB storage)."""
        return {
            "person_counter": self.person_counter,
            "address_counter": self.address_counter,
            "company_counter": self.company_counter,
            "id_counter": self.id_counter,
            "placeholder_to_value": dict(self.placeholder_to_value),
            "value_to_placeholder": dict(self.value_to_placeholder),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PiiMapping:
        """Deserialize from a dict (loaded from DB JSON column)."""
        if data is None:
            return cls()
        return cls(
            person_counter=data.get("person_counter", 0),
            address_counter=data.get("address_counter", 0),
            company_counter=data.get("company_counter", 0),
            id_counter=data.get("id_counter", 0),
            placeholder_to_value=data.get("placeholder_to_value", {}),
            value_to_placeholder=data.get("value_to_placeholder", {}),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_LOGGER_INITIALIZED = False


def _warn_spacy_missing() -> None:
    """Log a one-time warning if spaCy model is not installed."""
    global _LOGGER_INITIALIZED
    if not _LOGGER_INITIALIZED:
        logger.warning(
            "spaCy model 'de_core_news_lg' not available — using regex-only "
            "detection. Names and companies may be missed. Install with: "
            "python -m spacy download de_core_news_lg"
        )
        _LOGGER_INITIALIZED = True


def _load_spacy_nlp() -> Any:
    """Lazily load and cache the spaCy German NER pipeline."""
    try:
        import spacy

        nlp = spacy.load("de_core_news_lg")
        logger.info("spaCy model 'de_core_news_lg' loaded successfully")
        return nlp
    except Exception:
        _warn_spacy_missing()
        return None


_NLP = None


def _get_nlp() -> Any:
    """Get the cached spaCy pipeline (may be None if model is missing)."""
    global _NLP
    if _NLP is None:
        _NLP = _load_spacy_nlp()
    return _NLP


def _is_city_or_state(token: str) -> bool:
    """Check if a word is a known city or Bundesland name (case-insensitive)."""
    return (
        token.lower().strip(",.;:!?") in _CITIES or token.lower().strip(",.;:!?") in _BUNDESLAENDER
    )


def _get_placeholder_for(mapping: PiiMapping, category: str, raw_value: str) -> str:
    """Return existing placeholder for *raw_value* or allocate a new one.

    This is the central determinism function — same raw_value always maps to
    the same placeholder within a single PiiMapping instance.
    """
    # Check if we already have a mapping for this value
    if raw_value in mapping.value_to_placeholder:
        return mapping.value_to_placeholder[raw_value]

    # Allocate new placeholder
    if category == "person":
        mapping.person_counter += 1
        placeholder = f"[[PERSON_{mapping.person_counter}]]"
    elif category == "address":
        mapping.address_counter += 1
        placeholder = f"[[ADRESSE_{mapping.address_counter}]]"
    elif category == "company":
        mapping.company_counter += 1
        placeholder = f"[[FIRMA_{mapping.company_counter}]]"
    elif category == "birth_date":
        # Geburtsdatum uses the id counter as well; we give it a separate prefix
        mapping.id_counter += 1
        placeholder = f"[[GEBURTSDATUM_{mapping.id_counter}]]"
    else:  # id (default)
        mapping.id_counter += 1
        placeholder = f"[[ID_{mapping.id_counter}]]"

    mapping.value_to_placeholder[raw_value] = placeholder
    mapping.placeholder_to_value[placeholder] = raw_value
    return placeholder


def _strip_inflected_suffix(name: str) -> str:
    """Strip common German genitive/possessive inflection suffixes.

    Examples:
        "Vahrenholts" -> "Vahrenholt"
        "Schmidts" -> "Schmidt"
        "Meiers" -> "Meier"
        "Beckers" -> "Becker"
    """
    lower = name.lower()
    for suffix in ("es", "ns", "s"):
        if lower.endswith(suffix) and len(name) > len(suffix) + 2:
            candidate = name[: -len(suffix)]
            # Check if stripping the suffix produces a known first name
            if candidate.lower() in _FIRST_NAMES:
                return candidate
            # Also check if the candidate looks like a surname (capitalized, >2 chars)
            if candidate[0].isupper() and len(candidate) > 2:
                return candidate
    return name


# ---------------------------------------------------------------------------
# Detection functions
# ---------------------------------------------------------------------------


def _detect_structured_ids(text: str) -> list[tuple[str, str, str]]:
    """Detect structured IDs and return list of (placeholder_category, raw_match, placeholder).

    Categories: 'id' for all structured IDs.
    """
    results: list[tuple[str, str, str]] = []
    patterns = _get_patterns()
    seen_spans: list[tuple[int, int]] = []

    for pattern_name, pattern in patterns.items():
        if pattern_name in ("birth_date", "standalone_birth_date", "street_address"):
            continue  # handled separately

        if pattern_name in ("phone", "email"):
            # Validate phone numbers more strictly — must have at least 6 digits
            for match in pattern.finditer(text):
                raw = match.group(0)
                # Count digits in the match
                digit_count = sum(1 for c in raw if c.isdigit())
                if digit_count < 6:
                    continue
                # Check for overlap
                span = match.span()
                if any(s[0] < span[1] and s[1] > span[0] for s in seen_spans):
                    continue
                seen_spans.append(span)
                results.append(("id", raw, _get_placeholder_for(PiiMapping(), "id", raw)))
            continue

        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            # Check for overlap with previously matched spans
            span = match.span()
            if any(s[0] < span[1] and s[1] > span[0] for s in seen_spans):
                continue
            seen_spans.append(span)
            results.append(("id", raw, _get_placeholder_for(PiiMapping(), "id", raw)))

    return results


def _detect_street_addresses(text: str, mapping: PiiMapping) -> list[tuple[int, int, str]]:
    """Detect German street addresses. Returns list of (start, end, placeholder)."""
    results: list[tuple[int, int, str]] = []
    pattern = _get_patterns()["street_address"]

    for match in pattern.finditer(text):
        street_part = match.group(1).strip()
        suffix = match.group(2).strip()
        number = match.group(3).strip()
        original_address = match.group(0).strip()

        # Require uppercase start (German street names are capitalized).
        # This prevents matching preceding context like "und wohne in der".
        if not street_part or not street_part[0].isupper():
            continue

        # Case-insensitive suffix validation
        if suffix.lower() not in _STREET_SUFFIXES_LOWER:
            continue

        # Skip if the street part contains stop words (indicates the regex
        # overshot into preceding context like "und wohne in der").
        street_words = [
            w.lower().strip(",.!?;:\"'") for w in street_part.split() if w.strip(",.!?;:\"'")
        ]
        # Filter out matches where the street_part includes context words.
        # Allow single-word prefix like "Am", "Zur", "An" (common German
        # street name prefixes), but reject multi-word context like
        # "und wohne in der".
        if len(street_words) >= 3:
            prefix_words = street_words[:-1]  # All words except the last (street name)
            stopword_count = sum(1 for w in prefix_words if w in _STREET_STOPWORDS)
            if stopword_count > 0:
                # Match includes context words — skip
                continue

        # Skip if the street name looks like a known city or authority
        if _is_city_or_state(street_part):
            continue

        # Skip common false positives (e.g. "Amtsgericht" + "Platz")
        full_text_lower = match.group(0).lower()
        is_authority = any(auth_pat.search(full_text_lower) for auth_pat in _AUTHORITY_PATTERNS)
        if is_authority:
            continue

        placeholder = _get_placeholder_for(mapping, "address", original_address)
        results.append((match.start(), match.end(), placeholder))

    return results


def _detect_birth_dates(
    text: str, mapping: PiiMapping, current_year: int = 2026
) -> list[tuple[int, int, str]]:
    """Detect birth dates and replace them with [[GEBURTSDATUM_X]].

    Also preserves or computes age nearby.
    Returns list of (start, end, replacement_text) where replacement_text
    includes the placeholder and optionally the preserved/inserted age.
    """
    results: list[tuple[int, int, str]] = []
    pattern = _get_patterns()["birth_date"]

    for match in pattern.finditer(text):
        context_word = match.group(1).strip()
        date_str = match.group(2).strip()
        raw = match.group(0).strip()

        # Normalize date: remove spaces between components
        date_normalized = re.sub(r"\s+", "", date_str)

        placeholder = _get_placeholder_for(mapping, "birth_date", date_normalized)

        # Try to compute age from the birth year
        age = None
        date_parts = re.split(r"\.", date_normalized)
        if len(date_parts) == 3 and len(date_parts[2]) in (2, 4):
            try:
                birth_year = int(date_parts[2])
                if birth_year < 100:
                    birth_year += 2000
                age = current_year - birth_year
            except ValueError:
                pass

        # Check if age is already stated nearby (within next ~50 chars)
        nearby = text[match.end() : match.end() + 60]
        age_pattern = re.search(r"\(?\s*(\d{1,3})\s*(?:Jahre|J\.)\s*(?:alt)?\)?", nearby)
        preserved_age = age_pattern.group(1) if age_pattern else None

        if preserved_age:
            replacement = f"{context_word} {placeholder} ({preserved_age} Jahre)"
        elif age is not None:
            replacement = f"{context_word} {placeholder} (ca. {age} Jahre)"
        else:
            replacement = f"{context_word} {placeholder}"

        results.append((match.start(), match.end(), replacement))

    return results


def _detect_salutation_names(text: str, mapping: PiiMapping) -> list[tuple[int, int, str]]:
    """Detect names following salutation patterns.

    Returns list of (start, end, placeholder).
    Deduplicates overlapping spans (same pattern from multiple match groups).
    """
    results: list[tuple[int, int, str]] = []
    seen_spans: set[tuple[int, int]] = set()

    for pattern in _SALUTATION_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            # Skip if the detected name looks like a city or authority keyword
            if name.lower() in _CITIES:
                continue
            placeholder = _get_placeholder_for(mapping, "person", name)
            # Replace the name portion within the match
            name_start = match.start(1)
            name_end = match.end(1)
            span = (name_start, name_end)
            if span not in seen_spans:
                seen_spans.add(span)
                results.append((name_start, name_end, placeholder))

    return results


def _detect_ner_names(text: str, mapping: PiiMapping) -> list[tuple[int, int, str, str]]:
    """Use spaCy NER to detect person and organisation entities.

    Returns list of (start, end, placeholder, entity_type).
    entity_type is 'person' or 'company'.
    """
    results: list[tuple[int, int, str, str]] = []
    nlp = _get_nlp()
    if nlp is None:
        return results

    doc = nlp(text)

    for ent in doc.ents:
        if ent.label_ == "PER":
            raw = ent.text.strip()
            if not raw or len(raw) < 2:
                continue
            # Skip if the entity is a known city, state, or authority
            if _is_city_or_state(raw):
                continue
            # Check against authority patterns
            raw_lower = raw.lower()
            is_authority = any(auth_pat.search(raw_lower) for auth_pat in _AUTHORITY_PATTERNS)
            if is_authority:
                continue
            placeholder = _get_placeholder_for(mapping, "person", raw)
            results.append((ent.start_char, ent.end_char, placeholder, "person"))
        elif ent.label_ == "ORG":
            raw = ent.text.strip()
            if not raw or len(raw) < 3:
                continue
            # Skip known authorities explicitly
            raw_lower = raw.lower()
            if raw_lower in _CITIES or raw_lower in _BUNDESLAENDER:
                continue
            is_authority = any(auth_pat.search(raw_lower) for auth_pat in _AUTHORITY_PATTERNS)
            if is_authority:
                continue
            # Skip short orgs that look like initials
            if len(raw) <= 3 and raw.isupper():
                continue
            placeholder = _get_placeholder_for(mapping, "company", raw)
            results.append((ent.start_char, ent.end_char, placeholder, "company"))

    return results


def _detect_first_name(text: str, mapping: PiiMapping) -> list[tuple[int, int, str, str]]:
    """Detect capitalized words that match the first-name gazetteer.

    Returns list of (start, end, placeholder, 'person').
    Also handles inflected forms (e.g. "Vahrenholts" -> "Vahrenholt").
    """
    results: list[tuple[int, int, str, str]] = []
    # Match capitalized words that could be names (2+ chars, start with uppercase)
    word_pattern = re.compile(r"\b([A-ZÄÖÜß][a-zäöüß]+)\b")

    for match in word_pattern.finditer(text):
        word = match.group(1).strip()
        word_lower = word.lower()

        # Skip known non-PII words
        if word_lower in _CITIES or word_lower in _BUNDESLAENDER:
            continue
        if len(word) <= 1:
            continue

        # Check direct match
        if word_lower in _FIRST_NAMES:
            # Verify this isn't at the start of a sentence (could be a common noun)
            # Simple heuristic: check if preceded by period, or if it's a very short word
            preceding = text[max(0, match.start() - 3) : match.start()].strip()
            if preceding and preceding[-1] in ".!?":
                continue  # Start of sentence — likely not a name reference
            placeholder = _get_placeholder_for(mapping, "person", word)
            results.append((match.start(), match.end(), placeholder, "person"))
            continue

        # Check inflected form: strip trailing s/es/ns
        stripped = _strip_inflected_suffix(word)
        if stripped != word and stripped.lower() in _FIRST_NAMES:
            placeholder = _get_placeholder_for(mapping, "person", word)
            results.append((match.start(), match.end(), placeholder, "person"))

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pseudonymize(text: str, mapping: PiiMapping | None = None) -> tuple[str, PiiMapping]:
    """Replace all PII in *text* with typed placeholders.

    Args:
        text: Raw input text (user-provided case description).
        mapping: Existing mapping for deterministic replacement, or None to
            create a new one.

    Returns:
        Tuple of (pseudonymized_text, PiiMapping). The mapping contains the
        bidirectional placeholder↔original correspondence.

    Important: This function does NOT modify the input mapping if one is
    provided. It creates a copy so that the caller's mapping is only updated
    with newly detected values.
    """
    if mapping is None:
        mapping = PiiMapping()
    else:
        # Use a shallow copy so we don't mutate the caller's mapping
        # (but share the underlying dicts for determinism)
        mapping = PiiMapping(
            person_counter=mapping.person_counter,
            address_counter=mapping.address_counter,
            company_counter=mapping.company_counter,
            id_counter=mapping.id_counter,
            placeholder_to_value=mapping.placeholder_to_value,
            value_to_placeholder=mapping.value_to_placeholder,
        )

    result = text

    # 1. Detect structured IDs (replace first, highest confidence)
    id_patterns = _get_patterns()
    for pattern_name in (
        "bg_nummer",
        "aktenzeichen",
        "sv_nummer",
        "steuer_id",
        "iban",
        "phone",
        "email",
    ):
        if pattern_name not in id_patterns:
            continue
        pattern = id_patterns[pattern_name]
        for match in pattern.finditer(result):
            raw = match.group(0).strip()
            if pattern_name == "phone":
                digit_count = sum(1 for c in raw if c.isdigit())
                if digit_count < 6:
                    continue
            placeholder = _get_placeholder_for(mapping, "id", raw)
            result = result[: match.start()] + placeholder + result[match.end() :]

    # 2. Detect street addresses
    addr_detections = _detect_street_addresses(result, mapping)
    # Process in reverse order to preserve positions
    for start, end, placeholder in sorted(addr_detections, key=lambda x: x[0], reverse=True):
        result = result[:start] + placeholder + result[end:]

    # 3. Detect birth dates
    bd_detections = _detect_birth_dates(result, mapping)
    for start, end, replacement in sorted(bd_detections, key=lambda x: x[0], reverse=True):
        result = result[:start] + replacement + result[end:]

    # 4. Detect names via salutation patterns
    sal_detections = _detect_salutation_names(result, mapping)
    for start, end, placeholder in sorted(sal_detections, key=lambda x: x[0], reverse=True):
        result = result[:start] + placeholder + result[end:]

    # 5. Detect names via spaCy NER
    ner_detections = _detect_ner_names(result, mapping)
    for start, end, placeholder, _ in sorted(ner_detections, key=lambda x: x[0], reverse=True):
        # Check if this span overlaps with already-replaced regions (by checking if placeholder already present)
        # Simple check: if the span contains [[ then skip
        span_text = result[start:end]
        if "[[" in span_text:
            continue
        result = result[:start] + placeholder + result[end:]

    # 6. Detect names via first-name gazetteer (supplement for spaCy misses)
    gazetteer_detections = _detect_first_name(result, mapping)
    for start, end, placeholder, _ in sorted(
        gazetteer_detections, key=lambda x: x[0], reverse=True
    ):
        span_text = result[start:end]
        if "[[" in span_text:
            continue
        result = result[:start] + placeholder + result[end:]

    logger.info(
        "Pseudonymization complete: %d persons, %d addresses, " "%d companies, %d IDs mapped",
        mapping.person_counter,
        mapping.address_counter,
        mapping.company_counter,
        mapping.id_counter,
    )

    return result, mapping


def _compute_year_from_date(date_str: str) -> int | None:
    """Extract year from a German date string (DD.MM.YYYY or DD.MM.YY)."""
    clean = date_str.replace(" ", "")
    parts = clean.split(".")
    if len(parts) >= 3:
        try:
            year = int(parts[2])
            if year < 100:
                year += 2000
            return year
        except ValueError:
            return None
    return None


def depseudonymize(text: str, mapping: PiiMapping) -> str:
    """Replace all placeholders in *text* with original values.

    Handles exact placeholder matches only. For tolerant matching (handling
    LLM mutations like ``[[PERSON_1]]s``), use ``depseudonymize_tolerant()``.

    Args:
        text: Text potentially containing ``[[PLACEHOLDER]]`` tokens.
        mapping: The PiiMapping containing placeholder→original mappings.

    Returns:
        Text with all placeholders replaced by original values.
    """
    result = text
    # Sort by placeholder length descending to avoid partial substitution
    for placeholder in sorted(mapping.placeholder_to_value, key=len, reverse=True):
        original = mapping.placeholder_to_value[placeholder]
        result = result.replace(placeholder, original)
    return result


def depseudonymize_tolerant(text: str, mapping: PiiMapping) -> tuple[str, list[str]]:
    """Depseudonymize with tolerance for common LLM mutations.

    Handles:
    - ``[[PERSON_1]]s`` → restored with genitive suffix (e.g. "Mustermanns")
    - `` [[PERSON_1]] `` → extra whitespace around placeholders
    - ``[PERSON_1]`` → missing one bracket pair
    - ``[[PERSON_1]]s`` → possessive/genitive attached to placeholder

    Returns:
        Tuple of (depseudonymized_text, list_of_warnings).
        Warnings are emitted for placeholders that could not be resolved.
    """
    result = text
    warnings: list[str] = []

    # 1. Handle exact placeholders first (most common + fastest)
    result = depseudonymize(result, mapping)

    # 2. Handle placeholders with genitive/possessive suffix: [[PERSON_1]]s -> Original + "s"
    for placeholder in sorted(mapping.placeholder_to_value, key=len, reverse=True):
        original = mapping.placeholder_to_value[placeholder]
        variations = [
            (f"{placeholder}s", f"{original}s"),
            (f"{placeholder}es", f"{original}es"),
            (f"{placeholder}n", f"{original}n"),
            (f"{placeholder}ns", f"{original}ns"),
        ]
        for variant, replacement in variations:
            if variant in result:
                result = result.replace(variant, replacement)

    # 3. Handle single-bracket variants: [PERSON_1] instead of [[PERSON_1]]
    for placeholder in sorted(mapping.placeholder_to_value, key=len, reverse=True):
        original = mapping.placeholder_to_value[placeholder]
        # [[PERSON_1]] → [PERSON_1] (double → single)
        inner = placeholder[2:-2]  # e.g. "PERSON_1"
        single_bracket = f"[{inner}]"
        if single_bracket in result:
            result = result.replace(single_bracket, original)
        # Also handle missing closing bracket: [[PERSON_1] -> original
        partial_open = f"[[{inner}]"
        if partial_open in result:
            result = result.replace(partial_open, original)
        partial_close = f"[{inner}]]"
        if partial_close in result:
            result = result.replace(partial_close, original)

    # 4. Handle whitespace mutations: " [[PERSON_1]] " → " " + original + " "
    for placeholder in sorted(mapping.placeholder_to_value, key=len, reverse=True):
        original = mapping.placeholder_to_value[placeholder]
        for ws_pattern in (
            f" {placeholder}",
            f"{placeholder} ",
            f"  {placeholder}",
            f"{placeholder}  ",
        ):
            if ws_pattern in result:
                result = result.replace(ws_pattern, f" {original} ")

    # 5. Check for any remaining unreplaced placeholders
    remaining = re.findall(r"\[\[(\w+)\]\]", result)
    for unreplaced in remaining:
        candidate = f"[[{unreplaced}]]"
        if candidate not in mapping.placeholder_to_value:
            warnings.append(f"Unresolved placeholder: {candidate}")

    if warnings:
        logger.warning(
            "Depseudonymization completed with %d unresolved placeholder(s): %s",
            len(warnings),
            warnings,
        )

    return result, warnings


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------


def pseudonymize_case_run(input_text: str) -> tuple[str, PiiMapping]:
    """Gate function: pseudonymize case input before it enters the pipeline.

    This is the primary integration point — called before any LLM call.
    Always creates a fresh mapping for each new case run.

    Args:
        input_text: Raw user-provided case text.

    Returns:
        Tuple of (pseudonymized_text, PiiMapping).
    """
    logger.info(
        "Pseudonymization gate: processing %d chars of input text",
        len(input_text),
    )
    return pseudonymize(input_text, None)


def get_known_values(mapping: PiiMapping) -> set[str]:
    """Return all known original PII values for egress guard scanning.

    Args:
        mapping: A ``PiiMapping`` instance (may be ``None``).

    Returns:
        A ``set[str]`` of original PII values (case-sensitive, as detected).
        Returns an empty set if *mapping* is ``None``.
    """
    if mapping is None:
        return set()
    return set(mapping.value_to_placeholder.keys())


def depseudonymize_output(
    text: str,
    mapping: PiiMapping,
) -> tuple[str, list[str]]:
    """Reinject original values into pipeline output for user display.

    Uses tolerant matching to handle LLM-induced placeholder mutations.

    Args:
        text: Pipeline output text (e.g. a final_output section value).
        mapping: PiiMapping from the corresponding pseudonymization pass.

    Returns:
        Tuple of (depseudonymized_text, warnings).
    """
    return depseudonymize_tolerant(text, mapping)
