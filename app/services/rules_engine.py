"""Deterministic SGB II / SGB XII calculation rules engine.

Pure functions that compute correct monetary values according to German
Sozialrecht rules.  No I/O, no LLM calls — all math is locally verifiable.

Architecture:
    The LLM *extracts* structured data from a Jobcenter document.  This module
    *computes* what the correct values should be.  A second LLM call then
    *explains* any discrepancies in plain German.

Rules implemented:
    - Regelbedarf lookup (by year and person type)
    - Erwerbstätigenfreibetrag (§ 11b SGB II) — tiered brackets
    - Aufrechnung bei Darlehen (§ 42a SGB II) — 5 % of Regelbedarf
    - KdU arithmetic validation (subtotal vs. total)
    - Income offset arithmetic (income minus freibetrag)
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Regelbedarf lookup tables (monthly, in EUR)
# ---------------------------------------------------------------------------

# Person type → Regelbedarfsstufe mapping.
_PERSON_TYPE_TO_STUFE: dict[str, int] = {
    "alleinstehend": 1,
    "alleinerziehend": 1,
    "partner": 2,
}

# Year → Stufe → monthly Regelbedarf in EUR.
_REGELBEDARF_TABLE: dict[int, dict[int, float]] = {
    2025: {
        1: 563.00,  # Alleinstehende / Alleinerziehende
        2: 506.00,  # Partner in Bedarfsgemeinschaft
    },
    # Additional years can be added here as new Regelbedarfsstufen-
    # fortentwicklungsverordnungen are published.
}


def supported_years() -> list[int]:
    """Return a sorted list of years for which Regelbedarf data is available."""
    return sorted(_REGELBEDARF_TABLE.keys())


# ---------------------------------------------------------------------------
# Freibetrag brackets (Erwerbstätigenfreibetrag § 11b SGB II)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FreibetragBracket:
    """A single bracket in the Erwerbstätigenfreibetrag computation."""

    from_: float  # inclusive lower bound (EUR)
    to: float  # inclusive upper bound (EUR)
    rate: float  # e.g. 0.20 for 20 %


_FREIBETRAG_BRACKETS: tuple[_FreibetragBracket, ...] = (
    _FreibetragBracket(from_=0.00, to=100.00, rate=1.00),
    _FreibetragBracket(from_=100.01, to=520.00, rate=0.20),
    _FreibetragBracket(from_=520.01, to=1000.00, rate=0.30),
    _FreibetragBracket(from_=1000.01, to=1200.00, rate=0.10),
)

# When a minor child lives in the household, the upper bracket extends.
_FREIBETRAG_UPPER_LIMIT_WITH_CHILD: float = 1500.00


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_regelbedarf(
    year: int | None,
    person_type: str | None,
    param_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Look up the correct Regelbedarf for a given year and person type.

    Parameters
    ----------
    year :
        Calendar year of the Leistungszeitraum, e.g. 2025.
    person_type :
        One of ``"alleinstehend"``, ``"alleinerziehend"``, ``"partner"``.
    param_overrides :
        Optional dict with pre-fetched DB parameters keyed by
        ``"rbs1"`` / ``"rbs2"``.  When provided the hardcoded lookup
        table is bypassed entirely.

    Returns
    -------
    dict
        Keys:
        - ``value`` (``float | None``): expected monthly Regelbedarf in EUR.
        - ``stufe`` (``int | None``): Regelbedarfsstufe (1 or 2).
        - ``error`` (``str | None``): description if lookup failed.
    """
    # ── DB-provided override path ───────────────────────────────────
    if param_overrides:
        pt_lower_ov = person_type.strip().lower() if person_type else ""
        stufe_ov = _PERSON_TYPE_TO_STUFE.get(pt_lower_ov)
        if stufe_ov is None:
            return {
                "value": None,
                "stufe": None,
                "error": f"Unbekannter Personentyp: {person_type!r}",
            }
        rbs_key = f"rbs{stufe_ov}"
        param = param_overrides.get(rbs_key, {})
        value = param.get("value")
        error = param.get("error")
        if value is None:
            return {
                "value": None,
                "stufe": stufe_ov,
                "error": error or f"Keine Parameter für Regelbedarfsstufe {stufe_ov} in den übergebenen Daten.",
            }
        return {
            "value": float(value),
            "stufe": stufe_ov,
            "error": None,
        }

    # ── Hardcoded fallback path ─────────────────────────────────────
    if year is None:
        return {
            "value": None,
            "stufe": None,
            "error": "Kein Jahr angegeben — Regelbedarf kann nicht bestimmt werden.",
        }

    if person_type is None:
        return {
            "value": None,
            "stufe": None,
            "error": "Kein Personentyp angegeben — Regelbedarf kann nicht bestimmt werden.",
        }

    pt_lower = person_type.strip().lower()
    stufe = _PERSON_TYPE_TO_STUFE.get(pt_lower)
    if stufe is None:
        return {
            "value": None,
            "stufe": None,
            "error": f"Unbekannter Personentyp: {person_type!r}",
        }

    year_table = _REGELBEDARF_TABLE.get(year)
    if year_table is None:
        nearest = _nearest_available_year(year)
        if nearest is None:
            return {
                "value": None,
                "stufe": stufe,
                "error": f"Keine Regelbedarfsdaten für Jahr {year} verfügbar.",
            }
        return {
            "value": _REGELBEDARF_TABLE[nearest][stufe],
            "stufe": stufe,
            "error": (
                f"Keine Daten für {year} — verwende nächstes verfügbares Jahr "
                f"({nearest}). Bitte manuell prüfen."
            ),
        }

    return {
        "value": year_table[stufe],
        "stufe": stufe,
        "error": None,
    }


