"""Unit tests for the generic deadline-spec evaluator (WP-92).

The evaluator in ``app/fristen/`` consumes module deadline specs
(``fristen.yaml``, ARCHITECTURE.md § 2.3) and produces the same
``FristResult`` contract as the pre-split engine. These tests cover the
spec path directly; the SGG Widerspruchsfrist is additionally verified
end-to-end (unchanged) in ``tests/unit/test_fristen.py`` via the shim.

All cases are pure date arithmetic — no mocking required.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.fristen import FristResult
from app.fristen.evaluator import FristInput, evaluate_spec
from app.fristen.specs import DeadlineSpec, Duration, MissingRbb, find_spec, load_specs
from app.modules.registry import default_modules_root


# ---------------------------------------------------------------------------
# Fixture: the shipped sozialrecht Widerspruchsfrist spec
# ---------------------------------------------------------------------------


def _widerspruch_spec() -> DeadlineSpec:
    specs = load_specs(default_modules_root() / "sozialrecht" / "fristen.yaml")
    return find_spec(specs, "widerspruch_sgg_84")


def _evaluate(**kwargs: object) -> FristResult:
    return evaluate_spec(_widerspruch_spec(), FristInput(**kwargs))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Month-end arithmetic (§ 188 Abs. 2 BGB, via the spec's duration)
# ---------------------------------------------------------------------------


class TestMonthEndArithmetic:
    def test_month_end_jan_to_feb_non_leap(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2025, 1, 27),
            aufgabe_zur_post=date(2025, 1, 27),  # Mon → bekanntgabe Fri 31.01
        )
        assert result.bekanntgabe == date(2025, 1, 31)
        assert result.frist_ende == date(2025, 2, 28)  # Feb has no 31st
        assert result.frist_typ == "monat"

    def test_month_end_jan_to_feb_leap(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2024, 1, 27),
            aufgabe_zur_post=date(2024, 1, 27),
        )
        assert result.bekanntgabe == date(2024, 1, 31)
        assert result.frist_ende == date(2024, 2, 29)

    def test_month_end_mar_to_apr(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2025, 3, 27),
            aufgabe_zur_post=date(2025, 3, 27),  # bekanntgabe Mon 31.03
        )
        assert result.bekanntgabe == date(2025, 3, 31)
        assert result.frist_ende == date(2025, 4, 30)  # Apr has no 31st

    def test_month_end_dec_to_jan(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2025, 11, 27),
            aufgabe_zur_post=date(2025, 11, 27),  # bekanntgabe Mon 01.12
        )
        assert result.bekanntgabe == date(2025, 12, 1)
        # fristende rechnerisch 01.01.2026 (Neujahr) → rolled to 02.01.
        assert result.frist_ende == date(2026, 1, 2)
        assert result.rollover_applied


# ---------------------------------------------------------------------------
# Workday rollover (spec rollover: sgg_64_3)
# ---------------------------------------------------------------------------


class TestRollover:
    def test_fristende_on_saturday_rolls_to_monday(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2025, 3, 30),
            aufgabe_zur_post=date(2025, 3, 30),  # bekanntgabe Thu 03.04
        )
        # fristende rechnerisch Sat 03.05 → Mon 05.05
        assert result.frist_ende == date(2025, 5, 5)
        assert result.rollover_applied
        assert "§ 64 Abs. 3" in result.explanation_de

    def test_no_rollover_on_workday(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2025, 4, 11),
            aufgabe_zur_post=date(2025, 4, 11),  # bekanntgabe Tue 15.04
        )
        assert result.frist_ende == date(2025, 5, 15)
        assert not result.rollover_applied

    def test_christmas_rollover_skips_holiday_chain(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2025, 11, 27),
            aufgabe_zur_post=date(2025, 11, 27),  # bekanntgabe Mon 01.12
        )
        # fristende rechnerisch 01.01.2026 (Neujahr) → 02.01.2026
        assert result.frist_ende == date(2026, 1, 2)
        assert result.rollover_applied


# ---------------------------------------------------------------------------
# Holiday calendar per Land (spec path must honour the Bundesland)
# ---------------------------------------------------------------------------


class TestHolidaysPerLand:
    def test_heilige_drei_koenige_rolls_in_bw_not_in_nw(self) -> None:
        # bekanntgabe Sat 06.12.2025 (OQ-1), fristende rechnerisch 06.01.2026.
        kwargs: dict[str, object] = {
            "bescheid_datum": date(2025, 12, 2),
            "aufgabe_zur_post": date(2025, 12, 2),
        }
        bw = _evaluate(**kwargs, bundesland="BW")
        nw = _evaluate(**kwargs, bundesland="NW")
        # BW: 06.01 is Heilige Drei Könige → roll to 07.01 (Wed).
        assert bw.frist_ende == date(2026, 1, 7)
        assert bw.rollover_applied
        # NW: 06.01 is an ordinary workday → no rollover.
        assert nw.frist_ende == date(2026, 1, 6)
        assert not nw.rollover_applied

    def test_fronleichnam_rolls_in_nw_not_in_sh(self) -> None:
        # Fristende rechnerisch 04.06.2026 (Fronleichnam) requires
        # bekanntgabe 04.05.2026 → aufgabe 30.04.2026 (Thu).
        kwargs: dict[str, object] = {
            "bescheid_datum": date(2026, 4, 30),
            "aufgabe_zur_post": date(2026, 4, 30),
        }
        nw = _evaluate(**kwargs, bundesland="NW")
        sh = _evaluate(**kwargs, bundesland="SH")
        assert nw.frist_ende == date(2026, 6, 5)
        assert nw.rollover_applied
        assert sh.frist_ende == date(2026, 6, 4)
        assert not sh.rollover_applied


# ---------------------------------------------------------------------------
# Missing/defective Rechtsbehelfsbelehrung → one-year deadline (§ 66 Abs. 2)
# ---------------------------------------------------------------------------


class TestDefectiveRbbOneYear:
    def test_rbb_fehlerhaft_gives_jahresfrist(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2026, 2, 9),
            aufgabe_zur_post=date(2026, 2, 9),  # bekanntgabe Fri 13.02.2026
            rbb_status="fehlerhaft",
        )
        # 1 year later: Sat 13.02.2027 → Mon 15.02.2027
        assert result.frist_typ == "jahr"
        assert result.bekanntgabe == date(2026, 2, 13)
        assert result.frist_ende == date(2027, 2, 15)
        assert result.rollover_applied

    def test_rbb_fehlt_gives_jahresfrist(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2025, 3, 15),
            aufgabe_zur_post=date(2025, 3, 15),  # bekanntgabe Wed 19.03.2025
            rbb_status="fehlt",
        )
        assert result.frist_typ == "jahr"
        assert result.frist_ende == date(2026, 3, 19)  # Thu — no rollover

    def test_explanation_cites_spec_basis(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2025, 3, 15),
            aufgabe_zur_post=date(2025, 3, 15),
            rbb_status="fehlt",
        )
        # The one-year basis comes from the spec (§ 66 Abs. 2 SGG), not core.
        assert "§ 66 Abs. 2 SGG" in result.explanation_de

    def test_oq1_alternate_uses_governing_duration(self) -> None:
        """OQ-1 alternate deadline uses the GOVERNING duration, not always
        one month (D-048).

        aufgabe 03.01.2024 (Wed) + 4 = Sonntag 07.01.2024 → OQ-1;
        citizen reading 08.01.2024 (Mon). With a defective RBB the governing
        deadline is the Jahresfrist, so the citizen-favorable alternate is
        08.01.2025 (+1 year) — the pre-split engine computed +1 month here,
        which put the "alternate" BEFORE the primary end (07.01.2025) and
        was therefore not citizen-favorable. Pinned to prevent regression
        in either direction.
        """
        result = _evaluate(
            bescheid_datum=date(2024, 1, 1),
            aufgabe_zur_post=date(2024, 1, 3),
            rbb_status="fehlt",
        )
        assert result.oq1_flag
        assert result.bekanntgabe == date(2024, 1, 7)
        assert result.frist_ende == date(2025, 1, 7)  # primary: +1 year
        assert result.oq1_alternate_ende == date(2025, 1, 8)  # alternate: +1 year
        assert result.oq1_alternate_ende > result.frist_ende


# ---------------------------------------------------------------------------
# Result contract
# ---------------------------------------------------------------------------


class TestResultContract:
    def test_result_carries_module_and_spec_id(self) -> None:
        result = evaluate_spec(
            _widerspruch_spec(),
            FristInput(
                bescheid_datum=date(2025, 3, 15),
                aufgabe_zur_post=date(2025, 3, 15),
            ),
            module_id="sozialrecht",
        )
        assert result.module_id == "sozialrecht"
        assert result.spec_id == "widerspruch_sgg_84"

    def test_module_id_is_optional(self) -> None:
        result = _evaluate(
            bescheid_datum=date(2025, 3, 15),
            aufgabe_zur_post=date(2025, 3, 15),
        )
        assert result.module_id is None
        assert result.spec_id == "widerspruch_sgg_84"

    def test_spec_loads_from_module_yaml(self) -> None:
        specs = load_specs(default_modules_root() / "sozialrecht" / "fristen.yaml")
        spec = find_spec(specs, "widerspruch_sgg_84")
        assert spec.trigger == "bekanntgabe"
        assert spec.bekanntgabe_fiction == "sgbx_37_2"
        assert spec.duration == Duration(months=1)
        assert spec.rollover == "sgg_64_3"
        assert spec.missing_rechtsbehelfsbelehrung == MissingRbb(
            duration=Duration(years=1), basis="§ 66 Abs. 2 SGG"
        )
        assert spec.basis == "§ 84 Abs. 1 SGG"
        assert spec.severity == "critical"

    def test_unknown_spec_id_raises(self) -> None:
        specs = load_specs(default_modules_root() / "sozialrecht" / "fristen.yaml")
        with pytest.raises(KeyError):
            find_spec(specs, "gibt_es_nicht")


# ---------------------------------------------------------------------------
# Unimplemented library ids fail loudly (fail-loud, never silently wrong)
# ---------------------------------------------------------------------------


class TestUnimplementedLibraryIds:
    def test_unknown_fiction_id_raises(self) -> None:
        spec = DeadlineSpec(
            id="test_spec",
            label_de="Test",
            trigger="bekanntgabe",
            bekanntgabe_fiction="gibts_nicht",
            duration=Duration(months=1),
            rollover=None,
            missing_rechtsbehelfsbelehrung=None,
            basis="Testgesetz",
            severity="critical",
            applies_when={},
            fristbeginn_basis="Testgesetz",
            not_applicable=None,
        )
        with pytest.raises(NotImplementedError):
            evaluate_spec(
                spec,
                FristInput(bescheid_datum=date(2025, 3, 15), aufgabe_zur_post=None),
            )

    def test_unknown_rollover_id_raises(self) -> None:
        spec = DeadlineSpec(
            id="test_spec",
            label_de="Test",
            trigger="bekanntgabe",
            bekanntgabe_fiction="sgbx_37_2",
            duration=Duration(months=1),
            rollover="gibts_nicht",
            missing_rechtsbehelfsbelehrung=None,
            basis="Testgesetz",
            severity="critical",
            applies_when={},
            fristbeginn_basis="Testgesetz",
            not_applicable=None,
        )
        with pytest.raises(NotImplementedError):
            evaluate_spec(
                spec,
                FristInput(bescheid_datum=date(2025, 3, 15), aufgabe_zur_post=None),
            )
