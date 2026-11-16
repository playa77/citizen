"""WP-101 — chronology builder (app/dossier/chronology.py).

Deterministic extraction rules (letter date, periods, module cues, dedupe),
the merge of the person's decisions, and validation of the PUT body.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — P10

from __future__ import annotations

import unicodedata
from datetime import date

import pytest

from app.dossier.chronology import (
    KIND_DOCUMENT_DATE,
    KIND_MENTIONED,
    KIND_PERIOD_END,
    KIND_PERIOD_START,
    STATUS_CONFIRMED,
    STATUS_PROPOSED,
    STATUS_REJECTED,
    STATUS_USER_ADDED,
    ChronologyCue,
    ChronologyDecisions,
    SourceText,
    apply_decisions,
    propose_entries,
    validate_update,
)

CUES = (
    ChronologyCue("antrag", "Antrag", ("antrag vom",), "mod"),
    ChronologyCue("anhoerung", "Anhörung", ("anhörung vom",), "mod"),
)


def _kinds(text: str, cues: tuple[ChronologyCue, ...] = CUES) -> list[tuple[str, str]]:
    return [
        (e.date.isoformat(), e.kind)
        for e in propose_entries([SourceText("case_input", "t", text)], cues)
    ]


class TestExtraction:
    def test_letter_date_line_and_cue(self) -> None:
        text = "Stadt Essen\nEssen, 06.07.2026\n\nauf Ihren Antrag vom 15.06.2026 wird"
        assert _kinds(text) == [("2026-07-06", KIND_DOCUMENT_DATE), ("2026-06-15", "antrag")]

    def test_only_first_letter_date_line_counts(self) -> None:
        text = "Essen, 06.07.2026\nBerlin, den 7. Juli 2026\n"
        assert _kinds(text) == [("2026-07-06", KIND_DOCUMENT_DATE), ("2026-07-07", KIND_MENTIONED)]

    def test_heading_bescheid_vom_is_the_letter_date(self) -> None:
        assert _kinds("Bescheid vom 15.02.2025\nJobcenter X")[0] == (
            "2025-02-15",
            KIND_DOCUMENT_DATE,
        )

    def test_bescheid_vom_in_running_text_is_not_the_letter_date(self) -> None:
        assert _kinds("mit Bescheid vom 21.11.2025 wurden")[0][1] != KIND_DOCUMENT_DATE

    def test_period_on_one_line_and_wrapped(self) -> None:
        assert _kinds("für den Zeitraum vom 01.08.2026 bis 31.07.2027 Leistungen") == [
            ("2026-08-01", KIND_PERIOD_START),
            ("2027-07-31", KIND_PERIOD_END),
        ]
        assert _kinds("Zeitraum 01.12.2025 bis\n31.05.2026 aufgehoben") == [
            ("2025-12-01", KIND_PERIOD_START),
            ("2026-05-31", KIND_PERIOD_END),
        ]

    def test_period_never_spans_a_paragraph(self) -> None:
        assert _kinds("am 01.12.2025 bis\n\n31.05.2026 geschah") == [
            ("2025-12-01", KIND_MENTIONED),
            ("2026-05-31", KIND_MENTIONED),
        ]

    def test_cue_may_wrap_one_line_but_not_pass_the_previous_date(self) -> None:
        text = "auf Ihren Antrag vom\n05.11.2025 Leistungen ab 01.12.2025 gezahlt"
        assert _kinds(text) == [("2025-11-05", "antrag"), ("2025-12-01", KIND_MENTIONED)]

    def test_cue_does_not_cross_a_paragraph(self) -> None:
        assert _kinds("Antrag vom\n\n05.11.2025") == [("2025-11-05", KIND_MENTIONED)]

    def test_word_month_and_iso_dates(self) -> None:
        assert _kinds("am 3. März 2026 und 2026-04-01") == [
            ("2026-03-03", KIND_MENTIONED),
            ("2026-04-01", KIND_MENTIONED),
        ]

    def test_invalid_dates_and_digit_runs_are_ignored(self) -> None:
        assert _kinds("am 31.02.2026, Az 12.03.20261, Tel 0176.12.2026") == []

    def test_repeated_date_and_kind_is_kept_once(self) -> None:
        assert _kinds("am 01.02.2026 und erneut am 01.02.2026") == [("2026-02-01", KIND_MENTIONED)]

    def test_decomposed_umlauts_match_cues(self) -> None:
        text = unicodedata.normalize("NFD", "nach Anhörung vom 12.01.2026 wird")
        assert _kinds(text) == [("2026-01-12", "anhoerung")]

    def test_ids_are_stable_and_carry_the_source(self) -> None:
        source = SourceText("conversation_document:abc", "brief.pdf", "x\nEssen, 06.07.2026")
        first = propose_entries([source])
        assert [e.entry_id for e in first] == [e.entry_id for e in propose_entries([source])]
        assert first[0].entry_id.startswith("chr-")
        assert first[0].source == {
            "document": "conversation_document:abc",
            "label": "brief.pdf",
            "line": 2,
            "excerpt": "Essen, 06.07.2026",
        }
        assert first[0].status == STATUS_PROPOSED


class TestDecisions:
    def _proposals(self) -> list[object]:
        return propose_entries(
            [SourceText("case_input", "t", "Essen, 06.07.2026\nAntrag vom 15.06.2026")], CUES
        )

    def test_confirm_reject_correct_and_add(self) -> None:
        proposals = propose_entries(
            [SourceText("case_input", "t", "Essen, 06.07.2026\nAntrag vom 15.06.2026")], CUES
        )
        letter, antrag = proposals
        decisions, added = validate_update(
            {
                "entries": [
                    {"entry_id": letter.entry_id, "status": "confirmed", "date": "2026-07-07"},
                    {"entry_id": antrag.entry_id, "status": "rejected"},
                ],
                "added": [{"date": "2026-07-10", "label_de": "Brief erhalten"}],
            },
            {letter.entry_id, antrag.entry_id},
        )
        merged = apply_decisions(proposals, ChronologyDecisions(decisions, added))
        by_status = {e.status: e for e in merged}
        assert by_status[STATUS_CONFIRMED].date == date(2026, 7, 7)
        assert by_status[STATUS_CONFIRMED].as_dict()["original_date"] == "2026-07-06"
        assert by_status[STATUS_REJECTED].kind == "antrag"
        assert by_status[STATUS_USER_ADDED].label_de == "Brief erhalten"
        assert [e.date for e in merged] == sorted(e.date for e in merged)

    def test_stale_decisions_are_ignored(self) -> None:
        proposals = propose_entries([SourceText("case_input", "t", "Essen, 06.07.2026")])
        merged = apply_decisions(
            proposals, ChronologyDecisions({"chr-000000000000": {"status": "confirmed"}})
        )
        assert [e.status for e in merged] == [STATUS_PROPOSED]

    @pytest.mark.parametrize(
        "body, message",
        [
            ({"entries": {}}, "must be lists"),
            ({"entries": [{"entry_id": "chr-unknown", "status": "confirmed"}]}, "unknown entry_id"),
            ({"entries": [{"entry_id": "chr-a", "status": "maybe"}]}, "status must be"),
            ({"entries": [{"entry_id": "chr-a", "status": "confirmed", "date": "06.07"}]}, "ISO"),
            ({"added": [{"date": "2026-01-01"}]}, "label_de"),
            ({"added": [{"date": "2026-01-01", "label_de": "x", "kind": "Bad Kind"}]}, "kind"),
        ],
    )
    def test_invalid_update_bodies(self, body: dict[str, object], message: str) -> None:
        with pytest.raises(ValueError, match=message):
            validate_update(body, {"chr-a"})
