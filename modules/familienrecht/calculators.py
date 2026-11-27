"""Qualified statutory family arithmetic (D-077); never determine entitlement."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.modules.sdk import Calculator, ParameterSource

_TYPES = frozenset({"minimum_maintenance", "uvg_amount", "retroactive_maintenance"})
_BASES = {
    "minimum_maintenance": "§1 MinUhV; §§1612a,1612b BGB",
    "uvg_amount": "§§1,2 UhVorschG; §1 MinUhV; §66 EStG",
    "retroactive_maintenance": "§1613 Abs.1 BGB",
}


def _date(value: Any) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Bestätigtes ISO-Datum erforderlich.")
    return date.fromisoformat(value)


def _int(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Nichtnegative ganze Zahl erforderlich; keine Schätzung.")
    return value


def _confirm(facts: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if facts.get(key) is not True:
            raise ValueError(f"{key}: ausdrückliche qualifizierte Bestätigung fehlt.")


def _covered(day: date, row: dict[str, Any]) -> None:
    if not _date(str(row["valid_from"])) <= day <= _date(str(row["valid_to"])):
        raise ValueError("Zeitraum nicht durch gültige Parameter abgedeckt.")


def _amount(f: dict[str, Any], p: dict[str, Any], row: dict[str, Any], day: date) -> dict[str, Any]:
    month = _date(f.get("period_month"))
    _covered(month, row)
    if month.day != 1 or month > day.replace(day=1):
        raise ValueError("Bestätigter vergangener oder laufender Berechnungsmonat erforderlich.")
    _confirm(
        f,
        "age_for_period_confirmed",
        "minor_entire_month_confirmed",
        "full_child_benefit_confirmed",
    )
    age = _int(f.get("age_at_month_end"))
    bands = [r for r in p["age_bands"] if r["min"] <= age <= r["max"]]
    if age >= 18 or len(bands) != 1:
        raise ValueError("Nur minderjährige Kinder im unterstützten Altersband.")
    minimum = _int(bands[0]["minimum_cents"])
    benefit = _int(p["child_benefit_cents"])
    if f["calculation_type"] == "minimum_maintenance":
        _confirm(
            f,
            "separate_households_confirmed",
            "one_parent_care_confirmed",
            "no_special_credit_confirmed",
        )
        if benefit % 2:
            raise ValueError("Halber Kindergeldbetrag nicht centgenau darstellbar.")
        credit = benefit // 2
        amount = max(0, minimum - credit)
        scope = (
            "Nur gesetzlicher Mindestbedarf und hälftige Kindergeldanrechnung im bestätigten "
            "Betreuungsmodell. Altersstufe nach Alter am Monatsende (§1612a Abs.3 BGB). "
            "Kein festgestellter Unterhaltsanspruch oder vollstreckbarer Zahlbetrag; "
            "Leistungsfähigkeit, Einkommen, Rang, Mehr-/Sonderbedarf, Titel und Wechselmodell "
            "gesondert prüfen. Keine Düsseldorfer Tabelle, Einkommensgruppen oder Selbstbehalte."
        )
    else:
        _confirm(
            f,
            "uvg_eligibility_confirmed",
            "full_month_eligibility_confirmed",
            "stable_age_band_entire_month_confirmed",
            "no_section2_4_deductions_confirmed",
            "complete_income_confirmed",
        )
        if age >= 12:
            _confirm(f, "additional_12_17_conditions_confirmed")
        credit = benefit
        receipts = _int(f.get("maintenance_received_cents"))
        orphan = _int(f.get("orphan_received_cents"))
        amount = max(0, minimum - credit - receipts - orphan)
        scope = (
            "Nur rechnerischer voller UVG-Monat nach bestätigten Voraussetzungen, vollem "
            "Kindergeldabzug und vollständigen Unterhalts-/Waisenbezügen desselben Monats. "
            "Kein Leistungsbescheid oder festgestellter Anspruch. Teilmonate, Altersstufenwechsel "
            "im Monat, §2 Abs.4-Einkommensabzüge und ungeklärte Berechtigung ausgeschlossen. "
            "Für 12–17 Jahre zusätzliche §1 Abs.1a-Voraussetzungen bestätigen. "
            "Antrag/Rückwirkung (§4), Mitwirkung und Anspruchsübergang gesondert prüfen."
        )
    return {
        "period_month": month.isoformat(),
        "age_at_month_end": age,
        "minimum_cents": minimum,
        "child_benefit_credit_cents": credit,
        "amount_cents": amount,
        "scope": scope,
    }


def _retroactivity(f: dict[str, Any], row: dict[str, Any], day: date) -> dict[str, Any]:
    _confirm(
        f,
        "minor_child_regime_confirmed",
        "event_legally_effective_confirmed",
        "claim_existed_month_start_confirmed",
        "no_special_retroactivity_confirmed",
    )
    event = _date(f.get("event_on"))
    _covered(event, row)
    if event > day or f.get("event_basis") not in ("information_request", "default", "lis_pendens"):
        raise ValueError(
            "Wirksames, bestätigtes §1613 Abs.1-Ereignis fehlt; kein Briefdatum verwenden."
        )
    return {
        "conditional_start_date": event.replace(day=1).isoformat(),
        "event_on": event.isoformat(),
        "event_basis": f["event_basis"],
        "scope": "Bedingter Monatsbeginn nach §1613 Abs.1 BGB, keine Ausschlussfrist und "
        "keine Verjährungsberechnung. Nur wenn Anspruch dem Grunde nach am Monatsersten "
        "bestand. Wirksamkeit/Zugang des Auskunftsverlangens, Verzug oder Rechtshängigkeit "
        "müssen qualifiziert bestätigt sein. Sonderbedarf, Hindernisse, Titel, "
        "Anspruchsübergang und andere Unterhaltsarten gesondert prüfen; kein Anspruchsbetrag.",
    }


def process_extraction(
    extraction: dict[str, Any], param_overrides: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    kind = extraction.get("calculation_type")
    if kind in (None, "none"):
        return []
    computed: dict[str, Any] = {"deterministic_result": None}
    status = "unavailable"
    try:
        if kind not in _TYPES:
            raise ValueError("Unbekannte Familienrechtsberechnung.")
        _confirm(extraction, "applicability_confirmed", "current_regime_confirmed")
        day = _date(extraction.get("as_of"))
        row = (param_overrides or {}).get("maintenance_rules", {})
        if row.get("error") or not isinstance(row.get("value"), dict):
            raise ValueError("Gültige Parameter fehlen; keine Ersatzwerte.")
        _covered(day, row)
        computed = (
            _retroactivity(extraction, row, day)
            if kind == "retroactive_maintenance"
            else _amount(extraction, row["value"], row, day)
        )
        status = "provisional"
        computed["deterministic_result"] = {
            "status": status,
            "review_status": "proposed",
            "calculation_type": kind,
            "parameter_valid_from": str(row["valid_from"]),
            "parameter_valid_to": str(row["valid_to"]),
            **computed,
        }
        detail = (
            "Vorgeschlagene Parameter; menschliche Rechtsprüfung ausstehend. " + computed["scope"]
        )
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
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
            else computed.get("conditional_start_date", ""),
            "discrepancy_found": False,
            "discrepancy_amount_eur": 0,
            "discrepancy_direction": "keine",
            "relevant_rule": _BASES.get(str(kind), ""),
            "commentary": detail,
        }
    ]


async def load_parameters(
    extraction: dict[str, Any], source: ParameterSource
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if extraction.get("calculation_type") not in _TYPES:
        return {}, None
    try:
        day = _date(extraction.get("as_of"))
    except ValueError:
        return {}, {"missing_input": "as_of", "parameter_versions": []}
    row = await source.json("maintenance_rules", day)
    return {"maintenance_rules": row}, {
        "as_of": day.isoformat(),
        "parameter_versions": [f'maintenance_rules@{row.get("valid_from")}'],
        "parameters": {
            "maintenance_rules": {k: str(v) if isinstance(v, date) else v for k, v in row.items()}
        },
    }


EXTRACTION_PROMPT = """Nur belegte Fakten als JSON extrahieren; unbekannt=null.
Keine rechtliche Bestätigung aus Rohdaten oder Schweigen ableiten.
calculation_type: minimum_maintenance|uvg_amount|retroactive_maintenance|none.
as_of ISO-Datum; applicability_confirmed, current_regime_confirmed (verifiziert 27.11.2026).
Beträge: period_month=YYYY-MM-01, age_at_month_end ganze Jahre für diesen Monat,
age_for_period_confirmed, minor_entire_month_confirmed, full_child_benefit_confirmed.
Keine Namen, Geburtstage, Adressen oder sensiblen Angaben zu Kind/Ex-Partner ausgeben.
Mindestunterhalt: separate_households_confirmed, one_parent_care_confirmed,
no_special_credit_confirmed. Nur 100% gesetzlicher Mindestunterhalt, keine Tabelle,
Einkommensgruppen, Leistungsfähigkeit oder Selbstbehalt schätzen.
UVG: uvg_eligibility_confirmed (§1 vollständig), full_month_eligibility_confirmed,
stable_age_band_entire_month_confirmed, no_section2_4_deductions_confirmed,
complete_income_confirmed; maintenance_received_cents, orphan_received_cents ganze Cent
im selben Monat, auch 0 nur ausdrücklich bestätigt. Ab 12 zusätzlich
additional_12_17_conditions_confirmed (§1 Abs.1a). Keine Anspruchsentscheidung.
§1613: minor_child_regime_confirmed, event_on, event_basis=information_request|default|lis_pendens,
event_legally_effective_confirmed, claim_existed_month_start_confirmed,
no_special_retroactivity_confirmed. Qualifiziert wirksames Auskunftsverlangen zum Zweck
Unterhaltsgeltendmachung/Verzug/Rechtshängigkeit, niemals Versand/Briefdatum als Zugang.
Alle *_confirmed Felder nur nach ausdrücklicher qualifizierter Bestätigung."""

FAMILY_CALCULATOR = Calculator(
    id="family_checks",
    extraction_prompt=EXTRACTION_PROMPT,
    explanation_prompt="Nur deterministische Ergebnisse auf Deutsch erklären. "
    "Keine eigene Rechnung. "
    "Unavailable bleibt offen. Keine Anspruchs- oder Kindeswohlentscheidung. "
    "JSON: enriched_calculations (index, commentary), "
    "overall_assessment (summary, recommended_action).",
    load_parameters=load_parameters,
    process=process_extraction,
    summarise_extraction=lambda extraction: extraction,
    cross_check=lambda extraction, document: [],
    referral_hint="Lassen Sie Unterhalt, Frist und Vertretung individuell beraten; "
    "Kindeswohl, Sorge und Umgang zuerst an qualifizierte Hilfe verweisen.",
)
CALCULATORS = (FAMILY_CALCULATOR,)
