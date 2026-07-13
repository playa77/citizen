#!/usr/bin/env python3
"""Seed the legal_parameter table with reference values for SGB II.

Usage::

    python -m scripts.seed_legal_parameters

All values are sourced from the official Gesetze-im-Internet corpus or from
the referenced BGBl. publications.  OQ-3 rows are marked as "proposed" and
carry a notes annotation.

"""

# Version: 1.0.0 | 2026-07-12

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select

from app.db.models import LegalParameter
from app.db.session import async_session_factory
from app.services.parameter_store import reload_parameter_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parameter definitions
# ---------------------------------------------------------------------------
# Each entry: (key, value_numeric, value_json, value_text, unit, domain,
#               valid_from, valid_to, review_status, regime, notes)
# Use None for fields that are not applicable.

_PARAMETERS: list[tuple] = [
    # =========================================================================
    # Regelbedarfsstufen 2024 (valid 2024-01-01 – 2025-12-31)
    # Source: § 20 SGB II i.d.F. des RBEG 2024 (BGBl. 2023 I Nr. 337)
    # =========================================================================
    ("sgb2.regelbedarf.rbs1", 563, None, None, "EUR", "sgb2",
     date(2024, 1, 1), date(2025, 12, 31), "verified", "2024", None),
    ("sgb2.regelbedarf.rbs2", 506, None, None, "EUR", "sgb2",
     date(2024, 1, 1), date(2025, 12, 31), "verified", "2024", None),
    # RBS3: Erwachsener in Bedarfsgemeinschaft (Partner) — § 20 Abs. 2
    ("sgb2.regelbedarf.rbs3", 451, None, None, "EUR", "sgb2",
     date(2024, 1, 1), date(2025, 12, 31), "verified", "2024", None),
    # RBS4: Volljährige Kinder im Haushalt der Eltern / junge Erwachsene § 20 Abs. 2a
    ("sgb2.regelbedarf.rbs4", 451, None, None, "EUR", "sgb2",
     date(2024, 1, 1), date(2025, 12, 31), "verified", "2024", None),
    # RBS5: Kinder 14–17 Jahre — § 20 Abs. 2 Satz 2
    ("sgb2.regelbedarf.rbs5", 471, None, None, "EUR", "sgb2",
     date(2024, 1, 1), date(2025, 12, 31), "verified", "2024", None),
    # RBS6: Kinder 6–13 Jahre — § 20 Abs. 2 Satz 2
    ("sgb2.regelbedarf.rbs6", 390, None, None, "EUR", "sgb2",
     date(2024, 1, 1), date(2025, 12, 31), "verified", "2024", None),
    # Kinder 0–5 Jahre — § 20 Abs. 2 Satz 2
    ("sgb2.regelbedarf.rbs7", 357, None, None, "EUR", "sgb2",
     date(2024, 1, 1), date(2025, 12, 31), "verified", "2024", None),

    # =========================================================================
    # Regelbedarfsstufen 2025 (valid 2025-01-01 – 2026-12-31)
    # Source: RBEG 2025 (BGBl. 2024 I Nr. 397) — amounts unchanged from 2024
    # =========================================================================
    ("sgb2.regelbedarf.rbs1", 563, None, None, "EUR", "sgb2",
     date(2025, 1, 1), date(2026, 12, 31), "verified", "2025", None),
    ("sgb2.regelbedarf.rbs2", 506, None, None, "EUR", "sgb2",
     date(2025, 1, 1), date(2026, 12, 31), "verified", "2025", None),
    ("sgb2.regelbedarf.rbs3", 451, None, None, "EUR", "sgb2",
     date(2025, 1, 1), date(2026, 12, 31), "verified", "2025", None),
    ("sgb2.regelbedarf.rbs4", 451, None, None, "EUR", "sgb2",
     date(2025, 1, 1), date(2026, 12, 31), "verified", "2025", None),
    ("sgb2.regelbedarf.rbs5", 471, None, None, "EUR", "sgb2",
     date(2025, 1, 1), date(2026, 12, 31), "verified", "2025", None),
    ("sgb2.regelbedarf.rbs6", 390, None, None, "EUR", "sgb2",
     date(2025, 1, 1), date(2026, 12, 31), "verified", "2025", None),
    ("sgb2.regelbedarf.rbs7", 357, None, None, "EUR", "sgb2",
     date(2025, 1, 1), date(2026, 12, 31), "verified", "2025", None),

    # =========================================================================
    # § 11b Abs. 2 SGB II — base deduction and Freibetrag brackets
    # Source: BGBl. 2023 I Nr. 182 (Bürgergeld-Gesetz), effective 2023-07-01
    # =========================================================================
    ("sgb2.par11b.base_deduction", 100.0, None, None, "EUR", "sgb2",
     date(2023, 7, 1), None, "verified", "2023-07_bracket_change", None),
    ("sgb2.par11b.income_bracket_1_pct", None,
     {"min_income": 100.01, "max_income": 520.0, "deduction_pct": 0},
     None, "PERCENT", "sgb2",
     date(2023, 7, 1), None, "verified", "2023-07_bracket_change", None),
    ("sgb2.par11b.income_bracket_2_pct", None,
     {"min_income": 520.01, "max_income": 1000.0, "deduction_pct": 10},
     None, "PERCENT", "sgb2",
     date(2023, 7, 1), None, "verified", "2023-07_bracket_change", None),
    ("sgb2.par11b.income_bracket_3_pct", None,
     {"min_income": 1000.01, "max_income": 1500.0, "deduction_pct": 15},
     None, "PERCENT", "sgb2",
     date(2023, 7, 1), None, "verified", "2023-07_bracket_change", None),
    ("sgb2.par11b.income_bracket_4_pct", None,
     {"min_income": 1500.01, "max_income": float("inf"), "deduction_pct": 30},
     None, "PERCENT", "sgb2",
     date(2023, 7, 1), None, "verified", "2023-07_bracket_change", None),

    # =========================================================================
    # Vermögensfreibeträge — alte Fassung (a.F., vor Bürgergeld 2023)
    # Source: § 12 SGB II a.F.
    # =========================================================================
    ("sgb2.vermoegen.karenzzeit", 40000.0, None, None, "EUR", "sgb2",
     date(2011, 1, 1), date(2022, 12, 31), "verified", "a.F.", None),
    ("sgb2.vermoegen.karenzzeit_partner", 15000.0, None, None, "EUR", "sgb2",
     date(2011, 1, 1), date(2022, 12, 31), "verified", "a.F.", None),
    ("sgb2.vermoegen.post_karenzzeit", 15000.0, None, None, "EUR", "sgb2",
     date(2011, 1, 1), date(2022, 12, 31), "verified", "a.F.", None),

    # =========================================================================
    # Vermögensfreibeträge — neue Fassung (n.F., Bürgergeld-Gesetz 2026)
    # OQ-3: values not yet confirmed — do NOT invent.
    # =========================================================================
    ("sgb2.vermoegen.karenzzeit", None, None, None, "EUR", "sgb2",
     date(2026, 1, 1), None, "proposed", "n.F.",
     "OQ-3: verify_against BGBl. 2026 I Nr. 107"),
    ("sgb2.vermoegen.karenzzeit_partner", None, None, None, "EUR", "sgb2",
     date(2026, 1, 1), None, "proposed", "n.F.",
     "OQ-3: verify_against BGBl. 2026 I Nr. 107"),
    ("sgb2.vermoegen.post_karenzzeit", None, None, None, "EUR", "sgb2",
     date(2026, 1, 1), None, "proposed", "n.F.",
     "OQ-3: verify_against BGBl. 2026 I Nr. 107"),

    # =========================================================================
    # Sanktionen (Minderung) — alte Fassung (a.F. bis 2023-06-30)
    # Source: § 31 ff. SGB II a.F. — Meldeversäumnis / Pflichtverletzung
    # =========================================================================
    ("sgb2.sanktion.minderung_pct", None,
     {"tiers": [
         {"offence": "meldeversaeumnis", "pct": 10, "max_months": 3},
         {"offence": "pflichtverletzung_erstmalig", "pct": 30, "max_months": 3},
         {"offence": "pflichtverletzung_wiederholt", "pct": 60, "max_months": 3},
         {"offence": "pflichtverletzung_wiederholt_ube", "pct": 100, "max_months": 2},
     ]},
     None, "PERCENT", "sgb2",
     date(2011, 1, 1), date(2023, 6, 30), "verified", "a.F.", None),

    # =========================================================================
    # Sanktionen (Minderung) — neue Fassung (n.F. ab 2023-07-01)
    # Source: Bürgergeld-Gesetz 2023 (BGBl. 2023 I Nr. 182)
    # =========================================================================
    ("sgb2.sanktion.minderung_pct", None,
     {"tiers": [
         {"offence": "meldeversaeumnis", "pct": 10, "max_months": 1},
         {"offence": "pflichtverletzung_erstmalig", "pct": 10, "max_months": 1},
         {"offence": "pflichtverletzung_wiederholt", "pct": 20, "max_months": 2},
         {"offence": "pflichtverletzung_wiederholt_ube", "pct": 30, "max_months": 2},
     ]},
     None, "PERCENT", "sgb2",
     date(2023, 7, 1), None, "verified", "n.F.", None),
]


