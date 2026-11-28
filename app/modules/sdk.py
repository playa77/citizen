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
0.13.0 (WP-137, core 3.12.0): ``SDK_VERSION`` "3.10" — tax corpus,
AO notification/rollover safeguards and assistance scope metadata (D-079).
0.12.0 (WP-136, core 3.11.0): ``SDK_VERSION`` "3.9" — residence corpus,
VwGO calendar, qualification exclusions and static safety/referral copy (D-078).
0.11.0 (WP-135, core 3.10.0): ``SDK_VERSION`` "3.8" — family corpus
sources and qualified FamFG calendar rollover (D-077).
0.10.0 (WP-134, core 3.9.0): ``SDK_VERSION`` "3.7" — traffic/procedural
federal corpus sources and StPO calendar rollover (D-076).
0.9.0 (WP-133, core 3.8.0): ``SDK_VERSION`` "3.6" — official EGBGB and
EUR-Lex article corpus support; existing calculator/deadline interfaces reused.
0.8.0 (WP-132, core 3.7.0): ``SDK_VERSION`` "3.5" — explicit knowledge-date
deadline evaluation. Existing receipt/event/service semantics remain supported.
0.7.0 (WP-131, core 3.6.0): ``SDK_VERSION`` "3.4" — explicit receipt/event
deadlines, calendar-month-end anchoring, qualification facts and civil calendar
helper. Existing administrative/service contracts remain supported.
0.6.0 (WP-130, core 3.5.0): ``SDK_VERSION`` "3.3" — actual-service
deadline specs, explicit dossier service facts and the optional public
``intake_schema`` manifest entry (D-071). Older modules
retain their existing evaluator path; service-spec modules require >=3.3.
0.5.0 (WP-122, core 3.4.0): ``SDK_VERSION`` "3.2" — the manifest schema
gains the optional ``plain_language`` key (module copy files per language and
the plain-language goldset). A 3.1 core rejects it, so a module using it
declares ``core_api: ">=3.2,<4.0"``. No Python surface change.
0.4.0 (WP-110/WP-112, core 3.3.0): ``SDK_VERSION`` "3.1" — the manifest
schema gains the optional ``errata`` key (a 3.0 core rejects it, so a module
using it declares ``core_api: ">=3.1,<4.0"``) and out-of-tree modules load
through the ``citizen.modules`` entry-point group. No Python surface change;
every ``>=3.0`` manifest stays compatible.
0.3.0 (prompt set 3.0.0, CR-06): optional ``RegimeProvider.reference_period``
— the module reads the reference date from the document, so the regime no
longer follows the server's clock (F-06). Additive; ``SDK_VERSION`` stays "3.0".
0.2.0 (WP-93): ``Calculator``, ``RegimeProvider``, ``ParameterSource``,
``ParameterLookup``. Additive to an unreleased contract; ``SDK_VERSION``
stays "3.0" (core 3.0.0 shipped at the P9 exit gate, WP-97).
0.1.0 (WP-91): ``SDK_VERSION`` only.
"""

# Semantic Version: 0.10.0

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from app.fristen.civil_calendar import civil_is_holiday as civil_is_holiday

SDK_VERSION = "3.10"
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
