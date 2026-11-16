"""Fristen core (WP-92; ARCHITECTURE.md § 3.5).

Domain-neutral German deadline machinery: holiday calendar per Bundesland,
Bekanntgabe/Zustellung fiction library, workday rollover library,
Rechtsbehelfsbelehrung-defect extension, and the generic evaluator for
module deadline specs (``fristen.yaml``, ARCHITECTURE.md § 2.3).

Every date computed here is deterministic and LLM-free. Area-specific law
lives in module spec files (``modules/*/fristen.yaml``), not in this
package; library entries whose semantics a module needs but that no module
has shipped yet raise ``NotImplementedError`` instead of guessing.
"""

# Semantic Version: 0.1.0

from app.fristen.calendar import (
    is_holiday,
    is_workday,
    next_workday,
    same_day_next_month,
    same_day_next_year,
    weekday_name,
)
from app.fristen.evaluator import FristInput, evaluate_spec
from app.fristen.results import FristResult
from app.fristen.specs import Duration, MissingRbb, NotApplicable, find_spec, load_specs

__all__ = [
    "Duration",
    "FristInput",
    "FristResult",
    "MissingRbb",
    "NotApplicable",
    "evaluate_spec",
    "find_spec",
    "is_holiday",
    "is_workday",
    "load_specs",
    "next_workday",
    "same_day_next_month",
    "same_day_next_year",
    "weekday_name",
]
