"""WP-131: qualified tenant-side arithmetic, not an applicability decision.

Values and regional designations are date-selected parameters. Unknown coverage,
exceptions or facts never produce a fallback legal amount. Integer/Fraction
arithmetic keeps money cent-exact; outputs remain provisional pending review.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

from app.modules.sdk import Calculator, ParameterSource, civil_is_holiday


def _date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("Ein ausdrücklich bestätigtes ISO-Datum fehlt.")
    return date.fromisoformat(value)


def _integer(value: Any, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name}: ganze nichtnegative Zahl erforderlich.")
    return value


def _confirm(facts: dict[str, Any], name: str, expected: bool = True) -> None:
    if facts.get(name) is not expected:
        raise ValueError(f"{name}: ausdrückliche qualifizierte Bestätigung erforderlich.")


def _parameters(rows: dict[str, Any] | None, key: str, day: date) -> dict[str, Any]:
    row = (rows or {}).get(key, {})
    if row.get("error") or not isinstance(row.get("value"), dict):
        raise ValueError(f"{key}: versionierte Parameter fehlen; keine Ersatzwerte.")
    end = _date(str(row["valid_to"])) if row.get("valid_to") else date.max
    if not _date(str(row.get("valid_from"))) <= day <= end:
        raise ValueError(f"{key}: keine Parameter für das bestätigte Bezugsdatum.")
    return dict(row["value"])


def _designation(facts: dict[str, Any], rows: dict[str, Any] | None, kind: str) -> dict[str, Any]:
    _confirm(facts, "municipality_confirmed")
    day = _date(facts.get("as_of"))
    data = _parameters(rows, "regional_designations", day)
    matches = [
        row
        for row in data["designations"]
        if row["kind"] == kind
        and row["bundesland"] == facts.get("bundesland")
        and facts.get("municipality") in row["municipalities"]
        and _date(row["valid_from"]) <= day <= _date(row["valid_to"])
    ]
    if len(matches) != 1:
        raise ValueError(
            "Gebiet/Geltungszeit der Landesverordnung nicht eindeutig belegt; keine "
            "Standardannahme."
        )
    return matches[0]


def _increase(
    facts: dict[str, Any], p: dict[str, Any], rows: dict[str, Any] | None
) -> dict[str, Any]:
    for name in ("baseline_confirmed", "stability_confirmed", "waiting_period_confirmed"):
        _confirm(facts, name)
    _confirm(facts, "subsidy_exception", False)
    if facts.get("rent_regime") != "ordinary":
        raise ValueError("Index-/Staffelmiete, Bindung und Sonderregeln gesondert prüfen.")
    designation = _designation(facts, rows, "cap")
    baseline = _integer(facts.get("base_rent_cents"), "Dreijahres-Ausgangsmiete", positive=True)
    current = _integer(facts.get("current_rent_cents"), "Aktuelle Nettomiete", positive=True)
    comparison = _integer(facts.get("comparison_rent_cents"), "Vergleichsmiete", positive=True)
    if baseline > current:
        raise ValueError("Mietsenkung/abweichende Ausgangsmiete: Bezugsbasis gesondert prüfen.")
    cap = baseline * (100 + designation["percent"]) // 100
    return {
        "amount_cents": max(current, min(cap, comparison)),
        "cap_cents": cap,
        "comparison_ceiling_cents": comparison,
        "ordinance": designation,
        "scope": (
            "Qualifizierte Prüfobergrenze, keine Zustimmungsempfehlung; Vergleichsmiete "
            "und alle Erhöhungen prüfen."
        ),
    }


def _brake(facts: dict[str, Any], p: dict[str, Any], rows: dict[str, Any] | None) -> dict[str, Any]:
    _confirm(facts, "exceptions_checked")
    for name in (
        "new_build",
        "first_after_comprehensive_modernisation",
        "prior_rent_exception",
        "modernisation_exception",
    ):
        _confirm(facts, name, False)
    designation = _designation(facts, rows, "brake")
    comparison = _integer(facts.get("comparison_rent_cents"), "Vergleichsmiete", positive=True)
    return {
        "amount_cents": comparison * (100 + p["brake_percent"]) // 100,
        "ordinance": designation,
        "scope": (
            "Qualifizierte Prüfobergrenze bei Mietbeginn; keine Rückforderung, Rüge oder"
            " Ausnahme selbst festgestellt."
        ),
    }


def _ratio(numerator: Any, denominator: Any, label: str) -> Fraction:
    if type(numerator) not in (int, float) or type(denominator) not in (int, float):
        raise ValueError(f"{label}: endliche nichtnegative Zahlen erforderlich.")
    # Decimal strings avoid binary-float rounding in fractional square metres
    # and meter readings. Fraction rejects NaN and infinity.
    n, d = Fraction(str(numerator)), Fraction(str(denominator))
    if n < 0 or d <= 0 or n > d:
        raise ValueError(f"{label}: Anteil über Gesamtwert.")
    return n / d


def _costs(facts: dict[str, Any], p: dict[str, Any], rows: dict[str, Any] | None) -> dict[str, Any]:
    _confirm(facts, "allocation_confirmed")
    _confirm(facts, "contract_allocation_confirmed")
    _confirm(facts, "nonallocable_costs_present", False)
    total = _integer(facts.get("total_cost_cents"), "Gesamtkosten")
    area = _ratio(facts.get("tenant_units"), facts.get("total_units"), "Flächen-/Umlageanteil")
    share = area
    if facts.get("cost_category") == "heating":
        _confirm(facts, "heating_exceptions", False)
        if type(facts.get("heating_70_required")) is not bool:
            raise ValueError("Anwendbarkeit der zwingenden 70%-Regel ungeklärt.")
        percent = _integer(facts.get("consumption_share_percent"), "Verbrauchsanteil")
        if not p["heating_min_percent"] <= percent <= p["heating_max_percent"]:
            raise ValueError("Verbrauchsanteil außerhalb des qualifizierten Regelbereichs.")
        if facts["heating_70_required"] and percent != p["heating_max_percent"]:
            raise ValueError("Zwingender 70%-Verbrauchsanteil nicht eingehalten.")
        consumption = _ratio(
            facts.get("tenant_consumption_units"), facts.get("total_consumption_units"), "Verbrauch"
        )
        share = consumption * Fraction(percent, 100) + area * Fraction(100 - percent, 100)
    elif facts.get("cost_category") != "operating":
        raise ValueError("Kostenart oder Sonderregime nicht unterstützt.")
    raw = total * share
    amount = (2 * raw.numerator + raw.denominator) // (2 * raw.denominator)
    advance = _integer(facts.get("advance_paid_cents"), "Vorauszahlungen")
    return {
        "amount_cents": amount,
        "balance_cents": amount - advance,
        "scope": (
            "Arithmetische Umlageprüfung bestätigter umlagefähiger Kosten; kein "
            "Zahlungsanspruch, keine Minderungsquote."
        ),
    }


def _add_months(day: date, months: int) -> date:
    total = day.year * 12 + day.month - 1 + months
    year, month = divmod(total, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _termination(
    facts: dict[str, Any], p: dict[str, Any], rows: dict[str, Any] | None
) -> dict[str, Any]:
    _confirm(facts, "ordinary_residential_confirmed")
    _confirm(facts, "special_contract", False)
    _confirm(facts, "feiertagskalender_bestaetigt")
    additional = facts.get("feiertage_zusaetzlich")
    if not isinstance(additional, list) or len(additional) > 366:
        raise ValueError("Bestätigte zusätzliche örtliche Feiertage fehlen.")
    holidays = {_date(d) for d in additional}
    received = _date(facts.get("received_on"))
    land = facts.get("bundesland")
    # Saturday is a Werktag for §573c, unlike §193 rollover; Sunday is not.
    counted, cutoff = 0, received.replace(day=1)
    while True:
        if not civil_is_holiday(cutoff, land) and cutoff.weekday() != 6 and cutoff not in holidays:
            counted += 1
        if counted == p["notice_workday"]:
            break
        cutoff += timedelta(days=1)
        if cutoff.month != received.month:
            raise ValueError("Feiertagskalender nicht plausibel.")
    effective_cutoff = cutoff
    while (
        effective_cutoff.weekday() >= 5
        or civil_is_holiday(effective_cutoff, land)
        or effective_cutoff in holidays
    ):
        effective_cutoff += timedelta(days=1)
    months = p["tenant_notice_months"] - 1 + (received > effective_cutoff)
    if facts.get("actor") == "landlord":
        handed = _date(facts.get("handed_over_on"))
        if handed > received:
            raise ValueError("Überlassung liegt nach Zugang.")
        months += (
            sum(
                received >= _add_months(handed, years * 12)
                for years in p["landlord_extension_years"]
            )
            * p["landlord_extension_months"]
        )
    elif facts.get("actor") != "tenant":
        raise ValueError("Kündigende Seite ungeklärt.")
    end = _add_months(received, months)
    end = end.replace(day=calendar.monthrange(end.year, end.month)[1])
    return {
        "termination_date": end.isoformat(),
        "third_workday": cutoff.isoformat(),
        "receipt_cutoff": effective_cutoff.isoformat(),
        "scope": (
            "Nur rechnerischer ordentlicher Beendigungstermin; Wirksamkeit, "
            "Kündigungsgrund und Härtefall bleiben ungeprüft."
        ),
    }


def _deposit(
    facts: dict[str, Any], p: dict[str, Any], rows: dict[str, Any] | None
) -> dict[str, Any]:
    _confirm(facts, "cash_deposit_confirmed")
    net = _integer(facts.get("net_rent_cents"), "Nettomiete", positive=True)
    return {
        "amount_cents": net * p["deposit_months"],
        "instalments": p["deposit_instalments"],
        "scope": (
            "Höchstbetrag der vereinbarten Geldsicherheit, keine Fälligkeits- oder "
            "Rückzahlungsfeststellung."
        ),
    }


_PROCESSORS = {
    "rent_increase": _increase,
    "rent_brake": _brake,
    "operating_costs": _costs,
    "ordinary_termination": _termination,
    "deposit": _deposit,
}
_RULES = {
    "rent_increase": "§558 BGB",
    "rent_brake": "§§556d–556g BGB",
    "operating_costs": "§556 BGB; BetrKV; HeizkostenV",
    "ordinary_termination": "§573c BGB",
    "deposit": "§551 BGB",
}


def process_extraction(
    extraction: dict[str, Any], param_overrides: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    kind = extraction.get("calculation_type")
    if kind in (None, "none"):
        return []
    computed: dict[str, Any] = {"deterministic_result": None}
    status = "missing_input"
    try:
        _confirm(extraction, "applicability_confirmed")
        day = _date(extraction.get("as_of"))
        p = _parameters(param_overrides, "tenancy_rules", day)
        if kind not in _PROCESSORS:
            raise ValueError("Unbekannte Berechnung.")
        result = _PROCESSORS[kind](extraction, p, param_overrides)
        computed.update(result)
        amount = result.get("amount_cents")
        computed["deterministic_result"] = amount / 100 if amount is not None else None
        status = "provisional"
        detail = "Parameter vorgeschlagen; menschliche Prüfung ausstehend. " + result["scope"]
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        detail = str(exc)
    amount = computed.get("amount_cents")
    stated = extraction.get(
        "requested_rent_cents" if kind in ("rent_increase", "rent_brake") else "stated_amount_cents"
    )
    difference = (
        stated - amount if type(stated) is int and stated >= 0 and amount is not None else 0
    )
    computed["computation_detail"] = detail
    return [
        {
            "label": str(kind),
            "status": status,
            "document_values": {"extracted_numbers": {}, "authority_calculation": ""},
            "computed_values": computed,
            "correct_calculation": f"{amount/100:.2f} EUR"
            if amount is not None
            else computed.get("termination_date", ""),
            "discrepancy_found": difference > 0,
            "discrepancy_amount_eur": abs(difference) / 100,
            "discrepancy_direction": "zulasten"
            if difference > 0
            else "zugunsten"
            if difference < 0
            else "keine",
            "relevant_rule": _RULES.get(str(kind), ""),
            "commentary": detail,
        }
    ]


async def load_parameters(
    extraction: dict[str, Any], source: ParameterSource
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    kind = extraction.get("calculation_type")
    if kind not in _PROCESSORS:
        return {}, None
    try:
        day = _date(extraction.get("as_of"))
    except ValueError:
        return {}, {"missing_input": "as_of", "parameter_versions": []}
    keys = ["tenancy_rules"]
    if kind in ("rent_increase", "rent_brake"):
        keys.append("regional_designations")
    rows = {key: await source.json(key, day) for key in keys}
    return rows, {
        "as_of": day.isoformat(),
        "parameter_versions": [f'{key}@{row.get("valid_from")}' for key, row in rows.items()],
        "parameters": {
            key: {k: str(v) if isinstance(v, date) else v for k, v in row.items()}
            for key, row in rows.items()
        },
    }


EXTRACTION_PROMPT = (
    "Extrahieren Sie nur ausdrücklich belegte Fakten aus DOKUMENT als JSON, keine "
    "Rechtsanwendung. Unbekannte Werte null, Bestätigungen niemals selbst ableiten. "
    "calculation_type: "
    "rent_increase|rent_brake|operating_costs|ordinary_termination|deposit|none. as_of "
    "YYYY-MM-DD bezeichnet den rechtlich bestätigten Wirksamkeits-/Mietbeginnzeitpunkt. "
    "applicability_confirmed erfordert ausdrückliche qualifizierte Bestätigung. Geldwerte "
    "ganze Cent. Felder: bundesland, municipality (exakter amtlicher Gemeindename), "
    "municipality_confirmed, base_rent_cents (bereinigte Ausgangsmiete vor drei Jahren), "
    "current_rent_cents, comparison_rent_cents, requested_rent_cents, stated_amount_cents,"
    " baseline_confirmed, stability_confirmed (15 Monate), waiting_period_confirmed "
    "(Verlangen nach Jahr), rent_regime ordinary|index|stepped|subsidised|unknown, "
    "subsidy_exception. Mietpreisbremse: exceptions_checked, new_build, "
    "first_after_comprehensive_modernisation, prior_rent_exception, "
    "modernisation_exception (rechtlich geprüft; ohne ausdrücklichen Beleg null). Kosten: "
    "cost_category operating|heating, total_cost_cents, tenant_units, total_units, "
    "tenant_consumption_units, total_consumption_units, consumption_share_percent, "
    "heating_70_required, heating_exceptions, advance_paid_cents, allocation_confirmed, "
    "contract_allocation_confirmed, nonallocable_costs_present. Kündigung: actor "
    "tenant|landlord (nur eigene Angelegenheit des Mieters), received_on, handed_over_on, "
    "ordinary_residential_confirmed, special_contract, feiertagskalender_bestaetigt, "
    "feiertage_zusaetzlich (ISO-Liste aller örtlichen Zusatzfeiertage am rechtlich "
    "relevanten Ort). Kaution: net_rent_cents, cash_deposit_confirmed. Keine "
    "Minderungsquote, kein berechneter Mietspiegel und keine Rechtsbestätigung aus "
    "Schweigen oder fehlenden Angaben."
)

TENANCY_CALCULATOR = Calculator(
    id="tenancy_checks",
    extraction_prompt=EXTRACTION_PROMPT,
    explanation_prompt=(
        "Erklären Sie nur die deterministischen Ergebnisse auf Deutsch. Keine eigene"
        " Berechnung, Rechtsfeststellung oder Minderungsquote. Fehlende Bestätigung "
        "bleibt offen. JSON: enriched_calculations mit index und commentary; "
        "overall_assessment mit summary und recommended_action."
    ),
    load_parameters=load_parameters,
    process=process_extraction,
    summarise_extraction=lambda extraction: extraction,
    cross_check=lambda extraction, document: [],
    referral_hint=(
        "Lassen Sie Fristen, Gebiet, Vergleichsmiete und Voraussetzungen bei einer "
        "Mieterberatung oder Rechtsanwältin bzw. einem Rechtsanwalt prüfen."
    ),
)
CALCULATORS = (TENANCY_CALCULATOR,)
