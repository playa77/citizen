"""Qualified contract checks; exact arithmetic, no entitlement inference or fallbacks."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

from app.modules.sdk import Calculator, ParameterSource

_KEYS = {
    "default_interest": "default_interest_rates",
    "withdrawal": "contract_rules",
    "flight_compensation": "contract_rules",
}


def _date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("Ausdrückliches ISO-Datum erforderlich.")
    return date.fromisoformat(value)


def _int(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("Ganze Zahl im zulässigen Bereich erforderlich.")
    return value


def _confirm(f: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if f.get(key) is not True:
            raise ValueError(f"{key}: qualifizierte Bestätigung fehlt.")


def _bool(f: dict[str, Any], key: str) -> bool:
    value = f.get(key)
    if type(value) is not bool:
        raise ValueError(f"{key}: ausdrückliches Ja/Nein fehlt.")
    return value


def _parameter(rows: dict[str, Any] | None, key: str, day: date) -> dict[str, Any]:
    row = (rows or {}).get(key, {})
    if (
        row.get("error")
        or not isinstance(row.get("value"), dict)
        or not _date(str(row.get("valid_from"))) <= day <= _date(str(row.get("valid_to")))
    ):
        raise ValueError("Keine gültigen begrenzten Parameter; keine Ersatzwerte.")
    return dict(row["value"])


def _interest(f: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    _confirm(f, "default_confirmed", "principal_constant_confirmed", "no_compounding_confirmed")
    consumer = _bool(f, "consumer_involved")
    if not consumer:
        _confirm(f, "payment_claim_confirmed")
    principal = _int(f.get("principal_cents"), 1)
    start, end = _date(f.get("period_start")), _date(f.get("period_end"))
    if end < start:
        raise ValueError("Zinszeitraum umgekehrt.")
    cursor, exact, segments = start, Fraction(0), []
    # A single inclusive period must be completely covered; no inferred future rates.
    while cursor <= end:
        matches = [r for r in p["segments"] if _date(r["start"]) <= cursor <= _date(r["end"])]
        if len(matches) != 1:
            raise ValueError("Basiszinsperiode fehlt oder ist mehrdeutig.")
        row = matches[0]
        last = min(end, _date(row["end"]), date(cursor.year, 12, 31))
        days = (last - cursor).days + 1
        rate = row["basis_points"] + p["consumer_margin_bp" if consumer else "business_margin_bp"]
        denominator = 366 if calendar.isleap(cursor.year) else 365
        exact += Fraction(principal * rate * days, 10000 * denominator)
        segments.append(
            {
                "start": cursor.isoformat(),
                "end": last.isoformat(),
                "days": days,
                "annual_rate_basis_points": rate,
                "year_days": denominator,
            }
        )
        cursor = last + timedelta(days=1)
    amount = (2 * exact.numerator + exact.denominator) // (2 * exact.denominator)
    return {
        "amount_cents": amount,
        "segments": segments,
        "exact_cents": {"numerator": exact.numerator, "denominator": exact.denominator},
        "scope": "Einfache Zinsen, tatsächliche Tage / Kalendertage des Jahres; einmal auf Cent "
        "kaufmännisch gerundet. Keine Pauschale, Kosten oder Zinseszinsen. "
        "Verzug, Zeitraum und unveränderte Hauptforderung müssen bestätigt sein.",
    }


def _roll(day: date, f: dict[str, Any]) -> date:
    _confirm(f, "calendar_confirmed")
    if not isinstance(f.get("holiday_dates"), list):
        raise ValueError("Bestätigter Feiertagskalender des Leistungsorts fehlt.")
    holidays = {_date(x) for x in f["holiday_dates"]}
    for _ in range(370):
        if day.weekday() < 5 and day not in holidays:
            return day
        day += timedelta(days=1)
    raise ValueError("Feiertagskalender nicht plausibel.")


def _withdrawal(f: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    _confirm(f, "trigger_confirmed", "exceptions_excluded_confirmed")
    if f.get("regime") not in ("goods", "services"):
        raise ValueError("Sonderregime nicht unterstützt; rechtlich prüfen.")
    trigger = _date(f.get("trigger_on"))
    days = p["withdrawal_days"]
    notice = f.get("notice_status")
    if notice == "adequate":
        informed = _date(f.get("notice_on"))
        if informed > trigger:
            raise ValueError("Spätere Belehrung als late qualifizieren.")
        raw = trigger + timedelta(days=days)
        outer = None
    elif notice in ("absent", "late"):
        year, month_index = divmod(
            trigger.year * 12 + trigger.month - 1 + _int(p["withdrawal_outer_months"], 1), 12
        )
        month = month_index + 1
        anniversary = date(year, month, min(trigger.day, calendar.monthrange(year, month)[1]))
        outer = anniversary + timedelta(days=days)
        raw = outer
        if notice == "late":
            informed = _date(f.get("notice_on"))
            if informed < trigger:
                raise ValueError("Nachbelehrung liegt vor Fristanker.")
            raw = min(outer, informed + timedelta(days=days))
    else:
        raise ValueError("Qualifikation der Widerrufsbelehrung fehlt.")
    adjusted = _roll(raw, f)
    if outer is not None and raw == outer and adjusted != raw:
        _confirm(f, "outer_limit_rollover_confirmed")
    return {
        "unadjusted_expiry_date": raw.isoformat(),
        "expiry_date": adjusted.isoformat(),
        "outer_limit_date": outer.isoformat() if outer else None,
        "scope": "Nur bestätigtes Fernabsatz-/Außergeschäftsraum-Regime nach §356 Abs.2–5 BGB; "
        "Waren: maßgeblichen Empfang einschließlich Mehrteillieferungen bestätigen; "
        "Dienstleistungen: Vertragsschluss. Keine Finanzdienstleistungen, digitalen Inhalte "
        "oder Sonderregeln. §193 anhand bestätigtem Kalender; keine Anspruchsentscheidung.",
    }


def _flight(f: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    _confirm(
        f,
        "eu261_scope_confirmed",
        "entitlement_confirmed",
        "extraordinary_circumstances_excluded_confirmed",
    )
    if f.get("claim_basis") not in ("denied_boarding", "cancellation", "long_delay"):
        raise ValueError("Anspruchsgrund nicht qualifiziert.")
    distance = _int(f.get("distance_km"), 1)
    intra, reduction = _bool(f, "intra_eu"), _bool(f, "reduction_confirmed")
    amount = p["flight_cents"][
        0 if distance <= p["short_km"] else 1 if intra or distance <= p["medium_km"] else 2
    ]
    return {
        "amount_cents": amount // _int(p["flight_reduction_divisor"], 1) if reduction else amount,
        "unreduced_amount_cents": amount,
        "scope": "Art.7 VO (EG)261/2004; bestätigte Großkreisentfernung und Anspruchsgrundlage. "
        "50%-Kürzung nur bei ausdrücklich rechtlich bestätigter Zulässigkeit einschließlich "
        "Ersatzbeförderung/Ankunft und einschlägiger Rechtsprechung. Keine automatische "
        "Anspruchs-, Verspätungs- oder Umstandsprüfung.",
    }


_PROCESSORS = {
    "default_interest": _interest,
    "withdrawal": _withdrawal,
    "flight_compensation": _flight,
}
_RULES = {
    "default_interest": "§§247,286,288,289 BGB",
    "withdrawal": "§§187–193,355,356 BGB",
    "flight_compensation": "Art.3–7 VO (EG)261/2004; einschlägige EuGH-Rechtsprechung",
}


def process_extraction(
    extraction: dict[str, Any], param_overrides: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    kind = extraction.get("calculation_type")
    if kind in (None, "none"):
        return []
    computed: dict[str, Any] = {}
    status = "unavailable"
    try:
        if kind not in _PROCESSORS:
            raise ValueError("Unbekannte Berechnung.")
        _confirm(extraction, "applicability_confirmed")
        p = _parameter(param_overrides, _KEYS[kind], _date(extraction.get("as_of")))
        computed = _PROCESSORS[kind](extraction, p)
        status = "provisional"
        detail = (
            "Vorgeschlagene Parameter; menschliche Rechtsprüfung ausstehend. " + computed["scope"]
        )
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
        detail = str(exc)
    computed["computation_detail"] = detail
    amount = computed.get("amount_cents")
    return [
        {
            "label": str(kind),
            "status": status,
            "document_values": {"extracted_numbers": {}, "authority_calculation": ""},
            "computed_values": computed,
            "correct_calculation": f"{amount // 100}.{amount % 100:02d} EUR"
            if amount is not None
            else computed.get("expiry_date", ""),
            "discrepancy_found": False,
            "discrepancy_amount_eur": 0,
            "discrepancy_direction": "keine",
            "relevant_rule": _RULES.get(str(kind), ""),
            "commentary": detail,
        }
    ]


async def load_parameters(
    extraction: dict[str, Any], source: ParameterSource
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    key = _KEYS.get(str(extraction.get("calculation_type")))
    if key is None:
        return {}, None
    try:
        day = _date(extraction.get("as_of"))
    except ValueError:
        return {}, {"missing_input": "as_of", "parameter_versions": []}
    row = await source.json(key, day)
    return {key: row}, {
        "as_of": day.isoformat(),
        "parameter_versions": [f'{key}@{row.get("valid_from")}'],
        "parameters": {key: {k: str(v) if isinstance(v, date) else v for k, v in row.items()}},
    }


EXTRACTION_PROMPT = """Nur ausdrücklich belegte Fakten aus dem Dokument als JSON; unbekannt=null.
Keine Rechtsanwendung oder Bestätigung aus Schweigen. calculation_type:
default_interest|withdrawal|flight_compensation|none; as_of ISO-Datum;
applicability_confirmed nur ausdrückliche qualifizierte rechtliche Bestätigung.
Zinsen: principal_cents ganze positive Cent; period_start/period_end inklusive bestätigte
Zinstage; default_confirmed, principal_constant_confirmed, no_compounding_confirmed;
consumer_involved bool; ohne Verbraucher payment_claim_confirmed.
Widerruf: regime goods|services, trigger_on ISO-Datum, trigger_confirmed (maßgeblicher
Warenempfang einschließlich Teil-/Mehrfachlieferungen bzw Vertragsschluss),
exceptions_excluded_confirmed, notice_status adequate|absent|late, notice_on,
calendar_confirmed (vollständiger Feiertagskalender des Leistungsorts), holiday_dates ISO-Liste.
outer_limit_rollover_confirmed: gesonderte rechtliche Bestätigung, falls §193 das äußere
Erlöschen verlängern würde; ohne Bestätigung dann unavailable.
Flug: distance_km positive ganze Großkreiskilometer; intra_eu bool; claim_basis
 denied_boarding|cancellation|long_delay; eu261_scope_confirmed, entitlement_confirmed,