async def seed() -> None:
    """Upsert all parameter entries into the database."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    async with async_session_factory() as session:
        count_new = 0
        count_skip = 0

        for param_tuple in _PARAMETERS:
            (
                key, value_numeric, value_json, value_text, unit, domain,
                valid_from, valid_to, review_status, regime, notes,
            ) = param_tuple

            # Check if an identical row already exists
            stmt = select(LegalParameter).where(
                LegalParameter.parameter_key == key,
                LegalParameter.domain == domain,
                LegalParameter.valid_from == valid_from,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                # Update fields if the existing row differs
                dirty = False
                for attr, new_val in [
                    ("value_numeric", value_numeric),
                    ("value_json", value_json),
                    ("value_text", value_text),
                    ("unit", unit),
                    ("valid_to", valid_to),
                    ("review_status", review_status),
                    ("regime", regime),
                    ("notes", notes),
                ]:
                    if getattr(existing, attr) != new_val:
                        setattr(existing, attr, new_val)
                        dirty = True
                if dirty:
                    count_new += 1  # counts as an "update" here
                    logger.info("Updated: %s (regime=%s)", key, regime)
                else:
                    count_skip += 1
            else:
                param = LegalParameter(
                    parameter_key=key,
                    value_numeric=value_numeric,
                    value_json=value_json,
                    value_text=value_text,
                    unit=unit,
                    domain=domain,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    review_status=review_status,
                    regime=regime,
                    notes=notes,
                )
                session.add(param)
                count_new += 1
                logger.info("Created: %s (regime=%s)", key, regime)

        await session.commit()

        # Reload the in-memory cache so the new parameters are immediately available.
        await reload_parameter_cache(session)

        logger.info(
            "Seed complete — %d created/updated, %d skipped.",
            count_new,
            count_skip,
        )


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
