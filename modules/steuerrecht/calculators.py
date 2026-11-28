"""Bounded 2026 tax arithmetic; no assessment, gross-income conversion or filing."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from app.modules.sdk import Calculator, ParameterSource

_TYPES = frozenset({"income_tax", "allowance", "assessment_difference", "filing_deadline"})
_STATES = frozenset(
    {"BB", "BE", "BW", "BY", "HB", "HE", "HH", "MV", "NI", "NW", "RP", "SH", "SL", "SN", "ST", "TH"}
)
EVIDENCE_MARKER = "CITIZEN_TAX_FACTS:"
_CONFIRMATIONS = frozenset(
    {
        "own_matter_confirmed",
        "applicability_confirmed",
        "current_regime_confirmed",
        "taxable_income_confirmed",
        "no_special_tariff_confirmed",
        "joint_assessment_confirmed",
        "allowance_basis_confirmed",
        "no_higher_expenses_confirmed",
        "comparison_basis_confirmed",
        "mandatory_filing_confirmed",
        "unadvised_confirmed",
        "no_special_filing_regime_confirmed",
        "no_individual_notice_or_extension_confirmed",
        "filing_calendar_confirmed",
    }
)
_CENTS = frozenset(
    {"taxable_income_cents", "eligible_income_cents", "assessed_cents", "declared_cents"}
)
_FACT_KEYS = (
    _CONFIRMATIONS
    | _CENTS
    | {"calculation_type", "tax_year", "tariff", "allowance_type", "bundesland"}
)


def _cents(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 10**15:
        raise ValueError("Nichtnegative ganze Cent innerhalb des Rechenbereichs erforderlich.")
    return value


def _confirm(f: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if f.get(key) is not True:
            raise ValueError(f"{key}: ausdrückliche qualifizierte Bestätigung fehlt.")


def _validate(f: dict[str, Any]) -> None:
    if set(f) - _FACT_KEYS:
        raise ValueError("Unbekannte oder sensible Eingabefelder.")
    for key, value in f.items():
        if key == "bundesland" and (not isinstance(value, str) or value not in _STATES):
            raise ValueError("Ausdrückliches gültiges Bundesland erforderlich.")
        if key in _CONFIRMATIONS and type(value) is not bool:
            raise ValueError("Bestätigungen müssen boolesch sein.")
        if key in _CENTS:
            _cents(value)
        if key == "tax_year" and type(value) is not int:
            raise ValueError("Steuerjahr muss ganzzahlig sein.")
        if key == "calculation_type" and value not in _TYPES:
            raise ValueError("Unbekannte Berechnung.")
        if key == "tariff" and (not isinstance(value, str) or value not in {"basic", "splitting"}):
            raise ValueError("Unbekannter Tarif.")
        if key == "allowance_type" and (
            not isinstance(value, str) or value not in {"employee", "pensioner", "saver"}
        ):
            raise ValueError("Unbekannter Pauschbetrag.")


def _tariff(cents: int, p: dict[str, Any], split: bool) -> int:
    # §32a(5): apply (1), including BOTH euro roundings, to half the joint income.
    x = Decimal(cents // (200 if split else 100))

    def d(key: str) -> Decimal:
        return Decimal(str(p[key]))

    with localcontext() as ctx:
        ctx.prec = 50
        if x <= d("basic_allowance_eur"):
            tax = Decimal(0)
        elif x <= d("first_band_end_eur"):
            y = (x - d("basic_allowance_eur")) / d("scale")
            tax = (d("first_coefficient") * y + d("first_linear")) * y
        elif x <= d("second_band_end_eur"):
            z = (x - d("first_band_end_eur")) / d("scale")
            tax = (d("second_coefficient") * z + d("second_linear")) * z + d("second_offset")
        elif x <= d("third_band_end_eur"):
            tax = d("third_rate") * x - d("third_offset")
        else:
            tax = d("top_rate") * x - d("top_offset")
        return int(tax) * (200 if split else 100)


def process_extraction(
    extraction: dict[str, Any], param_overrides: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    kind = extraction.get("calculation_type")
    if kind in (None, "none"):
        return []
    values: dict[str, Any] = {"deterministic_result": None}
    status = "unavailable"
    try:
        _validate(extraction)
        _confirm(
            extraction,
            "own_matter_confirmed",
            "applicability_confirmed",
            "current_regime_confirmed",
        )
        row = (param_overrides or {}).get("tax_rules", {})
        p = row.get("value")
        if row.get("error") or not isinstance(p, dict):
            raise ValueError("Gültige Parameter fehlen; keine Ersatzwerte.")
        year = extraction.get("tax_year")
        if type(year) is not int or year != p["tax_year"]:
            raise ValueError("Nur verifizierter Veranlagungszeitraum 2026 unterstützt.")
        if (
            not date.fromisoformat(str(row["valid_from"]))
            <= date(year, 1, 1)
            <= date.fromisoformat(str(row["valid_to"]))
        ):
            raise ValueError("Parameterzeitraum passt nicht zum Steuerjahr.")
        if kind == "income_tax":
            _confirm(extraction, "taxable_income_confirmed", "no_special_tariff_confirmed")
            tariff = extraction["tariff"]
            split = tariff == "splitting"
            if split:
                _confirm(extraction, "joint_assessment_confirmed")
            values["tax_cents"] = _tariff(_cents(extraction.get("taxable_income_cents")), p, split)
            scope = (
                "Nur §32a-Grundtarif oder bestätigtes Ehegatten-Splitting nach Abs.5 auf "
                "bestätigtes zu versteuerndes Einkommen; kein Bruttolohn. "
                "§§32b,32d,34,34a,34b,34c, Abs.6, Soli, Kirchensteuer, Steuerermäßigungen und "
                "Anrechnungen ausgeschlossen."
            )
        elif kind == "allowance":
            _confirm(extraction, "allowance_basis_confirmed", "no_higher_expenses_confirmed")
            allowance = extraction["allowance_type"]
            cap = p["allowances_cents"][allowance]
            if allowance == "saver" and extraction.get("joint_assessment_confirmed") is True:
                cap *= 2
            values["allowance_cents"] = min(_cents(extraction.get("eligible_income_cents")), cap)
            scope = (
                "Nur begrenzte Pauschbetragsarithmetik: Arbeitnehmer §9a S.1 Nr.1a, "
                "Renteneinkünfte §22 Nr.1/1a/5 nach §9a S.1 Nr.3 (keine Versorgungsbezüge), "
                "Sparer §20 Abs.9. Einkunftsart, positive Bemessungsgrundlage und gemeinsame "
                "Veranlagung ausdrücklich prüfen; keine Berechtigung oder Steuerersparnis "
                "festgestellt."
            )
        elif kind == "filing_deadline":
            _confirm(
                extraction,
                "mandatory_filing_confirmed",
                "unadvised_confirmed",
                "no_special_filing_regime_confirmed",
                "no_individual_notice_or_extension_confirmed",
                "filing_calendar_confirmed",
            )
            if extraction.get("bundesland") not in _STATES:
                raise ValueError("Ausdrückliches Bundesland fehlt.")
            filing = p["filing_deadline"]
            values["filing_deadline"] = date.fromisoformat(filing["date"]).isoformat()
            values["nominal_filing_deadline"] = date.fromisoformat(filing["nominal"]).isoformat()
            scope = (
                "Nur verpflichtende, nicht beratene Kalenderjahr-Einkommensteuererklärung 2026 "
                "nach §149 Abs.2 AO: sieben Monate, Samstag 31.07.2027 nach §108 Abs.3 AO "
                "auf Montag 02.08.2027. Versioniertes vorausberechnetes Datum; kein allgemeiner "
                "Fristenrechner. filing_calendar_confirmed bestätigt insbesondere keinen "
                "zusätzlichen örtlichen Feiertag am 02.08.2027 und den aktuellen Rechtsstand. "
                "Keine freiwillige oder beratene Erklärung, Übergangsverlängerung nach EGAO, "
                "Einzelaufforderung, individuelle Verlängerung oder sonstiges Sonderregime. "
                "Keine Zahlungsfrist. Voraussetzungen und Änderungen individuell prüfen."
            )
        else:
            _confirm(extraction, "comparison_basis_confirmed")
            values["difference_cents"] = _cents(extraction.get("assessed_cents")) - _cents(
                extraction.get("declared_cents")
            )
            scope = (
                "Festgesetzt minus erklärt in Cent; nur gleichartige bestätigte Beträge, keine "
                "Aussage zu Rechtswidrigkeit, Erstattung oder Abzugsberechtigung."
            )
        status = "provisional"
        values["scope"] = scope
        values["deterministic_result"] = {
            "status": status,
            "review_status": "proposed",
            "calculation_type": kind,
            "tax_year": year,
            **values,
        }
        detail = "Menschliche Rechtsprüfung ausstehend. " + scope
    except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError) as exc:
        detail = str(exc)
    values["computation_detail"] = detail
    amount = values.get("tax_cents", values.get("allowance_cents", values.get("difference_cents")))
    display = (
        values.get("filing_deadline", "")
        if amount is None
        else f'{"-" if amount < 0 else ""}{abs(amount)//100}.{abs(amount)%100:02d} EUR'
    )
    # A same-basis difference is arithmetic, not a finding that the assessment
    # is unlawful. Propagate it so the harness cannot summarise it as agreement.
    difference = values.get("difference_cents", 0) if status == "provisional" else 0
    return [
        {
            "label": str(kind),
            "status": status,
            "document_values": {"extracted_numbers": {}, "authority_calculation": ""},
            "computed_values": values,
            "correct_calculation": display,
            "discrepancy_found": difference != 0,
            "discrepancy_amount_eur": abs(difference) / 100,
            "discrepancy_direction": (
                "zulasten" if difference > 0 else "zugunsten" if difference < 0 else "keine"
            ),
            "relevant_rule": (
                "§32a, §9a, §20 Abs.9 EStG; " "§§149 Abs.2,108 Abs.3 AO; Betragsvergleich"
            ),
            "commentary": detail,
        }
    ]


async def load_parameters(
    extraction: dict[str, Any], source: ParameterSource
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if extraction.get("calculation_type") not in _TYPES:
        return {}, None
    year = extraction.get("tax_year")
    if type(year) is not int or year != 2026:
        return {}, {"missing_input": "supported_tax_year", "parameter_versions": []}
    row = await source.json("tax_rules", date(year, 1, 1))
    return {"tax_rules": row}, {
        "tax_year": year,
        "parameter_versions": [f'tax_rules@{row.get("valid_from")}'],
        "parameters": {
            "tax_rules": {k: str(v) if isinstance(v, date) else v for k, v in row.items()}
        },
    }


def summarise_extraction(extraction: dict[str, Any]) -> dict[str, Any]:
    """Explanation needs the kind/year, never supplied financial amounts or identifiers."""
    allowed = {
        "calculation_type": _TYPES,
        "tariff": {"basic", "splitting"},
        "allowance_type": {"employee", "pensioner", "saver"},
    }
    summary = {
        k: v
        for k, v in extraction.items()
        if k in allowed and isinstance(v, str) and v in allowed[k]
    }
    if type(extraction.get("tax_year")) is int and extraction["tax_year"] == 2026:
        summary["tax_year"] = 2026
    return summary


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Doppelte JSON-Felder sind unzulässig.")
        result[key] = value
    return result


def cross_check_extraction(extraction: dict[str, Any], document: str) -> list[str]:
    kind = extraction.get("calculation_type")
    extraction.clear()
    extraction["calculation_type"] = (
        kind if isinstance(kind, str) and kind in _TYPES else "income_tax"
    )
    try:
        if document.count(EVIDENCE_MARKER) != 1:
            raise ValueError("Ein eindeutiger qualifizierter Eingabeblock fehlt.")
        facts, _ = json.JSONDecoder(object_pairs_hook=_unique_pairs).raw_decode(
            document.split(EVIDENCE_MARKER, 1)[1].lstrip()
        )
        if not isinstance(facts, dict):
            raise ValueError("JSON-Objekt erforderlich.")
        _validate(facts)
        _confirm(facts, "own_matter_confirmed")
        if facts.get("calculation_type") not in _TYPES:
            raise ValueError("Unterstützte Berechnung im Eingabeblock fehlt.")
        extraction.clear()
        extraction.update(facts)
        return []
    except (ValueError, TypeError, KeyError):
        return [
            "Qualifizierter Eingabeblock fehlt oder ist ungültig; "
            "keine Modellbestätigungen übernehmen."
        ]


TAX_CALCULATOR = Calculator(
    id="tax_checks",
    extraction_prompt=(
        "Nur minimale Fakten aus einem einzigen CITIZEN_TAX_FACTS:-JSON-Block "
        "übernehmen. Ohne Block keine Bestätigungen. Keine Steuer-ID, Kontodaten oder "
        "Daten Dritter. calculation_type "
        "income_tax|allowance|assessment_difference|filing_deadline; "
        "tax_year 2026. Beträge nur ganze Cent, Bestätigungen nur ausdrücklich "
        "boolesch."
    ),
    explanation_prompt=(
        "Nur deterministische Ergebnisse erklären, keine eigene Rechnung. Unavailable "
        "bleibt offen. Keine vollständige Steuerfestsetzung oder Anspruchszusage. JSON: "
        "enriched_calculations (index, commentary), overall_assessment (summary, "
        "recommended_action)."
    ),
    load_parameters=load_parameters,
    process=process_extraction,
    summarise_extraction=summarise_extraction,
    cross_check=cross_check_extraction,
    referral_hint=(
        "Bei offenen Voraussetzungen oder Fristen qualifizierte steuerrechtliche Hilfe "
        "für die eigene Angelegenheit suchen."
    ),
)
CALCULATORS = (TAX_CALCULATOR,)
