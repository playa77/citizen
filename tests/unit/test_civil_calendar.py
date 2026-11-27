"""Civil calendar regression: real Easter and current statewide holidays."""

from datetime import date

import pytest

from app.modules import sdk


@pytest.mark.parametrize(
    ("day", "land", "holiday"),
    [
        ("2026-10-31", "NW", False),
        ("2026-08-15", "BW", False),
        ("2026-11-01", "NW", True),
        ("2026-03-08", "BE", True),
        ("2026-03-08", "MV", True),
        ("2026-09-20", "TH", True),
        ("2026-11-18", "SN", True),
        ("2028-04-14", "BE", True),
        ("2028-04-17", "BE", True),
        ("2028-05-25", "HE", True),
        ("2028-06-15", "HE", True),
        ("2026-01-06", "BY", True),
        ("2026-01-06", "NW", False),
        ("2026-08-15", "BY", False),
    ],
)
def test_current_civil_statewide_holidays(day, land, holiday):
    assert sdk.civil_is_holiday(date.fromisoformat(day), land) is holiday


def test_additional_local_holiday_rolls_together_with_weekend():
    from app.fristen.civil_calendar import civil_next_workday

    assert civil_next_workday(date(2026, 8, 7), "BY", (date(2026, 8, 7),)) == date(2026, 8, 10)


def test_calendar_rejects_unknown_land():
    with pytest.raises(ValueError):
        sdk.civil_is_holiday(date(2026, 1, 1), "unknown")
