"""WP-130: conservative, evidence-qualified debt arithmetic in integer cents.

No applicability determination: explicit confirmations are required. Parameters
are selected by the document's as_of date, never the machine's clock. Outputs
remain provisional while the sourced parameter rows await human legal review.
"""

# Semantic Version: 0.1.0
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.modules.sdk import Calculator, ParameterSource

_KEYS = {
    "wage_attachment": "attachment_monthly",
    "p_account": "attachment_monthly",
    "limitation": "limitation_rules",
    "collection_costs": "collection_rvg",
}


def _date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("Ein ausdrückliches ISO-Datum fehlt.")
    return date.fromisoformat(value)


def _integer(value: Any, label: str, maximum: int | None = None) -> int:
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise ValueError(f"{label}: nichtnegative ganze Zahl erforderlich.")
    return value


def _confirm(facts: dict[str, Any], name: str, expected: bool = True) -> None:
    if facts.get(name) is not expected:
        raise ValueError(f"{name}: ausdrückliche Bestätigung erforderlich; bitte prüfen.")


def _parameters(extraction: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    day = _date(extraction.get("as_of"))
    key = _KEYS.get(str(extraction.get("calculation_type")))
    row = (overrides or {}).get(key or "", {})
    if not row or row.get("error") or not isinstance(row.get("value"), dict):
        raise ValueError("Keine passenden versionierten Parameter; keine Ersatzwerte.")
    end = _date(str(row["valid_to"])) if row.get("valid_to") else date.max
    if not _date(str(row.get("valid_from"))) <= day <= end:
        raise ValueError("Parameter gelten nicht für das ausdrücklich angegebene Datum.")
    return dict(row["value"])


def _dependants(facts: dict[str, Any], p: dict[str, Any]) -> int:
    n = _integer(facts.get("dependants"), "Unterhaltsberechtigte", p["max_dependants"])
    _confirm(facts, "dependants_confirmed")
    _confirm(facts, "special_order", False)
    return n


def _allowance(n: int, p: dict[str, Any]) -> int:
    return int(p["first_cents"] + (n - 1) * p["next_cents"]) if n else 0


def _wage(facts: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    _confirm(facts, "ordinary_claim")
    _confirm(facts, "monthly")
    n = _dependants(facts, p)
    income = _integer(facts.get("net_income_cents"), "Pfändungsnetto in Cent")
    # §850c(5): remove fully attachable excess before rounding down the
    # remaining income, then apply the protected share to the surplus.
    excess = max(0, income - p["cap_cents"])
    rounded = (income - excess) // p["rounding_cents"] * p["rounding_cents"]
    surplus = max(0, rounded - p["base_cents"] - _allowance(n, p))
    attachable = (surplus * (10 - p["protected_tenths"][n]) + 5) // 10
    return {
        "amount_cents": attachable + excess,
        "rounded_income_cents": rounded,
        "fully_attachable_excess_cents": excess,
    }


def _account(facts: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    n = _dependants(facts, p)
    _confirm(facts, "other_increases", False)
    if n:
        _confirm(facts, "actual_support")
    step = p["rounding_cents"]
    return {
        "amount_cents": ((p["base_cents"] + step - 1) // step * step) + _allowance(n, p),
        "scope": (
            "Monatlicher Grundbetrag und bestätigter gesetzlicher Unterhalt; "
            "keine Überträge, Sonderleistungen oder Bescheinigung nach § 903 ZPO geprüft."
        ),
    }


def _anniversary(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _limitation(facts: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    _confirm(facts, "applicability_confirmed")
    for flag in ("suspension", "restart", "special_limitation"):
        _confirm(facts, flag, False)
    arisen = _date(facts.get("arisen_on"))
    if facts.get("claim_class") == "ordinary":
        knowledge = _date(facts.get("knowledge_on"))
        end = date(max(arisen.year, knowledge.year) + p["ordinary_years"], 12, 31)
        end = min(end, _anniversary(arisen, p["ordinary_longstop_years"]))
    elif facts.get("claim_class") == "titled":
        _confirm(facts, "recurring_future_payments", False)
        _confirm(facts, "title_start_confirmed")
        start = max(arisen, _date(facts.get("title_effective_on")))
        end = _anniversary(start, p["titled_years"])
    else:
        raise ValueError("Anspruchsart rechtlich ungeklärt; keine Verjährungsberechnung.")
    _confirm(facts, "calendar_confirmed")
    holiday_values = facts.get("holiday_dates")
    if not isinstance(holiday_values, list):
        raise ValueError("Bestätigter Feiertagskalender des Leistungsorts fehlt (§193 BGB).")
    holidays = {_date(value) for value in holiday_values}
    raw_end = end
    for _ in range(370):
        if end.weekday() < 5 and end not in holidays:
            break
        end += timedelta(days=1)
    else:
        raise ValueError("Feiertagskalender nicht plausibel; bitte prüfen.")
    return {
        "unadjusted_expiry_date": raw_end.isoformat(),
        "expiry_date": end.isoformat(),
        "scope": (
            "Rechnerisches Fristende unter bestätigten Annahmen; "
            "keine Feststellung der Verjährung oder Durchsetzbarkeit."
        ),
    }


def _collection(facts: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    for flag in ("undisputed", "default_confirmed", "transition_confirmed"):
        _confirm(facts, flag)
    for flag in ("titled", "duplicate_fees"):
        _confirm(facts, flag, False)
    if type(facts.get("vat_recoverable")) is not bool:
        raise ValueError("Umsatzsteuer-Erstattungsfähigkeit ungeklärt.")
    principal = _integer(facts.get("principal_cents"), "Gegenstandswert in Cent")
    if principal == 0:
        raise ValueError("Gegenstandswert muss positiv sein.")
    rate = p["rates_tenths"].get(facts.get("fee_case"))
    if rate is None:
        raise ValueError(
            "Einfacher, normaler oder besonders umfangreicher/schwieriger Fall ungeklärt."
        )
    if facts.get("fee_case") == "extensive":
        _confirm(facts, "extensive_confirmed")
    fee = p["base_fee_cents"]
    if principal <= p["small_threshold_cents"]:
        fee = p["small_fee_cents"]
    else:
        lower = p["base_threshold_cents"]
        for upper, step, increment in p["bands"]:
            if principal > lower:
                fee += ((min(principal, upper) - lower + step - 1) // step) * increment
            lower = upper
        if principal > lower:
            raise ValueError("Gegenstandswert außerhalb der hinterlegten RVG-Tabelle.")
    business = max(p["minimum_fee_cents"], (fee * rate + 5) // 10)
    expenses = min(p["expenses_cap_cents"], (business * p["expenses_percent"] + 50) // 100)
    total = business + expenses
    if facts["vat_recoverable"]:
        total += (total * p["vat_percent"] + 50) // 100
    return {
        "amount_cents": total,
        "business_fee_cents": business,
        "expenses_cents": expenses,
        "scope": (
            "Plausibilitätsobergrenze für eine außergerichtliche Inkassotätigkeit; "
            "keine Bestätigung eines Erstattungsanspruchs. "
            "Andere Auslagen und doppelte Gebühren sind nicht geprüft."
        ),
    }


_PROCESSORS = {
    "wage_attachment": _wage,
    "p_account": _account,
    "limitation": _limitation,
    "collection_costs": _collection,
}


def process_extraction(
    extraction: dict[str, Any], param_overrides: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Return harness-compatible entries; unconfirmed facts produce no amount."""
    kind = extraction.get("calculation_type")
    if kind in (None, "none"):
        return []
    computed: dict[str, Any] = {"deterministic_result": None}
    status = "missing_input"
    try:
        p = _parameters(extraction, param_overrides)
        if kind not in _PROCESSORS:
            raise ValueError("Unbekannte Berechnung.")
        computed.update(_PROCESSORS[kind](extraction, p))
        computed["deterministic_result"] = (
            computed.get("amount_cents", 0) / 100 if "amount_cents" in computed else None
        )
        status = "provisional"
        detail = (
            "Versionierte Parameter: vorgeschlagen, menschliche Rechtsprüfung ausstehend. "
            + computed.get(
                "scope",
                "Berechnung nach § 850c ZPO; Pfändungsnetto und Unterhaltsansatz bitte prüfen.",
            )
        )
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        detail = str(exc)
    stated = extraction.get(
        "claimed_costs_cents" if kind == "collection_costs" else "stated_amount_cents"
    )
    valid_stated = type(stated) is int and stated >= 0
    amount = computed.get("amount_cents")
    difference = stated - amount if valid_stated and amount is not None else 0
    discrepancy = difference > 0 if kind == "collection_costs" else difference != 0
    # Less protected credit harms the account holder; higher deductions/costs
    # harm them in the other monetary checks. Keep the arithmetic delta intact.
    harmful_difference = -difference if kind == "p_account" else difference
    computed["computation_detail"] = detail
    return [
        {
            "label": str(kind),
            "status": status,
            "document_values": {"extracted_numbers": {}, "authority_calculation": ""},
            "computed_values": computed,
            "correct_calculation": f"{amount / 100:.2f} EUR"
            if amount is not None
            else computed.get("expiry_date", ""),
            "discrepancy_found": discrepancy,
            "discrepancy_amount_eur": abs(difference) / 100,
            "discrepancy_direction": "zulasten"
            if harmful_difference > 0
            else "zugunsten"
            if harmful_difference < 0
            else "keine",
            "relevant_rule": {
                "wage_attachment": "§ 850c ZPO",
                "p_account": "§§ 899, 902 ZPO",
                "limitation": "§§ 195, 197, 199, 201, 204, 212 BGB",
                "collection_costs": "§§ 13e, 13f RDG; § 13 RVG; VV 2300, 7002, 7008",
            }.get(str(kind), ""),
            "commentary": detail,
        }
    ]


async def load_parameters(
    extraction: dict[str, Any], source: ParameterSource
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        day = _date(extraction.get("as_of"))
    except ValueError:
        return {}, {"parameter_versions": [], "missing_input": "as_of"}
    key = _KEYS.get(str(extraction.get("calculation_type")))
    if key is None:
        return {}, None
    row = await source.json(key, day)
    snapshot = {
        "as_of": day.isoformat(),
        "parameter_versions": [f"{key}@{row.get('valid_from')}"],
        "parameters": {key: {k: str(v) if isinstance(v, date) else v for k, v in row.items()}},
    }
    return {key: row}, snapshot


def cross_check_extraction(extraction: dict[str, Any], document: str) -> list[str]:
    """Flag amounts absent from document text; never confirms legal facts."""
    warnings = []
    normalized = document.replace("\u00a0", " ")
    for key in (
        "net_income_cents",
        "principal_cents",
        "claimed_costs_cents",
        "stated_amount_cents",
    ):
        value = extraction.get(key)
        if type(value) is not int or value < 0:
            continue
        euros = f"{value // 100}.{value % 100:02d}"
        german = f"{value / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        if not any(
            candidate in normalized for candidate in (euros, euros.replace(".", ","), german)
        ):
            warnings.append(f"{key}: Betrag im Dokument nicht gefunden; Extraktion prüfen.")
    return warnings


EXTRACTION_PROMPT = (
    "Extrahieren Sie ausschließlich belegte Werte aus ## DOKUMENT als ein JSON-"
    "Objekt. Keine Rechtsanwendung, keine Berechnung, keine Werte aus KONTEXT. "
    "Unbekannte Werte sind null; Bestätigungen niemals aus fehlenden Angaben "
    "ableiten. calculation_type: "
    "wage_attachment|p_account|limitation|collection_costs|none; as_of: "
    "ausdrückliches Bezugsdatum YYYY-MM-DD. Geldwerte: ganze Cent, keine Euro-"
    "Dezimalwerte. Gemeinsame optionale Felder: stated_amount_cents, dependants "
    "(0..5), dependants_confirmed (tatsächlich gewährter gesetzlicher Unterhalt, "
    "keine bloße Haushaltszugehörigkeit), special_order. Lohn: net_income_cents "
    "(bereinigtes Pfändungsnetto), ordinary_claim (keine "
    "Unterhalts-/Deliktsforderung), monthly. P-Konto: actual_support, "
    "other_increases (andere §902-Leistungen oder Überträge; bei Unsicherheit "
    "null). Verjährung: claim_class ordinary|titled, applicability_confirmed "
    "(rechtlich qualifizierte Anwendbarkeit, niemals selbst bestimmen), arisen_on, "
    "knowledge_on, title_effective_on, title_start_confirmed, "
    "recurring_future_payments, suspension, restart, special_limitation, "
    "calendar_confirmed (vollständiger Feiertagskalender des Leistungsorts für "
    "Fristende), holiday_dates (ISO-Datum-Liste). Hemmung, Mahnbescheid, "
    "Anerkenntnis, Zahlung, Vollstreckung oder Unklarheit dazu müssen zur Prüfung "
    "führen. Inkasso: principal_cents, claimed_costs_cents, undisputed, titled, "
    "default_confirmed, transition_confirmed (geltende RVG-Fassung für den Auftrag "
    "ausdrücklich bestätigt), duplicate_fees, fee_case simple|normal|extensive, "
    "extensive_confirmed, vat_recoverable (Erstattung der Umsatzsteuer ausdrücklich"
    " bestätigt). Rechtliche Bestätigungen nur aus ausdrücklicher qualifizierter "
    "Angabe übernehmen, sonst null."
)

DEBT_CALCULATOR = Calculator(
    id="debt_checks",
    extraction_prompt=EXTRACTION_PROMPT,
    explanation_prompt=(
        "Erklären Sie ausschließlich die übergebenen deterministischen Ergebnisse auf "
        "Deutsch. Fehlende Eingaben und vorgeschlagene Parameter erfordern Prüfung. "
        "Keine eigene Berechnung oder Feststellung der Verjährung, Erstattungsfähigkeit"
        " oder Pfändbarkeit. Geben Sie JSON mit enriched_calculations (Liste aus index "
        "und commentary) und overall_assessment (summary, recommended_action) zurück."
    ),
    load_parameters=load_parameters,
    process=process_extraction,
    summarise_extraction=lambda extraction: extraction,
    cross_check=cross_check_extraction,
    referral_hint=(
        "Lassen Sie die Angaben und rechtlichen Voraussetzungen bei einer "
        "Schuldnerberatung oder einer Rechtsanwältin bzw. einem Rechtsanwalt prüfen."
    ),
)
CALCULATORS = (DEBT_CALCULATOR,)
