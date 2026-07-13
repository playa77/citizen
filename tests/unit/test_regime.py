"""Unit tests for intertemporal law selection (WP-24).

Tests the pure deterministic functions in ``app.services.regime``:
  - :func:`legal_regime` — date → regime tag
  - :func:`regime_for_period_range` — date range → regime segments
  - :func:`regime_banner` — tag → German banner string

Also validates goldset scenarios for GS-004, GS-005, GS-006, GS-008.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from datetime import date

import pytest

from app.services.regime import (
    REGIME_2023,
    REGIME_2025,
    REGIME_2026,
    REGIME_VOR_2023,
    legal_regime,
    regime_banner,
    regime_for_period_range,
    regime_transition_dates,
)

# ===========================================================================
# legal_regime()
# ===========================================================================


class TestLegalRegime:
    """Boundary coverage for ``legal_regime()``."""

    # -- Before first boundary (a.F._vor_2023) -----------------------------

    def test_epoch(self) -> None:
        """Well before any regime boundary → a.F._vor_2023."""
        assert legal_regime(date(2020, 1, 1)) == REGIME_VOR_2023

    def test_day_before_first_boundary(self) -> None:
        """2023-06-30, the last day before 2023-07-01 → a.F._vor_2023."""
        assert legal_regime(date(2023, 6, 30)) == REGIME_VOR_2023

    def test_first_boundary_open(self) -> None:
        """2023-07-01 is the first boundary → a.F._2023."""
        assert legal_regime(date(2023, 7, 1)) == REGIME_2023

    # -- Second regime (a.F._2023) -----------------------------------------

    def test_mid_2023(self) -> None:
        """Middle of 2023-07..2024 range → a.F._2023."""
        assert legal_regime(date(2024, 1, 15)) == REGIME_2023

    def test_last_day_of_2024(self) -> None:
        """2024-12-31, last day before second boundary → a.F._2023."""
        assert legal_regime(date(2024, 12, 31)) == REGIME_2023

    def test_2025_boundary_open(self) -> None:
        """2025-01-01 is the second boundary → a.F._2025."""
        assert legal_regime(date(2025, 1, 1)) == REGIME_2025

    # -- Third regime (a.F._2025) ------------------------------------------

    def test_mid_2025(self) -> None:
        """Middle of 2025 → a.F._2025."""
        assert legal_regime(date(2025, 6, 15)) == REGIME_2025

    def test_day_before_2026_boundary(self) -> None:
        """2026-06-30 → a.F._2025 (last day before n.F.)."""
        assert legal_regime(date(2026, 6, 30)) == REGIME_2025

    def test_2026_boundary_open(self) -> None:
        """2026-07-01 is the third boundary → n.F._2026."""
        assert legal_regime(date(2026, 7, 1)) == REGIME_2026

    # -- Fourth regime (n.F._2026) -----------------------------------------

    def test_post_2026_boundary(self) -> None:
        """Well into n.F. → n.F._2026."""
        assert legal_regime(date(2027, 1, 1)) == REGIME_2026

    def test_far_future(self) -> None:
        """Far future date → n.F._2026 (no boundary beyond 2026-07 known)."""
        assert legal_regime(date(2030, 12, 31)) == REGIME_2026


# ===========================================================================
# regime_transition_dates()
# ===========================================================================


class TestRegimeTransitionDates:
    """Trivial validation of the boundary list."""

    def test_returns_three_dates(self) -> None:
        assert len(regime_transition_dates()) == 3

    def test_chronological_order(self) -> None:
        dates = regime_transition_dates()
        for i in range(len(dates) - 1):
            assert dates[i] < dates[i + 1]

    def test_known_values(self) -> None:
        assert regime_transition_dates() == [
            date(2023, 7, 1),
            date(2025, 1, 1),
            date(2026, 7, 1),
        ]


# ===========================================================================
# regime_for_period_range()
# ===========================================================================


class TestRegimeForPeriodRange:
    """Splitting and edge-case behaviour."""

    # -- Fully within one regime -------------------------------------------

    def test_single_segment_same_regime(self) -> None:
        """Period wholly within a.F._2025 returns one segment."""
        segments = regime_for_period_range(date(2025, 6, 1), date(2025, 6, 30))
        assert segments == [(date(2025, 6, 1), date(2025, 6, 30), REGIME_2025)]

    def test_single_segment_early(self) -> None:
        """Period wholly within a.F._vor_2023."""
        segments = regime_for_period_range(date(2020, 1, 1), date(2020, 12, 31))
        assert segments == [(date(2020, 1, 1), date(2020, 12, 31), REGIME_VOR_2023)]

    def test_single_segment_future(self) -> None:
        """Period wholly within n.F._2026."""
        segments = regime_for_period_range(date(2027, 3, 1), date(2027, 3, 31))
        assert segments == [(date(2027, 3, 1), date(2027, 3, 31), REGIME_2026)]

    # -- Spanning two regimes ----------------------------------------------

    def test_span_2025_to_2026(self) -> None:
        """Period crossing the 2026-07-01 boundary → two segments."""
        segments = regime_for_period_range(date(2026, 5, 1), date(2026, 8, 31))
        assert len(segments) == 2
        assert segments[0] == (date(2026, 5, 1), date(2026, 6, 30), REGIME_2025)
        assert segments[1] == (date(2026, 7, 1), date(2026, 8, 31), REGIME_2026)

    def test_span_2024_to_2025(self) -> None:
        """Period crossing 2025-01-01 → two segments."""
        segments = regime_for_period_range(date(2024, 12, 1), date(2025, 1, 31))
        assert len(segments) == 2
        assert segments[0] == (date(2024, 12, 1), date(2024, 12, 31), REGIME_2023)
        assert segments[1] == (date(2025, 1, 1), date(2025, 1, 31), REGIME_2025)

    # -- Spanning multiple regimes -----------------------------------------

    def test_span_three_boundaries(self) -> None:
        """Period spanning all three boundaries → four segments."""
        segments = regime_for_period_range(date(2023, 3, 1), date(2027, 2, 28))
        assert len(segments) == 4
        assert segments[0] == (date(2023, 3, 1), date(2023, 6, 30), REGIME_VOR_2023)
        assert segments[1] == (date(2023, 7, 1), date(2024, 12, 31), REGIME_2023)
        assert segments[2] == (date(2025, 1, 1), date(2026, 6, 30), REGIME_2025)
        assert segments[3] == (date(2026, 7, 1), date(2027, 2, 28), REGIME_2026)

    # -- Edge: range ending exactly on a boundary day ----------------------

    def test_end_on_boundary(self) -> None:
        """Range [2026-06-01, 2026-07-01] — ends exactly on 2026-07-01."""
        segments = regime_for_period_range(date(2026, 6, 1), date(2026, 7, 1))
        assert len(segments) == 2
        assert segments[0] == (date(2026, 6, 1), date(2026, 6, 30), REGIME_2025)
        assert segments[1] == (date(2026, 7, 1), date(2026, 7, 1), REGIME_2026)

    def test_start_on_boundary(self) -> None:
        """Range [2026-07-01, 2026-08-31] — starts exactly on 2026-07-01."""
        segments = regime_for_period_range(date(2026, 7, 1), date(2026, 8, 31))
        assert len(segments) == 1
        assert segments[0] == (date(2026, 7, 1), date(2026, 8, 31), REGIME_2026)

    def test_single_day_on_boundary(self) -> None:
        """Single day 2026-07-01 → one segment in n.F."""
        segments = regime_for_period_range(date(2026, 7, 1), date(2026, 7, 1))
        assert len(segments) == 1
        assert segments[0] == (date(2026, 7, 1), date(2026, 7, 1), REGIME_2026)

    # -- Edge: start == end ------------------------------------------------

    def test_single_day(self) -> None:
        segments = regime_for_period_range(date(2025, 6, 15), date(2025, 6, 15))
        assert segments == [(date(2025, 6, 15), date(2025, 6, 15), REGIME_2025)]

    # -- Error cases -------------------------------------------------------

    def test_end_before_start_raises(self) -> None:
        """end < start should raise ValueError."""
        with pytest.raises(ValueError, match="must be >= start"):
            regime_for_period_range(date(2026, 7, 1), date(2026, 6, 1))


# ===========================================================================
# regime_banner()
# ===========================================================================


class TestRegimeBanner:
    """German banners for each regime tag."""

    def test_banner_vor_2023(self) -> None:
        banner = regime_banner(REGIME_VOR_2023)
        assert "vor dem" in banner
        assert "01.07.2023" in banner
        assert "a.F." in banner or "alte" in banner

    def test_banner_2023(self) -> None:
        banner = regime_banner(REGIME_2023)
        assert "01.07.2023" in banner
        assert "31.12.2024" in banner
        assert "Bürgergeld" in banner

    def test_banner_2025(self) -> None:
        banner = regime_banner(REGIME_2025)
        assert "01.01.2025" in banner
        assert "30.06.2026" in banner
        assert "Regelbedarf" in banner

    def test_banner_2026(self) -> None:
        banner = regime_banner(REGIME_2026)
        assert "01.07.2026" in banner
        assert "n.F." in banner
        assert "Vermögensfreibeträge" in banner

    def test_unknown_regime_raises(self) -> None:
        with pytest.raises(ValueError, match="Unbekanntes Regime"):
            regime_banner("nonexistent")

    def test_all_banners_nonempty(self) -> None:
        for tag in [REGIME_VOR_2023, REGIME_2023, REGIME_2025, REGIME_2026]:
            assert len(regime_banner(tag)) > 20


# ===========================================================================
# Goldset scenario assertions
# ===========================================================================
#
# These are structural regime assertions only (no LLM or DB needed). Full
# goldset validation (correct calculation results per regime) belongs to
# the integration-eval suite and WP-23.
#
# Goldset reference:
#   GS-004: cross-boundary SGB II case spanning 2025-2026
#   GS-005: post-2026 case (n.F.)
#   GS-006: pre-2023 case (a.F._vor_2023)
#   GS-008: 2024 case (a.F._2023)


class TestGoldsetRegimeScenarios:
    """Regime assertions for goldset cases GS-004, GS-005, GS-006, GS-008."""

    def test_gs004_cross_boundary_2025_to_2026(self) -> None:
        """GS-004 spans pre-2026 and post-2026 regimes.

        The Bescheid covers a period from May 2026 to August 2026,
        crossing the 2026-07-01 boundary.
        """
        segments = regime_for_period_range(date(2026, 5, 1), date(2026, 8, 31))
        # Must have two segments: a.F._2025 and n.F._2026
        assert len(segments) == 2
        assert segments[0][2] == REGIME_2025
        assert segments[1][2] == REGIME_2026
        # The boundary is exactly 2026-07-01
        assert segments[0][1] == date(2026, 6, 30)
        assert segments[1][0] == date(2026, 7, 1)

    def test_gs005_post_2026_regime(self) -> None:
        """GS-005 is a post-2026 case entirely in n.F.

        The Bescheid date (or the relevant period) is after 2026-07-01,
        so the regime is n.F._2026 throughout.
        """
        # Example: a Bescheid with a decision date in late 2026
        regime = legal_regime(date(2026, 9, 15))
        assert regime == REGIME_2026

        # Any single-month period in late 2026 is wholly n.F.
        segments = regime_for_period_range(date(2026, 10, 1), date(2026, 10, 31))
        assert len(segments) == 1
        assert segments[0][2] == REGIME_2026

    def test_gs006_pre_2023_regime(self) -> None:
        """GS-006 is a pre-2023 case entirely in a.F._vor_2023.

        The Bescheid dates from before the Bürgergeld reform, so all
        calculations must use pre-2023 rules.
        """
        regime = legal_regime(date(2022, 11, 1))
        assert regime == REGIME_VOR_2023

        # A three-month period in early 2022 is wholly a.F._vor_2023
        segments = regime_for_period_range(date(2022, 1, 1), date(2022, 3, 31))
        assert len(segments) == 1
        assert segments[0][2] == REGIME_VOR_2023

    def test_gs008_2024_regime(self) -> None:
        """GS-008 is a 2024 case entirely in a.F._2023.

        The Bescheid falls within the 2023-07-01 to 2024-12-31 window,
        so the Bürgergeld-Gesetz rules (a.F._2023) apply.
        """
        regime = legal_regime(date(2024, 6, 1))
        assert regime == REGIME_2023

        # A single month in 2024-06 is wholly a.F._2023
        segments = regime_for_period_range(date(2024, 6, 1), date(2024, 6, 30))
        assert len(segments) == 1
        assert segments[0][2] == REGIME_2023

        # Even a longer period that stays within 2024 boundaries
        segments = regime_for_period_range(date(2024, 3, 1), date(2024, 11, 30))
        assert len(segments) == 1
        assert segments[0][2] == REGIME_2023


# ===========================================================================
# Integration smoke: param() with regime filter
# ===========================================================================
#
# These tests verify that the ``param()`` function in parameter_store.py
# correctly handles the new ``regime`` kwarg.  They use the in-memory cache
# directly (no DB).  The cache is populated manually so the tests are
# deterministic and self-contained.


class TestParamWithRegimeFilter:
    """Test the ``regime`` kwarg on ``app.services.parameter_store.param()``.

    Relies on the module-level ``_parameter_cache`` being populated via
    :func:`reload_parameter_cache` or direct assignment.  These tests use
    direct assignment to avoid a DB dependency.
    """

    def _populate_cache(self) -> None:
        """Replace the module cache with known test data.

        Two parameters with the same key and date but different regimes.
        """
        # pylint: disable=import-outside-toplevel
        from app.services import parameter_store as ps

        ps._parameter_cache = {
            ("test.param", "sgb2"): [
                {
                    "value_numeric": 502.0,
                    "value_json": None,
                    "value_text": None,
                    "unit": "EUR",
                    "valid_from": date(2026, 1, 1),
                    "valid_to": date(2026, 6, 30),
                    "review_status": "verified",
                    "regime": REGIME_2025,
                    "notes": "Old regime value",
                },
                {
                    "value_numeric": 563.0,
                    "value_json": None,
                    "value_text": None,
                    "unit": "EUR",
                    "valid_from": date(2026, 7, 1),
                    "valid_to": None,
                    "review_status": "verified",
                    "regime": REGIME_2026,
                    "notes": "New regime value",
                },
                {
                    "value_numeric": 400.0,
                    "value_json": None,
                    "value_text": None,
                    "unit": "EUR",
                    "valid_from": date(2020, 1, 1),
                    "valid_to": date(2022, 12, 31),
                    "review_status": "verified",
                    "regime": REGIME_VOR_2023,
                    "notes": "Pre-2023 value",
                },
            ],
        }

    def _cleanup_cache(self) -> None:
        """Restore empty cache."""
        # pylint: disable=import-outside-toplevel
        from app.services import parameter_store as ps

        ps._parameter_cache = {}

    # -- Happy paths -------------------------------------------------------

    def test_param_with_regime_filter(self) -> None:
        """Explicit regime filter returns the correct entry."""
        self._populate_cache()
        try:
            from app.services.parameter_store import param

            # On a date where both regimes are valid, regime filter picks
            # the right one.
            result = param("test.param", date(2026, 8, 1), regime=REGIME_2026)
            assert result["value"] == 563.0
            assert result["regime"] == REGIME_2026
            assert result["error"] is None
        finally:
            self._cleanup_cache()

    def test_param_without_regime_fallback(self) -> None:
        """Without regime, falls back to date-based lookup (existing behaviour)."""
        self._populate_cache()
        try:
            from app.services.parameter_store import param

            result = param("test.param", date(2026, 8, 1))
            # Should find the n.F._2026 entry (valid_from <= date and valid_to
            # is NULL, meaning open-ended).
            assert result["value"] == 563.0
            assert result["regime"] == REGIME_2026
        finally:
            self._cleanup_cache()

    def test_param_regime_mismatch_returns_error(self) -> None:
        """Regime filter with no matching entry returns error."""
        self._populate_cache()
        try:
            from app.services.parameter_store import param

            # A date that matches the valid window but with a regime filter
            # that doesn't exist.
            result = param("test.param", date(2022, 6, 1), regime=REGIME_2026)
            assert result["value"] is None
            assert result["error"] is not None
            assert "regime=n.F._2026" in result["error"]
        finally:
            self._cleanup_cache()

    def test_param_regime_on_boundary_date(self) -> None:
        """On a boundary date, regime filter picks the correct entry."""
        self._populate_cache()
        try:
            from app.services.parameter_store import param

            # 2026-07-01: the n.F._2026 entry has valid_from=2026-07-01,
            # so it should match.
            result = param("test.param", date(2026, 7, 1), regime=REGIME_2026)
            assert result["value"] == 563.0
            assert result["error"] is None

            # 2026-07-01: the a.F._2025 entry has valid_to=2026-06-30,
            # so it should NOT match.
            result = param("test.param", date(2026, 7, 1), regime=REGIME_2025)
            assert result["value"] is None
            assert result["error"] is not None
        finally:
            self._cleanup_cache()

    def test_param_regime_nonexistent_key(self) -> None:
        """Unknown key with regime filter → error."""
        from app.services.parameter_store import param

        result = param("nonexistent.key", date(2026, 8, 1), regime=REGIME_2026)
        assert result["value"] is None
        assert result["error"] is not None
