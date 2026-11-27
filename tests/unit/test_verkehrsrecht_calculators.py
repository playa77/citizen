"""Literal traffic arithmetic and refusal contracts, independent of inference."""

from datetime import date
from pathlib import Path

import pytest
import yaml


def calculator():
    path = Path("modules/verkehrsrecht/calculators.py")
    assert path.exists(), "Traffic calculator implementation is absent"
    from app.modules.content import import_module_file
    from app.modules.registry import default_modules_root, discover_modules

    return import_module_file(
        discover_modules(default_modules_root())["verkehrsrecht"], "calculators"
    )


def parameters():
    path = Path("modules/verkehrsrecht/parameters/traffic.yaml")
    assert path.exists(), "Traffic parameters are absent"
    return {r["key"]: r for r in yaml.safe_load(path.read_text())["parameters"]}


def result(kind, **facts):
    rows = {key: {**r, "value": r["value_json"]} for key, r in parameters().items()}
    f = dict(
        calculation_type=kind,
        as_of="2026-12-20",
        applicability_confirmed=True,
        current_regime_confirmed=True,
        **facts,
    )
    return calculator().process_extraction(f, rows)[0]


def sanction(**overrides):
    return dict(
        offence_on="2026-11-27",
        vehicle_class="bkat_11_3",
        location="inside",
        excess_kmh=21,
        tolerance_deducted_confirmed=True,
        ordinary_negligence_confirmed=True,
        no_aggravation_confirmed=True,
        no_repeat_offence_confirmed=True,
        **overrides,
    )


@pytest.mark.parametrize(
    "excess,location,cents,points,months",
    [
        (10, "inside", 3000, 0, 0),
        (11, "outside", 4000, 0, 0),
        (20, "inside", 7000, 0, 0),
        (21, "inside", 11500, 1, 0),
        (25, "outside", 10000, 1, 0),
        (26, "inside", 18000, 1, 0),
        (30, "inside", 18000, 1, 0),
        (31, "inside", 26000, 2, 1),
        (40, "outside", 20000, 1, 0),
        (41, "outside", 32000, 2, 1),
        (50, "inside", 40000, 2, 1),
        (51, "inside", 56000, 2, 2),
        (60, "outside", 48000, 2, 1),
        (61, "outside", 60000, 2, 2),
        (70, "inside", 70000, 2, 3),
        (71, "outside", 70000, 2, 3),
    ],
)
def test_speed_bands(excess, location, cents, points, months):
    f = sanction()
    f.update(excess_kmh=excess, location=location)
    r = result("sanction_lookup", **f)
    assert r["status"] == "provisional"
    c = r["computed_values"]
    assert (c["amount_cents"], c["points"], c["driving_ban_months"]) == (cents, points, months)
    assert c["table_entry"].startswith("11.3.")


@pytest.mark.parametrize(
    "field,value",
    [
        ("vehicle_class", "truck"),
        ("location", "unknown"),
        ("excess_kmh", True),
        ("excess_kmh", 0),
        ("ordinary_negligence_confirmed", False),
        ("tolerance_deducted_confirmed", None),
        ("no_aggravation_confirmed", None),
        ("no_repeat_offence_confirmed", False),
        ("offence_on", "2026-10-01"),
    ],
)
def test_unsupported_sanction_never_guesses(field, value):
    f = sanction()
    f[field] = value
    assert result("sanction_lookup", **f)["status"] == "unavailable"


def limitation(**overrides):
    f = {
        "offence_on": "2026-11-27",
        "offence_regime": "stvg_24_1_standard",
        "offence_completed_confirmed": True,
        "complete_file_confirmed": True,
        "no_suspension_confirmed": True,
        "no_court_proceeding_confirmed": True,
        "interruptions": [],
    }
    f.update(overrides)
    return f


def test_current_six_month_limitation_and_absolute_cap():
    r = result("prosecution_limitation", **limitation())
    assert r["status"] == "provisional"
    assert r["computed_values"]["expiry_date"] == "2027-05-26"
    assert r["computed_values"]["absolute_limit_date"] == "2028-11-26"
    assert "expired" not in r["computed_values"]


def test_qualified_interruption_restarts_without_service_fiction():
    r = result(
        "prosecution_limitation",
        **limitation(
            interruptions=[
                {"date": "2026-12-01", "basis": "owig_33_1_1", "qualified_confirmed": True}
            ]
        ),
    )
    assert r["computed_values"]["expiry_date"] == "2027-05-31"


