"""Reasoning engine: LLM-driven claim construction, verification, output formatting,
and OCR result synthesis with spell/grammar correction.

Implements stages 2-3 and 5-7 of the 7-stage pipeline:
    Combined Triage (WP-006)           → triage_document()
    2. Issue Classification             → classify_issues()
    3. Question Decomposition            → decompose_questions()
    5. Claim Construction                → construct_claims()
    6. Verification Pass                 → verify_claims()
    7. Output Generation                 → generate_output()

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
from typing import Any

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
        f"LLM returned malformed JSON for {context}. "
        f"Raw output (truncated): {raw[:300]!r}"
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
    logger.info("classify_issues: starting (input=%d chars)", len(normalized_text))
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
    logger.info("decompose_questions: starting (input=%d chars)", len(normalized_text))
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
# Combined Stages 2+3 — Triage (WP-006)
# ---------------------------------------------------------------------------

_TRIAGE_SYSTEM = (
    "Du bist ein Experte für deutsches Sozialrecht. Dir wird der Text eines "
    "behördlichen Dokuments (z. B. Jobcenter-Bescheid) vorgelegt.\n\n"
    "Erledige BEIDE der folgenden Aufgaben in einem einzigen Durchlauf:\n\n"
    "1. **Themenidentifikation:** Identifiziere alle rechtlichen Themen / "
    "Problemfelder, die in dem Dokument angesprochen werden. Verwende präzise "
    "deutsche sozialrechtliche Fachbegriffe (z. B. \"Meldefristverletzung\", "
    "\"Eingliederungsvereinbarung\", \"Bewilligungsbescheid\", "
    "\"Kosten der Unterkunft\", \"Sanktion nach § 31 SGB II\"). Liefere 1–8 "
    "Themen.\n\n"
    "2. **Fragenableitung:** Leite daraus 3–5 konkrete, beantwortbare "
    "Rechtsfragen ab. Jede Frage muss mit dem deutschen Sozialrecht "
    "(insbesondere SGB II, SGB X, SGB XII) beantwortbar sein.\n\n"
    "Gib NUR ein JSON-Objekt mit genau diesen zwei Schlüsseln zurück:\n"
    '{ "issues": ["Thema A", "Thema B", ...], '
    '"questions": ["Frage 1", "Frage 2", ...] }\n\n'
    "Kein Prosatext. Keine Markdown-Formatierung. Keine Erklärungen."
)


async def triage_document(normalized_text: str) -> dict[str, list[str]]:
    """Perform combined classification and decomposition in a single LLM call.

    Instead of calling ``classify_issues()`` and ``decompose_questions()``
    sequentially, this function asks one LLM call for both lists at once.

    Parameters
    ----------
    normalized_text :
        Cleaned text from the OCR / ingestion pipeline.

    Returns
    -------
    dict[str, list[str]]
        A dict with keys ``issues`` (list of legal issue labels) and
        ``questions`` (list of explicit legal questions).
    """
    from app.core.config import settings as s

    triage_model = s.TRIAGE_MODEL or s.PRIMARY_MODEL
    triage_timeout = s.TRIAGE_TIMEOUT_SEC

    logger.info(
        "triage_document: starting (input=%d chars, model=%s, timeout=%.1fs)",
        len(normalized_text),
        triage_model,
        triage_timeout,
    )
    client = _get_client()

    messages = [
        {"role": "system", "content": _TRIAGE_SYSTEM + _STRICT_SUFFIX},
        {
            "role": "user",
            "content": normalized_text[:8000],
        },
    ]

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
            {"role": "system", "content": _TRIAGE_SYSTEM + _STRICT_SUFFIX},
            {"role": "user", "content": normalized_text[:4000]},
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

    logger.info(
        "triage_document: complete (model=%s, %d issues, %d questions)",
        triage_model,
        len(clean_issues),
        len(clean_questions),
    )
    return {"issues": clean_issues, "questions": clean_questions}


# ---------------------------------------------------------------------------
# Combined Stages 5+6+7 — Grounded Answer Generation (WP-007)
# ---------------------------------------------------------------------------

_GROUNDED_ANSWER_SYSTEM = (
    "Du bist ein Experte für deutsches Sozialrecht (SGB II, SGB X, SGB XII).\n"
    "Dir werden vorgelegt:\n"
    "1. Der normalisierte Text eines behördlichen Dokuments.\n"
    "2. Eine Liste identifizierter rechtlicher Themen.\n"
    "3. Eine Liste konkreter Rechtsfragen.\n"
    "4. Eine Sammlung von Rechtsprechungs- und Gesetzes-Chunks aus einer "
    "Vektordatenbank.\n\n"
    "Deine Aufgabe:\n\n"
    "A) **Claims erstellen:** Für jede Rechtsfrage 1–3 rechtliche Aussagen "
    "(Claims) formulieren. Jeder Claim MUSS:\n"
    '  - "claim_text" (str): die Aussage selbst, auf Deutsch\n'
    '  - "confidence_score" (float 0.0–1.0): deine subjektive Sicherheit\n'
    '  - "claim_type" (str): "fact" | "interpretation" | "recommendation"\n'
    '  - "question" (str): die Rechtsfrage, auf die sich der Claim bezieht\n'
    '  - "evidence_chunk_id" (str): die ID des Chunks, aus dem die Evidenz stammt\n'
    '  - "evidence_hierarchy" (str): die Hierarchie der Rechtsquelle '
    '(z. B. "SGB II > § 31 > Abs. 1")\n'
    '  - "evidence_quote" (str): das EXAKTE wörtliche Zitat aus dem Chunk\n\n'
    "WICHTIGE REGELN:\n"
    "- Verwende NUR die bereitgestellten Chunks als Quelle.\n"
    "- Kopiere evidence_quote WÖRTLICH aus dem Chunk-Text (copy-paste, keine "
    "Paraphrasierung).\n"
    "- Wenn die Evidenz nicht ausreicht, setze confidence_score niedrig "
    "(≤ 0.4) und sage dies im claim_text.\n"
    "- Erfinde KEINE Paragraphen oder Aktenzeichen.\n"
    "- evidence_chunk_id MUSS exakt die chunk_id aus den bereitgestellten "
    "Chunks sein.\n\n"
    "B) **Abschnitte generieren:** Erstelle die folgenden 6 Abschnitte "
    "auf Deutsch:\n"
    '  - "sachverhalt": Zusammenfassung des Sachverhalts\n'
    '  - "rechtliche_wuerdigung": Rechtliche Würdigung mit Zitaten der '
    "einschlägigen Vorschriften\n"
    '  - "ergebnis": Ergebnis / Fazit\n'
    '  - "handlungsempfehlung": Konkrete Handlungsempfehlungen\n'
    '  - "entwurf": Entwurf eines Antwortschreibens\n'
    '  - "unsicherheiten": Verbleibende Unsicherheiten oder fehlende '
    "Informationen\n\n"
    "Gib NUR ein JSON-Objekt zurück:\n"
    '{\n'
    '  "claims": [\n'
    '    {\n'
    '      "claim_text": "...",\n'
    '      "confidence_score": 0.82,\n'
    '      "claim_type": "interpretation",\n'
    '      "question": "...",\n'
    '      "evidence_chunk_id": "...",\n'
    '      "evidence_hierarchy": "SGB II > § 31 > Abs. 1",\n'
    '      "evidence_quote": "..."\n'
    '    }\n'
    '  ],\n'
    '  "sections": {\n'
    '    "sachverhalt": "...",\n'
    '    "rechtliche_wuerdigung": "...",\n'
    '    "ergebnis": "...",\n'
    '    "handlungsempfehlung": "...",\n'
    '    "entwurf": "...",\n'
    '    "unsicherheiten": "..."\n'
    '  }\n'
    '}\n\n'
    "Kein Prosatext außerhalb des JSON. Keine Markdown-Fences."
)


async def generate_grounded_answer(
    normalized_text: str,
    issues: list[str],
    questions: list[str],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate claims and 6-part output in a single grounded LLM call.

    Replaces three sequential LLM calls (``construct_claims()``,
    ``verify_claims()``, ``generate_output()``) with one combined call
    that asks the model to produce both evidence-bound claims and the
    final six output sections.

    The model is instructed to:
    - Only use the provided chunks as sources.
    - Copy ``evidence_quote`` exactly from chunk text.
    - Explicitly state uncertainty when evidence is insufficient.
    - Return strict JSON with ``claims`` (list) and ``sections`` (dict).

    Parameters
    ----------
    normalized_text :
        Cleaned text from the OCR / ingestion pipeline.
    issues :
        Legal topics identified during triage.
    questions :
        Explicit legal questions from triage.
    chunks :
        Evidence chunks retrieved from pgvector. Each chunk should have
        ``chunk_id``, ``text_content``, and ``hierarchy_path`` fields.

    Returns
    -------
    dict[str, Any]
        A dict with keys:
        - ``claims``: ``list[dict]`` — claims with evidence bindings.
        - ``sections``: ``dict[str, str]`` — the 6 output sections.
    """
    from app.core.config import settings as s

    final_model = s.FINAL_MODEL or s.PRIMARY_MODEL
    final_timeout = s.FINAL_TIMEOUT_SEC

    logger.info(
        "generate_grounded_answer: starting (input=%d chars, %d issues, "
        "%d questions, %d chunks, model=%s, timeout=%.1fs)",
        len(normalized_text),
        len(issues),
        len(questions),
        len(chunks),
        final_model,
        final_timeout,
    )
    client = _get_client()

    # Build chunk context (cap to manageable size).
    max_chunk_chars = 7000
    chunk_lines: list[str] = []
    total_chunk_chars = 0
    for c in chunks[:12]:
        chunk_id = c.get("chunk_id", "?")
        hierarchy = c.get("hierarchy_path", "?")
        text = c.get("text_content", "")
        line = (
            f"CHUNK [{chunk_id}] {hierarchy}:\n"
            f"{text}\n"
        )
        if total_chunk_chars + len(line) > max_chunk_chars:
            remaining = max_chunk_chars - total_chunk_chars
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
    user_parts.append(normalized_text[:4000])

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
        {"role": "system", "content": _GROUNDED_ANSWER_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

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
            {"role": "system", "content": _GROUNDED_ANSWER_SYSTEM + _STRICT_SUFFIX},
            {"role": "user", "content": user_content[:4000]},
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
        logger.warning(
            "generate_grounded_answer: unexpected 'claims' type: %s", type(raw_claims)
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
        claims.append({
            "claim_text": str(item.get("claim_text", "")).strip(),
            "confidence_score": cs,
            "claim_type": ct,
            "question": str(item.get("question", "")).strip(),
            "evidence_chunk_id": str(item.get("evidence_chunk_id", "")).strip(),
            "evidence_hierarchy": str(item.get("evidence_hierarchy", "")).strip(),
            "evidence_quote": str(item.get("evidence_quote", "")).strip(),
        })

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
    ]
    sections: dict[str, str] = {}
    for key in required_keys:
        sections[key] = str(raw_sections.get(key, "")).strip()

    logger.info(
        "generate_grounded_answer: complete (model=%s, %d claims, %d sections)",
        final_model,
        len(claims),
        len(sections),
    )
    return {"claims": claims, "sections": sections}


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
    logger.info("construct_claims: starting (%d chunks, %d questions)", len(chunks), len(questions))
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

    logger.info("verify_claims: starting (%d claims, %d chunks)", len(claims), len(chunks))
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
    logger.info("generate_output: starting (%d verified claims)", len(verified_claims))
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
    ``deepseek/deepseek-v4-flash``) via OpenRouter to:

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

    client = _get_client()

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
        "Sending dual-OCR results to %s for synthesis and correction "
        "(A: %d chars, B: %d chars)",
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


# ---------------------------------------------------------------------------
# Reset helper (for tests)
# ---------------------------------------------------------------------------


def reset_client() -> None:
    """Reset the module-level ``_client`` singleton. Useful in unit tests."""
    global _client
    _client = None


async def close_client() -> None:
    """Close the module-level OpenRouter client and free resources.

    For use in application shutdown hooks.
    """
    global _client
    if _client is not None:
        await _client.close()
        _client = None
