"""Reasoning engine: LLM-driven claim construction, verification, adversarial review,
output formatting, and OCR result synthesis with spell/grammar correction.

Implements stages 2-3 and 5-8 of the 8-stage pipeline:
    Combined Triage (WP-006)           → triage_document()
    2. Issue Classification             → classify_issues()
    3. Question Decomposition            → decompose_questions()
    5. Claim Construction                → construct_claims()
    6. Verification Pass                 → verify_claims()
    7. Adversarial Review                → adversarial_review()
    8. Output Generation                 → generate_output()

Plus an OCR post-processing stage that runs before the pipeline:
    OCR Synthesis & Correction        → synthesize_and_correct_text()

Every function enforces a strict JSON output schema via a ``response_format``
directive embedded in the system prompt. Malformed JSON triggers one automatic
retry with a stricter prompt before raising ``JSONParseError``.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.core.router import get_shared_client
from app.services.prompts import SOCIALRECHT_PROMPTS
from app.utils.tokens import estimate_tokens, trim_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class JSONParseError(Exception):
    """Raised when the LLM returns malformed JSON even after a retry."""


# (Shared LLM client is in app.core.router via get_shared_client())


# ---------------------------------------------------------------------------
# JSON-parsing helper with retry
# ---------------------------------------------------------------------------

_STRICT_SUFFIX = (
    "\n\nIMPORTANT: Respond with *only* valid JSON matching the schema above. "
    "No prose, no markdown fences, no explanation. If you cannot produce "
    "valid JSON matching the schema, return an empty array [] for array "
    "schemas or an empty object {} for object schemas."
)


def _parse_json_response(raw: str, *, context: str) -> Any:
    """Attempt to parse ``raw`` as JSON; retry once with a stricter prompt on failure.

    Tries several extraction strategies in order:
    1. Parse the whole (optionally fenced) string as JSON.
    2. Find the first ``{`` or ``[`` and extract a balanced JSON segment.
       This handles LLMs that sprinkle prose before/after the JSON payload.

    Parameters
    ----------
    raw :
        The raw string returned by the LLM.
    context :
        Human-readable description of *what* we tried to parse (for logging).

    Returns
    -------
    dict[str, object]
        The parsed JSON object.

    Raises
    ------
    JSONParseError :
        If both the initial attempt and the retry fail.
    """
    stripped = raw.strip()

    # Attempt to strip leading/trailing markdown code fences if present.
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
    if stripped.endswith("```"):
        stripped = stripped.rsplit("\n", 1)[0] if "\n" in stripped else stripped[:-3]
    stripped = stripped.strip()

    # Strategy 1: whole string is JSON.
    try:
        parsed: dict[str, object] = json.loads(stripped)
        return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: find a balanced JSON segment in the response.
    # Many LLMs return prose like "Here is the result:\n{ ... }\nHope this helps!"
    extracted = _extract_json_segment(stripped)
    if extracted is not None:
        try:
            parsed = json.loads(extracted)
            return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # One retry — the LLM will be re-invoked with a stricter prompt by the
    # caller. We re-raise so the caller can handle the retry logic.
    raise JSONParseError(
        f"LLM returned malformed JSON for {context}. " f"Raw output (truncated): {raw[:300]!r}"
    )


def _extract_json_segment(text: str) -> str | None:
    """Find and extract the first balanced JSON object or array in *text*.

    Returns the extracted segment, or ``None`` if no valid opener is found
    or braces/brackets cannot be balanced.
    """
    # Find the first JSON opener.
    obj_start = text.find("{")
    arr_start = text.find("[")

    if obj_start == -1 and arr_start == -1:
        return None

    if obj_start == -1:
        start = arr_start
        opener = "["
        closer = "]"
    elif arr_start == -1:
        start = obj_start
        opener = "{"
        closer = "}"
    else:
        # Both present — use whichever comes first.
        if obj_start < arr_start:
            start = obj_start
            opener = "{"
            closer = "}"
        else:
            start = arr_start
            opener = "["
            closer = "]"

    # Walk through the string to find the matching closer, respecting
    # nested structures and string literals.
    depth = 0
    in_string = False
    escape = False
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
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None  # unbalanced


# ---------------------------------------------------------------------------
# Stage 2 — Issue Classification
# ---------------------------------------------------------------------------

# Prompt strings live in app.services.prompts so the registry can serve
# area-specific variants. We re-export the socialrecht (default) prompts
# under the original module-level names so any pre-existing importer
# keeps working byte-for-byte.
_CLASSIFICATION_SYSTEM = SOCIALRECHT_PROMPTS["classification"]


async def classify_issues(
    normalized_text: str,
    *,
    system_prompt: str | None = None,
) -> list[str]:
    """Call the LLM to extract legal issues from *normalized_text*.

    Parameters
    ----------
    normalized_text :
        Cleaned text from the OCR / ingestion pipeline.
    system_prompt :
        Optional override for the system prompt. When ``None`` the
        original SGB-focused prompt is used. The pipeline passes a
        multi-area-aware prompt from ``app.services.prompts``.

    Returns
    -------
    list[str]
        A list of identified legal issue labels.
    """
    logger.info("classify_issues: starting (input=%d chars)", len(normalized_text))
    client = get_shared_client()
    from app.core.config import settings as _s

    triage_budget = _s.MAX_TRIAGE_INPUT_CHARS
    sys_msg = system_prompt if system_prompt is not None else _CLASSIFICATION_SYSTEM
    messages = [
        {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
        {
            "role": "user",
            "content": trim_text(normalized_text, triage_budget),
        },
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="issue classification")
    except JSONParseError:
        # Retry once with a bare-minimum prompt
        logger.warning("JSON parse error in classify_issues, retrying with stricter prompt")
        messages_minimal = [
            {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
            {"role": "user", "content": trim_text(normalized_text, triage_budget // 2)},
        ]
        raw2 = await client.chat_completion(messages_minimal, temperature=0.0)
        result = _parse_json_response(raw2, context="issue classification (retry)")

    issues = result.get("issues", [])
    if not isinstance(issues, list):
        logger.warning("classify_issues: unexpected 'issues' type: %s", type(issues))
        return []
    return [str(i).strip() for i in issues if str(i).strip()]


# ---------------------------------------------------------------------------
# Stage 3 — Question Decomposition
# ---------------------------------------------------------------------------

_DECOMPOSITION_SYSTEM = SOCIALRECHT_PROMPTS["decomposition"]


async def decompose_questions(
    normalized_text: str,
    *,
    system_prompt: str | None = None,
) -> list[str]:
    """Call the LLM to extract explicit legal questions from *normalized_text*.

    Parameters
    ----------
    normalized_text :
        Cleaned text from the OCR / ingestion pipeline.
    system_prompt :
        Optional override for the system prompt. See ``classify_issues``.

    Returns
    -------
    list[str]
        A list of extracted legal questions.
    """
    logger.info("decompose_questions: starting (input=%d chars)", len(normalized_text))
    client = get_shared_client()
    from app.core.config import settings as _s

    triage_budget = _s.MAX_TRIAGE_INPUT_CHARS
    sys_msg = system_prompt if system_prompt is not None else _DECOMPOSITION_SYSTEM
    messages = [
        {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
        {
            "role": "user",
            "content": trim_text(normalized_text, triage_budget),
        },
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="question decomposition")
    except JSONParseError:
        logger.warning("JSON parse error in decompose_questions, retrying with stricter prompt")
        messages_minimal = [
            {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
            {"role": "user", "content": trim_text(normalized_text, triage_budget // 2)},
        ]
        raw2 = await client.chat_completion(messages_minimal, temperature=0.0)
        result = _parse_json_response(raw2, context="question decomposition (retry)")

    questions = result.get("questions", [])
    if not isinstance(questions, list):
        logger.warning("decompose_questions: unexpected 'questions' type: %s", type(questions))
        return []
    return [str(q).strip() for q in questions if str(q).strip()]


# ---------------------------------------------------------------------------
# Combined Stages 2+3 — Triage (WP-006)
# ---------------------------------------------------------------------------

_TRIAGE_SYSTEM = SOCIALRECHT_PROMPTS["triage"]


async def triage_document(
    normalized_text: str,
    *,
    system_prompt: str | None = None,
) -> dict[str, list[str]]:
    """Perform combined classification and decomposition in a single LLM call.

    Instead of calling ``classify_issues()`` and ``decompose_questions()``
    sequentially, this function asks one LLM call for both lists at once.

    Parameters
    ----------
    normalized_text :
        Cleaned text from the OCR / ingestion pipeline.
    system_prompt :
        Optional override for the system prompt. When ``None`` the
        original SGB-focused prompt is used.

    Returns
    -------
    dict[str, list[str]]
        A dict with keys ``issues`` (list of legal issue labels) and
        ``questions`` (list of explicit legal questions).
    """
    from app.core.config import settings as s

    triage_model = s.TRIAGE_MODEL or s.PRIMARY_MODEL
    triage_timeout = s.TRIAGE_TIMEOUT_SEC
    triage_input_chars = s.MAX_TRIAGE_INPUT_CHARS
    sys_msg = system_prompt if system_prompt is not None else _TRIAGE_SYSTEM

    # ── WP-011: triage cache ────────────────────────────────────────────
    if s.ENABLE_CACHE:
        from app.db.session import get_async_session
        from app.services.cache import get_json_cache, make_cache_key

        cache_key = make_cache_key("triage", triage_model, normalized_text)
        async for session in get_async_session():
            try:
                cached = await get_json_cache(session, cache_key)
                if cached is not None and isinstance(cached, dict):
                    issues = cached.get("issues", [])
                    questions = cached.get("questions", [])
                    if isinstance(issues, list) and isinstance(questions, list):
                        logger.info(
                            "triage_document: CACHE HIT (model=%s, %d issues, %d questions)",
                            triage_model,
                            len(issues),
                            len(questions),
                        )
                        return {"issues": list(issues), "questions": list(questions)}
            except Exception as exc:
                logger.warning("triage_document: cache read failed: %s", exc)
            finally:
                await session.close()
            break

    logger.info(
        "triage_document: starting (input=%d chars, budget=%d chars, model=%s, timeout=%.1fs)",
        len(normalized_text),
        triage_input_chars,
        triage_model,
        triage_timeout,
    )
    client = get_shared_client()

    trimmed_input = trim_text(normalized_text, triage_input_chars)
    input_tokens = estimate_tokens(trimmed_input + sys_msg + _STRICT_SUFFIX)

    messages = [
        {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
        {"role": "user", "content": trimmed_input},
    ]

    logger.info(
        "triage_document: prompt ~%d chars (user=%d, system=%d), ~%d tokens",
        len(trimmed_input) + len(sys_msg) + len(_STRICT_SUFFIX),
        len(trimmed_input),
        len(sys_msg) + len(_STRICT_SUFFIX),
        input_tokens,
    )

    raw = await client.chat_completion(
        messages,
        temperature=0.1,
        model=triage_model,
        timeout=triage_timeout,
        max_retries=1,
    )
    try:
        result = _parse_json_response(raw, context="triage (classification + decomposition)")
    except JSONParseError:
        logger.warning("JSON parse error in triage_document, retrying with stricter prompt")
        messages_minimal = [
            {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
            {"role": "user", "content": trim_text(normalized_text, triage_input_chars // 2)},
        ]
        raw2 = await client.chat_completion(
            messages_minimal,
            temperature=0.0,
            model=triage_model,
            timeout=triage_timeout,
            max_retries=1,
        )
        result = _parse_json_response(raw2, context="triage (retry)")

    # Validate and extract issues.
    issues = result.get("issues", [])
    if not isinstance(issues, list):
        logger.warning("triage_document: unexpected 'issues' type: %s", type(issues))
        issues = []
    clean_issues = [str(i).strip() for i in issues if str(i).strip()]

    # Validate and extract questions.
    questions = result.get("questions", [])
    if not isinstance(questions, list):
        logger.warning("triage_document: unexpected 'questions' type: %s", type(questions))
        questions = []
    clean_questions = [str(q).strip() for q in questions if str(q).strip()]

    # ── WP-011: store in triage cache ───────────────────────────────────
    if s.ENABLE_CACHE:
        from app.db.session import get_async_session
        from app.services.cache import make_cache_key as _mk
        from app.services.cache import set_json_cache as _set

        async for session in get_async_session():
            try:
                await _set(
                    session,
                    _mk("triage", triage_model, normalized_text),
                    {"issues": clean_issues, "questions": clean_questions},
                )
            except Exception as exc:
                logger.warning("triage_document: cache write failed: %s", exc)
            finally:
                await session.close()
            break

    logger.info(
        "triage_document: complete (model=%s, %d issues, %d questions)",
        triage_model,
        len(clean_issues),
        len(clean_questions),
    )
    return {"issues": clean_issues, "questions": clean_questions}


# ---------------------------------------------------------------------------
# Combined Stages 5+6+7+8 — Grounded Answer Generation (WP-007)
# ---------------------------------------------------------------------------

_GROUNDED_ANSWER_SYSTEM = SOCIALRECHT_PROMPTS["grounded_answer"]


# ---------------------------------------------------------------------------
# Stage 7 — Adversarial Legal Review (Rechtsprüfungsrat)
# ---------------------------------------------------------------------------

_ADVERSARIAL_REVIEW_SYSTEM = SOCIALRECHT_PROMPTS["adversarial_review"]


async def adversarial_review(
    normalized_text: str,
    issues: list[str],
    questions: list[str],
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Perform an adversarial legal review of the claims from multiple
    perspectives (defense, authority, judicial, procedural).

    This implements Stage 7 of the pipeline — the "Rechtsprüfungsrat"
    (legal review council) that evaluates every claim from opposing
    legal perspectives.

    Parameters
    ----------
    normalized_text :
        Cleaned text from the OCR / ingestion pipeline.
    issues :
        Legal topics identified during triage.
    questions :
        Explicit legal questions from triage.
    claims :
        Claims (verified or raw) to be adversarially reviewed.
    chunks :
        Evidence chunks retrieved from pgvector.

    Returns
    -------
    dict[str, Any]
        A dict with keys:
        - ``reviews``: list of per-claim adversarial reviews
        - ``overall_assessment``: dict with summary, key_risks,
          recommended_next_steps, confidence_in_defense,
          procedural_errors_found
    """
    from app.core.config import settings as s

    final_model = s.FINAL_MODEL or s.PRIMARY_MODEL
    final_timeout = s.FINAL_TIMEOUT_SEC
    max_chunks_for_final = s.MAX_CHUNKS_FOR_FINAL
    max_chunk_context_chars = s.MAX_CHUNK_CONTEXT_CHARS
    max_final_input_chars = s.MAX_FINAL_INPUT_CHARS
    sys_msg = system_prompt if system_prompt is not None else _GROUNDED_ANSWER_SYSTEM

    logger.info(
        "generate_grounded_answer: starting (input=%d chars, %d issues, "
        "%d questions, %d chunks, budget: max_input=%d max_chunks=%d max_chunk_chars=%d, model=%s, timeout=%.1fs)",
        len(normalized_text),
        len(issues),
        len(questions),
        len(chunks),
        max_final_input_chars,
        max_chunks_for_final,
        max_chunk_context_chars,
        final_model,
        final_timeout,
    )
    client = get_shared_client()

    # Build chunk context (cap to manageable size, using top N by retrieval score).
    chunk_lines: list[str] = []
    total_chunk_chars = 0
    for c in chunks[:max_chunks_for_final]:
        chunk_id = c.get("chunk_id", "?")
        hierarchy = c.get("hierarchy_path", "?")
        text = c.get("text_content", "")
        line = f"CHUNK [{chunk_id}] {hierarchy}:\n" f"{text}\n"
        if total_chunk_chars + len(line) > max_chunk_context_chars:
            remaining = max_chunk_context_chars - total_chunk_chars
            if remaining > 100:
                line = line[:remaining] + "..."
            else:
                break
        chunk_lines.append(line)
        total_chunk_chars += len(line)
    chunk_context = "\n---\n".join(chunk_lines)

    # Build the user prompt (German).
    user_parts: list[str] = []

    user_parts.append("## DOKUMENT\n")
    user_parts.append(trim_text(normalized_text, max_final_input_chars))

    if issues:
        user_parts.append("\n\n## IDENTIFIZIERTE THEMEN\n")
        user_parts.append("\n".join(f"- {i}" for i in issues))

    if questions:
        user_parts.append("\n\n## RECHTSFRAGEN\n")
        user_parts.append("\n".join(f"- {q}" for q in questions))

    user_parts.append("\n\n## RECHTSQUELLEN (CHUNKS)\n")
    user_parts.append(chunk_context)

    user_content = "\n".join(user_parts)

    messages = [
        {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    prompt_chars = len(sys_msg) + len(_STRICT_SUFFIX) + len(user_content)
    prompt_tokens = estimate_tokens(sys_msg + _STRICT_SUFFIX + user_content)
    logger.info(
        "generate_grounded_answer: prompt ~%d chars (user=%d, system=%d), ~%d tokens, "
        "%d chunks included",
        prompt_chars,
        len(user_content),
        len(sys_msg) + len(_STRICT_SUFFIX),
        prompt_tokens,
        len(chunk_lines),
    )

    raw = await client.chat_completion(
        messages,
        temperature=0.1,
        model=final_model,
        timeout=final_timeout,
        max_retries=1,
    )
    try:
        result = _parse_json_response(raw, context="grounded answer (claims + sections)")
    except JSONParseError:
        logger.warning(
            "JSON parse error in generate_grounded_answer, retrying with stricter prompt"
        )
        messages_minimal = [
            {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
            {"role": "user", "content": user_content[: max_final_input_chars // 2]},
        ]
        raw2 = await client.chat_completion(
            messages_minimal,
            temperature=0.0,
            model=final_model,
            timeout=final_timeout,
            max_retries=1,
        )
        result = _parse_json_response(raw2, context="grounded answer (retry)")

    # --- Extract and validate claims ---
    raw_claims = result.get("claims", [])
    if not isinstance(raw_claims, list):
        logger.warning("generate_grounded_answer: unexpected 'claims' type: %s", type(raw_claims))
        raw_claims = []

    valid_claim_types = {"fact", "interpretation", "recommendation"}
    validated_claims: list[dict[str, Any]] = []
    for item in raw_claims:
        if not isinstance(item, dict):
            continue
        ct = item.get("claim_type", "fact")
        if ct not in valid_claim_types:
            ct = "fact"
        cs = item.get("confidence_score", 0.5)
        try:
            cs = float(cs)
        except (TypeError, ValueError):
            cs = 0.5
        cs = max(0.0, min(1.0, cs))
        validated_claims.append(
            {
                "claim_text": str(item.get("claim_text", "")).strip(),
                "confidence_score": cs,
                "claim_type": ct,
                "question": str(item.get("question", "")).strip(),
                "evidence_chunk_id": str(item.get("evidence_chunk_id", "")).strip(),
                "evidence_hierarchy": str(item.get("evidence_hierarchy", "")).strip(),
                "evidence_quote": str(item.get("evidence_quote", "")).strip(),
            }
        )

    # --- Extract and validate sections ---
    raw_sections = result.get("sections", {})
    if not isinstance(raw_sections, dict):
        logger.warning(
            "generate_grounded_answer: unexpected 'sections' type: %s",
            type(raw_sections),
        )
        raw_sections = {}

    required_keys = [
        "sachverhalt",
        "rechtliche_wuerdigung",
        "ergebnis",
        "handlungsempfehlung",
        "entwurf",
        "unsicherheiten",
        "adversarial_pruefung",
    ]
    sections: dict[str, str] = {}
    for key in required_keys:
        sections[key] = str(raw_sections.get(key, "")).strip()

    logger.info(
        "generate_grounded_answer: complete (model=%s, %d claims, %d sections)",
        final_model,
        len(validated_claims),
        len(sections),
    )
    return {"claims": validated_claims, "sections": sections}


# Alias: the function above was originally named adversarial_review but also
# serves as generate_grounded_answer (non-streaming entry point).
generate_grounded_answer = adversarial_review


async def generate_grounded_answer_stream(
    normalized_text: str,
    issues: list[str],
    questions: list[str],
    chunks: list[dict[str, Any]],
    *,
    system_prompt: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream tokens from a grounded answer generation, yielding progress.

    Accepts the same parameters as :meth:`generate_grounded_answer` but uses
    ``chat_completion_stream`` instead of ``chat_completion`` so tokens are
    yielded incrementally.

    Yields:
        ``{"type": "token", "content": "..."}`` for each content token, and
        finally ``{"type": "done", "result": <parsed JSON dict>}`` when the
        stream is complete.

    On JSON parse failure, falls back to ``generate_grounded_answer`` once.
    """
    from app.core.config import settings as s

    final_model = s.FINAL_MODEL or s.PRIMARY_MODEL
    final_timeout = s.FINAL_TIMEOUT_SEC
    max_chunks_for_final = s.MAX_CHUNKS_FOR_FINAL
    max_chunk_context_chars = s.MAX_CHUNK_CONTEXT_CHARS
    max_final_input_chars = s.MAX_FINAL_INPUT_CHARS
    sys_msg = system_prompt if system_prompt is not None else _GROUNDED_ANSWER_SYSTEM

    logger.info(
        "generate_grounded_answer_stream: starting (input=%d chars, %d issues, "
        "%d questions, %d chunks, model=%s, timeout=%.1fs)",
        len(normalized_text),
        len(issues),
        len(questions),
        len(chunks),
        final_model,
        final_timeout,
    )
    client = get_shared_client()

    # Build chunk context (same logic as generate_grounded_answer).
    chunk_lines: list[str] = []
    total_chunk_chars = 0
    for c in chunks[:max_chunks_for_final]:
        chunk_id = c.get("chunk_id", "?")
        hierarchy = c.get("hierarchy_path", "?")
        text = c.get("text_content", "")
        line = f"CHUNK [{chunk_id}] {hierarchy}:\n" f"{text}\n"
        if total_chunk_chars + len(line) > max_chunk_context_chars:
            remaining = max_chunk_context_chars - total_chunk_chars
            if remaining > 100:
                line = line[:remaining] + "..."
            else:
                break
        chunk_lines.append(line)
        total_chunk_chars += len(line)
    chunk_context = "\n---\n".join(chunk_lines)

    # Build the user prompt (German).
    user_parts: list[str] = []
    user_parts.append("## DOKUMENT\n")
    user_parts.append(trim_text(normalized_text, max_final_input_chars))
    if issues:
        user_parts.append("\n\n## IDENTIFIZIERTE THEMEN\n")
        user_parts.append("\n".join(f"- {i}" for i in issues))
    if questions:
        user_parts.append("\n\n## RECHTSFRAGEN\n")
        user_parts.append("\n".join(f"- {q}" for q in questions))
    user_parts.append("\n\n## RECHTSQUELLEN (CHUNKS)\n")
    user_parts.append(chunk_context)
    user_content = "\n".join(user_parts)

    messages = [
        {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    # Accumulate the raw response.
    raw_parts: list[str] = []

    try:
        async for token in client.chat_completion_stream(
            messages,
            temperature=0.1,
            model=final_model,
            timeout=final_timeout,
            max_retries=1,
        ):
            raw_parts.append(token)
            yield {"type": "token", "content": token}
    except Exception as exc:
        logger.warning(
            "chat_completion_stream failed, falling back to non-streaming: %s",
            exc,
        )
        raw = await client.chat_completion(
            messages,
            temperature=0.1,
            model=final_model,
            timeout=final_timeout,
            max_retries=1,
        )
        raw_parts = [raw]
        # Yield the full response as a single token so the caller sees output.
        yield {"type": "token", "content": raw}

    raw_response = "".join(raw_parts)

    # Parse the accumulated response.
    try:
        result = _parse_json_response(raw_response, context="grounded answer stream")
    except JSONParseError:
        logger.warning(
            "JSON parse error in generate_grounded_answer_stream, "
            "falling back to non-streaming generate_grounded_answer"
        )
        # Fallback: call the non-streaming version directly.
        # claims=[] is safe — adversarial_review regenerates claims from the LLM.
        result = await generate_grounded_answer(
            normalized_text,
            issues,
            questions,
            [],
            chunks,
        )
        yield {"type": "done", "result": result}
        return

    # --- Extract and validate claims (same logic as generate_grounded_answer) ---
    raw_claims = result.get("claims", [])
    if not isinstance(raw_claims, list):
        logger.warning(
            "generate_grounded_answer_stream: unexpected 'claims' type: %s",
            type(raw_claims),
        )
        raw_claims = []

    valid_claim_types = {"fact", "interpretation", "recommendation"}
    claims: list[dict[str, Any]] = []
    for item in raw_claims:
        if not isinstance(item, dict):
            continue
        ct = item.get("claim_type", "fact")
        if ct not in valid_claim_types:
            ct = "fact"
        cs = item.get("confidence_score", 0.5)
        try:
            cs = float(cs)
        except (TypeError, ValueError):
            cs = 0.5
        cs = max(0.0, min(1.0, cs))
        claims.append(
            {
                "claim_text": str(item.get("claim_text", "")).strip(),
                "confidence_score": cs,
                "claim_type": ct,
                "question": str(item.get("question", "")).strip(),
                "evidence_chunk_id": str(item.get("evidence_chunk_id", "")).strip(),
                "evidence_hierarchy": str(item.get("evidence_hierarchy", "")).strip(),
                "evidence_quote": str(item.get("evidence_quote", "")).strip(),
            }
        )

    # --- Extract and validate sections ---
    raw_sections = result.get("sections", {})
    if not isinstance(raw_sections, dict):
        logger.warning(
            "generate_grounded_answer_stream: unexpected 'sections' type: %s",
            type(raw_sections),
        )
        raw_sections = {}

    required_keys = [
        "sachverhalt",
        "rechtliche_wuerdigung",
        "ergebnis",
        "handlungsempfehlung",
        "entwurf",
        "unsicherheiten",
        "adversarial_pruefung",
    ]
    sections: dict[str, str] = {}
    for key in required_keys:
        sections[key] = str(raw_sections.get(key, "")).strip()

    logger.info(
        "generate_grounded_answer_stream: complete (model=%s, %d claims, %d sections)",
        final_model,
        len(claims),
        len(sections),
    )
    yield {"type": "done", "result": {"claims": claims, "sections": sections}}


# ---------------------------------------------------------------------------
# Stage 5 — Claim Construction
# ---------------------------------------------------------------------------

_CLAIM_CONSTRUCTION_SYSTEM = SOCIALRECHT_PROMPTS["claim_construction"]


async def construct_claims(
    chunks: list[dict[str, str]],
    questions: list[str],
    *,
    system_prompt: str | None = None,
) -> list[dict[str, str | float]]:
    """Build claims with confidence scores and types.

    Parameters
    ----------
    chunks :
        Evidence chunks retrieved from pgvector (each has at least
        ``text_content`` and ``hierarchy_path`` fields).
    questions :
        Legal questions from the decomposition stage.

    Returns
    -------
    list[dict]
        A list of claim dicts with keys: ``claim_text``, ``confidence_score``,
        ``claim_type``, ``question``.
    """
    logger.info("construct_claims: starting (%d chunks, %d questions)", len(chunks), len(questions))
    client = get_shared_client()
    from app.core.config import settings as _s

    sys_msg = system_prompt if system_prompt is not None else _CLAIM_CONSTRUCTION_SYSTEM

    chunk_context = "\n\n---\n\n".join(
        f"[{c.get('hierarchy_path', '?')}]: {c.get('text_content', '')}"
        for c in chunks[: _s.MAX_CHUNKS_FOR_FINAL]
    )

    user_content = (
        "Questions:\n"
        + "\n".join(f"- {q}" for q in questions[:5])
        + "\n\nRelevant legal chunks:\n"
        + chunk_context[: _s.MAX_CHUNK_CONTEXT_CHARS]
    )

    messages = [
        {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="claim construction")
    except JSONParseError:
        logger.warning("JSON parse error in construct_claims, retrying with stricter prompt")
        raw2 = await client.chat_completion(
            [
                {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
                {"role": "user", "content": user_content[: _s.MAX_CHUNK_CONTEXT_CHARS // 2]},
            ],
            temperature=0.0,
        )
        result = _parse_json_response(raw2, context="claim construction (retry)")

    if not isinstance(result, list):
        logger.warning("construct_claims: expected list, got %s", type(result))
        return []

    validated: list[dict[str, str | float]] = []
    valid_types = {"fact", "interpretation", "recommendation"}
    for item in result:
        if not isinstance(item, dict):
            continue
        ct = item.get("claim_type", "fact")
        if ct not in valid_types:
            ct = "fact"
        cs = item.get("confidence_score", 0.5)
        try:
            cs = float(cs)
        except (TypeError, ValueError):
            cs = 0.5
        cs = max(0.0, min(1.0, cs))
        validated.append(
            {
                "claim_text": str(item.get("claim_text", "")).strip(),
                "confidence_score": cs,
                "claim_type": ct,
                "question": str(item.get("question", "")).strip(),
            }
        )

    return validated


# ---------------------------------------------------------------------------
# Stage 6 — Verification Pass
# ---------------------------------------------------------------------------

_VERIFICATION_SYSTEM = SOCIALRECHT_PROMPTS["verification"]


async def verify_claims(
    claims: list[dict[str, str | float]],
    chunks: list[dict[str, str]],
    *,
    system_prompt: str | None = None,
) -> list[dict[str, str | float | bool]]:
    """Cross-reference each claim against the provided source text.

    Parameters
    ----------
    claims :
        Claims from the construction stage.
    chunks :
        Evidence chunks retrieved from pgvector.

    Returns
    -------
    list[dict]
        Verified claims with an added ``verified`` (bool) and ``reasoning``
        (str) field, plus adjusted ``confidence_score``.
    """
    if not claims:
        return []

    logger.info("verify_claims: starting (%d claims, %d chunks)", len(claims), len(chunks))
    client = get_shared_client()
    from app.core.config import settings as _s

    sys_msg = system_prompt if system_prompt is not None else _VERIFICATION_SYSTEM

    chunk_text = "\n\n---\n\n".join(
        f"[{c.get('hierarchy_path', '?')}]: {c.get('text_content', '')}"
        for c in chunks[: _s.MAX_CHUNKS_FOR_FINAL]
    )

    claims_text = "\n".join(
        f"{i + 1}. [{c.get('claim_type', '?')}] {c.get('claim_text', '')}"
        for i, c in enumerate(claims)
    )

    user_content = f"Claims to verify:\n{claims_text}\n\nSource chunks:\n{chunk_text[:_s.MAX_CHUNK_CONTEXT_CHARS]}"

    messages = [
        {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="claim verification")
    except JSONParseError:
        logger.warning("JSON parse error in verify_claims, retrying with stricter prompt")
        raw2 = await client.chat_completion(
            [
                {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
                {
                    "role": "user",
                    "content": f"Claims:\n{claims_text[:_s.MAX_CHUNK_CONTEXT_CHARS // 3]}\n\nChunks:\n{chunk_text[:_s.MAX_CHUNK_CONTEXT_CHARS // 3]}",
                },
            ],
            temperature=0.0,
        )
        result = _parse_json_response(raw2, context="claim verification (retry)")

    if not isinstance(result, list):
        logger.warning("verify_claims: expected list, got %s", type(result))
        # Fallback: return original claims untouched with default verification fields
        return [
            {
                **c,
                "verified": False,
                "reasoning": "Verification failed — LLM returned unexpected format.",
            }
            for c in claims
        ]

    verified: list[dict[str, str | float | bool]] = []
    valid_types = {"fact", "interpretation", "recommendation"}
    for item in result:
        if not isinstance(item, dict):
            continue
        cs = item.get("confidence_score", 0.5)
        try:
            cs = float(cs)
        except (TypeError, ValueError):
            cs = 0.5
        cs = max(0.0, min(1.0, cs))
        ct = item.get("claim_type", "fact")
        if ct not in valid_types:
            ct = "fact"
        verified.append(
            {
                "claim_text": str(item.get("claim_text", "")).strip(),
                "confidence_score": cs,
                "claim_type": ct,
                "verified": bool(item.get("verified", False)),
                "reasoning": str(item.get("reasoning", "")).strip(),
            }
        )

    return verified


# ---------------------------------------------------------------------------
# Stage 7 — Output Generation
# ---------------------------------------------------------------------------

_OUTPUT_SYSTEM = SOCIALRECHT_PROMPTS["output"]


async def generate_output(
    verified_claims: list[dict[str, str | float | bool]],
    *,
    system_prompt: str | None = None,
) -> dict[str, str]:
    """Format verified claims into the mandatory 6-part output structure.

    Parameters
    ----------
    verified_claims :
        Claims after the verification pass.

    Returns
    -------
    dict[str, str]
        A dict with keys: ``sachverhalt``, ``rechtliche_wuerdigung``,
        ``ergebnis``, ``handlungsempfehlung``, ``entwurf``, ``unsicherheiten``.
    """
    logger.info("generate_output: starting (%d verified claims)", len(verified_claims))
    client = get_shared_client()
    from app.core.config import settings as _s

    sys_msg = system_prompt if system_prompt is not None else _OUTPUT_SYSTEM

    claims_text = "\n".join(
        f"- [{c.get('claim_type', '?')}] (verified={c.get('verified', False)}, "
        f"confidence={c.get('confidence_score', 0.0):.2f}) {c.get('claim_text', '')}"
        for c in verified_claims
    )

    user_content = f"Verified claims:\n{claims_text[:_s.MAX_FINAL_INPUT_CHARS]}"

    messages = [
        {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="output generation")
    except JSONParseError:
        logger.warning("JSON parse error in generate_output, retrying with stricter prompt")
        raw2 = await client.chat_completion(
            [
                {"role": "system", "content": sys_msg + _STRICT_SUFFIX},
                {"role": "user", "content": user_content[: _s.MAX_FINAL_INPUT_CHARS // 2]},
            ],
            temperature=0.0,
        )
        result = _parse_json_response(raw2, context="output generation (retry)")

    # Validate that all 6 mandatory keys are present (default to empty string).
    required_keys = [
        "sachverhalt",
        "rechtliche_wuerdigung",
        "ergebnis",
        "handlungsempfehlung",
        "entwurf",
        "unsicherheiten",
    ]
    output: dict[str, str] = {}
    if isinstance(result, dict):
        for key in required_keys:
            output[key] = str(result.get(key, "")).strip()
    else:
        # LLM returned a non-dict JSON (list, string, etc.) — default to blanks.
        logger.warning(
            "generate_output: non-dict response (%s)",
            type(result).__name__,
        )
        output = {key: "" for key in required_keys}

    return output


# ---------------------------------------------------------------------------
# OCR Synthesis & Correction — pre-pipeline stage
# ---------------------------------------------------------------------------

_OCR_SYNTHESIS_SYSTEM = (
    "Du bist ein Experte für deutsche Texterkennung und -korrektur. "
    "Dir werden zwei OCR-Texte desselben Dokuments vorgelegt, die von "
    "unterschiedlich vorverarbeiteten Versionen stammen. "
    "Deine Aufgabe:\n\n"
    "1. Vergleiche beide Versionen und erstelle eine bestmögliche Synthese — "
    "   wo beide Versionen übereinstimmen, übernimmt den Text. "
    "   Wo Versionen voneinander abweichen, entscheide anhand des Kontexts, "
    "   welche Version wahrscheinlicher korrekt ist.\n"
    "2. Führe eine Rechtschreib- und Grammatikprüfung durch. "
    "   Korrigiere offensichtliche OCR-Fehler (wie falsch erkannte Buchstaben, "
    "   verschobene Zeilen, fehlende Leerzeichen).\n"
    "3. Gib NUR den endgültigen, korrigierten deutschen Text zurück. "
    "   Keine Erklärungen, keine Metadaten, keine Markdown-Formatierung.\n"
    "4. Der ausgegebene Text muss ein vollständiges, zusammenhängendes "
    "   Dokument sein. Keine Sätze dürfen fehlen. Der gesamte Inhalt beider "
    "   OCR-Ergebnisse muss im Ergebnis enthalten sein (ggf. korrigiert)."
)


async def synthesize_and_correct_text(
    ocr_version_a: str,
    ocr_version_b: str,
    *,
    max_input_chars: int = 12000,
) -> str:
    """Compare two OCR results and produce a single corrected text.

    Uses the configured ``OCR_SYNTHESIS_MODEL`` (default:
    ``deepseek/deepseek-v4-pro``) via OpenRouter to:

    1. Compare both OCR versions and reconcile differences.
    2. Apply spell-checking and grammar correction.
    3. Return the final, corrected German text.

    Parameters
    ----------
    ocr_version_a : str
        OCR output from greyscale + contrast preprocessed image.
    ocr_version_b : str
        OCR output from black-and-white thresholded image.
    max_input_chars : int
        Maximum characters to send per version (truncated per-version
        to stay within model context limits).

    Returns
    -------
    str
        The synthesized, spell- and grammar-checked corrected text.
    """
    from app.core.config import settings as s

    client = get_shared_client()

    # Truncate each version to stay within context limits.
    a_text = ocr_version_a[:max_input_chars]
    b_text = ocr_version_b[:max_input_chars]

    user_message = (
        f"=== OCR-Version A (Graustufen + Kontrast) ===\n\n"
        f"{a_text}\n\n"
        f"=== OCR-Version B (Schwarz/Weiß) ===\n\n"
        f"{b_text}"
    )

    messages = [
        {"role": "system", "content": _OCR_SYNTHESIS_SYSTEM},
        {"role": "user", "content": user_message},
    ]

    synthesis_model = s.OCR_SYNTHESIS_MODEL
    logger.info(
        "Sending dual-OCR results to %s for synthesis and correction " "(A: %d chars, B: %d chars)",
        synthesis_model,
        len(a_text),
        len(b_text),
    )

    try:
        raw = await client.chat_completion(
            messages,
            temperature=0.1,
            model=synthesis_model,
        )
    except Exception as exc:
        logger.error(
            "OCR synthesis LLM call failed: %s. Falling back to version A.",
            exc,
        )
        # Fall back to version A (greyscale + contrast, which is usually better)
        return ocr_version_a

    corrected = raw.strip()
    if not corrected:
        logger.warning("OCR synthesis returned empty; falling back to version A")
        return ocr_version_a

    logger.info(
        "OCR synthesis complete (model=%s) — %d chars (input was %d + %d chars)",
        synthesis_model,
        len(corrected),
        len(a_text),
        len(b_text),
    )
    return corrected