@pytest.mark.parametrize(
    "overrides",
    [
        {"complete_file_confirmed": False},
        {"no_suspension_confirmed": None},
        {"no_court_proceeding_confirmed": False},
        {"offence_regime": "alcohol"},
        {"interruptions": None},
        {"interruptions": [{"date": "2026-12-01", "basis": "hearing_received"}]},
        {
            "interruptions": [
                {"date": "2026-12-21", "basis": "owig_33_1_1", "qualified_confirmed": True}
            ]
        },
        {
            "interruptions": [
                {"date": "2026-11-26", "basis": "owig_33_1_1", "qualified_confirmed": True}
            ]
        },
    ],
)
def test_incomplete_or_unsupported_limitation_refuses(overrides):
    assert result("prosecution_limitation", **limitation(**overrides))["status"] == "unavailable"


def ban(**overrides):
    f = {
        "final_on": "2026-11-27",
        "regime": "stvg_25_3_1",
        "finality_confirmed": True,
        "ordered_regime_confirmed": True,
        "custody_or_endorsement_required_confirmed": True,
        "no_multiple_bans_confirmed": True,
        "custody_on": None,
    }
    f.update(overrides)
    return f


def test_current_driving_ban_caps_are_not_end_of_ban_dates():
    c = result("driving_ban_start", **ban())["computed_values"]
    assert c["latest_effective_date"] == "2027-03-27"
    assert "expiry_date" not in c  # Saturday cap, no procedural rollover
    assert c["duration_start_date"] is None
    c = result("driving_ban_start", **ban(regime="stvg_25_2"))["computed_values"]
    assert c["latest_effective_date"] == "2026-12-27"
    assert c["duration_start_date"] is None


def test_custody_and_effectiveness_are_separate():
    c = result("driving_ban_start", **ban(custody_on="2026-12-05"))["computed_values"]
    assert c["effective_date"] == "2026-12-05"
    assert c["duration_start_date"] == "2026-12-05"
    assert result("driving_ban_start", **ban(custody_on="2026-11-26"))["status"] == "unavailable"
    assert (
        result("driving_ban_start", **ban(no_multiple_bans_confirmed=False))["status"]
        == "unavailable"
    )


def register(**overrides):
    f = {
        "records": [
            {
                "record_id": "a",
                "final_on": "2026-11-27",
                "points": 1,
                "owi_classification_confirmed": True,
            }
        ],
        "complete_register_confirmed": True,
        "no_special_register_rules_confirmed": True,
        "no_probationary_license_confirmed": True,
    }
    f.update(overrides)
    return f


def test_register_retention_is_not_automatic_point_or_entitlement_decision():
    r = result("register_retention", **register())
    assert r["status"] == "provisional"
    c = r["computed_values"]
    row = c["records"][0]
    assert row["retention_end_date"] == "2029-05-26"
    assert row["deletion_earliest_date"] == "2030-05-27"
    assert c["recorded_points_sum"] == 1
    assert "current_points" not in c and "may_drive" not in c
    f = register()
    f["records"][0]["points"] = 2
    row = result("register_retention", **f)["computed_values"]["records"][0]
    assert row["retention_end_date"] == "2031-11-26"


@pytest.mark.parametrize(
    "overrides",
    [
        {"complete_register_confirmed": False},
        {"no_special_register_rules_confirmed": False},
        {"no_probationary_license_confirmed": False},
        {"records": []},
        {
            "records": [
                {
                    "record_id": "a",
                    "final_on": "2026-11-27",
                    "points": 3,
                    "owi_classification_confirmed": True,
                }
            ]
        },
    ],
)
def test_unknown_register_refuses(overrides):
    assert result("register_retention", **register(**overrides))["status"] == "unavailable"


def test_missing_expired_or_future_parameters_never_fall_back():
    c = calculator()
    f = dict(
        calculation_type="sanction_lookup",
        as_of="2026-12-20",
        applicability_confirmed=True,
        current_regime_confirmed=True,
        **sanction(),
    )
    assert c.process_extraction(f, {})[0]["status"] == "unavailable"
    row = parameters()["traffic_rules"]
    row = {**row, "value": row["value_json"]}
    for day in ("2026-11-26", "2027-01-01"):
        assert (
            c.process_extraction({**f, "as_of": day}, {"traffic_rules": row})[0]["status"]
            == "unavailable"
        )
    assert c.process_extraction({"calculation_type": "none"}, {}) == []
    assert c.process_extraction({"calculation_type": "invented"}, {})[0]["status"] == "unavailable"


