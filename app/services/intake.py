"""Multi-turn intake interview service.

Every case at Citizen is preceded by a 2–8 turn LLM-driven interview
that:
  1. Asks focused legal questions to disambiguate the case
  2. After enough context, returns a structured ``IntakeResult`` with
     ``primary_area``, ``secondary_areas``, a short ``summary``, key
     ``facts``, relevant ``dates``, and involved ``parties``
  3. Persists all messages in ``intake_session`` so the user can resume
     after disconnect

The LLM is asked to return ``primary_area`` and ``secondary_areas`` as
strings from a closed enum (the values in
``app.db.models.LEGAL_AREA_ALLOWED``). The parser validates the result
against that enum and falls back to keyword matching if the LLM
hallucinated an unknown area.
"""

# Semantic Version: 0.3.0

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.router import OpenRouterClient
from app.db.models import LEGAL_AREA_ALLOWED, IntakeSession
from app.utils.tokens import trim_text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class IntakeError(Exception):
    """Generic intake failure (LLM call, validation, persistence)."""


class IntakeTurnLimitReached(IntakeError):
    """Raised when the user tries to continue past the turn cap."""


# ---------------------------------------------------------------------------
# Shared LLM client
# ---------------------------------------------------------------------------

_client: OpenRouterClient | None = None


def _get_client() -> OpenRouterClient:
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


def reset_client() -> None:
    """Reset module-level client singleton (test helper)."""
    global _client
    _client = None


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

# Closed enum the LLM must pick from. Mirrors
# app.db.models.LEGAL_AREA_ALLOWED.
_LEGAL_AREAS_ENUM: tuple[str, ...] = LEGAL_AREA_ALLOWED

_INTAKE_SYSTEM = (
    "Du bist ein erfahrener juristischer Erstberater für deutsches Recht. "
    "Deine Aufgabe ist ein strukturiertes Aufnahmegespräch (Intake), um "
    "den Fall eines Bürgers rechtlich einzuordnen, BEVOR eine automatisierte "
    "Rechtsanalyse läuft.\n\n"
    "Dir wird die bisherige Schilderung des Bürgers sowie das bisherige "
    "Gesprächsprotokoll vorgelegt. Du sollst jeweils EINE einzige, gut "
    "fokussierte Rückfrage stellen, die den Sachverhalt weiter eingrenzt.\n\n"
    "Zugelassene Rechtsgebiete (du MUSST exakt einen dieser Werte verwenden):\n"
    + "\n".join(f"- {a}" for a in _LEGAL_AREAS_ENUM)
    + "\n\n"
    "Wichtige Regeln:\n"
    "- Stelle nur EINE Frage pro Antwort — keine Aufzählungen.\n"
    "- Die Frage soll kurz, klar und für Laien verständlich sein.\n"
    "- Vermeide doppelte Fragen; prüfe das Gesprächsprotokoll.\n"
    "- Wenn du genug Informationen hast (typischerweise nach 2–3 Fragen "
    "für einfache Fälle, maximal 8 Fragen), beende das Gespräch mit "
    '"done": true und liefere die unten genannten Felder.\n'
    "- Erfinde keine Tatsachen, Paragraphen oder Aktenzeichen.\n"
    "- Falls du dir unsicher bist, wähle '" + _LEGAL_AREAS_ENUM[-1] + "' als Fallback.\n\n"
    "Antwortformat: GENAU ein JSON-Objekt mit folgenden Schlüsseln:\n"
    "{\n"
    '  "done": false,                     // true wenn Interview beendet\n'
    '  "question": "Deine Rückfrage",     // leer wenn done=true\n'
    '  "primary_area": "sozialrecht",     // nur wenn done=true; sonst null\n'
    '  "secondary_areas": ["..."],        // nur wenn done=true; sonst []\n'
    '  "summary": "Kurze Sachverhalts-Zusammenfassung",   // nur wenn done=true\n'
    '  "facts": ["Tatsache 1", "Tatsache 2"],            // nur wenn done=true\n'
    '  "dates": ["YYYY-MM-DD oder ungefähre Angabe"],    // nur wenn done=true\n'
    '  "parties": ["Partei A", "Partei B"]                // nur wenn done=true\n'
    "}\n\n"
    "Gib ausschließlich gültiges JSON zurück. Kein Prosatext. Keine "
    "Markdown-Formatierung."
)


# ---------------------------------------------------------------------------
# Keyword fallback for area resolution
# ---------------------------------------------------------------------------

_AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sozialrecht": (
        "jobcenter", "bürgergeld", "sozialamt", "sanktion", "harzt iv", "harzt 2",
        "sgb", "sozialhilfe", "arbeitslosengeld", "kosten der unterkunft",
        "eingliederungsvereinbarung", "aufstocker", "regelsatz",
    ),
    "erbrecht": (
        "erbe", "testament", "erbfolge", "erbschein", "pflichtteil", "nachlass",
        "verstorb", "hinterblieb", "miterb", "erbanteil", "erbvertrag", "erblasser",
    ),
    "schenkungsrecht": (
        "schenkung", "schenken", "verschenk", "schenkungsvertrag", "freibetrag schenkung",
    ),
    "familienrecht": (
        "scheidung", "geschieden", "unterhalt", "sorgerecht", "umgangsrecht", "ehe",
        "famili", "kindesunterhalt", "trennungsunterhalt", "zugewinn", "ex-mann", "ex-frau",
    ),
    "mietrecht": (
        "miete", "vermieter", "mieter", "wohnung", "kündigung wohnung",
        "mietminderung", "kaution", "nebenkosten",
    ),
    "arbeitsrecht": (
        "arbeitgeber", "kündigung arbeit", "abfindung", "arbeitsvertrag",
        "betriebsrat", "kündigungsschutz", "abmahnung", "lohn", "gehalt",
    ),
    "vertragsrecht": (
        "vertrag", "kaufvertrag", "werkvertrag", "darlehen", "rücktritt",
        "gewährleistung", "garantie", "widerruf",
    ),
    "verwaltungsrecht": (
        "verwaltungsakt", "widerspruch", "baugenehmigung", "gewerbe",
        "ausländerbehörde", "führerschein", "bußgeldbescheid",
    ),
    "strafrecht": (
        "anzeige", "strafanzeige", "verfahren", "vorwurf", "tat",
        "strafrecht", "bewährung", "geldstrafe", "freiheitsstrafe",
    ),
}


def _fallback_areas_from_text(text: str) -> tuple[str, list[str]]:
    """Return (primary, secondary) areas by keyword matching.

    Used when the LLM returns an unknown area or fails entirely.
    """
    haystack = (text or "").lower()
    if not haystack.strip():
        return _LEGAL_AREAS_ENUM[-1], []  # 'andere'

    hits: list[tuple[str, int]] = []
    for area, kws in _AREA_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in haystack)
        if score:
            hits.append((area, score))
    if not hits:
        return _LEGAL_AREAS_ENUM[-1], []  # 'andere'

    hits.sort(key=lambda h: h[1], reverse=True)
    primary = hits[0][0]
    secondary = [a for a, _ in hits[1:3]]  # up to 2 secondaries
    return primary, secondary


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

_STRICT_SUFFIX = (
    "\n\nIMPORTANT: Respond with *only* valid JSON matching the schema above. "
    "No prose, no markdown fences, no explanation. If you cannot produce "
    "valid JSON matching the schema, return {\"done\": true, \"question\": \"\", "
    "\"primary_area\": \"andere\", \"secondary_areas\": [], "
    "\"summary\": \"\", \"facts\": [], \"dates\": [], \"parties\": []}."
)


