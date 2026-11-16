"""Stable import surface for module code (WP-91/WP-93, ARCHITECTURE.md § 2.4).

Module code may import **only** `app.modules.sdk` (enforced by
`app.modules.lint`). Everything a module may legitimately use from the core
is re-exported here and versioned with the ``core_api`` contract: breaking
this surface requires a core major (ARCHITECTURE.md § 6.1).

First-party modules are predominantly data (manifests, deadline specs,
parameters, prompt profiles, intake/corpus tables, document templates).
Code is admitted only for the two typed extension points that cannot be
expressed as data (§ 2.4):

``Calculator``
    Deterministic area math plus the LLM *extraction* and *explanation*
    prompts that frame it. The core harness (``app.services.calculation``)
    owns the LLM calls, timeouts and result assembly; the module supplies
    prompts, a parameter loader and a pure ``process`` function.
``RegimeProvider``
    Intertemporal law selection (e.g. the SGB II reform 2026-07-01): a
    regime key per reference date and the banner text the pipeline injects
    into stage prompts.

Both are plain frozen dataclasses of callables so module code needs no
base-class import beyond this file. ``ParameterSource`` is the read-only
parameter-store view the core hands to ``Calculator.load_parameters`` — the
module never touches the database or the core's session handling.

Changes
-------
0.3.0 (prompt set 3.0.0, CR-06): optional ``RegimeProvider.reference_period``
— the module reads the reference date from the document, so the regime no
longer follows the server's clock (F-06). Additive; ``SDK_VERSION`` stays "3.0".
0.2.0 (WP-93): ``Calculator``, ``RegimeProvider``, ``ParameterSource``,
``ParameterLookup``. Additive to an unreleased contract; ``SDK_VERSION``
stays "3.0" (core 3.0.0 shipped at the P9 exit gate, WP-97).
0.1.0 (WP-91): ``SDK_VERSION`` only.
"""

# Semantic Version: 0.3.0

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

SDK_VERSION = "3.0"
"""Core module-contract version; must stay compatible with every manifest's ``core_api``."""


#: Result of one parameter-store lookup: the dict shape returned by
#: ``app.services.parameter_store.get_parameter_numeric``/``get_parameter_json``
#: (keys ``value``, ``unit``, ``valid_from``, ``valid_to``, ``parameter_key``,
#: ``review_status``, ``regime``, ``notes``, ``error``; ``value`` is ``None``
#: when no row matches).
ParameterLookup = dict[str, Any]


class ParameterSource(Protocol):
    """Read-only, as-of view of the versioned parameter store.

    The core binds it to the module's parameter ``domain`` (manifest
    ``parameters.domain``) and an open DB session; lookups never raise for
    a missing key — ``value`` is ``None`` instead.
    """

    async def numeric(self, key: str, as_of: date) -> ParameterLookup: ...

    async def json(self, key: str, as_of: date) -> ParameterLookup: ...


#: ``load_parameters(extraction, source) -> (param_overrides, legal_snapshot)``
ParameterLoader = Callable[
    [dict[str, Any], ParameterSource],
    Awaitable[tuple[dict[str, Any], dict[str, Any] | None]],
]

#: ``process(extraction, param_overrides) -> calculation entries`` — pure, no I/O.
CalculationProcessor = Callable[[dict[str, Any], dict[str, Any] | None], list[dict[str, Any]]]


@dataclass(frozen=True)
class Calculator:
    """Deterministic calculation check of one module (ARCHITECTURE.md § 2.4).

    Attributes
    ----------
    id :
        Stable calculator id, unique within the module.
    extraction_prompt :
        System prompt for the LLM extraction phase (structured values only).
    explanation_prompt :
        System prompt for the LLM explanation phase (engine numbers are
        authoritative; the LLM only explains them).
    load_parameters :
        Fetches the parameter overrides for this extraction from the store
        and returns them with an audit snapshot. A failure is caught by the
        core, which then runs ``process`` with empty overrides (hard-coded
        fallbacks inside the calculator).
    process :
        Pure function computing the calculation entries.
    summarise_extraction :
        Projects the extraction onto the context the explanation LLM sees
        (module schema → JSON-serialisable dict).
    cross_check :
        ``(extraction, document_text) -> warnings`` — flags extracted values
        that do not occur in the document (logged by the core, never fatal).
    referral_hint :
        Fallback ``recommended_action`` when discrepancies exist and the
        explanation LLM gave none (area-specific referral wording).
    """

    id: str
    extraction_prompt: str
    explanation_prompt: str
    load_parameters: ParameterLoader
    process: CalculationProcessor
    summarise_extraction: Callable[[dict[str, Any]], dict[str, Any]]
    cross_check: Callable[[dict[str, Any], str], list[str]]
    referral_hint: str


#: ``(start, end, source)`` of the period a document concerns. ``start`` is
#: the reference date (``None``: none found), ``end`` the last day of a
#: period when the document states one, ``source`` a short German label of
#: where the date came from ("Beginn des Leistungszeitraums laut Dokument").
ReferencePeriod = tuple[date | None, date | None, str]


@dataclass(frozen=True)
class RegimeProvider:
    """Intertemporal regime selection of one module (ARCHITECTURE.md § 2.4).

    ``reference_period`` (optional, sdk 0.3.0) extracts the reference period
    from the normalized document text deterministically (no LLM); without it,
    or when it finds no date, the core falls back to the current date and says
    so in the prompt.
    """

    regime_for: Callable[[date], str]
    banner: Callable[[str], str]
    reference_period: Callable[[str], ReferencePeriod] | None = None


__all__ = [
    "SDK_VERSION",
    "CalculationProcessor",
    "Calculator",
    "ParameterLoader",
    "ParameterLookup",
    "ParameterSource",
    "ReferencePeriod",
    "RegimeProvider",
]
