"""Sachverhalts-Chronologie builder (WP-101; ARCHITECTURE.md § 3.7 item 1).

Deterministic, LLM-free extraction of dated events from the case's
user-confirmed document texts (the analysed input text plus documents
attached to the case). Every extracted entry is a **proposal**; it becomes
part of the confirmed chronology only through the user confirmation step
(``PUT /api/v1/cases/{case_id}/dossier/chronology``).

Core vs. module split: the core knows German date notation and the generic
letter conventions every area shares (the letter's own date line
"Ort, den TT.MM.JJJJ", periods "vom … bis …"). What a date *means* in one
area of law ("Antrag vom", "Meldetermin am") is module data: the
``chronology_cues`` of the module's ``dossier.yaml`` (WP-102).

Entry ids are content hashes of (source, offset, date, kind), so a user's
confirmation survives a rebuild of the dossier as long as the text is
unchanged.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-101 initial.

from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

#: Core entry kinds (module cues add their own kinds).
KIND_DOCUMENT_DATE = "document_date"
KIND_PERIOD_START = "period_start"
KIND_PERIOD_END = "period_end"
KIND_MENTIONED = "mentioned"
KIND_USER = "user_event"

CORE_KIND_LABELS: dict[str, str] = {
    KIND_DOCUMENT_DATE: "Datum des Schreibens",
    KIND_PERIOD_START: "Beginn eines genannten Zeitraums",
    KIND_PERIOD_END: "Ende eines genannten Zeitraums",
    KIND_MENTIONED: "Im Schreiben genanntes Datum",
    KIND_USER: "Vom Nutzer ergänztes Ereignis",
}

#: Entry status values (schema ``citizen-dossier-v1.0``).
STATUS_PROPOSED = "proposed"
STATUS_CONFIRMED = "confirmed"
STATUS_REJECTED = "rejected"
STATUS_USER_ADDED = "user_added"
DECISION_STATUSES = (STATUS_CONFIRMED, STATUS_REJECTED)

_MONTHS = {
    "januar": 1,
    "jänner": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}

# dd.mm.yyyy (1–2 digit day/month); the look-arounds keep the match off
# longer digit runs such as reference numbers.
_NUMERIC_DATE = r"(?<![\d.])(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})(?![\d])"
_WORD_DATE = r"(?<![\d.])(\d{1,2})\.\s*(" + "|".join(_MONTHS) + r")\s+(\d{4})(?![\d])"
_ISO_DATE = r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d])"
_DATE_RE = re.compile(
    rf"(?:{_NUMERIC_DATE})|(?:{_WORD_DATE})|(?:{_ISO_DATE})",
    re.IGNORECASE,
)

# "Essen, 06.07.2026" / "Essen, den 6. Juli 2026" / "Datum: 06.07.2026" on a
# line of its own — the generic German letter-date convention.
_PLACE_DATE_LINE = re.compile(r"^\s*[^\d\n,:]{2,60},\s*(?:den\s+)?$", re.IGNORECASE)
# "Datum: …" or a heading line "Bescheid vom …" / "Schreiben vom …" (any
# "…bescheid": Bewilligungs-, Steuer-, Bußgeldbescheid — cross-area German
# administrative vocabulary, not one area's terminology).
_LABEL_DATE_LINE = re.compile(
    r"^\s*(?:datum|ausgestellt am|[\wäöüß-]*bescheid\s+vom|schreiben\s+vom)\s*:?\s*$",
    re.IGNORECASE,
)
# Period connectors between two dates on the same line.
_PERIOD_GAP = re.compile(r"^\s*(?:bis(?:\s+(?:zum|einschließlich))?|–|-|—)\s*$", re.IGNORECASE)
_BLANK_LINE = re.compile(r"\n[ \t]*\n")
#: Characters of same-line context searched for module cues before a date.
_CUE_WINDOW = 60
#: Maximum excerpt length stored per entry.
_EXCERPT_MAX = 200


@dataclass(frozen=True)
class SourceText:
    """One user-confirmed text the chronology is built from."""

    ref: str  # "case_input" | "conversation_document:<uuid>"
    label: str
    text: str


@dataclass(frozen=True)
class ChronologyCue:
    """Module cue: phrase just before a date that names its meaning."""

    kind: str
    label_de: str
    before_any: tuple[str, ...]
    module_id: str


@dataclass
class ChronologyEntry:
    entry_id: str
    date: date
    kind: str
    label_de: str
    status: str
    source: dict[str, Any] | None
    module_id: str | None = None
    note: str | None = None
    # Annotated via the module: the field named ``date`` shadows the type.
    original_date: dt.date | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "entry_id": self.entry_id,
            "date": self.date.isoformat(),
            "kind": self.kind,
            "label_de": self.label_de,
            "status": self.status,
            "source": self.source,
            "module_id": self.module_id,
            "note": self.note,
        }
        if self.original_date is not None and self.original_date != self.date:
            out["original_date"] = self.original_date.isoformat()
        return out


@dataclass
class _Match:
    start: int
    end: int
    value: date


@dataclass
class ChronologyDecisions:
    """The user's confirmation state (stored per case, WP-101).

    ``decisions`` maps a proposed ``entry_id`` to
    ``{"status": "confirmed"|"rejected", "date"?: ISO, "label_de"?: str,
    "note"?: str}``; ``added`` holds user-added events.
    """

    decisions: dict[str, dict[str, Any]] = field(default_factory=dict)
    added: list[dict[str, Any]] = field(default_factory=list)


def _to_date(groups: Sequence[str | None]) -> date | None:
    d1, m1, y1, d2, mon, y2, iy, im, iday = groups
    try:
        if d1 is not None and m1 is not None and y1 is not None:
            return date(int(y1), int(m1), int(d1))
        if d2 is not None and mon is not None and y2 is not None:
            return date(int(y2), _MONTHS[mon.lower()], int(d2))
        if iy is not None and im is not None and iday is not None:
            return date(int(iy), int(im), int(iday))
    except (ValueError, KeyError):
        return None
    return None


def _find_dates(text: str) -> list[_Match]:
    found: list[_Match] = []
    for m in _DATE_RE.finditer(text):
        value = _to_date(m.groups())
        if value is not None and 1900 <= value.year <= 2100:
            found.append(_Match(m.start(), m.end(), value))
    return found


def _entry_id(ref: str, offset: int, value: date, kind: str) -> str:
    digest = hashlib.sha256(f"{ref}|{offset}|{value.isoformat()}|{kind}".encode()).hexdigest()
    return f"chr-{digest[:12]}"


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return start, (len(text) if end == -1 else end)


def _excerpt(line: str) -> str:
    clean = " ".join(line.split())
    return clean if len(clean) <= _EXCERPT_MAX else clean[: _EXCERPT_MAX - 1] + "…"


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _cue_for(window: str, cues: Sequence[ChronologyCue]) -> ChronologyCue | None:
    lowered = _fold(window)
    for cue in cues:
        if any(_fold(phrase) in lowered for phrase in cue.before_any):
            return cue
    return None


def propose_entries(
    sources: Iterable[SourceText],
    cues: Sequence[ChronologyCue] = (),
) -> list[ChronologyEntry]:
    """Extract chronology proposals from *sources* (deterministic).

    Per source: the first letter-date line becomes ``document_date``; a
    "date bis date" pair on one line becomes ``period_start``/``period_end``;
    any other date takes the first matching module cue in the text just
    before it (same line or the wrapped line before), else
    ``mentioned``. Within one source, a repeated (date, kind) is kept once.
    """
    entries: list[ChronologyEntry] = []
    for source in sources:
        text = source.text
        matches = _find_dates(text)
        seen: set[tuple[date, str]] = set()
        document_date_taken = False
        period_partner: dict[int, str] = {}

        # Periods: consecutive dates on the same line joined by "bis"/dash.
        for first, second in itertools.pairwise(matches):
            gap = text[first.end : second.start]
            # A period may wrap onto the next line, never across a paragraph.
            if not _BLANK_LINE.search(gap) and _PERIOD_GAP.match(gap):
                period_partner[first.start] = KIND_PERIOD_START
                period_partner[second.start] = KIND_PERIOD_END

        previous_end = 0
        for match in matches:
            # Cue window: up to _CUE_WINDOW characters before the date, but
            # never past the previous date (a cue belongs to the nearest date)
            # nor across a paragraph break; it may wrap one line.
            window_start = max(previous_end, match.start - _CUE_WINDOW)
            window = text[window_start : match.start]
            paragraph = list(_BLANK_LINE.finditer(window))
            if paragraph:
                window = window[paragraph[-1].end() :]
            previous_end = match.end
            line_start, line_end = _line_bounds(text, match.start)
            before = text[line_start : match.start]
            after = text[match.end : line_end]
            line_no = text.count("\n", 0, match.start) + 1

            kind: str
            label: str
            module_id: str | None = None
            if (
                not document_date_taken
                and not after.strip()
                and (_PLACE_DATE_LINE.match(before) or _LABEL_DATE_LINE.match(before))
            ):
                kind, label = KIND_DOCUMENT_DATE, CORE_KIND_LABELS[KIND_DOCUMENT_DATE]
                document_date_taken = True
            elif match.start in period_partner:
                kind = period_partner[match.start]
                label = CORE_KIND_LABELS[kind]
            else:
                cue = _cue_for(window, cues)
                if cue is not None:
                    kind, label, module_id = cue.kind, cue.label_de, cue.module_id
                else:
                    kind, label = KIND_MENTIONED, CORE_KIND_LABELS[KIND_MENTIONED]

            if (match.value, kind) in seen:
                continue
            seen.add((match.value, kind))
            entries.append(
                ChronologyEntry(
                    entry_id=_entry_id(source.ref, match.start, match.value, kind),
                    date=match.value,
                    kind=kind,
                    label_de=label,
                    status=STATUS_PROPOSED,
                    source={
                        "document": source.ref,
                        "label": source.label,
                        "line": line_no,
                        "excerpt": _excerpt(text[line_start:line_end]),
                    },
                    module_id=module_id,
                )
            )
    return entries


def _parse_iso(value: Any, context: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{context}: invalid ISO date {value!r}") from exc


def apply_decisions(
    proposals: Sequence[ChronologyEntry], state: ChronologyDecisions
) -> list[ChronologyEntry]:
    """Merge the user's confirmation state into *proposals*.

    Returns every entry including rejected ones (callers filter), sorted by
    date and then source order. A decision may correct the date or label;
    the extracted date is kept as ``original_date``. Decisions for entry ids
    that no longer exist (text changed) are ignored.
    """
    merged: list[ChronologyEntry] = []
    for entry in proposals:
        decision = state.decisions.get(entry.entry_id)
        if decision is None:
            merged.append(entry)
            continue
        status = str(decision.get("status", STATUS_PROPOSED))
        new_date = (
            _parse_iso(decision["date"], entry.entry_id) if decision.get("date") else entry.date
        )
        merged.append(
            ChronologyEntry(
                entry_id=entry.entry_id,
                date=new_date,
                kind=entry.kind,
                label_de=str(decision.get("label_de") or entry.label_de),
                status=status if status in DECISION_STATUSES else STATUS_PROPOSED,
                source=entry.source,
                module_id=entry.module_id,
                note=decision.get("note"),
                original_date=entry.date,
            )
        )
    for raw in state.added:
        merged.append(
            ChronologyEntry(
                entry_id=str(raw["entry_id"]),
                date=_parse_iso(raw["date"], str(raw["entry_id"])),
                kind=str(raw.get("kind") or KIND_USER),
                label_de=str(raw.get("label_de") or CORE_KIND_LABELS[KIND_USER]),
                status=STATUS_USER_ADDED,
                source=None,
                module_id=None,
                note=raw.get("note"),
            )
        )
    order = {id(e): i for i, e in enumerate(merged)}
    return sorted(merged, key=lambda e: (e.date, order[id(e)]))


def user_entry_id(value: date, label: str, index: int) -> str:
    digest = hashlib.sha256(f"user|{index}|{value.isoformat()}|{label}".encode()).hexdigest()
    return f"usr-{digest[:12]}"


def validate_update(
    payload: Mapping[str, Any], known_ids: set[str]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Validate a chronology PUT body; return (decisions, added).

    Body shape::

        {"entries": [{"entry_id": "chr-…", "status": "confirmed"|"rejected",
                      "date"?: "YYYY-MM-DD", "label_de"?: str, "note"?: str}],
         "added":   [{"date": "YYYY-MM-DD", "label_de": str, "kind"?: str,
                      "note"?: str}]}

    Raises ``ValueError`` with a German-free, developer-facing message.
    """
    entries = payload.get("entries", [])
    added_raw = payload.get("added", [])
    if not isinstance(entries, list) or not isinstance(added_raw, list):
        raise ValueError("'entries' and 'added' must be lists")
    decisions: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("every entry must be an object")
        entry_id = item.get("entry_id")
        if entry_id not in known_ids:
            raise ValueError(f"unknown entry_id {entry_id!r}")
        status = item.get("status")
        if status not in DECISION_STATUSES:
            raise ValueError(f"entry {entry_id}: status must be 'confirmed' or 'rejected'")
        decision: dict[str, Any] = {"status": status}
        if item.get("date") is not None:
            decision["date"] = _parse_iso(item["date"], str(entry_id)).isoformat()
        for key in ("label_de", "note"):
            if item.get(key) is not None:
                decision[key] = str(item[key])[:500]
        decisions[str(entry_id)] = decision
    added: list[dict[str, Any]] = []
    for index, item in enumerate(added_raw):
        if not isinstance(item, dict) or not item.get("label_de"):
            raise ValueError("every added event needs 'date' and 'label_de'")
        value = _parse_iso(item.get("date"), f"added[{index}]")
        label = str(item["label_de"])[:500]
        kind = str(item.get("kind") or KIND_USER)
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", kind):
            raise ValueError(f"added[{index}]: invalid kind {kind!r}")
        added.append(
            {
                "entry_id": user_entry_id(value, label, index),
                "date": value.isoformat(),
                "label_de": label,
                "kind": kind,
                "note": (str(item["note"])[:500] if item.get("note") is not None else None),
            }
        )
    return decisions, added