def _parse_intake_response(raw: str) -> dict[str, Any]:
    """Parse the LLM response into a dict. Tolerant to JSON-in-prose.

    Raises ``IntakeError`` if the LLM output is unparseable.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0] if "\n" in text else text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # Tolerant: find first balanced JSON object.
    start = text.find("{")
    if start == -1:
        raise IntakeError("LLM response contained no JSON object")
    depth, in_string, escape = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except (json.JSONDecodeError, ValueError) as exc:
                    raise IntakeError(f"Malformed JSON: {exc}") from exc
    raise IntakeError("Unbalanced JSON braces in LLM response")


def _normalise_area(area: str | None) -> str | None:
    """Map an arbitrary area string back into the closed enum.

    Returns the input verbatim if it already matches a known area, else
    ``None``. Caller is expected to fall back to keyword matching.
    """
    if not area:
        return None
    a = str(area).strip().lower()
    if a in _LEGAL_AREAS_ENUM:
        return a
    # Common synonyms.
    _SYNONYMS: dict[str, str] = {
        "social": "sozialrecht",
        "sozial": "sozialrecht",
        "soziales": "sozialrecht",
        "arbeitslosengeld ii": "sozialrecht",
        "erbschaft": "erbrecht",
        "erben": "erbrecht",
        "nachfolge": "erbrecht",
        "schenken": "schenkungsrecht",
        "schenkung": "schenkungsrecht",
        "scheidungsrecht": "familienrecht",
        "trennung": "familienrecht",
    }
    if a in _SYNONYMS:
        return _SYNONYMS[a]
    # Fuzzy: contains.
    for k, v in _SYNONYMS.items():
        if k in a:
            return v
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_intake_messages(
    initial_text: str,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build the LLM message list for one intake turn.

    The system prompt is always first; the user turn carries the
    full transcript so the model has full context. The transcript
    format is::

        Bisherige Schilderung des Bürgers:
        <initial_text>

        Gesprächsprotokoll:
        Assistent: <q1>
        Bürger: <a1>
        Assistent: <q2>
        Bürger: <a2>
        ...
    """
    history = history or []
    parts: list[str] = []
    parts.append("## Bisherige Schilderung des Bürgers\n")
    parts.append(trim_text(initial_text, 4000))
    if history:
        parts.append("\n\n## Gesprächsprotokoll")
        for entry in history:
            role = entry.get("role", "").capitalize()
            content = entry.get("content", "")
            parts.append(f"\n{role}: {content}")
    user_content = "".join(parts)
    return [
        {"role": "system", "content": _INTAKE_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]


async def _call_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Call the LLM and parse the response into a dict."""
    from app.core.config import settings as s

    client = _get_client()
    raw = await client.chat_completion(
        messages,
        temperature=0.1,
        model=s.PRIMARY_MODEL,
        max_retries=1,
    )
    return _parse_intake_response(raw)


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


def _session_to_dict(s: IntakeSession) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "session_id": s.session_id,
        "status": s.status,
        "turn_count": s.turn_count,
        "max_turns": s.max_turns,
        "messages": s.messages or [],
        "intake_result": s.intake_result,
        "primary_area": s.primary_area,
        "secondary_areas": list(s.secondary_areas or []),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


async def start_intake(
    session: AsyncSession,
    *,
    session_id: str,
    initial_text: str,
    max_turns: int = 8,
) -> dict[str, Any]:
    """Begin a new intake session and ask the first question.

    Returns the freshly-persisted :class:`IntakeSession` as a dict.
    The LLM is asked once with the initial text as the only context.
    """
    if not (initial_text or "").strip():
        raise IntakeError("initial_text must be non-empty")

    messages = build_intake_messages(initial_text)
    try:
        llm_result = await _call_llm(messages)
    except IntakeError as exc:
        logger.warning("start_intake: LLM parse failed (%s); using fallback", exc)
        primary, secondary = _fallback_areas_from_text(initial_text)
        llm_result = {
            "done": True,
            "question": "",
            "primary_area": primary,
            "secondary_areas": secondary,
            "summary": trim_text(initial_text, 500),
            "facts": [],
            "dates": [],
            "parties": [],
        }

    intake_session = IntakeSession(
        session_id=session_id,
        status="completed" if llm_result.get("done") else "active",
        turn_count=0,
        max_turns=max_turns,
        messages=[],
        intake_result=None,
        primary_area=None,
        secondary_areas=None,
    )
    session.add(intake_session)
    await session.flush()

    if llm_result.get("done"):
        return await _finalise_session(
            session, intake_session, initial_text, llm_result,
        )

    # Otherwise persist the first assistant turn.
    intake_session.messages = [
        {"role": "user", "content": initial_text.strip()},
        {"role": "assistant", "content": str(llm_result.get("question", "")).strip()},
    ]
    intake_session.turn_count = 1
    await session.commit()
    await session.refresh(intake_session)
    return _session_to_dict(intake_session)


async def continue_intake(
    session: AsyncSession,
    *,
    intake_id: UUID,
    user_message: str,
) -> dict[str, Any]:
    """Continue an in-progress intake with the user's reply.

    Enforces the turn cap. If the LLM signals ``done=true`` (or the
    cap is reached), the session is finalised and the result is
    persisted.
    """
    intake_session = await _load_session(session, intake_id)
    if intake_session.status == "completed":
        raise IntakeError("Intake already completed")
    if intake_session.status == "abandoned":
        raise IntakeError("Intake was abandoned")

    if intake_session.turn_count >= intake_session.max_turns:
        raise IntakeTurnLimitReached(
            f"Intake reached its cap of {intake_session.max_turns} turns"
        )

    if not (user_message or "").strip():
        raise IntakeError("user_message must be non-empty")

    history = list(intake_session.messages or [])
    # Replay the initial text as the first user message of the transcript.
    initial_text = ""
    if history and history[0].get("role") == "user":
        initial_text = str(history[0].get("content", ""))

    # Append the new user turn.
    new_history = history + [{"role": "user", "content": user_message.strip()}]
    messages = build_intake_messages(initial_text, history=new_history)

    try:
        llm_result = await _call_llm(messages)
    except IntakeError as exc:
        logger.warning("continue_intake: LLM parse failed (%s); forcing finalize", exc)
        primary, secondary = _fallback_areas_from_text(
            initial_text + " " + user_message
        )
        llm_result = {
            "done": True,
            "question": "",
            "primary_area": primary,
            "secondary_areas": secondary,
            "summary": trim_text(initial_text, 500),
            "facts": [],
            "dates": [],
            "parties": [],
        }

    # Append assistant turn (or finalise).
    intake_session.messages = new_history + [
        {"role": "assistant", "content": str(llm_result.get("question", "")).strip()},
    ]
    intake_session.turn_count = intake_session.turn_count + 1
    await session.flush()

    if llm_result.get("done") or intake_session.turn_count >= intake_session.max_turns:
        return await _finalise_session(
            session, intake_session, initial_text, llm_result,
            extra_user_message=user_message,
        )

    await session.commit()
    await session.refresh(intake_session)
    return _session_to_dict(intake_session)


async def finalize_intake(
    session: AsyncSession,
    *,
    intake_id: UUID,
) -> dict[str, Any]:
    """Force-finalise an intake at the current turn count.

    Used by the 8-turn cap enforcement and the /confirm endpoint.
    """
    intake_session = await _load_session(session, intake_id)
    if intake_session.status == "completed":
        return _session_to_dict(intake_session)

    initial_text = ""
    history = list(intake_session.messages or [])
    if history and history[0].get("role") == "user":
        initial_text = str(history[0].get("content", ""))

    all_user_text = " ".join(
        m.get("content", "") for m in history if m.get("role") == "user"
    )
    primary, secondary = _fallback_areas_from_text(all_user_text or initial_text)
    llm_result = {
        "done": True,
        "question": "",
        "primary_area": primary,
        "secondary_areas": secondary,
        "summary": trim_text(initial_text, 500),
        "facts": [],
        "dates": [],
        "parties": [],
    }
    return await _finalise_session(
        session, intake_session, initial_text, llm_result,
    )


async def restart_intake(
    session: AsyncSession,
    *,
    intake_id: UUID,
) -> dict[str, Any]:
    """Abandon the current intake and reset to turn 0."""
    intake_session = await _load_session(session, intake_id)
    intake_session.status = "abandoned"
    intake_session.messages = []
    intake_session.turn_count = 0
    intake_session.intake_result = None
    intake_session.primary_area = None
    intake_session.secondary_areas = None
    await session.commit()
    await session.refresh(intake_session)
    return _session_to_dict(intake_session)


async def get_intake(
    session: AsyncSession,
    intake_id: UUID,
) -> dict[str, Any] | None:
    """Return the current state of an intake session, or None."""
    intake_session = await _load_session(session, intake_id)
    return _session_to_dict(intake_session)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _load_session(
    session: AsyncSession,
    intake_id: UUID,
) -> IntakeSession:
    stmt = select(IntakeSession).where(IntakeSession.id == intake_id)
    result = await session.execute(stmt)
    obj = result.scalar_one_or_none()
    if obj is None:
        raise IntakeError(f"IntakeSession {intake_id} not found")
    return obj


async def _finalise_session(
    session: AsyncSession,
    intake_session: IntakeSession,
    initial_text: str,
    llm_result: dict[str, Any],
    *,
    extra_user_message: str | None = None,
) -> dict[str, Any]:
    """Persist the final IntakeResult and return the session dict."""
    primary_raw = llm_result.get("primary_area")
    primary_norm = _normalise_area(primary_raw) if primary_raw else None

    if not primary_norm:
        # Fallback: keyword-based area detection over the full transcript.
        all_text = initial_text
        if extra_user_message:
            all_text = f"{all_text}\n{extra_user_message}"
        for entry in (intake_session.messages or []):
            all_text = f"{all_text}\n{entry.get('content', '')}"
        primary_norm, _ = _fallback_areas_from_text(all_text)

    # Validate secondary areas; drop unknowns.
    raw_secs = llm_result.get("secondary_areas") or []
    secondary_clean: list[str] = []
    for a in raw_secs:
        norm = _normalise_area(a) if isinstance(a, str) else None
        if norm and norm not in secondary_clean and norm != primary_norm:
            secondary_clean.append(norm)

    intake_session.primary_area = primary_norm
    intake_session.secondary_areas = secondary_clean
    intake_session.intake_result = {
        "primary_area": primary_norm,
        "secondary_areas": secondary_clean,
        "summary": str(llm_result.get("summary", "")).strip(),
        "facts": [str(f).strip() for f in (llm_result.get("facts") or []) if str(f).strip()],
        "dates": [str(d).strip() for d in (llm_result.get("dates") or []) if str(d).strip()],
        "parties": [str(p).strip() for p in (llm_result.get("parties") or []) if str(p).strip()],
    }
    intake_session.status = "completed"
    await session.commit()
    await session.refresh(intake_session)
    return _session_to_dict(intake_session)
