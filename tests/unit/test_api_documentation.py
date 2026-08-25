"""Guard G4 — API_DOCUMENTATION.md must stay in sync with the live routes.

Parses every ``METHOD /path`` occurrence from the documentation's code spans
and asserts the set matches the FastAPI OpenAPI route table exactly
(framework-provided self-description endpoints are documented in prose and
excluded from the strict comparison).

Version: 1.0.0 | 2026-08-25
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.routing import APIRoute

from app.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOC = PROJECT_ROOT / "API_DOCUMENTATION.md"

# Framework endpoints: present in the app but documented in prose only.
_FRAMEWORK_ROUTES = {
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/redoc"),
}

_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# Matches e.g. "GET /api/v1/cases/{case_id}" inside backticks or tables.
_ROUTE_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE) (/[\w\-{}/.]+)")


def _documented_routes() -> set[tuple[str, str]]:
    """Return documented route pairs under /api/ (the strict-parity scope)."""
    text = DOC.read_text(encoding="utf-8")
    found: set[tuple[str, str]] = set()
    for method, path in _ROUTE_RE.findall(text):
        method_u = method.upper()
        if method_u in _METHODS and path.startswith("/api/"):
            found.add((method_u, path.rstrip("`")))
    return found


def _app_routes() -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                if route.path.startswith("/api/"):
                    result.add((method.upper(), route.path))
    return result


def test_documentation_file_exists() -> None:
    assert DOC.is_file(), "API_DOCUMENTATION.md must exist at the repository root"


def test_service_routes_mentioned() -> None:
    """/health and /robots.txt live outside /api and are documented in prose."""
    text = DOC.read_text(encoding="utf-8")
    assert "`GET /health`" in text
    assert "`GET /robots.txt`" in text


def test_every_app_route_is_documented() -> None:
    missing = _app_routes() - _FRAMEWORK_ROUTES - _documented_routes()
    assert not missing, f"Routes missing from API_DOCUMENTATION.md: {sorted(missing)}"


def test_no_phantom_routes_in_documentation() -> None:
    phantom = _documented_routes() - _app_routes()
    assert not phantom, f"Documented routes that do not exist in the app: {sorted(phantom)}"
