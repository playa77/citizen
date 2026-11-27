"""Qualified residence arithmetic only; never decide immigration status or eligibility."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.modules.sdk import Calculator, ParameterSource

_TYPES = frozenset({"title_expiry", "residence_period", "livelihood_budget"})
_BASES = {
    "title_expiry": "§81 Abs.4 AufenthG; §51 Abs.1 AufenthG",
    "residence_period": "§10 Abs.1 StAG; §§187,188 BGB; §12b StAG gesondert prüfen",
    "livelihood_budget": "§2 Abs.3 AufenthG; bestätigte individuelle Bedarfsgrundlage",
}


def _date(value: Any) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Bestätigtes ISO-Datum erforderlich.")
    return date.fromisoformat(value)


def _cents(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Nichtnegative ganze Cent erforderlich; keine Schätzung.")
    return value


def _confirm(facts: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if facts.get(key) is not True:
            raise ValueError(f"{key}: ausdrückliche qualifizierte Bestätigung fehlt.")


def _compute(f: dict[str, Any], p: dict[str, Any], day: date) -> dict[str, Any]:
    kind = f["calculation_type"]
    if kind == "title_expiry":
        _confirm(
            f,
            "title_and_expiry_confirmed",
            "application_receipt_confirmed",
            "section81_4_regime_confirmed",
            "no_schengen_visa_confirmed",
            "no_authority_decision_confirmed",
        )
        expiry = _date(f.get("title_expires_on"))
        received = _date(f.get("application_received_on"))
        if received > day:
            raise ValueError("Nur tatsächlich belegter Antragseingang, kein künftiger Termin.")
        if received > expiry:
            raise ValueError("Verspäteter Antrag: Härtefallentscheidung gesondert beraten lassen.")
        return {
            "title_expires_on": expiry.isoformat(),
            "application_received_on": received.isoformat(),
            "days_until_expiry": (expiry - day).days,
            "application_before_expiry": True,
            "scope": "Nur Vergleich bestätigter Daten bei bestätigtem §81 Abs.4-Regime. "
            "Eingang am letzten Gültigkeitstag liegt vor Ablauf dieses Tages. "
            "Keine Feststellung von Aufenthaltsstatus, Fiktionswirkung, "
            "Reise- oder Arbeitserlaubnis. "
            "Andere Erlöschensgründe (§51), Behördenentscheidung und Beleg/Fiktionsbescheinigung "
            "individuell prüfen. Ein gebuchter Termin ist kein belegter Antragseingang.",
        }
    if kind == "residence_period":
        _confirm(
            f,
            "continuous_lawful_ordinary_residence_confirmed",
            "no_credit_or_interruption_confirmed",
            "standard_section10_regime_confirmed",
        )
        start = _date(f.get("lawful_residence_started_on"))
        if start > day:
            raise ValueError("Aufenthaltsbeginn liegt in der Zukunft.")
        years = p["standard_residence_years"]
        if type(years) is not int or years <= 0:
            raise ValueError("Gültige gesetzliche Aufenthaltsdauer fehlt.")
        try:
            anniversary = start.replace(year=start.year + years)
        except ValueError:
            # §188 Abs.3 BGB: last day when the corresponding day is absent.
            anniversary = date(start.year + years, 2, 28)
        return {
            "five_year_anniversary": anniversary.isoformat(),
            "period_reached": anniversary <= day,
            "scope": "Nur kalendarischer Jahrestag nach bestätigtem ununterbrochenem "
            "rechtmäßigem gewöhnlichem Aufenthalt. Keine Einbürgerungsberechtigung, "
            "Entscheidungsfrist oder Zusage. Weitere §10-Voraussetzungen, §12b-Unterbrechungen, "
            "Anrechnung, Miteinbürgerung und Sonderregime individuell prüfen. "
            "Keine frühere Dreijahresregel anwenden.",
        }
    _confirm(
        f,
        "need_and_income_basis_confirmed",
        "insurance_coverage_confirmed",
        "complete_household_confirmed",
        "no_special_livelihood_regime_confirmed",
    )
    income = _cents(f.get("eligible_income_cents"))
    need = _cents(f.get("confirmed_need_cents"))
    insurance = _cents(f.get("insurance_cost_cents"))
    return {
        "eligible_income_cents": income,
        "total_need_cents": need + insurance,
        "budget_balance_cents": income - need - insurance,
        "scope": "Nur Budgetdifferenz aus bestätigten individuellen Eingaben in ganzen Cent. "
        "Bedarf ohne den getrennten Krankenversicherungsbetrag angeben; keine Doppelzählung. "
        "Keine Feststellung gesicherten Lebensunterhalts "
        "oder eines Leistungs-/Aufenthaltsanspruchs. "
        "Einkommensbewertung, öffentliche Mittel/Ausnahmen, Haushalt, Abzüge und Prognose "
        "individuell prüfen. Sonderregime für Ausbildung/Studium ausgeschlossen. "
        "Keine Sozialrecht-Parameter oder Module stillschweigend laden.",
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
            raise ValueError("Unbekannte Aufenthaltsrechtsberechnung.")
        _confirm(extraction, "applicability_confirmed", "current_regime_confirmed")
        day = _date(extraction.get("as_of"))
        row = (param_overrides or {}).get("residence_rules", {})
        if row.get("error") or not isinstance(row.get("value"), dict):
            raise ValueError("Gültige Parameter fehlen; keine Ersatzwerte.")
        if not _date(str(row["valid_from"])) <= day <= _date(str(row["valid_to"])):
            raise ValueError("Rechtsstand außerhalb des verifizierten Parameterzeitraums.")
        computed = _compute(extraction, row["value"], day)
        status = "provisional"
        computed["deterministic_result"] = {
            "status": status,
            "review_status": "proposed",
            "calculation_type": kind,
            "parameter_valid_from": str(row["valid_from"]),
            "parameter_valid_to": str(row["valid_to"]),
            **computed,
        }
        detail = "Menschliche Rechtsprüfung ausstehend. " + computed["scope"]
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
        detail = (
            str(exc) + " Bei Fristen oder drohender Abschiebung sofort qualifizierte Hilfe suchen."
        )
    computed["computation_detail"] = detail
    balance = computed.get("budget_balance_cents")
    display = (
        f"{'-' if balance < 0 else ''}{abs(balance) // 100}.{abs(balance) % 100:02d} EUR"
        if balance is not None
        else computed.get("five_year_anniversary", computed.get("title_expires_on", ""))
    )
    return [
        {
            "label": str(kind),
            "status": status,
            "document_values": {"extracted_numbers": {}, "authority_calculation": ""},
            "computed_values": computed,
            "correct_calculation": display,
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
    row = await source.json("residence_rules", day)
    return {"residence_rules": row}, {
        "as_of": day.isoformat(),
        "parameter_versions": [f'residence_rules@{row.get("valid_from")}'],
        "parameters": {
            "residence_rules": {k: str(v) if isinstance(v, date) else v for k, v in row.items()}
        },
    }


# Only this explicit source block can establish the qualified input for the
# LLM-driven path. A model assertion that a fact is confirmed is not evidence.
EVIDENCE_MARKER = "CITIZEN_RESIDENCE_FACTS:"
_FACT_KEYS = frozenset(
    {
        "own_matter_confirmed",
        "calculation_type",
        "as_of",
        "title_expires_on",
        "application_received_on",
        "lawful_residence_started_on",
        "eligible_income_cents",
        "confirmed_need_cents",
        "insurance_cost_cents",
        "applicability_confirmed",
        "current_regime_confirmed",
        "title_and_expiry_confirmed",
        "application_receipt_confirmed",
        "section81_4_regime_confirmed",
        "no_schengen_visa_confirmed",
        "no_authority_decision_confirmed",
        "continuous_lawful_ordinary_residence_confirmed",
        "no_credit_or_interruption_confirmed",
        "standard_section10_regime_confirmed",
        "need_and_income_basis_confirmed",
        "insurance_coverage_confirmed",
        "complete_household_confirmed",
        "no_special_livelihood_regime_confirmed",
    }
)


def summarise_extraction(extraction: dict[str, Any]) -> dict[str, Any]:
    """Never send unexpected identifiers or sensitive narrative keys to explanation."""
    return {k: v for k, v in extraction.items() if k in _FACT_KEYS}


def cross_check_extraction(extraction: dict[str, Any], document: str) -> list[str]:
    """Replace model claims with explicit, minimal source-bound qualified inputs."""
    kind = extraction.get("calculation_type")
    extraction.clear()
    extraction["calculation_type"] = kind
    try:
        if document.count(EVIDENCE_MARKER) != 1:
            raise ValueError("Eindeutiger qualifizierter Eingabeblock fehlt.")
        payload = document.split(EVIDENCE_MARKER, 1)[1].lstrip()
        facts, _ = json.JSONDecoder().raw_decode(payload)
        if not isinstance(facts, dict) or set(facts) - _FACT_KEYS:
            raise ValueError("Eingabeblock enthält unbekannte oder sensible Felder.")
        if facts.get("own_matter_confirmed") is not True:
            raise ValueError("Eigene Angelegenheit nicht ausdrücklich bestätigt.")
        if facts.get("calculation_type") not in _TYPES:
            raise ValueError("Unterstützte Berechnung im Eingabeblock fehlt.")
        for key, value in facts.items():
            if key.endswith("_confirmed") and type(value) is not bool:
                raise ValueError("Bestätigungen müssen ausdrücklich boolesch sein.")
            if key.endswith("_cents"):
                _cents(value)
            if key in (
                "as_of",
                "title_expires_on",
                "application_received_on",
                "lawful_residence_started_on",
            ):
                _date(value)
        extraction.clear()
        extraction.update(facts)
        return []
    except (ValueError, TypeError, KeyError) as exc:
        # Retain only the requested kind: processing must return unavailable,
        # rather than silently treating unbound model data as confirmed.
        return [str(exc)]


EXTRACTION_PROMPT = """Nur belegte minimale Fakten als JSON extrahieren; unbekannt=null.
Qualifizierte Eingaben nur aus einem expliziten CITIZEN_RESIDENCE_FACTS:-JSON-Block.
Ohne diesen Block keine Bestätigungen erfinden. own_matter_confirmed muss true sein.
calculation_type: title_expiry|residence_period|livelihood_budget|none; as_of ISO-Datum.
applicability_confirmed, current_regime_confirmed nur nach qualifizierter Bestätigung.
Titel: title_expires_on, application_received_on (tatsächlicher Eingang, kein Termin);
title_and_expiry_confirmed, application_receipt_confirmed, section81_4_regime_confirmed,
no_schengen_visa_confirmed, no_authority_decision_confirmed.
Aufenthaltsdauer: lawful_residence_started_on, continuous_lawful_ordinary_residence_confirmed,
no_credit_or_interruption_confirmed, standard_section10_regime_confirmed.
Budget: eligible_income_cents, confirmed_need_cents OHNE getrennte insurance_cost_cents,
alle nichtnegative ganze Cent; need_and_income_basis_confirmed, insurance_coverage_confirmed,
complete_household_confirmed, no_special_livelihood_regime_confirmed.
Alle *_confirmed nur ausdrücklich qualifiziert bestätigt, niemals aus Schweigen ableiten.
Keine Verfolgungsnarrative, Religion, Diagnosen, Passnummern oder Daten Dritter ausgeben.
Keine Rechtsstatus-, Fiktions-, Arbeits-/Reise- oder Einbürgerungsentscheidung treffen."""

RESIDENCE_CALCULATOR = Calculator(
    id="residence_checks",
    extraction_prompt=EXTRACTION_PROMPT,
    explanation_prompt="Nur deterministische Ergebnisse auf Deutsch erklären; "
    "keine eigene Rechnung. "
    "Unavailable bleibt offen. Keine Rechtsstatus- "
    "oder Anspruchsentscheidung. "
    "JSON: enriched_calculations (index, commentary), "
    "overall_assessment (summary, recommended_action).",
    load_parameters=load_parameters,
    process=process_extraction,
    summarise_extraction=summarise_extraction,
    cross_check=cross_check_extraction,
    referral_hint="Bei Fristen oder drohender Abschiebung sofort qualifizierte "
    "Migrations-/Asylberatung oder anwaltliche Hilfe suchen; keinen sicheren Status zusagen.",
)
CALCULATORS = (RESIDENCE_CALCULATOR,)
