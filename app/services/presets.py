"""Case-type presets — a flat catalog of 5 composite legal-area packages.

The intake LLM is allowed to choose any combination of the supported
``legal_areas`` per case. A *preset* is a sensible default bundle (e.g.
"Erbe mit Testament" → erbrecht + familienrecht) that the LLM can
suggest or the user can pick manually. Presets are kept here in code so
the catalog is version-controlled and easy to extend.

The composite for any specific case is composed dynamically by the LLM;
presets are starting points, not restrictions.
"""

# Semantic Version: 0.3.0

from __future__ import annotations

from typing import Any


# The 5 flat presets defined in the plan. Each preset is keyed by a
# short slug; ``legal_areas`` lists the area keys in priority order
# (primary first). ``description`` is the German long form shown in the
# UI; ``typical_scenarios`` are example user inputs that would suggest
# this preset.
PRESETS: list[dict[str, Any]] = [
    {
        "id": "sozialrecht-allgemein",
        "name": "Sozialrecht (Bürgergeld / Jobcenter)",
        "description": (
            "Standardfall im SGB II / SGB X: Bürgergeld-Bescheid, "
            "Sanktion, Anhörung, Eingliederungsvereinbarung oder "
            "Aufhebungs- und Erstattungsbescheid."
        ),
        "legal_areas": ["sozialrecht"],
        "typical_scenarios": [
            "Jobcenter hat meinen Bürgergeld-Bescheid aufgehoben.",
            "Ich habe eine Sanktion nach § 31 SGB II bekommen.",
            "Meine Kosten der Unterkunft wurden nicht anerkannt.",
        ],
    },
    {
        "id": "erbe-mit-testament",
        "name": "Erbe mit Testament",
        "description": (
            "Erbrecht mit letztwilliger Verfügung: Testamentsauslegung, "
            "Erbquote, Pflichtteil, Erbscheinsverfahren, "
            "Erbschaftsteuer-Freibeträge."
        ),
        "legal_areas": ["erbrecht"],
        "typical_scenarios": [
            "Ich habe ein handschriftliches Testament geerbt — was nun?",
            "Mein Bruder beansprucht einen höheren Pflichtteil.",
            "Wie berechnet sich die Erbschaftsteuer auf ein Haus?",
        ],
    },
    {
        "id": "erbe-mit-familie",
        "name": "Erbe mit Familienkonflikt",
        "description": (
            "Schnittstelle Erbrecht / Familienrecht: Erbfolge mit "
            "Scheidungsfolgen, Zugewinnausgleich im Nachlass, "
            "Ausgleichsansprüche zwischen Miterben."
        ),
        "legal_areas": ["erbrecht", "familienrecht"],
        "typical_scenarios": [
            "Meine geschiedene Frau beansprucht Erbanteile.",
            "Mein Ex-Mann ist verstorben — steht mir ein Pflichtteil zu?",
        ],
    },
    {
        "id": "schenkung-zu-lebzeiten",
        "name": "Schenkung zu Lebzeiten",
        "description": (
            "Schenkungsrecht und Erbschaftsteuer: vorzeitige "
            "Vermögensübertragung, Freibeträge alle 10 Jahre, "
            "Anzeigepflichten beim Finanzamt, Rückforderungsrechte."
        ),
        "legal_areas": ["schenkungsrecht", "erbrecht"],
        "typical_scenarios": [
            "Ich will meinem Kind noch zu Lebzeiten das Haus übertragen.",
            "Welche Steuern fallen bei einer Schenkung an?",
        ],
    },
    {
        "id": "hofesuebergabe",
        "name": "Höfeübergabe (Landwirtschaft)",
        "description": (
            "Sondererbrecht der Höfeordnung: Hofesübergabe zu Lebzeiten, "
            "Abfindung weichender Erben, Bewertung nach Ertragswert, "
            "Zusammenhang mit Erbschaftsteuer."
        ),
        "legal_areas": ["erbrecht", "schenkungsrecht"],
        "typical_scenarios": [
            "Ich übernehme den Hof von meinen Eltern.",
            "Wie wird der Hof für die Erbschaftsteuer bewertet?",
        ],
    },
]


# Quick lookup: id → preset dict.
_PRESET_BY_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in PRESETS}


def get_preset(preset_id: str) -> dict[str, Any] | None:
    """Return the preset with the given id, or ``None`` if not found."""
    return _PRESET_BY_ID.get(preset_id)


def list_presets() -> list[dict[str, Any]]:
    """Return all presets in declaration order."""
    return list(PRESETS)