extraordinary_circumstances_excluded_confirmed; bei long_delay muss entitlement_confirmed
insbesondere die qualifizierte Ankunftsverspätung am Endziel von mindestens drei Stunden
und die einschlägigen EuGH-Voraussetzungen umfassen; reduction_confirmed bool (true nur rechtlich
bestätigte 50%-Kürzung mit vollständigen Voraussetzungen; false nur bestätigt ungekürzt).
Keine Entfernung, Zinsen oder Frist selbst berechnen. Alle rechtlichen Bestätigungen müssen
qualifiziert ausdrücklich vorliegen, niemals selbst aus Rohdaten ableiten."""

CONTRACT_CALCULATOR = Calculator(
    id="contract_checks",
    extraction_prompt=EXTRACTION_PROMPT,
    explanation_prompt="Nur deterministische Ergebnisse auf Deutsch erklären; "
    "keine eigene Rechnung "
    "oder Anspruchsentscheidung. Unavailable bleibt offen. JSON: enriched_calculations "
    "(index, commentary), overall_assessment (summary, recommended_action).",
    load_parameters=load_parameters,
    process=process_extraction,
    summarise_extraction=lambda extraction: extraction,
    cross_check=lambda extraction, document: [],
    referral_hint="Lassen Sie Vertrag, Zugang, Fristen und Anspruchsvoraussetzungen unverzüglich "
    "bei einer Verbraucherberatung oder Rechtsanwältin bzw. einem Rechtsanwalt prüfen.",
)
CALCULATORS = (CONTRACT_CALCULATOR,)
