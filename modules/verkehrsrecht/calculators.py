"""Qualified traffic checks (D-076); no inferred legal facts or replacement parameters."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from app.modules.sdk import Calculator, ParameterSource

_TYPES = {"sanction_lookup", "prosecution_limitation", "driving_ban_start", "register_retention"}
_BASES = {
    "sanction_lookup": "BKatV Anlage Nr.11.3, Anhang Tabelle 1c; FeV Anlage 13",
    "prosecution_limitation": "§26 Abs.3 StVG; §§31–33 OWiG",
    "driving_ban_start": "§25 Abs.2, Abs.3 Nr.1, Abs.4 und Abs.6 StVG",
    "register_retention": "§29 Abs.1, Abs.4 Nr.3, Abs.6 StVG; §4 StVG",
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


def _add_months(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def inclusive_period_end(day: date, months: int) -> date:
    """Event day counts: preceding anniversary day, or last day if number is absent."""
    anniversary = _add_months(day, months)
    return anniversary - timedelta(days=1) if anniversary.day == day.day else anniversary


def _covered(day: date, row: dict[str, Any], as_of: date) -> None:
    if not _date(str(row["valid_from"])) <= day <= as_of:
        raise ValueError("Historischer Übergangsfall oder zukünftiges Ereignis: gesondert prüfen.")


def _sanction(
    f: dict[str, Any], p: dict[str, Any], row: dict[str, Any], day: date
) -> dict[str, Any]:
    _covered(_date(f.get("offence_on")), row, day)
    _confirm(
        f,
        "tolerance_deducted_confirmed",
        "ordinary_negligence_confirmed",
        "no_aggravation_confirmed",
        "no_repeat_offence_confirmed",
    )
    if f.get("vehicle_class") != "bkat_11_3" or f.get("location") not in ("inside", "outside"):
        raise ValueError("Nur bestätigte Fahrzeuggruppe Nr.11.3 und Ortslage unterstützt.")
    excess = _int(f.get("excess_kmh"), 1)
    matches = [
        band
        for band in p["speed_bands"]
        if band["min"] <= excess and (band["max"] is None or excess <= band["max"])
    ]
    if len(matches) != 1:
        raise ValueError("Sanktionseintrag fehlt oder ist mehrdeutig.")
    band = matches[0]
    amount, points, ban = band[f["location"]]
    return {
        "amount_cents": _int(amount),
        "points": _int(points),
        "driving_ban_months": _int(ban),
        "table_entry": band["entry"],
        "scope": "Nur Nr.11.3 Geschwindigkeitsüberschreitungen nach bestätigtem Toleranzabzug, "
        "gewöhnliche Fahrlässigkeit ohne Gefährdung, Sachschaden oder Wiederholungsfall. "
        "Regelsätze ohne Gebühren/Auslagen; kein verbindlicher Bescheid und keine "
        "Feststellung des tatsächlichen Punktestands. Keine vollständige BKat-Abdeckung.",
    }


def _limitation(
    f: dict[str, Any], p: dict[str, Any], row: dict[str, Any], day: date
) -> dict[str, Any]:
    _confirm(
        f,
        "offence_completed_confirmed",
        "complete_file_confirmed",
        "no_suspension_confirmed",
        "no_court_proceeding_confirmed",
    )
    if f.get("offence_regime") != "stvg_24_1_standard":
        raise ValueError("Nur bestätigter gewöhnlicher §24 Abs.1 StVG; keine Sondertatbestände.")
    start = _date(f.get("offence_on"))
    _covered(start, row, day)
    events = f.get("interruptions")
    if not isinstance(events, list) or len(events) > 100:
        raise ValueError("Vollständige ausdrücklich bestätigte Unterbrechungsliste fehlt.")
    end = inclusive_period_end(start, _int(p["limitation_months"], 1))
    absolute = inclusive_period_end(start, _int(p["absolute_minimum_months"], 1))
    previous = start
    first_hearing_used = False
    for event in events:
        _confirm(event, "qualified_confirmed")
        if event.get("basis") not in ("owig_33_1_1", "owig_33_1_9"):
            raise ValueError("Unterbrechungstatbestand nicht unterstützt; Akte prüfen.")
        if event["basis"] == "owig_33_1_1":
            if first_hearing_used:
                raise ValueError("Erste Anhörung/Bekanntgabe/Anordnung unterbricht nur einmal.")
            first_hearing_used = True
        on = _date(event.get("date"))
        # A late event cannot resurrect prosecution; no legal expiry finding is inferred.
        if not previous <= on <= min(day, end, absolute):
            raise ValueError("Ereignisfolge ungeordnet, künftig oder nach rechnerischer Grenze.")
        previous = on
        end = min(inclusive_period_end(on, _int(p["limitation_months"], 1)), absolute)
    return {
        "expiry_date": min(end, absolute).isoformat(),
        "absolute_limit_date": absolute.isoformat(),
        "scope": "Rechnerische Grenze im bestätigten aktuellen Sechsmonatsregime. "
        "Tattag/Unterbrechungstag zählt mit; keine Wochenendverschiebung. "
        "Keine Aussage, dass Verjährung eingetreten ist. Aktenvollständigkeit, personenbezogene "
        "Wirkung, rechtzeitiger Geschäftsgang, §33 Abs.1 Nr.9 (Erlass/Zustellung), "
        "Ruhen und gerichtliche Ereignisse rechtlich prüfen. Alt-/Übergangsfälle ausgeschlossen.",
    }


def _ban(f: dict[str, Any], p: dict[str, Any], row: dict[str, Any], day: date) -> dict[str, Any]:
    _confirm(
        f,
        "finality_confirmed",
        "ordered_regime_confirmed",
        "custody_or_endorsement_required_confirmed",
        "no_multiple_bans_confirmed",
    )
    final = _date(f.get("final_on"))
    _covered(final, row, day)
    regime = f.get("regime")
    if regime not in ("stvg_25_2", "stvg_25_3_1"):
        raise ValueError("Nur bestätigtes aktuelles Verwahrungs-/Vermerkregime unterstützt.")
    cap = _add_months(final, _int(p["ban_months"][regime], 1))
    custody = _date(f["custody_on"]) if f.get("custody_on") is not None else None
    if custody:
        _covered(custody, row, day)
        if custody < final:
            raise ValueError("Verwahrung vor Rechtskraft: Sonderfall/Anrechnung prüfen.")
    return {
        "latest_effective_date": cap.isoformat(),
        "effective_date": min(custody, cap).isoformat() if custody else None,
        "duration_start_date": custody.isoformat() if custody else None,
        "scope": "Grenze der Wirksamkeit, kein Ende des Fahrverbots und keine Fahrerlaubnis. "
        "Ohne Verwahrungsdatum bleibt die frühere tatsächliche Wirksamkeit offen; spätestens "
        "an der Grenze ist das Verbot wirksam. Die Verbotsdauer beginnt bei erforderlicher "
        "Verwahrung/Vermerk erst damit (§25 Abs.6). Keine Wochenendverlängerung. "
        "Mehrere Verbote, ausländische Sonderregime, vorläufige Entziehung und Anrechnung "
        "bedürfen gesonderter Prüfung; vier Monate nur bei entsprechend bestätigter Anordnung.",
    }


def _register(
    f: dict[str, Any], p: dict[str, Any], row: dict[str, Any], day: date
) -> dict[str, Any]:
    _confirm(
        f,
        "complete_register_confirmed",
        "no_special_register_rules_confirmed",
        "no_probationary_license_confirmed",
    )
    records = f.get("records")
    if not isinstance(records, list) or not 1 <= len(records) <= 100:
        raise ValueError("Vollständige Registereinträge fehlen.")
    results, seen, total = [], set(), 0
    for record in records:
        _confirm(record, "owi_classification_confirmed")
        rid = record.get("record_id")
        if not isinstance(rid, str) or not rid.strip() or rid in seen:
            raise ValueError("Eindeutige Registerkennung erforderlich.")
        seen.add(rid)
        points = _int(record.get("points"), 1)
        if points not in (1, 2):
            raise ValueError("Nur bestätigte OWi-Einträge mit einem oder zwei Punkten unterstützt.")
        final = _date(record.get("final_on"))
        _covered(final, row, day)
        retention = inclusive_period_end(final, _int(p["retention_months"][str(points)], 1))
        # The overlap starts after the inclusive retention end. Compute from
        # that start so a leap day is retained; deletion is possible afterwards.
        overlap_end = inclusive_period_end(
            retention + timedelta(days=1), _int(p["overlap_months"], 1)
        )
        deletion = overlap_end + timedelta(days=1)
        total += points
        results.append(
            {
                "record_id": rid,
                "points": points,
                "retention_end_date": retention.isoformat(),
                "overlap_end_date": overlap_end.isoformat(),
                "deletion_earliest_date": deletion.isoformat(),
            }
        )
    return {
        "records": results,
        "recorded_points_sum": total,
        "scope": "Nur unbereinigte Summe der gelieferten OWi-Einträge, kein aktueller Punktestand. "
        "Tilgungsfrist ab Rechtskrafttag, anschließend Überliegefrist. Tilgungsreife ist nicht "
        "Löschung; Sonderfälle der Probezeit und §29 Abs.6 bleiben ausgeschlossen. "
        "Tattagprinzip, Maßnahmenstufen, Ermäßigungen und Verwertbarkeit gesondert prüfen. "
        "Keine automatische Entziehung oder Bestätigung einer Fahrberechtigung.",
    }


_PROCESSORS = {
    "sanction_lookup": _sanction,
    "prosecution_limitation": _limitation,
    "driving_ban_start": _ban,
    "register_retention": _register,
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
            raise ValueError("Unbekannte Berechnung.")
        _confirm(extraction, "applicability_confirmed", "current_regime_confirmed")
        day = _date(extraction.get("as_of"))
        row = (param_overrides or {}).get("traffic_rules", {})
        if (
            row.get("error")
            or not isinstance(row.get("value"), dict)
            or not _date(str(row.get("valid_from"))) <= day <= _date(str(row.get("valid_to")))
        ):
            raise ValueError("Keine gültigen begrenzten Parameter; keine Ersatzwerte.")
        computed = _PROCESSORS[kind](extraction, row["value"], row, day)
        status = "provisional"
        # The harness and dossier project this existing SDK field, rather
        # than the module-specific top-level keys. Keep qualified values intact.
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
            else (
                "Späteste Wirksamkeit: "
                + computed["latest_effective_date"]
                + "; kein Ende des Fahrverbots"
                if "latest_effective_date" in computed
                else computed.get("expiry_date", "")
            ),
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
    row = await source.json("traffic_rules", day)
    return {"traffic_rules": row}, {
        "as_of": day.isoformat(),
        "parameter_versions": [f'traffic_rules@{row.get("valid_from")}'],
        "parameters": {
            "traffic_rules": {k: str(v) if isinstance(v, date) else v for k, v in row.items()}
        },
    }


EXTRACTION_PROMPT = """Nur ausdrücklich belegte Fakten als JSON, unbekannt=null.
Keine rechtliche Bestätigung selbst aus Rohdaten oder Schweigen ableiten.
calculation_type: sanction_lookup|prosecution_limitation|driving_ban_start|register_retention|none.
as_of ISO-Datum; applicability_confirmed und current_regime_confirmed nur bei ausdrücklich
qualifiziert bestätigter Anwendbarkeit des am 27.11.2026 verifizierten aktuellen Regimes.
Sanktion: offence_on, vehicle_class=bkat_11_3 (Fahrzeuge außerhalb Nr.11.1/11.2), location
inside|outside, excess_kmh ganze km/h nach bestätigtem Toleranzabzug;
tolerance_deducted_confirmed, ordinary_negligence_confirmed, no_aggravation_confirmed,
no_repeat_offence_confirmed (insbesondere §4 Abs.2 BKatV). Keine Messwerte selbst bereinigen.
Verjährung: offence_on (bestätigtes Ende der Tat), offence_regime=stvg_24_1_standard;
offence_completed_confirmed, complete_file_confirmed, no_suspension_confirmed,
no_court_proceeding_confirmed; interruptions ausdrücklich vollständige chronologische Liste
{date, basis:owig_33_1_1|owig_33_1_9, qualified_confirmed}. Nr.1: rechtlich bestätigte
wirksame erste Vernehmung/Bekanntgabe/Anordnung, nicht Empfangsdatum eines Anhörungsbogens.
Nr.9: qualifiziertes Unterbrechungsdatum unter Berücksichtigung von Erlass, tatsächlicher
Zustellung binnen zwei Wochen oder späterer Zustellung und §33 Abs.2 OWiG; nie selbst ableiten.
Fahrverbot: final_on, regime=stvg_25_2|stvg_25_3_1, custody_on oder null;
finality_confirmed, ordered_regime_confirmed, custody_or_endorsement_required_confirmed,
no_multiple_bans_confirmed. §25 Abs.3 Nr.1 nur ausdrücklich bestätigte Viermonatsanordnung;
sonstige ausländische Fälle, Vorverwahrung/Anrechnung und mehrere Verbote nicht unterstützt.
Register: complete_register_confirmed, no_special_register_rules_confirmed,
no_probationary_license_confirmed; records Liste {record_id, final_on, points:1|2,
owi_classification_confirmed}. Kein tatsächlicher Punktestand oder Fahrberechtigung ableiten.
Alle *_confirmed Felder benötigen ausdrückliche qualifizierte Bestätigung."""

TRAFFIC_CALCULATOR = Calculator(
    id="traffic_checks",
    extraction_prompt=EXTRACTION_PROMPT,
    explanation_prompt="Nur deterministische Ergebnisse auf Deutsch erklären; "
    "keine eigene Rechnung. "
    "Unavailable bleibt offen; keine Aussage zu Verjährungseintritt oder Fahrberechtigung. "
    "JSON: enriched_calculations (index, commentary), "
    "overall_assessment (summary, recommended_action).",
    load_parameters=load_parameters,
    process=process_extraction,
    summarise_extraction=lambda extraction: extraction,
    cross_check=lambda extraction, document: [],
    referral_hint="Lassen Sie Zustellung, Aktenlage, Fristen und Fahrverbot "
    "unverzüglich anwaltlich prüfen.",
)
CALCULATORS = (TRAFFIC_CALCULATOR,)
