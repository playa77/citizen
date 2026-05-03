"""Reasoning engine: LLM-driven claim construction, verification, and output formatting.

Implements stages 2-3 and 5-7 of the 7-stage pipeline:
    2. Issue Classification          → classify_issues()
    3. Question Decomposition         → decompose_questions()
    5. Claim Construction             → construct_claims()
    6. Verification Pass              → verify_claims()
    7. Output Generation              → generate_output()

Every function enforces a strict JSON output schema via a ``response_format``
directive embedded in the system prompt. Malformed JSON triggers one automatic
retry with a stricter prompt before raising ``JSONParseError``.
"""

from __future__ import annotations

import json
import logging

from app.core.router import OpenRouterClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class JSONParseError(Exception):
    """Raised when the LLM returns malformed JSON even after a retry."""


# ---------------------------------------------------------------------------
# Shared LLM client
# ---------------------------------------------------------------------------

_client: OpenRouterClient | None = None


def _get_client() -> OpenRouterClient:
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


# ---------------------------------------------------------------------------
# JSON-parsing helper with retry
# ---------------------------------------------------------------------------

_STRICT_SUFFIX = (
    "\n\nIMPORTANT: Respond with *only* valid JSON matching the schema above. "
    "No prose, no markdown fences, no explanation. If you cannot produce "
    "valid JSON, return an empty JSON object {}."
)