def test_inclusive_calendar_boundaries_and_invalid_dates():
    c = calculator()
    assert c.inclusive_period_end(date(2027, 8, 31), 6) == date(2028, 2, 29)
    assert c.inclusive_period_end(date(2028, 2, 29), 12) == date(2029, 2, 28)
    assert (
        result("prosecution_limitation", **limitation(offence_on="invalid"))["status"]
        == "unavailable"
    )


async def test_parameter_loader_binds_version_and_type():
    c = calculator()

    class Source:
        async def json(self, key, as_of):
            assert key == "traffic_rules" and as_of == date(2026, 12, 20)
            row = parameters()[key]
            return {**row, "value": row["value_json"]}

    rows, snapshot = await c.load_parameters(
        {"calculation_type": "sanction_lookup", "as_of": "2026-12-20"}, Source()
    )
    assert rows["traffic_rules"]["review_status"] == "proposed"
    assert snapshot["as_of"] == "2026-12-20"


def test_ban_never_presents_commencement_as_expiry():
    r = result("driving_ban_start", **ban())
    assert "expiry_date" not in r["computed_values"]
    assert r["correct_calculation"] == "Späteste Wirksamkeit: 2027-03-27; kein Ende des Fahrverbots"


def test_deletion_is_after_inclusive_overlap_and_handles_leap_year():
    r = result("register_retention", **register())
    row = r["computed_values"]["records"][0]
    assert row["overlap_end_date"] == "2030-05-26"
    assert row["deletion_earliest_date"] == "2030-05-27"
    # Broad fixture validity isolates calendar arithmetic, not historical legal applicability.
    p = parameters()["traffic_rules"]
    p = {**p, "value": p["value_json"], "valid_from": "2024-01-01"}
    f = register()
    f["records"][0]["final_on"] = "2024-08-29"
    f.update(
        calculation_type="register_retention",
        as_of="2026-12-20",
        applicability_confirmed=True,
        current_regime_confirmed=True,
    )
    row = calculator().process_extraction(f, {"traffic_rules": p})[0]["computed_values"]["records"][
        0
    ]
    assert row["retention_end_date"] == "2027-02-28"
    assert row["overlap_end_date"] == "2028-02-29"
    assert row["deletion_earliest_date"] == "2028-03-01"


def test_first_hearing_order_and_actual_hearing_cannot_interrupt_twice():
    events = [
        {"date": "2026-11-28", "basis": "owig_33_1_1", "qualified_confirmed": True},
        {"date": "2026-12-01", "basis": "owig_33_1_1", "qualified_confirmed": True},
    ]
    assert (
        result("prosecution_limitation", **limitation(interruptions=events))["status"]
        == "unavailable"
    )


@pytest.mark.parametrize(
    "kind,factory,field",
    [
        ("sanction_lookup", sanction, "amount_cents"),
        ("prosecution_limitation", limitation, "expiry_date"),
        ("driving_ban_start", ban, "latest_effective_date"),
        ("register_retention", register, "records"),
    ],
)
def test_actual_traffic_result_survives_explanation_and_dossier_projection(kind, factory, field):
    from app.dossier.builder import _calculations_section
    from app.services.calculation import _summarise_engine_output

    r = result(kind, **factory())
    for projected in [
        _summarise_engine_output([r])[0],
        _calculations_section({"result": {"calculations_found": [r]}})["items"][0],
    ]:
        d = projected["deterministic_result"]
        assert isinstance(d, dict)
        assert d[field] == r["computed_values"][field]
        assert d["status"] == "provisional" and d["review_status"] == "proposed"
        assert d["scope"]
    f = factory()
    # Every calculator must preserve a null result when qualification fails.
    f["current_regime_confirmed"] = False
    rows = {k: {**v, "value": v["value_json"]} for k, v in parameters().items()}
    refused = calculator().process_extraction(
        dict(calculation_type=kind, as_of="2026-12-20", applicability_confirmed=True, **f), rows
    )[0]
    assert refused["computed_values"].get("deterministic_result") is None