def compute_freibetrag(
    brutto_einkommen: float | None,
    has_minor_child: bool | None = None,
    param_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute the correct Erwerbstätigenfreibetrag (§ 11b SGB II).

    Parameters
    ----------
    brutto_einkommen :
        Monthly gross earned income in EUR.
    has_minor_child :
        Whether at least one minor child lives in the Bedarfsgemeinschaft.
        ``None`` means "unknown" — the standard 1,200 EUR cap is used.
    param_overrides :
        Optional dict with pre-fetched DB parameters.  When it contains
        ``"freibetrag_brackets"`` the hardcoded bracket table is replaced.

    Returns
    -------
    dict
        Keys:
        - ``value`` (``float | None``): computed Freibetrag in EUR.
        - ``brackets_applied`` (``list[dict]``): each bracket used in the
          computation with ``from_``, ``to``, ``rate``, ``amount``.
        - ``upper_limit`` (``float``): the effective gross income cap.
        - ``error`` (``str | None``): description if computation failed.
    """
    if brutto_einkommen is None:
        return {
            "value": None,
            "brackets_applied": [],
            "upper_limit": 1200.00,
            "error": "Kein Bruttoeinkommen angegeben — Freibetrag kann nicht berechnet werden.",
        }

    if brutto_einkommen <= 0:
        return {
            "value": 0.0,
            "brackets_applied": [],
            "upper_limit": 1200.00,
            "error": None,
        }

    # ── DB-provided override path ───────────────────────────────────
    if param_overrides and "freibetrag_brackets" in param_overrides:
        brackets_data = param_overrides["freibetrag_brackets"]
        base_allowance = param_overrides.get("freibetrag_base_allowance", 100.0)
        child_upper = param_overrides.get("freibetrag_child_upper_limit", 1500.0)

        if has_minor_child:
            upper_limit = child_upper
        else:
            upper_limit = 1200.0

        total = base_allowance
        applied: list[dict[str, Any]] = []
        applied.append({"from_": 0.0, "to": base_allowance, "rate": 1.0, "amount": base_allowance})

        remaining = brutto_einkommen - base_allowance
        for band in brackets_data:
            lower = float(band["from_"])
            upper = min(float(band["to"]), upper_limit)
            rate = float(band["rate"])
            if remaining <= 0:
                break
            in_band = min(remaining, upper - lower)
            amount = round(in_band * rate, 2)
            total += amount
            applied.append({"from_": lower, "to": upper, "rate": rate, "amount": amount})
            remaining -= in_band

        total = round(total, 2)
        return {
            "value": total,
            "brackets_applied": applied,
            "upper_limit": upper_limit,
            "error": None,
        }

    # Select bracket set based on child status.
    upper_limit = _FREIBETRAG_UPPER_LIMIT_WITH_CHILD if has_minor_child else 1200.00

    # Build brackets.  The last bracket is extended from 1200 to upper_limit
    # when upper_limit > 1200 (e.g. with a minor child).
    brackets: list[_FreibetragBracket] = []
    for b in _FREIBETRAG_BRACKETS:
        if b.from_ >= upper_limit:
            break
        if b.to > upper_limit:
            brackets.append(_FreibetragBracket(from_=b.from_, to=upper_limit, rate=b.rate))
            break
        # If this is the last bracket and upper_limit exceeds its to, extend it.
        if b is _FREIBETRAG_BRACKETS[-1] and upper_limit > b.to:
            brackets.append(_FreibetragBracket(from_=b.from_, to=upper_limit, rate=b.rate))
        else:
            brackets.append(b)

    total = 0.0
    applied: list[dict[str, Any]] = []

    for b in brackets:
        if brutto_einkommen <= b.from_:
            # Income doesn't reach this bracket.
            break
        relevant_income = min(brutto_einkommen, b.to) - b.from_
        if relevant_income <= 0:
            continue
        amount = round(relevant_income * b.rate, 2)
        total += amount
        applied.append({
            "from_": b.from_,
            "to": b.to,
            "rate": b.rate,
            "amount": amount,
        })

    total = round(total, 2)

    return {
        "value": total,
        "brackets_applied": applied,
        "upper_limit": upper_limit,
        "error": None,
    }


def compute_aufrechnung(regelbedarf: float | None, aufrechnung_rate: float = 0.05) -> dict[str, Any]:
    """Compute the monthly Aufrechnung for a Darlehen (§ 42a SGB II).

    The legal rate is 5 % of the relevant monthly Regelbedarf.

    Parameters
    ----------
    regelbedarf :
        Monthly Regelbedarf in EUR (e.g. 563.00).
    aufrechnung_rate :
        Decimal rate to apply (default 0.05 = 5 %).  Can be overridden with a
        DB-provided value.

    Returns
    -------
    dict
        Keys:
        - ``value`` (``float | None``): monthly Aufrechnung in EUR.
        - ``rate`` (``float``): the applied percentage.
        - ``error`` (``str | None``): description if computation failed.
    """
    if regelbedarf is None:
        return {
            "value": None,
            "rate": aufrechnung_rate,
            "error": "Kein Regelbedarf angegeben — Aufrechnung kann nicht berechnet werden.",
        }

    if regelbedarf <= 0:
        return {
            "value": 0.0,
            "rate": aufrechnung_rate,
            "error": None,
        }

    return {
        "value": round(regelbedarf * aufrechnung_rate, 2),
        "rate": aufrechnung_rate,
        "error": None,
    }


def check_arithmetic(
    parts: list[float | None],
    expected_total: float | None,
    tolerance: float = 0.02,
) -> dict[str, Any]:
    """Check whether the sum of *parts* equals *expected_total* within *tolerance*.

    Useful for verifying that subtotals (e.g. KdU components) add up to the
    authority's stated total.  Rounds intermediate values to 2 decimal places.

    Parameters
    ----------
    parts :
        Individual amounts that should sum to the total.
    expected_total :
        The authority's stated total.
    tolerance :
        Acceptable rounding difference in EUR (default 0.02).

    Returns
    -------
    dict
        Keys:
        - ``checkable`` (``bool``): whether the check could be performed.
        - ``expected_total`` (``float | None``): the authority's stated total.
        - ``computed_total`` (``float | None``): the sum of parts.
        - ``discrepancy`` (``float | None``): difference (computed - expected).
        - ``error`` (``str | None``): description if check failed.
    """
    if expected_total is None:
        return {
            "checkable": False,
            "expected_total": None,
            "computed_total": None,
            "discrepancy": None,
            "error": "Kein erwarteter Gesamtbetrag angegeben.",
        }

    valid_parts = [p for p in parts if p is not None]
    if not valid_parts:
        return {
            "checkable": False,
            "expected_total": expected_total,
            "computed_total": None,
            "discrepancy": None,
            "error": "Keine Einzelbeträge zum Aufsummieren vorhanden.",
        }

    computed = round(sum(valid_parts), 2)
    discrepancy = round(computed - expected_total, 2)

    return {
        "checkable": True,
        "expected_total": expected_total,
        "computed_total": computed,
        "discrepancy": discrepancy,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Orchestrator: process an extraction into calculation entries
# ---------------------------------------------------------------------------


def _discrepancy_result(
    label: str,
    checkable: bool,
    authority_value: float | None,
    computed_value: float | None,
    relevant_rule: str,
    computation_detail: str,
    commentary_template: str = "{}",
) -> dict[str, Any]:
    """Build a single ``calculations_found`` entry from computed results.

    ``commentary_template`` may contain ``{computed}``, ``{authority}``,
    ``{diff}`` as format placeholders.
    """
    if not checkable or computed_value is None:
        return {
            "label": label,
            "document_values": {
                "extracted_numbers": _clean_numbers({"authority": authority_value}),
                "authority_calculation": "",
            },
            "computed_values": {
                "deterministic_result": computed_value,
                "computation_detail": computation_detail,
            },
            "correct_calculation": "",
            "discrepancy_found": False,
            "discrepancy_amount_eur": 0.0,
            "discrepancy_direction": "keine",
            "relevant_rule": relevant_rule,
            "commentary": computation_detail,
        }

    diff = round((computed_value or 0.0) - (authority_value or 0.0), 2)
    discrepancy = abs(diff) >= 0.02

    if discrepancy:
        direction = "zulasten" if diff > 0 else "zugunsten"
    else:
        direction = "keine"

    commentary = commentary_template.format(
        computed=f"{computed_value:.2f}",
        authority=f"{authority_value:.2f}",
        diff=f"{abs(diff):.2f}",
    )

    return {
        "label": label,
        "document_values": {
            "extracted_numbers": _clean_numbers({"authority": authority_value}),
            "authority_calculation": "",
        },
        "computed_values": {
            "deterministic_result": computed_value,
            "computation_detail": computation_detail,
        },
        "correct_calculation": f"{computed_value:.2f} EUR",
        "discrepancy_found": discrepancy,
        "discrepancy_amount_eur": abs(diff) if discrepancy else 0.0,
        "discrepancy_direction": direction,
        "relevant_rule": relevant_rule,
        "commentary": commentary,
    }


def process_extraction(extraction: dict[str, Any], param_overrides: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Take an LLM-extracted structured document and run all deterministic checks.

    Parameters
    ----------
    extraction :
        Parsed JSON from the extraction LLM call.  Expected keys are
        defined by the extraction prompt.  All numeric fields are optional;
        the engine skips any check for which required data is missing.
    param_overrides :
        Optional dict with pre-fetched DB parameters.  Passed through to
        ``compute_regelbedarf``, ``compute_freibetrag``, and
        ``compute_aufrechnung`` to allow DB-backed overrides of hardcoded
        constants.

    Returns
    -------
    list[dict[str, Any]]
        One entry per checked calculation, with the same shape as the
        current ``calculations_found`` output (including new
        ``computed_values`` field).
    """
    results: list[dict[str, Any]] = []

    # -- Convenience helpers -------------------------------------------------
    def _get(path: str, default: Any = None) -> Any:
        """Access nested dict by dot-separated path."""
        keys = path.split(".")
        val: Any = extraction
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
            if val is None:
                return default
        return val if val is not None else default

    def _num(path: str) -> float | None:
        val = _get(path)
        if val is None:
            return None
        try:
            return round(float(val), 2)
        except (TypeError, ValueError):
            return None

    def _bool_or_none(path: str) -> bool | None:
        val = _get(path)
        if val is None:
            return None
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            sl = val.strip().lower()
            if sl in ("true", "ja", "yes", "1"):
                return True
            if sl in ("false", "nein", "no", "0", "nein"):
                return False
        return None

    # -- 1. Regelbedarf check ------------------------------------------------
    person_type = _get("person_type")
    period_year = None
    p_raw = _get("period_year")
    if p_raw is not None:
        try:
            period_year = int(p_raw)
        except (TypeError, ValueError):
            pass

    rb_result = compute_regelbedarf(period_year, person_type, param_overrides=param_overrides)
    rb_authority = _num("extracted_values.regelbedarf_authority")

    if rb_result["error"] is None and rb_authority is not None:
        results.append(
            _discrepancy_result(
                label="Regelbedarf",
                checkable=True,
                authority_value=rb_authority,
                computed_value=rb_result["value"],
                relevant_rule=(
                    f"§ 20 SGB II — Regelbedarfsstufe {rb_result['stufe']} "
                    f"({period_year})"
                ),
                computation_detail=(
                    f"Erwarteter Regelbedarf für {person_type} "
                    f"(Stufe {rb_result['stufe']}, {period_year}): "
                    f"{rb_result['value']:.2f} EUR"
                ),
                commentary_template=(
                    "Die Behörde setzt {authority} EUR an. "
                    "Der gesetzliche Regelbedarf beträgt {computed} EUR. "
                    "Differenz: {diff} EUR."
                ),
            )
        )
    elif rb_result["error"] is not None:
        # Could not compute; emit a non-checkable entry.
        results.append(
            _discrepancy_result(
                label="Regelbedarf",
                checkable=False,
                authority_value=rb_authority,
                computed_value=None,
                relevant_rule="§ 20 SGB II",
                computation_detail=rb_result["error"],
            )
        )

    # -- 2. Erwerbstätigenfreibetrag check ------------------------------------
    brutto = _num("extracted_values.brutto_einkommen")
    has_child = _bool_or_none("has_minor_child")
    fb_result = compute_freibetrag(brutto, has_child, param_overrides=param_overrides)
    fb_authority = _num("extracted_values.freibetrag_authority")

    if fb_result["error"] is None and fb_authority is not None:
        brackets_desc = " + ".join(
            f"{b['rate']*100:.0f} % von {b['from_']:.2f}–{b['to']:.2f} EUR = {b['amount']:.2f} EUR"
            for b in fb_result.get("brackets_applied", [])
        )
        results.append(
            _discrepancy_result(
                label="Erwerbstätigenfreibetrag",
                checkable=True,
                authority_value=fb_authority,
                computed_value=fb_result["value"],
                relevant_rule=(
                    f"§ 11b SGB II — Freibetrag bei Erwerbstätigkeit "
                    f"(Obergrenze {fb_result['upper_limit']:.2f} EUR"
                    + (" mit Kind" if has_child else "")
                    + ")"
                ),
                computation_detail=(
                    f"Bruttoeinkommen: {brutto:.2f} EUR. "
                    f"Berechnung: {brackets_desc or 'Kein Freibetrag'}. "
                    f"Gesamt: {fb_result['value']:.2f} EUR."
                ),
                commentary_template=(
                    "Die Behörde setzt {authority} EUR an. "
                    "Der korrekte Freibetrag beträgt {computed} EUR. "
                    "Differenz: {diff} EUR."
                ),
            )
        )
    elif fb_result["error"] is not None and fb_authority is not None:
        results.append(
            _discrepancy_result(
                label="Erwerbstätigenfreibetrag",
                checkable=False,
                authority_value=fb_authority,
                computed_value=None,
                relevant_rule="§ 11b SGB II",
                computation_detail=fb_result["error"],
            )
        )

    # -- 3. Aufrechnung check -------------------------------------------------
    # The Aufrechnung depends on the Regelbedarf.  Use the computed
    # Regelbedarf if available, otherwise fall back to a value stated
    # in the document that the authority used as their basis.
    aufr_rb = _num("extracted_values.aufrechnung_regelbedarf_used")
    # Prefer our computed RB, fall back to the authority's stated RB.
    effective_rb = rb_result.get("value") if rb_result["error"] is None else aufr_rb
    aufr_rate = param_overrides.get("aufrechnung_rate", 0.05) if param_overrides else 0.05
    aufr_result = compute_aufrechnung(effective_rb, aufrechnung_rate=aufr_rate)
    aufr_authority = _num("extracted_values.aufrechnung_authority")

    if aufr_result["error"] is None and aufr_authority is not None:
        results.append(
            _discrepancy_result(
                label="Aufrechnung (Darlehen)",
                checkable=True,
                authority_value=aufr_authority,
                computed_value=aufr_result["value"],
                relevant_rule=(
                    f"§ 42a SGB II — 5 % des Regelbedarfs "
                    f"({effective_rb:.2f} EUR)"
                ),
                computation_detail=(
                    f"5 % von {effective_rb:.2f} EUR = "
                    f"{aufr_result['value']:.2f} EUR"
                ),
                commentary_template=(
                    "Die Behörde rechnet monatlich {authority} EUR auf. "
                    "5 % des Regelbedarfs ({computed} EUR) ergeben "
                    "{computed} EUR. Differenz: {diff} EUR."
                ),
            )
        )
    elif aufr_result["error"] is not None and aufr_authority is not None:
        results.append(
            _discrepancy_result(
                label="Aufrechnung (Darlehen)",
                checkable=False,
                authority_value=aufr_authority,
                computed_value=None,
                relevant_rule="§ 42a SGB II",
                computation_detail=aufr_result["error"],
            )
        )

    # -- 4. KdU arithmetic check ----------------------------------------------
    kdu_parts = [
        _num("extracted_values.kdu_unterkunft"),
        _num("extracted_values.kdu_heizung"),
        _num("extracted_values.kdu_nebenkosten"),
    ]
    kdu_total = _num("extracted_values.kdu_gesamt_authority")
    kdu_check = check_arithmetic(kdu_parts, kdu_total)
    if kdu_check["checkable"]:
        results.append(
            _discrepancy_result(
                label="Kosten der Unterkunft (KdU)",
                checkable=True,
                authority_value=kdu_total,
                computed_value=kdu_check["computed_total"],
                relevant_rule="§ 22 SGB II — Angemessenheit der Unterkunftskosten",
                computation_detail=(
                    f"Summe der Einzelposten: {kdu_check['computed_total']:.2f} EUR. "
                    f"Behörden-Gesamtbetrag: {kdu_check['expected_total']:.2f} EUR."
                ),
                commentary_template=(
                    "Summe der Einzelposten: {computed} EUR, "
                    "Behörde gibt {authority} EUR an. "
                    "Differenz: {diff} EUR."
                ),
            )
        )

    # -- 5. Income offset check (Einkommensanrechnung) -------------------------
    # If both brutto and freibetrag were computed, check net offset arithmetic.
    netto_auth = _num("extracted_values.netto_einkommen")
    fb_computed = fb_result.get("value")
    if brutto is not None and netto_auth is not None and fb_computed is not None:
        # Simplified: Netto - Freibetrag = anrechenbares Einkommen.
        # The authority may have a different structure, but this checks
        # the most common pattern.
        anrechenbar_computed = round(brutto - fb_computed, 2)
        anrechenbar_authority = _num("extracted_values.anrechenbares_einkommen_authority")
        if anrechenbar_authority is not None:
            results.append(
                _discrepancy_result(
                    label="Einkommensanrechnung (Brutto - Freibetrag)",
                    checkable=True,
                    authority_value=anrechenbar_authority,
                    computed_value=anrechenbar_computed,
                    relevant_rule="§ 11b SGB II — Bereinigung des Einkommens",
                    computation_detail=(
                        f"Brutto {brutto:.2f} EUR - Freibetrag "
                        f"{fb_computed:.2f} EUR = {anrechenbar_computed:.2f} EUR"
                    ),
                    commentary_template=(
                        "Anrechenbares Einkommen: {computed} EUR "
                        "(Behörde: {authority} EUR). Differenz: {diff} EUR."
                    ),
                )
            )

    # -- 6. Auszahlungsbetrag check (Gesamtbetrag) ----------------------------
    # Check if total_payment = regelbedarf + kdu - anrechenbares_einkommen
    # (simplified — actual formulas are more complex).
    rb_c = rb_result.get("value")
    kdu_c = kdu_check.get("computed_total") if kdu_check["checkable"] else kdu_total
    anz_ec = None
    if brutto is not None and fb_computed is not None:
        anz_ec = round(brutto - fb_computed, 2)

    auszahlung_auth = _num("extracted_values.auszahlungsbetrag_authority")
    if rb_c is not None and kdu_c is not None and anz_ec is not None and auszahlung_auth is not None:
        expected_payment = round(rb_c + kdu_c - anz_ec, 2)
        results.append(
            _discrepancy_result(
                label="Auszahlungsbetrag (Gesamt)",
                checkable=True,
                authority_value=auszahlung_auth,
                computed_value=expected_payment,
                relevant_rule="§ 19 SGB II — Arbeitslosengeld II / Sozialgeld",
                computation_detail=(
                    f"Regelbedarf {rb_c:.2f} + KdU {kdu_c:.2f} "
                    f"- anrechenbares Einkommen {anz_ec:.2f} "
                    f"= {expected_payment:.2f} EUR"
                ),
                commentary_template=(
                    "Erwarteter Auszahlungsbetrag: {computed} EUR. "
                    "Behörde: {authority} EUR. Differenz: {diff} EUR."
                ),
            )
        )

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clean_numbers(raw: dict[str, Any]) -> dict[str, Any]:
    """Remove None values from a dict, keeping only non-None entries."""
    return {k: v for k, v in raw.items() if v is not None}


def _nearest_available_year(year: int) -> int | None:
    """Return the closest available year for which we have Regelbedarf data."""
    available = sorted(_REGELBEDARF_TABLE.keys())
    if not available:
        return None
    # Find the nearest year (prefer same or earlier, then later).
    for a in reversed(available):
        if a <= year:
            return a
    return available[0]
