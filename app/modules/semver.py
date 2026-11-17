"""Module semver helpers (WP-110; ARCHITECTURE.md § 6.2).

Module versions are plain ``MAJOR.MINOR.PATCH`` (no pre-release tags — the
manifest schema enforces that). Ranges are comma-separated comparators,
e.g. ``">=1.0.0,<1.3.1"``; each bound may omit the patch (``">=3.0"`` means
``>=3.0.0``). Used for errata ``affected_versions``, update-feed
``applies_to`` ranges and changelog ordering checks — one parser for all, so
"is version X affected" has exactly one answer.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-110: initial version.

from __future__ import annotations

import re

Version = tuple[int, int, int]

_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_TERM_RE = re.compile(r"^(>=|<=|>|<|==|=)?\s*(\d+)\.(\d+)(?:\.(\d+))?$")


class VersionRangeError(ValueError):
    """An unparsable version or range string."""


def parse_version(text: str) -> Version:
    """Parse ``MAJOR.MINOR.PATCH``; raise ``VersionRangeError`` otherwise."""
    match = _VERSION_RE.match(text.strip())
    if match is None:
        raise VersionRangeError(f"not a MAJOR.MINOR.PATCH version: {text!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _terms(spec: str) -> list[tuple[str, Version]]:
    terms: list[tuple[str, Version]] = []
    for raw in spec.split(","):
        match = _TERM_RE.match(raw.strip())
        if match is None:
            raise VersionRangeError(f"unparsable version range term {raw!r} in {spec!r}")
        op = match.group(1) or "=="
        bound = (int(match.group(2)), int(match.group(3)), int(match.group(4) or 0))
        terms.append((op, bound))
    return terms


def validate_range(spec: str) -> None:
    """Raise ``VersionRangeError`` if *spec* is not a parsable range."""
    _terms(spec)


def in_range(version: str | Version, spec: str) -> bool:
    """Whether *version* satisfies every comparator of *spec*."""
    v = parse_version(version) if isinstance(version, str) else version
    for op, bound in _terms(spec):
        ok = {
            ">=": v >= bound,
            ">": v > bound,
            "<=": v <= bound,
            "<": v < bound,
            "==": v == bound,
            "=": v == bound,
        }[op]
        if not ok:
            return False
    return True


__all__ = ["Version", "VersionRangeError", "in_range", "parse_version", "validate_range"]
