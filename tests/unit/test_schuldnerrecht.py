"""WP-130: explicit module scope and debt-specific preparation."""

from app.dossier.module_content import module_dossier, select_checklist
from app.modules.areas import area_tables
from app.modules.registry import default_modules_root, load_registry
from app.modules.runtime import get_manifest, request_modules


def test_debt_module_is_explicit_and_experimental() -> None:
    manifest = get_manifest("schuldnerrecht")
    assert manifest.tier == "experimental"
    assert manifest.raw["scope"]["own_matter_only"] is True
    assert request_modules([]) == []
    assert request_modules(["schuldnerrecht"]) == ["schuldnerrecht"]
    assert request_modules(["schuldnerrecht", "sozialrecht"]) == ["schuldnerrecht", "sozialrecht"]
    assert "schuldnerrecht" in load_registry(default_modules_root(), "self", None).enabled
    assert "schuldnerrecht" not in load_registry(default_modules_root(), "provider", None).enabled


def test_explicit_debt_scope_uses_its_own_persona_and_sources() -> None:
    from app.services.prompts import get_prompts

    prompts = get_prompts(["schuldnerrecht"])
    assert any("ZPO" in text for text in prompts.values())
    assert all("Jobcenter" not in text for text in prompts.values())
    tables = area_tables()
    assert tables.prompt_profiles["schuldnerrecht"] != tables.prompt_profiles["sozialrecht"]
    assert tables.source_types["schuldnerrecht"] == ("bgb", "zpo", "inso", "rdg", "rvg")


def test_appointment_preparation_includes_creditors_and_service_evidence() -> None:
    content = module_dossier("schuldnerrecht")
    assert content is not None
    items = select_checklist([content], ["Synthetischer Mahnbescheid mit Kontopfändung"])
    ids = {item["id"].split(":")[-1] for item in items}
    assert {"glaeubigerliste", "forderungsunterlagen", "zustellnachweise"} <= ids


def test_intake_suggests_debt_area_without_loading_it() -> None:
    from app.services.intake import _INTAKE_SYSTEM, _fallback_areas_from_text, _normalise_area

    assert _fallback_areas_from_text("Synthetischer Mahnbescheid vom Inkasso") == (
        "schuldnerrecht",
        [],
    )
    assert _normalise_area("Schulden") == "schuldnerrecht"
    assert "schuldnerrecht" in _INTAKE_SYSTEM
    assert request_modules([]) == []
