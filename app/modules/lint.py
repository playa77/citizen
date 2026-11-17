"""Module import lint (WP-91; ARCHITECTURE.md § 2.4).

Module code may import only ``app.modules.sdk`` — importing anything else
from ``app.*`` fails the lint. Relative imports inside the module package
and third-party/stdlib imports are allowed; the rule bounds the coupling
between reviewable community data packages and the compliance core.

Run as part of the unit suite (``tests/unit/test_modules_registry.py``) so
CI enforces it; the WP-115 validator (``scripts/validate_module.py``) runs it
per module, and the registry runs it on every enabled out-of-tree module.
"""

# Semantic Version: 0.2.0 | 2026-11-17 — lint_module_dir() for one module (WP-112/WP-115).
# 0.1.0

from __future__ import annotations

import ast
from pathlib import Path

#: The only ``app.*`` import module code may use.
ALLOWED_APP_MODULES = frozenset({"app.modules.sdk"})


def _violations_in_file(path: Path) -> list[str]:
    """Return one message per disallowed app-import in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [f"{path}: unreadable Python ({exc})"]

    messages: list[str] = []
    for node in ast.walk(tree):
        imported: list[tuple[int, str]] = []
        if isinstance(node, ast.Import):
            imported = [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # Relative imports stay inside the module package — allowed.
                continue
            if node.module:
                imported = [(node.lineno, node.module)]
        for lineno, name in imported:
            if not name.startswith("app."):
                continue
            if name in ALLOWED_APP_MODULES or any(
                name == allowed or name.startswith(allowed + ".") for allowed in ALLOWED_APP_MODULES
            ):
                continue
            messages.append(
                f"{path}:{lineno}: module code imports {name!r} — "
                "only app.modules.sdk is allowed"
            )
    return messages


def lint_module_dir(module_dir: Path) -> list[str]:
    """Lint every ``*.py`` of one module directory (WP-112/WP-115)."""
    if not module_dir.is_dir():
        return []
    violations: list[str] = []
    for py_file in sorted(module_dir.rglob("*.py")):
        violations.extend(_violations_in_file(py_file))
    return violations


def lint_module_imports(modules_dir: Path) -> list[str]:
    """Lint every ``*.py`` under ``modules/*``; return violation messages."""
    if not modules_dir.is_dir():
        return []
    violations: list[str] = []
    for py_file in sorted(modules_dir.rglob("*.py")):
        violations.extend(_violations_in_file(py_file))
    return violations
