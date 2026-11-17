"""Overall-assessment scorer (eval/extractors.py 1.2.0, D-069).

Pins the defects of the 1.0.0/1.1.0 keyword scorer — negation, label
precedence over the whole text, "unzulässig", accusative "keinen
Verwaltungsakt", unrecognised "rechtmäßig" — and the verdict-sentence path
the P-04/P-08 prompts require ("Vorläufige Einordnung: <Begriff>.").
"""

from __future__ import annotations

import pytest

from eval.extractors import extract_assessment_from_pipeline
from eval.pipeline_adapter import PipelineOutput


def _assess(ergebnis: str) -> str | None:
    return extract_assessment_from_pipeline(PipelineOutput(final_output={"ergebnis": ergebnis}))


@pytest.mark.parametrize(
    ("term", "label"),
    [
        ("rechtswidrig", "rechtswidrig"),
        ("teilweise rechtswidrig", "teilweise_rechtswidrig"),
        ("überwiegend rechtmäßig", "ueberwiegend_rechtmaessig"),
        ("kein Verwaltungsakt", "kein_verwaltungsakt"),
        ("Einordnung offen", "einordnung_offen"),
    ],
)
def test_verdict_sentence_maps_every_category(term: str, label: str) -> None:
    # Every term of the sozialrecht result_categories plus the core's
    # "Einordnung offen" (app/services/prompts.py _OPEN_CATEGORY).
    assert _assess(f"Vorläufige Einordnung: {term}. Begründung folgt.") == label


def test_verdict_sentence_beats_terms_in_the_reasoning() -> None:
    # 1.1.0 returned "rechtswidrig": label precedence over the whole section.
    text = (
        "Vorläufige Einordnung: kein Verwaltungsakt. Die angekündigte Absenkung "
        "wäre erst in einem späteren Bescheid zu prüfen und könnte dort rechtswidrig sein."
    )
    assert _assess(text) == "kein_verwaltungsakt"


def test_verdict_sentence_beats_reasoning_for_partial_unlawfulness() -> None:
    text = "Vorläufige Einordnung: rechtswidrig. Er ist nicht nur teilweise rechtswidrig."
    assert _assess(text) == "rechtswidrig"


@pytest.mark.parametrize(
    ("text", "label"),
    [
        # Negation (1.1.0: "rechtswidrig").
        ("Der Bescheid ist nicht rechtswidrig.", None),
        ("Eine Rechtswidrigkeit ist nicht erkennbar; der Bescheid ist rechtmäßig.", "rechtmaessig"),
        ("Eine Rechtswidrigkeit liegt nicht vor.", None),
        ("Der Bescheid ist nicht rechtmäßig.", "rechtswidrig"),
        # "nicht nur" intensifies, it does not negate.
        ("Der Bescheid ist nicht nur teilweise rechtswidrig.", "teilweise_rechtswidrig"),
        # Accusative and remedy wording (1.1.0: "rechtswidrig" via "unzulässig").
        (
            "Es handelt sich um keinen Verwaltungsakt; ein Widerspruch wäre unzulässig.",
            "kein_verwaltungsakt",
        ),
        ("Ein Widerspruch wäre unzulässig.", None),
        # Earliest match wins in the fallback.
        (
            "Der Bescheid ist teilweise rechtswidrig, im Übrigen nicht rechtswidrig.",
            "teilweise_rechtswidrig",
        ),
        ("Der Bescheid ist im Wesentlichen korrekt.", "ueberwiegend_rechtmaessig"),
        ("Der Bescheid ist rechtmäßig.", "rechtmaessig"),
        ("", None),
    ],
)
def test_free_text_fallback(text: str, label: str | None) -> None:
    assert _assess(text) == label


def test_negated_verdict_term_falls_back_to_free_text() -> None:
    # The prompt forbids negated terms in the verdict sentence; if a model
    # writes one anyway, it must not be read as the affirmative label.
    assert _assess("Vorläufige Einordnung: nicht rechtswidrig.") is None
