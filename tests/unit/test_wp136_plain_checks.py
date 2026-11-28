"""Multilingual safety gates must exercise sentences rather than entire paragraphs."""

import pytest

from app.plain.checks import discouraging_hits, sentences
from app.plain.languages import format_date
from datetime import date


@pytest.mark.parametrize(
    "text,want",
    [
        (
            "Проверьте срок. Немедленно обратитесь за помощью.",
            ["Проверьте срок.", "Немедленно обратитесь за помощью."],
        ),
        (
            "Перевірте строк. Негайно зверніться по допомогу.",
            ["Перевірте строк.", "Негайно зверніться по допомогу."],
        ),
        ("تحقق فوراً. اطلب مساعدة.", ["تحقق فوراً.", "اطلب مساعدة."]),
        ("مهلت روشن نیست؟ کمک بگیرید.", ["مهلت روشن نیست؟", "کمک بگیرید."]),
    ],
)
def test_non_latin_sentences_are_checked_individually(text, want):
    assert sentences(text) == want


@pytest.mark.parametrize(
    "phrase", ["لا جدوى", "بی‌فایده است", "немає шансів", "hiç şansınız yok", "нет шансов"]
)
def test_discouraging_copy_is_rejected_in_additional_languages(phrase):
    assert discouraging_hits(phrase)


@pytest.mark.parametrize("lang", ["ar", "fa", "uk", "tr", "ru"])
def test_additional_languages_retain_unambiguous_iso_dates(lang):
    assert format_date(date(2026, 11, 27), lang) == "2026-11-27"
