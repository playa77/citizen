"""Stable import surface for module code (WP-91, ARCHITECTURE.md § 2.4).

Module code may import **only** `app.modules.sdk` (enforced by
`app.modules.lint`). Everything a module may legitimately use from the core
is re-exported here and versioned with the ``core_api`` contract: breaking
this surface requires a core major (ARCHITECTURE.md § 6.1).

At core_api 3.0 the surface is deliberately minimal: first-party modules are
predominantly data (manifests, deadline specs, parameters, prompts), and no
module code ships yet — the calculators move into ``modules/*/calculators.py``
at WP-93. The surface grows with the typed extension points
(``Calculator``, ``RegimeProvider``) exactly when the first module code
lands, never speculatively.
"""

# Semantic Version: 0.1.0

SDK_VERSION = "3.0"
"""Core module-contract version; must stay compatible with every manifest's ``core_api``."""

__all__ = ["SDK_VERSION"]