def _parse_json_response(raw: str, *, context: str) -> dict[str, object]:
    """Attempt to parse ``raw`` as JSON; retry once with a stricter prompt on failure.

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

    try:
        parsed: dict[str, object] = json.loads(stripped)
        return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # One retry — the LLM will be re-invoked with a stricter prompt by the
    # caller. We re-raise so the caller can handle the retry logic.
    raise JSONParseError(
        f"LLM returned malformed JSON for {context}. " f"Raw output (truncated): {raw[:300]!r}"
    )


# ---------------------------------------------------------------------------
# Stage 2 — Issue Classification
# ---------------------------------------------------------------------------

_CLASSIFICATION_SYSTEM = (
    "You are an expert in German social law (SGB II, SGB X, SGB XII). "
    "Given the text of a document received from a Jobcenter or Sozialamt, "
    "identify all legal topics / issues that are at stake.\n\n"
    "Return a JSON object with exactly this key:\n"
    '{ "issues": ["topic A", "topic B", ...] }\n\n'
    "Use concise German legal terminology (e.g. "
    '"Meldefristverletzung", "Eingliederungsvereinbarung", "Bewilligungsbescheid", '
    '"Kosten der Unterkunft", "Gesundheitspr\u00fcfung"). Return 1-8 issues.'
)


async def classify_issues(normalized_text: str) -> list[str]:
    """Call the LLM to extract legal issues from *normalized_text*.

    Parameters
    ----------
    normalized_text :
        Cleaned text from the OCR / ingestion pipeline.

    Returns
    -------
    list[str]
        A list of identified legal issue labels.
    """
    client = _get_client()
    messages = [
        {"role": "system", "content": _CLASSIFICATION_SYSTEM + _STRICT_SUFFIX},
        {
            "role": "user",
            "content": normalized_text[:8000],  # truncate to stay within context limits
        },
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="issue classification")
    except JSONParseError:
        # Retry once with a bare-minimum prompt
        logger.warning("JSON parse error in classify_issues, retrying with stricter prompt")
        messages_minimal = [
            {"role": "system", "content": _CLASSIFICATION_SYSTEM + _STRICT_SUFFIX},
            {"role": "user", "content": normalized_text[:4000]},
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

_DECOMPOSITION_SYSTEM = (
    "You are an expert in German social law. Given the text of an official "
    "administratory letter or document, extract exactly 3-5 explicit legal "
    "questions that need to be answered to resolve the matter.\n\n"
    "Return a JSON object with exactly this key:\n"
    '{ "questions": ["question 1", "question 2", ...] }\n\n'
    "Each question should be specific enough to be answered by referencing "
    "German social law (SGB II, SGB X, SGB XII). Use German."
)


async def decompose_questions(normalized_text: str) -> list[str]:
    """Call the LLM to extract explicit legal questions from *normalized_text*.

    Parameters
    ----------
    normalized_text :
        Cleaned text from the OCR / ingestion pipeline.

    Returns
    -------
    list[str]
        A list of extracted legal questions.
    """
    client = _get_client()
    messages = [
        {"role": "system", "content": _DECOMPOSITION_SYSTEM + _STRICT_SUFFIX},
        {
            "role": "user",
            "content": normalized_text[:8000],
        },
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="question decomposition")
    except JSONParseError:
        logger.warning("JSON parse error in decompose_questions, retrying with stricter prompt")
        messages_minimal = [
            {"role": "system", "content": _DECOMPOSITION_SYSTEM + _STRICT_SUFFIX},
            {"role": "user", "content": normalized_text[:4000]},
        ]
        raw2 = await client.chat_completion(messages_minimal, temperature=0.0)
        result = _parse_json_response(raw2, context="question decomposition (retry)")

    questions = result.get("questions", [])
    if not isinstance(questions, list):
        logger.warning("decompose_questions: unexpected 'questions' type: %s", type(questions))
        return []
    return [str(q).strip() for q in questions if str(q).strip()]


# ---------------------------------------------------------------------------
# Stage 5 — Claim Construction
# ---------------------------------------------------------------------------

_CLAIM_CONSTRUCTION_SYSTEM = (
    "You are an expert in German social law. You will be given a set of legal "
    "chunks retrieved from our corpus and a list of legal questions derived "
    "from a user's document.\n\n"
    "For each question, construct 1-3 claims. Each claim must have:\n"
    '- "claim_text" (str): the assertion itself\n'
    '- "confidence_score" (float between 0.0 and 1.0)\n'
    '- "claim_type" (str): one of "fact", "interpretation", "recommendation"\n'
    '- "question" (str): the question this claim addresses\n\n'
    "Return a JSON array of claim objects:\n"
    '[ { "claim_text": "...", "confidence_score": 0.8, "claim_type": "fact", '
    '"question": "..." }, ... ]\n\n'
    "Use German. Base claims on the provided chunk text whenever possible."
)


async def construct_claims(
    chunks: list[dict[str, str]],
    questions: list[str],
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
    client = _get_client()

    chunk_context = "\n\n---\n\n".join(
        f"[{c.get('hierarchy_path', '?')}]: {c.get('text_content', '')}"
        for c in chunks[:12]  # cap context to stay within limits
    )

    user_content = (
        "Questions:\n"
        + "\n".join(f"- {q}" for q in questions[:5])
        + "\n\nRelevant legal chunks:\n"
        + chunk_context[:6000]
    )

    messages = [
        {"role": "system", "content": _CLAIM_CONSTRUCTION_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="claim construction")
    except JSONParseError:
        logger.warning("JSON parse error in construct_claims, retrying with stricter prompt")
        raw2 = await client.chat_completion(
            [
                {"role": "system", "content": _CLAIM_CONSTRUCTION_SYSTEM + _STRICT_SUFFIX},
                {"role": "user", "content": user_content[:3000]},
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

_VERIFICATION_SYSTEM = (
    "You are a rigorous quality checker for a German social law reasoning "
    "engine. You will be given a list of claims and the source chunks they "
    "should be based on.\n\n"
    "For each claim:\n"
    "- Check whether the source text supports the assertion.\n"
    "- If unsupported, lower the confidence score and flag it.\n"
    "- Return the adjusted list.\n\n"
    "Each output item must have:\n"
    '- "claim_text" (str): original claim\n'
    '- "confidence_score" (float 0.0-1.0): adjusted confidence\n'
    '- "claim_type" (str): one of "fact", "interpretation", "recommendation"\n'
    '- "verified" (bool): whether the source supports the claim\n'
    '- "reasoning" (str): brief explanation in German\n\n'
    "Return a JSON array:\n"
    '[ { "claim_text": "...", "confidence_score": 0.7, "claim_type": "fact", '
    '"verified": true, "reasoning": "..." }, ... ]'
)


async def verify_claims(
    claims: list[dict[str, str | float]],
    chunks: list[dict[str, str]],
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

    client = _get_client()

    chunk_text = "\n\n---\n\n".join(
        f"[{c.get('hierarchy_path', '?')}]: {c.get('text_content', '')}" for c in chunks[:12]
    )

    claims_text = "\n".join(
        f"{i + 1}. [{c.get('claim_type', '?')}] {c.get('claim_text', '')}"
        for i, c in enumerate(claims)
    )

    user_content = f"Claims to verify:\n{claims_text}\n\nSource chunks:\n{chunk_text[:6000]}"

    messages = [
        {"role": "system", "content": _VERIFICATION_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="claim verification")
    except JSONParseError:
        logger.warning("JSON parse error in verify_claims, retrying with stricter prompt")
        raw2 = await client.chat_completion(
            [
                {"role": "system", "content": _VERIFICATION_SYSTEM + _STRICT_SUFFIX},
                {
                    "role": "user",
                    "content": f"Claims:\n{claims_text[:2000]}\n\nChunks:\n{chunk_text[:2000]}",
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

_OUTPUT_SYSTEM = (
    "You are a German social law expert. Given a list of verified claims, "
    "produce a structured legal assessment in exactly 6 sections.\n\n"
    "Section keys (in English, as JSON object keys) must be:\n"
    '- "sachverhalt" (str): summary of the facts\n'
    '- "rechtliche_wuerdigung" (str): legal assessment citing statutes\n'
    '- "ergebnis" (str): the result / conclusion\n'
    '- "handlungsempfehlung" (str): actionable recommendations\n'
    '- "entwurf" (str): a draft letter / response\n'
    '- "unsicherheiten" (str): uncertainties or missing information\n\n'
    "Return a single JSON object:\n"
    '{ "sachverhalt": "...", "rechtliche_wuerdigung": "...", "ergebnis": "...", '
    '"handlungsempfehlung": "...", "entwurf": "...", "unsicherheiten": "..." }\n\n'
    "Cite statutes in the format '§ X Abs. Y Satz Z'. Use German."
)


async def generate_output(
    verified_claims: list[dict[str, str | float | bool]],
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
    client = _get_client()

    claims_text = "\n".join(
        f"- [{c.get('claim_type', '?')}] (verified={c.get('verified', False)}, "
        f"confidence={c.get('confidence_score', 0.0):.2f}) {c.get('claim_text', '')}"
        for c in verified_claims
    )

    user_content = f"Verified claims:\n{claims_text[:8000]}"

    messages = [
        {"role": "system", "content": _OUTPUT_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    raw = await client.chat_completion(messages, temperature=0.1)
    try:
        result = _parse_json_response(raw, context="output generation")
    except JSONParseError:
        logger.warning("JSON parse error in generate_output, retrying with stricter prompt")
        raw2 = await client.chat_completion(
            [
                {"role": "system", "content": _OUTPUT_SYSTEM + _STRICT_SUFFIX},
                {"role": "user", "content": user_content[:4000]},
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
# Reset helper (for tests)
# ---------------------------------------------------------------------------


def reset_client() -> None:
    """Reset the module-level ``_client`` singleton. Useful in unit tests."""
    global _client
    _client = None
