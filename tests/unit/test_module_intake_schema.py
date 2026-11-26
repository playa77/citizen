"""Module intake schemas are validated data available to API consumers."""

import pytest
import yaml

from app.modules.registry import discover_modules
from app.modules.validate import validate_module_dir


def test_invalid_declared_intake_schema_is_rejected(tmp_path):
    path = tmp_path / "example"
    path.mkdir()
    (path / "module.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "example",
                "version": "0.1.0",
                "core_api": ">=3.3,<4.0",
                "title": {"de": "Beispiel", "en": "Example"},
                "tier": "experimental",
                "scope": {"summary_de": "Eigene Angelegenheit", "own_matter_only": True},
                "intake_schema": "intake-schema.yaml",
            }
        )
    )
    (path / "intake-schema.yaml").write_text("type: invalid-schema-type\n")
    discover_modules(tmp_path)
    report = validate_module_dir(path, tmp_path)
    assert any("intake_schema" in error for error in report.errors)


@pytest.mark.asyncio
async def test_api_exposes_debt_intake_schema_without_selecting_module():
    from app.api.routes.modules import get_module
    from app.db.session import engine
    from app.modules.runtime import request_modules

    try:
        body = await get_module("schuldnerrecht")
    finally:
        await engine.dispose()
    assert body["intake_schema"]["properties"]["own_matter_confirmed"]["const"] is True
    assert "zustellung_tatsaechlich" in body["intake_schema"]["properties"]
    assert request_modules([]) == []
