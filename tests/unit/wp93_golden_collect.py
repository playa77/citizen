"""Collector for the WP-93 zero-behaviour-change golden (tests/unit/test_wp93_golden.py).

Produces a digest of every behaviour WP-93 moved from the core into module
data/code. The same function ran against the v2.0.0 tree (commit aae2888)
to create ``golden/wp93_v2_baseline.json``; the test re-runs it against the
current tree. The adapter isolates the import paths that WP-93 changed.

Only stdlib + app imports that exist in both trees are used at module level.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

PROMPT_AREA_SETS: list[list[str]] = [
    ["sozialrecht"],
    ["erbrecht"],
    ["schenkungsrecht"],
    ["familienrecht"],
    ["erbrecht", "familienrecht"],
    ["sozialrecht", "erbrecht"],
    ["erbrecht", "sozialrecht"],
    ["familienrecht", "sozialrecht", "schenkungsrecht"],
]

INTAKE_TEXTS: list[str] = [
    "",
    "   ",
    "Das Jobcenter hat mein Bürgergeld gekürzt, Sanktion wegen Meldeversäumnis.",
    "Mein Vater ist verstorben, es gibt ein Testament und einen Erbschein.",
    "Schenkung meines Hauses an die Tochter, Freibetrag Schenkung?",
    "Scheidung, Unterhalt und Zugewinn — mein Ex-Mann zahlt nicht.",
    "Vermieter will Kaution nicht zurückzahlen, Nebenkosten falsch.",
    "Kündigung vom Arbeitgeber, Abfindung?",
    "Kaufvertrag Rücktritt Gewährleistung",
    "Bußgeldbescheid und Führerschein",
    "Strafanzeige wegen Vorwurf",
    "jobcenter testament",
    "hof landwirtschaft höfeordnung testament",
    "nichts passendes hier",
]

NORMALISE_INPUTS: list[str | None] = [
    None,
    "",
    "Sozialrecht",
    "erbrecht",
    "Social",
    "sozialhilfe allgemein",
    "Erbschaft",
    "schenken",
    "Scheidungsrecht",
    "Trennungsjahr",
    "nachfolgeplanung",
    "verwaltungsrecht",
    "andere",
    "völlig unbekannt",
]


def _digest(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _selection_variants(compute: Callable[..., Any]) -> dict[str, Any]:
    """Frist results around *today* (selection depends on open vs. lapsed)."""
    today = date.today()
    return {
        "none": None,
        "open_monat": compute(bescheid_datum=today - timedelta(days=3)),
        "open_jahr": compute(bescheid_datum=today - timedelta(days=60), rbb_status="fehlerhaft"),
        "lapsed_monat": compute(bescheid_datum=date(2024, 1, 10)),
        "lapsed_jahr": compute(bescheid_datum=date(2023, 1, 10), rbb_status="fehlt"),
        "kein_va": compute(bescheid_datum=date(2025, 3, 3), ist_verwaltungsakt=False),
    }


def _document_variants(compute: Callable[..., Any]) -> dict[str, Any]:
    """Fixed-date Frist results: rendered bodies must not depend on today."""
    return {
        "none": None,
        "monat": compute(bescheid_datum=date(2025, 5, 14), aufgabe_zur_post=date(2025, 5, 15)),
        "jahr": compute(bescheid_datum=date(2023, 1, 10), rbb_status="fehlt"),
        "kein_va": compute(bescheid_datum=date(2025, 3, 3), ist_verwaltungsakt=False),
    }


def _claims() -> dict[str, list[dict[str, Any]]]:
    ok = {
        "claim_text": "Der Regelbedarf wurde zu niedrig angesetzt.",
        "verification_status": "exakt",
        "user_adjudication": {"status": "confirmed"},
    }
    ok2 = {
        "claim_text": "Die Heizkosten wurden nicht vollständig berücksichtigt.",
        "verification_status": "normalisiert",
        "user_adjudication": {"status": "confirmed"},
    }
    bad = {
        "claim_text": "Unbestätigte Behauptung " + "x" * 90,
        "verification_status": "exakt",
        "user_adjudication": {"status": "pending"},
    }
    return {
        "none": [],
        "verified": [ok, ok2],
        "unverified": [bad],
        "mixed": [bad, ok, {"claim_text": "  "}],
    }


def _reconciliations(line_item: Callable[..., Any]) -> dict[str, list[Any]]:
    def items(cls: Callable[..., Any] | None) -> list[Any]:
        rows = [
            ("Gesamtbedarf", 1103.0, 1103.0, 0.0),
            ("Anspruch (Leistung)", 400.0, 453.27, 53.27),
        ]
        out: list[Any] = []
        for label, jc, korrekt, diff in rows:
            fields = {
                "label": label,
                "jobcenter_ergebnis": jc,
                "korrekt": korrekt,
                "differenz": diff,
                "relevant_rule": "§ 19 SGB II",
                "detail": "",
            }
            out.append(cls(**fields) if cls is not None else fields)
        return out

    negative = items(None)
    negative[1]["differenz"] = -12.5
    only_bedarf = [items(None)[0]]
    return {
        "empty": [],
        "dataclass": items(line_item),
        "dict": items(None),
        "negative": negative,
        "only_bedarf": only_bedarf,
    }


def _strip_footer(text: str) -> str:
    # Footer carries today's date and the app version; the body is the contract.
    return text.split("\n---\nRechtsinformation:", 1)[0]


def collect(adapter: dict[str, Any]) -> dict[str, Any]:
    """Collect the digest map. *adapter* supplies the paths WP-93 changed:

    ``get_prompts``, ``intake`` (module), ``presets_route`` (module),
    ``list_presets``, ``area_source_types``, ``infer_bgb_area``,
    ``regime_banner`` + ``legal_regime``, ``compute_frist``,
    ``line_item_cls``, ``generate_document``, ``select_generator``,
    ``extraction_prompt``, ``explanation_prompt``, ``referral_hint``.
    """
    out: dict[str, Any] = {}

    get_prompts = adapter["get_prompts"]
    for areas in PROMPT_AREA_SETS:
        out[f"prompts:{'+'.join(areas) or '<empty>'}"] = _digest(get_prompts(areas))

    intake = adapter["intake"]
    out["intake:system"] = _digest(intake._INTAKE_SYSTEM)
    out["intake:strict_suffix"] = _digest(intake._STRICT_SUFFIX)
    out["intake:enum"] = list(intake._LEGAL_AREAS_ENUM)
    out["intake:keywords"] = _digest({k: list(v) for k, v in intake._AREA_KEYWORDS.items()})
    out["intake:keyword_order"] = list(intake._AREA_KEYWORDS)
    out["intake:fallback"] = [list(intake._fallback_areas_from_text(t)) for t in INTAKE_TEXTS]
    out["intake:normalise"] = [intake._normalise_area(a) for a in NORMALISE_INPUTS]

    route = adapter["presets_route"]
    out["presets:list"] = _digest(adapter["list_presets"]())
    # D-070 deliberately changes the no-match instruction; historical pin retired.
    out["presets:keyword_fallback"] = [list(map(str, row[:2])) for row in route._KEYWORD_FALLBACK]
    out["presets:keyword_suggest"] = [route._keyword_suggest(t) for t in INTAKE_TEXTS]

    out["corpus:area_source_types"] = {
        k: list(v) for k, v in adapter["area_source_types"]().items()
    }
    infer = adapter["infer_bgb_area"]
    out["corpus:bgb_tag_digest"] = _digest(
        {p: infer(f"BGB > § {p}") for p in range(1, 2400)}
    )
    out["corpus:bgb_tag_none"] = [infer(""), infer("BGB > Allgemein")]

    legal_regime = adapter["legal_regime"]
    banner = adapter["regime_banner"]
    out["regime:banners"] = {
        str(d): [legal_regime(d), _digest(banner(legal_regime(d)))]
        for d in (date(2022, 1, 1), date(2023, 7, 1), date(2025, 6, 1), date(2026, 7, 1))
    }

    out["calc:extraction_prompt"] = _digest(adapter["extraction_prompt"])
    out["calc:explanation_prompt"] = _digest(adapter["explanation_prompt"])
    out["calc:referral_hint"] = adapter["referral_hint"]

    selection = _selection_variants(adapter["compute_frist"])
    fristen = _document_variants(adapter["compute_frist"])
    claims = _claims()
    recs = _reconciliations(adapter["line_item_cls"])
    generate = adapter["generate_document"]
    select = adapter["select_generator"]
    out["documents:select"] = {name: select(fr, module_id="sozialrecht") for name, fr in selection.items()}

    doc_types = [
        "widerspruch",
        "widerspruch_jahresfrist",
        "ueberpruefungsantrag_44",
        "akteneinsichtsantrag_25",
        "gibt_es_nicht",
    ]
    user_datas: dict[str, dict[str, str] | None] = {
        "none": None,
        "name_only": {"name": "[[PERSON_1]]"},
        "full": {"name": "[[PERSON_1]]", "adresse": "[[ADRESSE_1]]"},
    }
    docs: dict[str, str] = {}
    for doc_type in doc_types:
        for frist_name in fristen:
            for rec_name, rec in recs.items():
                for claim_name, claim_list in claims.items():
                    for ud_name, ud in user_datas.items():
                        for inputs_name, inputs in {
                            "none": {},
                            "all": {
                                "bescheid_datum": date(2025, 2, 3),
                                "aktenzeichen": "AZ-123",
                                "behoerde": "[[BEHOERDE_1]]",
                            },
                            "empty_strings": {"aktenzeichen": "", "behoerde": ""},
                        }.items():
                            doc = generate(
                                doc_type,
                                fristen[frist_name],
                                rec,
                                claim_list,
                                user_data=ud,
                                module_id="sozialrecht",
                                **inputs,
                            )
                            key = "|".join(
                                (doc_type, frist_name, rec_name, claim_name, ud_name, inputs_name)
                            )
                            docs[key] = _digest(
                                {
                                    "title": doc.title,
                                    "body": _strip_footer(doc.rendered_text),
                                    "slots": [dataclasses.asdict(s) for s in doc.slots],
                                    "warnings": doc.warnings,
                                    "document_type": doc.document_type,
                                }
                            )
    out["documents:count"] = len(docs)
    out["documents:digest"] = _digest(docs)
    out["documents:sample"] = {k: docs[k] for k in sorted(docs)[:: max(1, len(docs) // 40)]}
    return out
