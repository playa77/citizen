"""WP-132: qualified statutory employment arithmetic; no entitlement decisions.

All legal constants come from date-selected proposed parameters. Fractions keep
leave and money exact until the declared rounding point; no model-calculated
amount or inferred applicability enters this module.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

from app.modules.sdk import Calculator, ParameterSource


def _date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("Bestätigtes ISO-Datum erforderlich.")
    return date.fromisoformat(value)


def _int(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name}: ganze Zahl ab {minimum} erforderlich.")
    return value


def _confirm(facts: dict[str, Any], key: str) -> None:
    if facts.get(key) is not True:
        raise ValueError(f"{key}: ausdrückliche qualifizierte Bestätigung fehlt.")


def _fraction(value: Any, name: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"{name}: bestätigte nichtnegative Zahl erforderlich.")
    number = Fraction(str(value))
    if number < 0:
        raise ValueError(f"{name}: negative Zahl unzulässig.")
    return number


def _months(day: date, count: int) -> date:
    index = day.year * 12 + day.month - 1 + count
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _period_boundary(start: date, months: int) -> date:
    # §187(2)/§188: employment includes the first day. If the corresponding
    # day does not exist, the final month ends inclusively on its last day.
    boundary = _months(start, months)
    return boundary + timedelta(days=1) if boundary.day < start.day else boundary


def _full_months(start: date, exclusive_end: date) -> int:
    months = (exclusive_end.year - start.year) * 12 + exclusive_end.month - start.month
    return months - (_period_boundary(start, months) > exclusive_end)


def _ratio(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _half_up(value: Fraction) -> int:
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def _parameter(rows: dict[str, Any] | None, key: str, day: date) -> dict[str, Any]:
    row = (rows or {}).get(key, {})
    end = _date(str(row["valid_to"])) if row.get("valid_to") else date.max
    if (
        row.get("error")
        or not isinstance(row.get("value"), dict)
        or not _date(str(row.get("valid_from"))) <= day <= end
    ):
        raise ValueError(f"{key}: keine gültigen versionierten Parameter; keine Ersatzwerte.")
    return dict(row["value"])


def _notice(f: dict[str, Any], p: dict[str, Any], day: date) -> dict[str, Any]:
    _confirm(f, "statutory_notice_confirmed")
    _confirm(f, "special_regime_excluded")
    received, start = _date(f.get("received_on")), _date(f.get("employment_start"))
    if received != day or start > received:
        raise ValueError(
            "Bezugsdatum muss Zugangstag sein; Beschäftigungsbeginn darf nicht später liegen."
        )
    probation = f.get("probation")
    if type(probation) is not bool or f.get("actor") not in ("employee", "employer"):
        raise ValueError("Kündigende Seite und vereinbarte Probezeit bestätigen.")
    if probation:
        if received >= _period_boundary(start, p["probation_max_months"]):
            raise ValueError("Probezeitregel nur innerhalb der ersten sechs Monate.")
        end = received + timedelta(days=p["probation_days"])
    else:
        years = _full_months(start, received) // 12
        months = 0
        if f["actor"] == "employer":
            for threshold, count in p["employer_notice_months"]:
                if years >= threshold:
                    months = count
        if months:
            target = _months(received, months)
            end = target.replace(day=calendar.monthrange(target.year, target.month)[1])
        else:
            target = received + timedelta(days=p["ordinary_days"])
            end = (
                target.replace(day=15)
                if target.day <= 15
                else target.replace(day=calendar.monthrange(target.year, target.month)[1])
            )
    return {
        "termination_date": end.isoformat(),
        "scope": "Frühester rechnerischer gesetzlicher Termin; kein Wirksamkeitsurteil. "
        "Tarif, Vertrag und Sonderkündigungsschutz müssen ausgeschlossen sein. "
        "Keine Verlängerung wegen Wochenende; Zugang nicht aus Briefdatum ableiten.",
    }


def _severance(f: dict[str, Any], p: dict[str, Any], day: date) -> dict[str, Any]:
    _confirm(f, "section_1a_confirmed")
    start, end = _date(f.get("employment_start")), _date(f.get("employment_end"))
    if end < start:
        raise ValueError("Beschäftigungsende liegt vor Beginn.")
    exclusive = end + timedelta(days=1)
    years = _full_months(start, exclusive) // p["months_per_year"]
    anniversary = _period_boundary(start, years * p["months_per_year"])
    if exclusive > _period_boundary(anniversary, p["severance_round_after_months"]):
        years += 1
    amount = Fraction(
        _int(f.get("monthly_earnings_cents"), "Monatsverdienst") * years, p["severance_divisor"]
    )
    return {
        "amount_cents": _half_up(amount),
        "employment_years": years,
        "scope": "Bedingte §-1a-Rechengröße, keine allgemeine Abfindung. Arbeitgeberhinweis, "
        "betriebsbedingter Grund, Fristablauf ohne Klage und weitere Voraussetzungen "
        "müssen qualifiziert geprüft sein. Nicht zum Verstreichenlassen einer Klagefrist "
        "verwenden; Kündigung sofort prüfen lassen. Cent: kaufmännisch gerundet.",
    }


def _workdays(f: dict[str, Any], p: dict[str, Any]) -> int:
    days = _int(f.get("working_days_per_week"), "Regelmäßige Arbeitstage", 1)
    if days > p["max_workdays"]:
        raise ValueError("Unregelmäßige oder mehr als sechs Arbeitstage gesondert prüfen.")
    return days


def _leave(f: dict[str, Any], p: dict[str, Any], day: date) -> dict[str, Any]:
    for key in (
        "statutory_leave_only_confirmed",
        "termination_confirmed",
        "no_prior_employer_leave_confirmed",
    ):
        _confirm(f, key)
    start, end = _date(f.get("employment_start")), _date(f.get("employment_end"))
    if end < start:
        raise ValueError("Beschäftigungsende liegt vor Beginn.")
    annual = Fraction(_workdays(f, p) * p["minimum_weeks"])
    exclusive = end + timedelta(days=1)
    waiting_met = _full_months(start, exclusive) >= p["waiting_months"]
    if waiting_met and end.month > p["partial_exit_last_month"]:
        entitlement = annual
    else:
        period_start = max(start, date(end.year, 1, 1))
        completed = _full_months(period_start, exclusive)
        entitlement = annual * Fraction(completed, p["months_per_year"])
        whole = entitlement.numerator // entitlement.denominator
        # §5(2) only rounds partial leave UP for fractions >= half a day.
        if entitlement - whole >= Fraction(p["round_numerator"], p["round_denominator"]):
            entitlement = Fraction(whole + 1)
    remaining = max(
        Fraction(0), entitlement - _fraction(f.get("leave_taken_days"), "Genommener Urlaub")
    )
    return {
        "entitlement_days": _ratio(entitlement),
        "remaining_days": _ratio(remaining),
        "scope": "Nur gesetzlicher Mindesturlaub bei bestätigtem Beschäftigungsende und "
        "regelmäßiger Wochenverteilung. Bruchteile unter einem halben Tag bleiben "
        "erhalten; kein automatischer Verfall, Zusatzurlaub oder Rückzahlungsanspruch. "
        "Vorarbeitgeberurlaub und Sonderregeln gesondert prüfen.",
    }


def _compensation(f: dict[str, Any], p: dict[str, Any], day: date) -> dict[str, Any]:
    _confirm(f, "compensation_conditions_confirmed")
    _confirm(f, "remuneration_basis_confirmed")
    days = _workdays(f, p)
    leave = _fraction(f.get("leave_days"), "Bestätigte abzugeltende Urlaubstage")
    earnings = _int(f.get("earnings_13_weeks_cents"), "Bereinigtes 13-Wochen-Entgelt")
    amount = Fraction(earnings, p["reference_weeks"] * days) * leave
    return {
        "amount_cents": _half_up(amount),
        "leave_days": _ratio(leave),
        "scope": "Brutto-Prüfbetrag nur bei bestätigter Abgeltung wegen Beendigung. "
        "13-Wochen-Basis: zusätzliches Überstundenentgelt ausschließen; dauerhafte "
        "Erhöhungen und unverschuldete Kürzungen nach §11 BUrlG berücksichtigen. "
        "Kaufmännisch auf Cent gerundet, keine Netto- oder Steuerberechnung.",
    }


def _wage(f: dict[str, Any], p: dict[str, Any], day: date) -> dict[str, Any]:
    _confirm(f, "milog_coverage_confirmed")
    _confirm(f, "remuneration_basis_confirmed")
    start, end = _date(f.get("period_start")), _date(f.get("period_end"))
    if day != start or end < start or start.year != end.year:
        raise ValueError(
            "Ein bestätigter Zeitraum innerhalb derselben Mindestlohnstufe erforderlich."
        )
    minutes = _int(f.get("working_minutes"), "Vergütungspflichtige Arbeitsminuten", 1)
    actual = _int(f.get("eligible_pay_cents"), "Anrechenbares Bruttoentgelt")
    exact = Fraction(p["hourly_rate_cents"] * minutes, p["minutes_per_hour"])
    minimum = -(-exact.numerator // exact.denominator)
    return {
        "amount_cents": minimum,
        "hourly_rate_cents": p["hourly_rate_cents"],
        "underpayment_cents": max(0, minimum - actual),
        "scope": "Allgemeiner gesetzlicher Brutto-Mindestlohn, auf den nächsten Cent "
        "aufgerundet. Persönliche Ausnahmen, Branchenmindestlohn, Arbeitszeit "
        "und anrechenbare Entgeltbestandteile müssen bestätigt geprüft sein. "
        "Keine Bestätigung, dass der gesamte Lohnanspruch erfüllt ist.",
    }


_PROCESSORS = {
    "notice": _notice,
    "severance": _severance,
    "leave": _leave,
    "leave_compensation": _compensation,
    "minimum_wage": _wage,
}
_RULES = {
    "notice": "§ 622 BGB",
    "severance": "§ 1a KSchG",
    "leave": "§§ 3–6 BUrlG",
    "leave_compensation": "§ 7 Abs. 4, § 11 BUrlG",
    "minimum_wage": "§§ 1, 22 MiLoG; MiLoV5",
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
            raise ValueError("Unbekannte Rechenprüfung; keine Ersatzberechnung.")
        _confirm(extraction, "applicability_confirmed")
        day = _date(extraction.get("as_of"))
        key = "minimum_wage" if kind == "minimum_wage" else "employment_rules"
        parameters = _parameter(param_overrides, key, day)
        computed = _PROCESSORS[kind](extraction, parameters, day)
        status = "provisional"
        detail = "Vorgeschlagene Parameter; menschliche Prüfung ausstehend. " + computed["scope"]
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
        detail = str(exc)
    computed["computation_detail"] = detail
    shortage = computed.get("underpayment_cents", 0)
    amount = computed.get("amount_cents")
    return [
        {
            "label": str(kind),
            "status": status,
            "document_values": {"extracted_numbers": {}, "authority_calculation": ""},
            "computed_values": computed,
            "correct_calculation": (
                f"{amount // 100}.{amount % 100:02d} EUR"
                if amount is not None
                else computed.get("termination_date", "")
            ),
            "discrepancy_found": shortage > 0,
            "discrepancy_amount_eur": shortage / 100,
            "discrepancy_direction": "zulasten" if shortage else "keine",
            "relevant_rule": _RULES.get(str(kind), ""),
            "commentary": detail,
        }
    ]


async def load_parameters(
    extraction: dict[str, Any], source: ParameterSource
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if extraction.get("calculation_type") not in _PROCESSORS:
        return {}, None
    try:
        day = _date(extraction.get("as_of"))
    except ValueError:
        return {}, {"missing_input": "as_of", "parameter_versions": []}
    key = "minimum_wage" if extraction["calculation_type"] == "minimum_wage" else "employment_rules"
    row = await source.json(key, day)
    return {key: row}, {
        "as_of": day.isoformat(),
        "parameter_versions": [f'{key}@{row.get("valid_from")}'],
        "parameters": {key: {k: str(v) if isinstance(v, date) else v for k, v in row.items()}},
    }


EXTRACTION_PROMPT = """
Extrahieren Sie nur ausdrücklich belegte Fakten als JSON. Unbekannt bleibt null.
Keine Bestätigung rechtlicher Voraussetzungen aus Schweigen oder fehlenden Angaben ableiten.
calculation_type: notice|severance|leave|leave_compensation|minimum_wage|none.
as_of: bestätigtes rechtliches Bezugsdatum YYYY-MM-DD, beim Mindestlohn period_start,
bei Kündigungsfrist received_on. applicability_confirmed nur bei ausdrücklicher qualifizierter
Bestätigung.
Geld in ganzen Cent, Arbeit in Minuten. employment_start, employment_end sind inklusive
Beschäftigungstage.
Kündigung: actor employee|employer, received_on, probation bool (vereinbart),
statutory_notice_confirmed,
special_regime_excluded (Tarif/Vertragsabweichung, Sonderregeln und Schutz rechtlich geprüft).
Abfindung: monthly_earnings_cents, section_1a_confirmed (betriebsbedingte Kündigung mit
gesetzlichem
Arbeitgeberhinweis, keine Klage bis Fristablauf und sämtliche Voraussetzungen qualifiziert
bestätigt).
Dies darf nie als Empfehlung zum Verstreichenlassen der Klagefrist erklärt werden.
Urlaub: working_days_per_week (regelmäßig 1..6), leave_taken_days,
statutory_leave_only_confirmed, termination_confirmed, no_prior_employer_leave_confirmed.
Abgeltung: leave_days, earnings_13_weeks_cents, compensation_conditions_confirmed (Beendigung
verhindert
Gewährung), remuneration_basis_confirmed (§11 BUrlG bereinigt, keine zusätzlichen
Überstundenvergütungen).
Mindestlohn: period_start, period_end, working_minutes, eligible_pay_cents,
milog_coverage_confirmed (§22 Ausnahmen, höhere Branchenmindestlöhne geprüft),
remuneration_basis_confirmed.
Keine Arbeitszeit, Fraktion, Summe, Beschäftigungsdauer oder rechtliche Qualifikation selbst
berechnen."""

EMPLOYMENT_CALCULATOR = Calculator(
    id="employment_checks",
    extraction_prompt=EXTRACTION_PROMPT,
    explanation_prompt=(
        "Erklären Sie nur deterministische Ergebnisse auf Deutsch; keine eigene Rechnung "
        "oder Anspruchsentscheidung. Unavailable bleibt offen. JSON: "
        "enriched_calculations mit index und commentary; overall_assessment mit summary "
        "und recommended_action. Bei Kündigung sofort Rat suchen; niemals zum "
        "Verstreichenlassen einer Klagefrist raten."
    ),
    load_parameters=load_parameters,
    process=process_extraction,
    summarise_extraction=lambda extraction: extraction,
    cross_check=lambda extraction, document: [],
    referral_hint=(
        "Lassen Sie Zugang, Fristen, Vertrag, Tarif und Sonderregeln unverzüglich bei "
        "einer Gewerkschaft, Beratungsstelle oder Rechtsanwältin bzw. einem Rechtsanwalt "
        "prüfen."
    ),
)
CALCULATORS = (EMPLOYMENT_CALCULATOR,)
