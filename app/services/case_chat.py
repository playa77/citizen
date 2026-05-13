"""Case Chat reasoning service — conversation grounded in completed pipeline results.

For the Case Chat tab, every message is answered with full awareness of the
pipeline output, user edits, and adjudication flags. The AI can discuss specific
sections, defend or reconsider conclusions, and suggest targeted re-analysis.

Targeted re-evaluation re-runs specific pipeline stages with user input as
additional context, updating only affected sections.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.core.config import settings
from app.core.pipeline import PipelineState, StageExecutionError, execute_stage
from app.core.router import OpenRouterClient
from app.utils.tokens import trim_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Downstream stage map for targeted re-evaluation
# ---------------------------------------------------------------------------

_DOWNSTREAM_MAP: dict[str, list[str]] = {
    "normalization": [
        "classification",
        "decomposition",
        "retrieval",
        "construction",
        "verification",
        "generation",
        "adversarial_review",
        "calculation_check",
    ],
    "classification": [
        "retrieval",
        "construction",
        "verification",
        "generation",
        "adversarial_review",
        "calculation_check",
    ],
    "decomposition": [
        "retrieval",
        "construction",
        "verification",
        "generation",
        "adversarial_review",
        "calculation_check",
    ],
    "retrieval": [
        "construction",
        "verification",
        "generation",
        "adversarial_review",
        "calculation_check",
    ],
    "construction": [
        "verification",
        "generation",
        "adversarial_review",
        "calculation_check",
    ],
    "verification": [
        "adversarial_review",
        "calculation_check",
    ],
    "adversarial_review": [
        "calculation_check",
    ],
    "calculation_check": [],
    "generation": [],
}


# ---------------------------------------------------------------------------
# Case Chat system prompt
# ---------------------------------------------------------------------------

_CASE_CHAT_SYSTEM_PROMPT = (
    "Du bist ein sachkundiger, sorgfältiger und präziser Assistent für "
    "deutsches Sozialrecht (insbesondere SGB II, SGB X, SGB XII). Du hilfst "
    "Bürgern, die Ergebnisse einer automatisierten rechtlichen Analyse zu "
    "verstehen, zu hinterfragen und zu verbessern.\n\n"
    "Dir liegt die **vollständige Analyse-Pipeline** für diesen Fall vor: "
    "Sachverhalt, rechtliche Würdigung, Ergebnis, Handlungsempfehlung, "
    "Entwurf, Unsicherheiten, adversarialle Prüfung und Berechnungsprüfung.\n\n"
    "Deine Antworten sind:\n"
    "- sachlich, präzise und gut nachvollziehbar\n"
    "- auf Deutsch\n"
    "- kurz und verständlich (kein Juristenkauderwelsch, aber fachlich korrekt)\n"
    "- streng an den vorliegenden Analyseergebnissen orientiert\n"
    "- klar getrennt in: was die Analyse ergibt, was rechtlich naheliegt "
    "und was unsicher bleibt\n"
    "- explizit vorsichtig, wenn Informationen oder Quellen nicht ausreichen\n\n"
    "Wichtige Regeln:\n"
    "- Beziehe dich auf konkrete Abschnitte der Analyse (z. B. "
    "'Im Abschnitt zur rechtlichen Würdigung wird § 31 Abs. 1 SGB II zitiert …').\n"
    "- Wenn der Nutzer einen Abschnitt korrigiert oder ergänzt hat (user_edits), "
    "berücksichtige diese Änderungen als autoritativ.\n"
    "- Wenn eine adversariale Prüfung (adversarial_pruefung) vorliegt, "
    "weise auf Risiken und Gegenargumente hin, die dort identifiziert wurden.\n"
    "- Wenn eine Berechnungsprüfung (berechnungspruefung) vorliegt, "
    "berücksichtige festgestellte Abweichungen und Diskrepanzen.\n"
    "- Erfinde keine Tatsachen, Paragraphen, Fristen, Aktenzeichen, "
    "Behördenhandlungen oder Rechtsfolgen.\n"
    "- Stelle Vermutungen niemals als feststehende Tatsachen dar.\n"
    "- Belege rechtliche Aussagen nach Möglichkeit mit den Analyseergebnissen.\n"
    "- Wenn die Analyse keine ausreichende Grundlage bietet, sage das klar "
    "und deutlich.\n"
    "- Gib keine übertriebene Sicherheit vor; benenne Unsicherheiten offen.\n"
    "- Wenn der Nutzer eine vertiefte Prüfung eines bestimmten Aspekts "
    "wünscht, schlage eine gezielte Neuauswertung vor.\n"
    "- Formuliere praxisnah und bürgerverständlich.\n\n"
    "Du zitierst Paragraphen im Format '§ 31 Abs. 1 Satz 2 SGB II'.\n"
    "Wenn du etwas nicht weißt oder die Analyse nicht ausreicht, sagst du "
    "das klar."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_case_chat_response(
    messages: list[dict[str, str]],
    *,
    pipeline_output: dict[str, str],
    user_edits: dict[str, Any] | None = None,
    adjudications: dict[str, Any] | None = None,
    claims: list[dict[str, Any]] | None = None,
    case_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Generate a chat response grounded in completed pipeline results.

    Builds a system prompt that includes all pipeline sections (trimmed to
    fit the configured character budget), plus any user edits, adjudication
    flags, and claims. Calls the LLM via ``OpenRouterClient`` and streams
    tokens as SSE events.

    Parameters
    ----------
    messages :
        The full conversation history as OpenAI-style ``{role, content}`` dicts.
        The last message must be from the user.
    pipeline_output :
        The completed pipeline output dict with keys like ``sachverhalt``,
        ``rechtliche_wuerdigung``, ``ergebnis``, etc.
    user_edits :
        Optional dict of user modifications to pipeline sections.
    adjudications :
        Optional dict of adjudication flags (accepted/rejected claims, etc.).
    claims :
        Optional list of claims generated during the pipeline.
    case_id :
        Optional identifier for logging.
    """
    client = _get_client()

    # ── Build system prompt with pipeline context ───────────────────────
    system_parts = [_CASE_CHAT_SYSTEM_PROMPT]

    pipeline_context = _build_pipeline_context(pipeline_output)
    system_parts.append(
        f"\n\nHier sind die vollständigen Analyseergebnisse des Falls:\n"
        f"{pipeline_context}"
    )

    if user_edits:
        edits_context = _build_edits_context(user_edits)
        system_parts.append(
            f"\n\nDer Nutzer hat folgende Korrekturen an der Analyse "
            f"vorgenommen (diese sind als autoritativ zu betrachten):\n"
            f"{edits_context}"
        )

    if adjudications:
        adjudication_context = _build_adjudication_context(adjudications)
        system_parts.append(
            f"\n\nFolgende Claims wurden vom Nutzer geprüft "
            f"(Adjudikationen):\n{adjudication_context}"
        )

    if claims:
        claims_prompt = _build_claims_context(claims)
        system_parts.append(
            f"\n\nDem Fall liegen folgende Claims zugrunde:\n{claims_prompt}"
        )

    # ── Build LLM message list ──────────────────────────────────────────
    llm_messages: list[dict[str, str]] = []

    system_content = "\n".join(system_parts)
    # Ensure system content fits within the available budget (account for
    # conversation history).
    system_budget = max(settings.MAX_FINAL_INPUT_CHARS - 1000, 2000)
    system_content = trim_text(system_content, system_budget)
    llm_messages.append({"role": "system", "content": system_content})

    # Conversation history (trimmed to remaining budget)
    history_max = max(settings.MAX_FINAL_INPUT_CHARS - len(system_content), 500)
    history = _trim_history(messages, max_chars=history_max)
    llm_messages.extend(history)

    # ── Call LLM and stream ────────────────────────────────────────────
    try:
        response_text = await client.chat_completion(
            llm_messages,
            model=settings.FINAL_MODEL,
            timeout=settings.FINAL_TIMEOUT_SEC,
            max_retries=1,
        )
    except Exception as exc:
        logger.exception("Case chat LLM call failed for case %s", case_id)
        error_payload = {
            "error": "case_chat_llm_failed",
            "detail": str(exc),
        }
        yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        return

    # Stream the response as SSE token events, followed by a final event.
    for i, chunk in enumerate(_tokenize_stream(response_text)):
        token_payload = {
            "type": "token",
            "index": i,
            "content": chunk,
        }
        yield f"data: {json.dumps(token_payload, ensure_ascii=False)}\n\n"

    # Final event signalling completion.
    done_payload = {
        "type": "done",
        "case_id": case_id,
        "full_response": response_text,
    }
    yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"


async def run_targeted_reevaluate(
    stage_name: str,
    context: str,
    *,
    pipeline_state: dict[str, Any],
    case_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Run a targeted re-evaluation of a single pipeline stage.

    Takes a stage name (e.g. ``"calculation_check"``) and user-provided
    context (e.g. a correction or additional information), reconstructs a
    ``PipelineState`` from the saved pipeline data, and executes the
    requested stage (plus any downstream stages that depend on it).

    Yields SSE events for each re-run stage and a final summary event.

    Parameters
    ----------
    stage_name :
        The name of the stage to re-run (e.g. ``"retrieval"``,
        ``"construction"``, ``"calculation_check"``).
    context :
        Additional context provided by the user (e.g. a correction,
        a new document snippet, or a specific question). This is injected
        into the pipeline state for the re-run.
    pipeline_state :
        The original (saved) pipeline state, used to reconstruct a
        ``PipelineState`` instance.
    case_id :
        Optional identifier for logging.
    """
    # ── Reconstruct PipelineState ───────────────────────────────────────
    state = _reconstruct_pipeline_state(pipeline_state, context)

    # ── Determine which stages to run ───────────────────────────────────
    stages_to_run: list[str] = [stage_name]
    stages_to_run.extend(_DOWNSTREAM_MAP.get(stage_name, []))

    logger.info(
        "Targeted re-evaluate for case %s: stage=%s → stages=%s",
        case_id,
        stage_name,
        stages_to_run,
    )

    # ── Yield initial event ─────────────────────────────────────────────
    reval_payload = json.dumps(
        {"type": "stage_reevaluate", "stage": stage_name, "status": "running"},
        ensure_ascii=False,
    )
    yield f"data: {reval_payload}\n\n"

    # ── Run each stage ──────────────────────────────────────────────────
    updated_sections: list[str] = []
    for name in stages_to_run:
        try:
            events: list[str] = []
            async for event in execute_stage(name, state):
                events.append(event)
        except StageExecutionError as exc:
            logger.exception(
                "Re-evaluate stage %s failed for case %s: %s",
                name,
                case_id,
                exc,
            )
            error_payload = {
                "type": "stage_reevaluate",
                "stage": name,
                "status": "error",
                "error": str(exc),
            }
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
            continue

        # Emit completion event for this stage.
        stage_payload = {
            "type": "stage_reevaluate",
            "stage": name,
            "status": "complete",
        }
        # Try to extract a meaningful payload from the SSE event data.
        for evt in events:
            if evt.startswith("data: "):
                try:
                    parsed = json.loads(evt[len("data: "):].strip())
                    if parsed.get("stage") == name and parsed.get("status") == "complete":
                        stage_payload["payload"] = parsed.get("payload")
                except (json.JSONDecodeError, IndexError):
                    pass

        yield f"data: {json.dumps(stage_payload, ensure_ascii=False)}\n\n"

        # ── Yield section update events ─────────────────────────────────
        section_key = _stage_to_section_key(name)
        if section_key and section_key in state.final_output:
            updated_sections.append(section_key)
            section_payload = {
                "type": "section_updated",
                "section": section_key,
                "content": state.final_output[section_key],
            }
            yield f"data: {json.dumps(section_payload, ensure_ascii=False)}\n\n"

    # ── Yield final summary event ───────────────────────────────────────
    done_payload = {
        "type": "reevaluate_done",
        "updated_sections": updated_sections,
    }
    yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


_client: OpenRouterClient | None = None


def _get_client() -> OpenRouterClient:
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


async def close_client() -> None:
    """Close the shared OpenRouter HTTP client."""
    global _client
    if _client is not None:
        await _client._client.aclose()
        _client = None


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


_PIPELINE_SECTION_LABELS: dict[str, str] = {
    "sachverhalt": "Sachverhalt",
    "rechtliche_wuerdigung": "Rechtliche Würdigung",
    "ergebnis": "Ergebnis",
    "handlungsempfehlung": "Handlungsempfehlung",
    "entwurf": "Entwurf / Formulierungshilfe",
    "unsicherheiten": "Unsicherheiten und offene Fragen",
    "adversarial_pruefung": "Adversariale Prüfung (Gegenargumente & Risiken)",
    "berechnungspruefung": "Berechnungsprüfung",
}


def _build_pipeline_context(pipeline_output: dict[str, str]) -> str:
    """Build a formatted context string from the pipeline output sections.

    Each section is labelled and trimmed to fit the configured character
    budget. Sections are separated by horizontal rules for readability.
    """
    parts: list[str] = []
    total_chars = 0
    max_chars = settings.MAX_CHUNK_CONTEXT_CHARS

    for key, label in _PIPELINE_SECTION_LABELS.items():
        content = pipeline_output.get(key, "")
        if not content:
            continue

        section_text = f"### {label}\n{content}"
        trimmed = trim_text(section_text, min(3000, max_chars - total_chars))
        parts.append(trimmed)
        total_chars += len(trimmed)

        if total_chars >= max_chars:
            remaining = [k for k in _PIPELINE_SECTION_LABELS if k != key and k in pipeline_output]
            if remaining:
                parts.append(
                    f"… (weitere Abschnitte nicht im Kontext: "
                    f"{', '.join(remaining)})"
                )
            break

    return "\n\n---\n\n".join(parts)


def _build_edits_context(user_edits: dict[str, Any]) -> str:
    """Build a formatted context string from user edits.

    User edits represent corrections the user has made to individual
    pipeline sections. These are treated as authoritative overrides.
    """
    parts: list[str] = []
    for section_key, edit_value in user_edits.items():
        label = _PIPELINE_SECTION_LABELS.get(section_key, section_key)
        if isinstance(edit_value, str):
            trimmed = trim_text(edit_value, 2000)
            parts.append(f"{label}:\n{trimmed}")
        elif isinstance(edit_value, dict):
            trimmed = trim_text(json.dumps(edit_value, ensure_ascii=False), 2000)
            parts.append(f"{label}:\n{trimmed}")
    return "\n\n---\n\n".join(parts) if parts else "Keine Nutzerkorrekturen."


def _build_adjudication_context(adjudications: dict[str, Any]) -> str:
    """Build a formatted context string from adjudication flags.

    Adjudications capture which claims the user accepted, rejected, or
    modified during review.
    """
    try:
        return trim_text(json.dumps(adjudications, ensure_ascii=False, indent=2), 3000)
    except (TypeError, ValueError):
        return trim_text(str(adjudications), 3000)


def _build_claims_context(claims: list[dict[str, Any]]) -> str:
    """Build a formatted context string from the claims list.

    Claims are the structured assertions generated during pipeline
    construction/verification stages.
    """
    parts: list[str] = []
    max_claims = min(len(claims), 10)
    for i, claim in enumerate(claims[:max_claims]):
        text = claim.get("text", claim.get("claim", ""))
        confidence = claim.get("confidence", claim.get("score", "?"))
        claim_type = claim.get("type", claim.get("claim_type", "?"))
        parts.append(
            f"Claim {i + 1} [{claim_type}] (confidence: {confidence}):\n{text}"
        )

    if len(claims) > max_claims:
        parts.append(f"… und {len(claims) - max_claims} weitere Claims")

    return "\n\n".join(parts) if parts else "Keine Claims vorhanden."


# ---------------------------------------------------------------------------
# Pipeline reconstruction
# ---------------------------------------------------------------------------


def _reconstruct_pipeline_state(
    saved_state: dict[str, Any],
    context: str,
) -> PipelineState:
    """Reconstruct a ``PipelineState`` from a saved pipeline data dict.

    The *saved_state* must contain at least ``input_text``. Additional
    fields (``normalized_text``, ``issues``, ``questions``, etc.) are
    populated if present. The *context* string is appended to the input
    text so re-run stages see the user's additional input.
    """
    input_text = saved_state.get("input_text", "")
    if context:
        input_text = f"{input_text}\n\n--- Nutzerkontext für Neuauswertung ---\n\n{context}"

    state = PipelineState(input_text=input_text)

    # Populate saved fields if available.
    if "normalized_text" in saved_state:
        state.normalized_text = saved_state["normalized_text"]
    if "issues" in saved_state:
        state.issues = list(saved_state["issues"])
    if "questions" in saved_state:
        state.questions = list(saved_state["questions"])
    if "retrieved_chunks" in saved_state:
        state.retrieved_chunks = list(saved_state["retrieved_chunks"])
    if "claims" in saved_state:
        state.claims = list(saved_state["claims"])
    if "verified_claims" in saved_state:
        state.verified_claims = list(saved_state["verified_claims"])
    if "adversarial_review" in saved_state:
        state.adversarial_review = dict(saved_state["adversarial_review"])
    if "calculation_result" in saved_state:
        state.calculation_result = dict(saved_state["calculation_result"])
    if "final_output" in saved_state:
        state.final_output = dict(saved_state["final_output"])
    if "errors" in saved_state:
        state.errors = list(saved_state["errors"])

    return state


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


_STAGE_TO_SECTION: dict[str, str | None] = {
    "normalization": None,
    "classification": None,
    "decomposition": None,
    "retrieval": None,
    "construction": None,
    "verification": None,
    "generation": None,
    "adversarial_review": "adversarial_pruefung",
    "calculation_check": "berechnungspruefung",
}


def _stage_to_section_key(stage_name: str) -> str | None:
    """Return the ``final_output`` section key updated by a given stage.

    Returns ``None`` for stages that don't directly populate a section
    in ``final_output``.
    """
    return _STAGE_TO_SECTION.get(stage_name)


# ---------------------------------------------------------------------------
# History trimming
# ---------------------------------------------------------------------------


def _trim_history(
    messages: list[dict[str, str]],
    *,
    max_chars: int = 5000,
) -> list[dict[str, str]]:
    """Trim conversation history so total characters fit within *max_chars*.

    Keeps the most recent messages (newest first trimming strategy), but
    always preserves the latest user message.
    """
    if not messages:
        return []

    # Always keep the last message (current user query).
    last = messages[-1]
    remaining = messages[:-1]

    result: list[dict[str, str]] = []
    total = len(last["content"])

    for msg in reversed(remaining):
        msg_chars = len(msg["content"])
        if total + msg_chars > max_chars:
            # Trim the oldest remaining message to fit budget.
            available = max_chars - total
            if available > 100:
                result.append({
                    "role": msg["role"],
                    "content": trim_text(msg["content"], available),
                })
            break
        result.append(msg)
        total += msg_chars

    result.reverse()
    result.append(last)
    return result


# ---------------------------------------------------------------------------
# Token streaming
# ---------------------------------------------------------------------------


def _tokenize_stream(text: str, *, chunk_size: int = 80) -> list[str]:
    """Split *text* into roughly *chunk_size* character segments for SSE streaming.

    Splits on word boundaries (spaces) where possible to avoid breaking mid-word.
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Try to break at a space.
            space = text.rfind(" ", start, end)
            if space > start + chunk_size // 2:
                end = space + 1
        chunks.append(text[start:end])
        start = end
    return chunks
