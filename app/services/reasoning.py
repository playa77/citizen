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

from app.core.router import OpenRouterClient
from app.utils.tokens import trim_text, estimate_tokens

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
    "Du bist ein sorgfältiger Experte für deutsches Sozialrecht "
    "(insbesondere SGB II, SGB X, SGB XII). Dir wird der Text eines "
    "behördlichen Dokuments vorgelegt, z. B. von einem Jobcenter, Sozialamt "
    "oder einer anderen Sozialbehörde.\n\n"
    "Aufgabe: Identifiziere die rechtlichen Themen / Problemfelder, die in "
    "dem Dokument tatsächlich angesprochen werden oder für die rechtliche "
    "Bewertung naheliegend relevant sind.\n\n"
    "Wichtige Regeln:\n"
    "- Verwende präzise deutsche sozialrechtliche Fachbegriffe.\n"
    "- Nenne keine Themen, die im Dokument keine erkennbare Grundlage haben.\n"
    "- Fasse ähnliche Themen zusammen; vermeide Wiederholungen.\n"
    "- Wenn das Dokument unklar ist, benenne das nächstliegende Thema "
    "allgemein, aber erfinde keine Tatsachen.\n"
    "- Liefere 1-8 Themen.\n\n"
    "Return a JSON object with exactly this key:\n"
    '{ "issues": ["topic A", "topic B", ...] }\n\n'
    "Beispiele für geeignete Begriffe: "
    '"Meldefristverletzung", "Mitwirkungspflicht", '
    '"Eingliederungsvereinbarung", "Bewilligungsbescheid", '
    '"Aufhebungs- und Erstattungsbescheid", "Kosten der Unterkunft", '
    '"Sanktion nach § 31 SGB II", "Anhörung nach § 24 SGB X", '
    '"Gesundheitsprüfung".\n\n'
    "Gib ausschließlich gültiges JSON zurück. Kein Prosatext. Keine "
    "Markdown-Formatierung."
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
    from app.core.config import settings as _s
    triage_budget = _s.MAX_TRIAGE_INPUT_CHARS
    messages = [
        {"role": "system", "content": _CLASSIFICATION_SYSTEM + _STRICT_SUFFIX},
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
            {"role": "system", "content": _CLASSIFICATION_SYSTEM + _STRICT_SUFFIX},
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

_DECOMPOSITION_SYSTEM = (
    "Du bist ein sorgfältiger Experte für deutsches Sozialrecht "
    "(insbesondere SGB II, SGB X, SGB XII). Dir wird der Text eines "
    "behördlichen Schreibens, Bescheids oder sonstigen Dokuments vorgelegt.\n\n"
    "Aufgabe: Leite genau 3-5 konkrete Rechtsfragen ab, die beantwortet "
    "werden müssen, um die Angelegenheit rechtlich einzuordnen.\n\n"
    "Wichtige Regeln:\n"
    "- Jede Frage muss konkret auf den vorgelegten Dokumenttext bezogen sein.\n"
    "- Jede Frage muss mit deutschem Sozialrecht beantwortbar sein, "
    "insbesondere SGB II, SGB X oder SGB XII.\n"
    "- Formuliere keine allgemeinen Ratgeberfragen, sondern prüfbare "
    "Rechtsfragen.\n"
    "- Unterscheide, soweit erkennbar, zwischen formellen Fragen "
    "(z. B. Anhörung, Begründung, Frist, Zuständigkeit) und materiellen "
    "Fragen (z. B. Anspruch, Sanktion, Mitwirkung, Unterkunftskosten).\n"
    "- Erfinde keine Tatsachen, Fristen, Paragraphen oder Behördenhandlungen, "
    "die im Dokument nicht angelegt sind.\n\n"
    "Return a JSON object with exactly this key:\n"
    '{ "questions": ["question 1", "question 2", ...] }\n\n'
    "Use German. Gib ausschließlich gültiges JSON zurück. Kein Prosatext. "
    "Keine Markdown-Formatierung."
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
    from app.core.config import settings as _s
    triage_budget = _s.MAX_TRIAGE_INPUT_CHARS
    messages = [
        {"role": "system", "content": _DECOMPOSITION_SYSTEM + _STRICT_SUFFIX},
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
            {"role": "system", "content": _DECOMPOSITION_SYSTEM + _STRICT_SUFFIX},
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

_TRIAGE_SYSTEM = (
    "Du bist ein sorgfältiger Experte für deutsches Sozialrecht "
    "(insbesondere SGB II, SGB X, SGB XII). Dir wird der Text eines "
    "behördlichen Dokuments vorgelegt, z. B. eines Jobcenter-Bescheids, "
    "einer Anhörung, Aufforderung zur Mitwirkung, Einladung, "
    "Eingliederungsvereinbarung oder eines Schreibens des Sozialamts.\n\n"
    "Erledige BEIDE der folgenden Aufgaben in einem einzigen Durchlauf:\n\n"
    "1. **Themenidentifikation:** Identifiziere alle rechtlichen Themen / "
    "Problemfelder, die in dem Dokument tatsächlich angesprochen werden oder "
    "für die rechtliche Bewertung naheliegend relevant sind. Verwende präzise "
    "deutsche sozialrechtliche Fachbegriffe (z. B. "
    "\"Meldefristverletzung\", \"Mitwirkungspflicht\", "
    "\"Eingliederungsvereinbarung\", \"Bewilligungsbescheid\", "
    "\"Aufhebungs- und Erstattungsbescheid\", \"Kosten der Unterkunft\", "
    "\"Sanktion nach § 31 SGB II\", \"Anhörung nach § 24 SGB X\"). Liefere "
    "1–8 Themen.\n\n"
    "2. **Fragenableitung:** Leite daraus 3–5 konkrete, beantwortbare "
    "Rechtsfragen ab. Jede Frage muss auf den Dokumenttext bezogen und mit "
    "deutschem Sozialrecht, insbesondere SGB II, SGB X oder SGB XII, "
    "beantwortbar sein. Berücksichtige, soweit relevant, formelle Fragen "
    "(z. B. Anhörung, Begründung, Frist, Zuständigkeit) und materielle "
    "Fragen (z. B. Anspruch, Sanktion, Mitwirkung, Unterkunftskosten).\n\n"
    "Wichtige Regeln:\n"
    "- Erfinde keine Tatsachen, Fristen, Paragraphen oder Aktenzeichen.\n"
    "- Nenne keine Themen oder Fragen ohne erkennbare Grundlage im Dokument.\n"
    "- Fasse Dopplungen zusammen.\n"
    "- Wenn das Dokument unklar ist, formuliere die Unsicherheit in der "
    "Rechtsfrage, statt etwas zu unterstellen.\n\n"
    "Gib NUR ein JSON-Objekt mit genau diesen zwei Schlüsseln zurück:\n"
    '{ "issues": ["Thema A", "Thema B", ...], '
    '"questions": ["Frage 1", "Frage 2", ...] }\n\n'
    "Kein Prosatext. Keine Markdown-Formatierung. Keine Erklärungen. "
    "Keine zusätzlichen Schlüssel."
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
    triage_input_chars = s.MAX_TRIAGE_INPUT_CHARS

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
    client = _get_client()

    trimmed_input = trim_text(normalized_text, triage_input_chars)
    input_tokens = estimate_tokens(trimmed_input + _TRIAGE_SYSTEM + _STRICT_SUFFIX)

    messages = [
        {"role": "system", "content": _TRIAGE_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": trimmed_input},
    ]

    logger.info(
        "triage_document: prompt ~%d chars (user=%d, system=%d), ~%d tokens",
        len(trimmed_input) + len(_TRIAGE_SYSTEM) + len(_STRICT_SUFFIX),
        len(trimmed_input),
        len(_TRIAGE_SYSTEM) + len(_STRICT_SUFFIX),
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
            {"role": "system", "content": _TRIAGE_SYSTEM + _STRICT_SUFFIX},
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
        from app.services.cache import make_cache_key as _mk, set_json_cache as _set

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
# Stage 7 — Adversarial Legal Review (Rechtsprüfungsrat)
# ---------------------------------------------------------------------------

_ADVERSARIAL_REVIEW_SYSTEM = (
    "Du bist der **Rechtsprüfungsrat** — ein Gremium aus mehreren "
    "Rechtsexpertinnen und -experten, die eine umfassende adversariale "
    "Prüfung des Falles aus allen Perspektiven durchführen.\n\n"
    "Dir werden vorgelegt:\n"
    "1. Der normalisierte Text eines behördlichen Dokuments.\n"
    "2. Eine Liste identifizierter rechtlicher Themen.\n"
    "3. Eine Liste konkreter Rechtsfragen.\n"
    "4. Eine Liste rechtlicher Claims (Aussagen) mit Konfidenzwerten.\n"
    "5. Rechtsquellen-Chunks aus dem Corpus.\n\n"
    "Deine Aufgabe ist nicht, die Claims automatisch zu verteidigen. Du "
    "prüfst jeden Claim kritisch, gegnerisch und neutral. Ein Claim kann "
    "stark, teilweise tragfähig, unsicher oder unbegründet sein.\n\n"
    "Du prüfst JEDEN Claim aus allen Perspektiven:\n\n"
    "**1. Verteidigerperspektive (Bürgeranwalt):**\n"
    "- Welche Gegenargumente sprechen gegen die Position der Behörde?\n"
    "- Welche Rechtsfehler hat die Behörde möglicherweise begangen?\n"
    "- Welche Schutzvorschriften kommen dem Bürger zugute?\n"
    "- Welche Tatsachen aus dem Dokument stützen die Position des Bürgers?\n\n"
    "**2. Behördenperspektive (gegnerische Partei):**\n"
    "- Was würde die Behörde / das Jobcenter / Sozialamt zur "
    "Verteidigung ihrer Position vorbringen?\n"
    "- Auf welche bereitgestellten Rechtsgrundlagen würde sie sich stützen?\n"
    "- Welche Ermessens-, Beurteilungs- oder Nachweisspielräume hätte sie?\n"
    "- Welche Schwächen oder Lücken in der Position des Bürgers würde sie "
    "angreifen?\n\n"
    "**3. Richterliche Perspektive (neutrale Instanz):**\n"
    "- Wie würde ein neutrales Gericht diesen Fall wahrscheinlich "
    "beurteilen?\n"
    "- Ist die Rechtslage eindeutig oder bestehen "
    "Auslegungsspielräume?\n"
    "- Ist der Claim anhand der bereitgestellten Chunks ausreichend belegt?\n"
    "- Wie hoch ist die Erfolgsaussicht qualitativ einzuschätzen "
    "(keine Garantie, keine verbindliche Rechtsberatung)?\n\n"
    "**4. Verfahrensprüfung:**\n"
    "- Wurden formelle Verfahrensvorschriften eingehalten?\n"
    "- Liegen formelle Fehler vor (fehlende Anhörung, unzureichende "
    "Begründung, Fristversäumnis, falsche Zuständigkeit, fehlende "
    "Bestimmtheit, unklare Rechtsbehelfsbelehrung)?\n"
    "- Ist der Bescheid formell angreifbar?\n"
    "- Welche Verfahrensfehler sind nur möglich, aber nicht sicher "
    "feststellbar?\n\n"
    "**5. Risikobewertung:**\n"
    "- Welche rechtlichen Risiken bestehen für den Bürger?\n"
    "- Wie hoch ist das Risiko einer negativen Entscheidung?\n"
    "- Wie stark ist die Verteidigungsposition insgesamt?\n"
    "- Welche fehlenden Tatsachen oder Unterlagen könnten entscheidend sein?\n\n"
    "Erstelle für JEDEN Claim eine Bewertung als JSON-Objekt:\n"
    "{\n"
    '  "reviews": [\n'
    "    {\n"
    '      "claim_index": 0,\n'
    '      "defense_argument": "Argument aus Verteidigersicht",\n'
    '      "authority_argument": "Argument der Behörde",\n'
    '      "judicial_assessment": "Einschätzung des Gerichts",\n'
    '      "procedural_issues": "Verfahrensfehler oder -bedenken",\n'
    '      "risk_level": "niedrig" | "mittel" | "hoch",\n'
    '      "recommended_strategy": "Empfohlene Strategie"\n'
    "    }\n"
    "  ],\n"
    '  "overall_assessment": {\n'
    '    "summary": "Gesamtbewertung aller Claims aus adversarialer Sicht",\n'
    '    "key_risks": [\n'
    '      "Risiko 1 – Beschreibung",\n'
    '      "Risiko 2 – Beschreibung",\n'
    '      "Risiko 3 – Beschreibung"\n'
    "    ],\n"
    '    "recommended_next_steps": [\n'
    '      "Schritt 1 – Beschreibung",\n'
    '      "Schritt 2 – Beschreibung",\n'
    '      "Schritt 3 – Beschreibung"\n'
    "    ],\n"
    '    "confidence_in_defense": 0.65,\n'
    '    "procedural_errors_found": [\n'
    '      "Formeller Fehler 1",\n'
    '      "Formeller Fehler 2"\n'
    "    ]\n"
    "  }\n"
    "}\n\n"
    "Wichtige Regeln:\n"
    "- Alle Texte auf Deutsch verfassen.\n"
    "- Keine Tatsachen, Paragraphen oder Aktenzeichen erfinden.\n"
    "- Nur auf Grundlage der bereitgestellten Dokumente und Chunks "
    "argumentieren.\n"
    "- Wenn ein Claim durch die bereitgestellten Chunks nicht ausreichend "
    "gestützt wird, sage das ausdrücklich und bewerte das Risiko entsprechend "
    "höher.\n"
    "- Die Behördenperspektive muss ernsthaft und stark formuliert werden, "
    "auch wenn dies der Nutzerposition schadet.\n"
    "- Die richterliche Perspektive muss neutral sein und darf keine "
    "Erfolgsaussicht übertreiben.\n"
    "- Die Risikobewertung soll ehrlich sein – eine schwache "
    "Verteidigungsposition eingestehen, wenn die Fakten dagegen "
    "sprechen.\n"
    "- Gib 3-5 key_risks und 3-5 recommended_next_steps an.\n"
    "- confidence_in_defense: 0.0 (sehr schwach) bis 1.0 (sehr stark).\n"
    "- procedural_errors_found kann auch leer sein, wenn keine "
    "Verfahrensfehler erkennbar sind.\n"
    "- Mögliche, aber nicht sicher feststellbare Verfahrensfehler gehören in "
    "procedural_issues oder key_risks, nicht zwingend in "
    "procedural_errors_found.\n"
    "- Jeder review-Eintrag MUSS einen claim_index haben, der auf den "
    "ursprünglichen Claim verweist.\n"
    "- Verwende für risk_level ausschließlich einen der Werte: "
    '"niedrig", "mittel" oder "hoch".\n\n'
    "Gib ausschließlich gültiges JSON zurück. Kein Prosatext. Keine "
    "Markdown-Formatierung."
)

async def adversarial_review(
    normalized_text: str,
    issues: list[str],
    questions: list[str],
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
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

    logger.info(
        "adversarial_review: starting (input=%d chars, %d issues, "
        "%d questions, %d claims, %d chunks, model=%s, timeout=%.1fs)",
        len(normalized_text),
        len(issues),
        len(questions),
        len(claims),
        len(chunks),
        final_model,
        final_timeout,
    )
    client = _get_client()

    # Build chunk context (same pattern as generate_grounded_answer).
    chunk_lines: list[str] = []
    total_chunk_chars = 0
    for c in chunks[:max_chunks_for_final]:
        chunk_id = c.get("chunk_id", "?")
        hierarchy = c.get("hierarchy_path", "?")
        text = c.get("text_content", c.get("text", ""))
        line = (
            f"CHUNK [{chunk_id}] {hierarchy}:\n"
            f"{text}\n"
        )
        if total_chunk_chars + len(line) > max_chunk_context_chars:
            remaining = max_chunk_context_chars - total_chunk_chars
            if remaining > 100:
                line = line[:remaining] + "..."
            else:
                break
        chunk_lines.append(line)
        total_chunk_chars += len(line)
    chunk_context = "\n---\n".join(chunk_lines)

    # Build claim text.
    claims_text = "\n".join(
        f"{i}. [{c.get('claim_type', '?')}] (confidence={c.get('confidence_score', 0.0):.2f}) "
        f"{c.get('claim_text', '')}"
        for i, c in enumerate(claims)
    )

    # Build user prompt.
    user_parts: list[str] = []

    user_parts.append("## DOKUMENT\n")
    user_parts.append(trim_text(normalized_text, 5000))

    if issues:
        user_parts.append("\n\n## IDENTIFIZIERTE THEMEN\n")
        user_parts.append("\n".join(f"- {i}" for i in issues))

    if questions:
        user_parts.append("\n\n## RECHTSFRAGEN\n")
        user_parts.append("\n".join(f"- {q}" for q in questions))

    user_parts.append("\n\n## ZU PRÜFENDE CLAIMS\n")
    user_parts.append(claims_text)

    user_parts.append("\n\n## RECHTSQUELLEN (CHUNKS)\n")
    user_parts.append(chunk_context)

    user_content = "\n".join(user_parts)

    messages = [
        {"role": "system", "content": _ADVERSARIAL_REVIEW_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    logger.info(
        "adversarial_review: prompt ~%d chars (user=%d, system=%d), %d chunks",
        len(user_content) + len(_ADVERSARIAL_REVIEW_SYSTEM) + len(_STRICT_SUFFIX),
        len(user_content),
        len(_ADVERSARIAL_REVIEW_SYSTEM) + len(_STRICT_SUFFIX),
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
        result = _parse_json_response(raw, context="adversarial review")
    except JSONParseError:
        logger.warning(
            "JSON parse error in adversarial_review, retrying with stricter prompt"
        )
        messages_minimal = [
            {"role": "system", "content": _ADVERSARIAL_REVIEW_SYSTEM + _STRICT_SUFFIX},
            {"role": "user", "content": user_content[:4000]},
        ]
        raw2 = await client.chat_completion(
            messages_minimal,
            temperature=0.0,
            model=final_model,
            timeout=final_timeout,
            max_retries=1,
        )
        result = _parse_json_response(raw2, context="adversarial review (retry)")

    # --- Validate reviews ---
    reviews = result.get("reviews", [])
    if not isinstance(reviews, list):
        logger.warning(
            "adversarial_review: unexpected 'reviews' type: %s", type(reviews)
        )
        reviews = []

    validated_reviews: list[dict[str, Any]] = []
    valid_risk_levels = {"niedrig", "mittel", "hoch"}
    for item in reviews:
        if not isinstance(item, dict):
            continue
        rl = item.get("risk_level", "mittel")
        if rl not in valid_risk_levels:
            rl = "mittel"
        validated_reviews.append({
            "claim_index": int(item.get("claim_index", -1)),
            "defense_argument": str(item.get("defense_argument", "")).strip(),
            "authority_argument": str(item.get("authority_argument", "")).strip(),
            "judicial_assessment": str(item.get("judicial_assessment", "")).strip(),
            "procedural_issues": str(item.get("procedural_issues", "")).strip(),
            "risk_level": rl,
            "recommended_strategy": str(item.get("recommended_strategy", "")).strip(),
        })

    # --- Validate overall assessment ---
    raw_overall = result.get("overall_assessment", {})
    if not isinstance(raw_overall, dict):
        logger.warning(
            "adversarial_review: unexpected 'overall_assessment' type: %s",
            type(raw_overall),
        )
        raw_overall = {}

    key_risks = raw_overall.get("key_risks", [])
    if not isinstance(key_risks, list):
        key_risks = []

    recommended_next_steps = raw_overall.get("recommended_next_steps", [])
    if not isinstance(recommended_next_steps, list):
        recommended_next_steps = []

    procedural_errors_found = raw_overall.get("procedural_errors_found", [])
    if not isinstance(procedural_errors_found, list):
        procedural_errors_found = []

    confidence_in_defense = raw_overall.get("confidence_in_defense", 0.5)
    try:
        confidence_in_defense = float(confidence_in_defense)
    except (TypeError, ValueError):
        confidence_in_defense = 0.5
    confidence_in_defense = max(0.0, min(1.0, confidence_in_defense))

    overall_assessment = {
        "summary": str(raw_overall.get("summary", "")).strip(),
        "key_risks": [str(r).strip() for r in key_risks if str(r).strip()],
        "recommended_next_steps": [
            str(s).strip() for s in recommended_next_steps if str(s).strip()
        ],
        "confidence_in_defense": confidence_in_defense,
        "procedural_errors_found": [
            str(e).strip() for e in procedural_errors_found if str(e).strip()
        ],
    }

    logger.info(
        "adversarial_review: complete (model=%s, %d reviews)",
        final_model,
        len(validated_reviews),
    )
    return {"reviews": validated_reviews, "overall_assessment": overall_assessment}

# ---------------------------------------------------------------------------
# Combined Stages 5+6+7+8 — Grounded Answer Generation (WP-007)
# ---------------------------------------------------------------------------

_GROUNDED_ANSWER_SYSTEM = (
    "Du bist ein sorgfältiger Experte für deutsches Sozialrecht "
    "(insbesondere SGB II, SGB X, SGB XII). Du arbeitest evidenzgebunden und "
    "darfst keine Rechtsquellen, Paragraphen, Fristen, Aktenzeichen oder "
    "Tatsachen erfinden.\n\n"
    "Dir werden vorgelegt:\n"
    "1. Der normalisierte Text eines behördlichen Dokuments.\n"
    "2. Eine Liste identifizierter rechtlicher Themen.\n"
    "3. Eine Liste konkreter Rechtsfragen.\n"
    "4. Eine Sammlung von Rechtsprechungs- und Gesetzes-Chunks aus einer "
    "Vektordatenbank.\n\n"
    "Arbeitsprinzip:\n"
    "- Tatsachen dürfen nur aus dem Dokument übernommen werden.\n"
    "- Rechtliche Aussagen dürfen nur auf den bereitgestellten Chunks "
    "beruhen.\n"
    "- Empfehlungen dürfen nur aus belegten Tatsachen und belegten "
    "rechtlichen Bewertungen folgen.\n"
    "- Wenn eine Frage mit den bereitgestellten Quellen nicht sicher "
    "beantwortet werden kann, musst du diese Unsicherheit ausdrücklich "
    "benennen.\n\n"
    "Deine Aufgabe:\n\n"
    "A) **Claims erstellen:** Für jede Rechtsfrage 1–3 rechtliche Aussagen "
    "(Claims) formulieren. Jeder Claim MUSS:\n"
    '  - "claim_text" (str): die Aussage selbst, auf Deutsch\n'
    '  - "confidence_score" (float 0.0–1.0): deine Sicherheit auf Grundlage '
    "der bereitgestellten Evidenz\n"
    '  - "claim_type" (str): "fact" | "interpretation" | "recommendation"\n'
    '  - "question" (str): die Rechtsfrage, auf die sich der Claim bezieht\n'
    '  - "evidence_chunk_id" (str): die ID des Chunks, aus dem die Evidenz stammt\n'
    '  - "evidence_hierarchy" (str): die Hierarchie der Rechtsquelle '
    '(z. B. "SGB II > § 31 > Abs. 1")\n'
    '  - "evidence_quote" (str): das EXAKTE wörtliche Zitat aus dem Chunk\n\n'
    "WICHTIGE REGELN FÜR CLAIMS:\n"
    "- Verwende NUR die bereitgestellten Chunks als Rechtsquellen.\n"
    "- Kopiere evidence_quote WÖRTLICH aus dem Chunk-Text "
    "(copy-paste, keine Paraphrasierung, keine Glättung).\n"
    "- evidence_quote muss die konkrete rechtliche Aussage stützen; ein nur "
    "thematisch ähnlicher Chunk reicht nicht aus.\n"
    "- evidence_chunk_id MUSS exakt die chunk_id aus den bereitgestellten "
    "Chunks sein.\n"
    "- evidence_hierarchy MUSS zur angegebenen Quelle passen, soweit sie im "
    "Chunk angegeben ist.\n"
    "- Wenn die Evidenz nicht ausreicht, setze confidence_score niedrig "
    "(≤ 0.4) und sage im claim_text ausdrücklich, dass die Frage mit den "
    "bereitgestellten Quellen nicht sicher beantwortet werden kann.\n"
    "- Wenn gar kein geeigneter Chunk vorhanden ist, erstelle keinen "
    "substantiven rechtlichen Claim. Formuliere stattdessen nur eine "
    "vorsichtige Aussage zur fehlenden Belegbarkeit mit niedrigem "
    "confidence_score und verwende leere Strings für evidence_chunk_id, "
    "evidence_hierarchy und evidence_quote.\n"
    "- Erfinde KEINE Paragraphen, Gerichtsentscheidungen, Aktenzeichen, "
    "Fristen oder Rechtsfolgen.\n"
    "- Übernimm keine Tatsache aus dem Dokument als sicher, wenn sie im "
    "Dokument nur behauptet, unklar oder streitig erscheint; kennzeichne sie "
    "dann vorsichtig.\n"
    "- Unterscheide sauber zwischen Tatsachen aus dem Dokument, rechtlicher "
    "Auslegung und Handlungsempfehlung.\n"
    "- Empfehlungen dürfen nur aus zuvor belegten rechtlichen Bewertungen "
    "folgen.\n"
    "- Eine hohe confidence_score ist nur zulässig, wenn Dokumenttatsachen "
    "und Rechtsquelle klar zusammenpassen.\n\n"
    "B) **Abschnitte generieren:** Erstelle die folgenden 7 Abschnitte "
    "auf Deutsch:\n"
    '  - "sachverhalt": Zusammenfassung des Sachverhalts\n'
    '  - "rechtliche_wuerdigung": Rechtliche Würdigung mit Zitaten der '
    "einschlägigen Vorschriften\n"
    '  - "ergebnis": Ergebnis / Fazit\n'
    '  - "handlungsempfehlung": Konkrete Handlungsempfehlungen\n'
    '  - "entwurf": Entwurf eines Antwortschreibens\n'
    '  - "unsicherheiten": Verbleibende Unsicherheiten oder fehlende '
    "Informationen\n"
    '  - "adversarial_pruefung": Vorläufige adversariale Einschätzung '
    "(wird später durch die detaillierte Rechtsprüfung ersetzt)\n\n"
    "WICHTIGE REGELN FÜR DIE ABSCHNITTE:\n"
    "- Schreibe verständlich für eine betroffene Person, aber rechtlich "
    "präzise.\n"
    "- Die rechtliche_wuerdigung muss auf den Claims und deren "
    "evidence_quote beruhen. Keine zusätzlichen Rechtsquellen einführen.\n"
    "- Mache deutlich, wenn eine Einschätzung unsicher ist oder weitere "
    "Informationen fehlen.\n"
    "- Nenne keine konkreten Fristen, wenn sie nicht aus dem Dokument oder "
    "den bereitgestellten Quellen hervorgehen.\n"
    "- Wenn eine Frist im Dokument genannt ist, darfst du sie wiedergeben, "
    "musst aber kenntlich machen, dass sie aus dem Dokument stammt.\n"
    "- Der Entwurf soll höflich, sachlich und behördentauglich sein.\n"
    "- Der Entwurf darf keine falschen Tatsachen behaupten; bei fehlenden "
    "Informationen nutze Platzhalter wie [Datum], [Aktenzeichen] oder "
    "[konkrete Begründung ergänzen].\n"
    "- Der Entwurf darf keine rechtlichen Behauptungen enthalten, die nicht "
    "durch die Claims gestützt sind.\n"
    "- Wenn die Rechtslage unsicher ist, formuliere den Entwurf vorsichtig "
    "als Prüfungs- oder Begründungsverlangen statt als sichere "
    "Rechtsbehauptung.\n"
    "- Stelle nicht dar, dass dies verbindliche anwaltliche Beratung sei.\n\n"
    "Gib NUR ein JSON-Objekt zurück:\n"
    "{\n"
    '  "claims": [\n'
    "    {\n"
    '      "claim_text": "...",\n'
    '      "confidence_score": 0.82,\n'
    '      "claim_type": "interpretation",\n'
    '      "question": "...",\n'
    '      "evidence_chunk_id": "...",\n'
    '      "evidence_hierarchy": "SGB II > § 31 > Abs. 1",\n'
    '      "evidence_quote": "..."\n'
    "    }\n"
    "  ],\n"
    '  "sections": {\n'
    '    "sachverhalt": "...",\n'
    '    "rechtliche_wuerdigung": "...",\n'
    '    "ergebnis": "...",\n'
    '    "handlungsempfehlung": "...",\n'
    '    "entwurf": "...",\n'
    '    "unsicherheiten": "...",\n'
    '    "adversarial_pruefung": "..."\n'
    "  }\n"
    "}\n\n"
    "Kein Prosatext außerhalb des JSON. Keine Markdown-Fences. Keine "
    "zusätzlichen Schlüssel."
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
    max_chunks_for_final = s.MAX_CHUNKS_FOR_FINAL
    max_chunk_context_chars = s.MAX_CHUNK_CONTEXT_CHARS
    max_final_input_chars = s.MAX_FINAL_INPUT_CHARS

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
    client = _get_client()

    # Build chunk context (cap to manageable size, using top N by retrieval score).
    chunk_lines: list[str] = []
    total_chunk_chars = 0
    for c in chunks[:max_chunks_for_final]:
        chunk_id = c.get("chunk_id", "?")
        hierarchy = c.get("hierarchy_path", "?")
        text = c.get("text_content", "")
        line = (
            f"CHUNK [{chunk_id}] {hierarchy}:\n"
            f"{text}\n"
        )
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
        {"role": "system", "content": _GROUNDED_ANSWER_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    prompt_chars = len(_GROUNDED_ANSWER_SYSTEM) + len(_STRICT_SUFFIX) + len(user_content)
    prompt_tokens = estimate_tokens(
        _GROUNDED_ANSWER_SYSTEM + _STRICT_SUFFIX + user_content
    )
    logger.info(
        "generate_grounded_answer: prompt ~%d chars (user=%d, system=%d), ~%d tokens, "
        "%d chunks included",
        prompt_chars,
        len(user_content),
        len(_GROUNDED_ANSWER_SYSTEM) + len(_STRICT_SUFFIX),
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
            {"role": "system", "content": _GROUNDED_ANSWER_SYSTEM + _STRICT_SUFFIX},
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
        "adversarial_pruefung",
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


async def generate_grounded_answer_stream(
    normalized_text: str,
    issues: list[str],
    questions: list[str],
    chunks: list[dict[str, Any]],
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
    client = _get_client()

    # Build chunk context (same logic as generate_grounded_answer).
    chunk_lines: list[str] = []
    total_chunk_chars = 0
    for c in chunks[:max_chunks_for_final]:
        chunk_id = c.get("chunk_id", "?")
        hierarchy = c.get("hierarchy_path", "?")
        text = c.get("text_content", "")
        line = (
            f"CHUNK [{chunk_id}] {hierarchy}:\n"
            f"{text}\n"
        )
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
        {"role": "system", "content": _GROUNDED_ANSWER_SYSTEM + _STRICT_SUFFIX},
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
        result = await generate_grounded_answer(
            normalized_text, issues, questions, chunks,
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

_CLAIM_CONSTRUCTION_SYSTEM = (
    "Du bist ein sorgfältiger Experte für deutsches Sozialrecht "
    "(insbesondere SGB II, SGB X, SGB XII). Du erhältst eine Liste konkreter "
    "Rechtsfragen und eine Sammlung von Rechtsquellen-Chunks aus dem Corpus.\n\n"
    "Aufgabe: Konstruiere für jede Frage 1-3 rechtliche Claims. Ein Claim ist "
    "eine einzelne prüfbare Aussage, die eine Rechtsfrage ganz oder teilweise "
    "beantwortet.\n\n"
    "Each claim must have:\n"
    '- "claim_text" (str): the assertion itself\n'
    '- "confidence_score" (float between 0.0 and 1.0)\n'
    '- "claim_type" (str): one of "fact", "interpretation", "recommendation"\n'
    '- "question" (str): the question this claim addresses\n\n'
    "Wichtige Regeln:\n"
    "- Schreibe alle claim_text-Werte auf Deutsch.\n"
    "- Stütze Claims so weit wie möglich auf die bereitgestellten Chunks.\n"
    "- Erfinde keine Paragraphen, Aktenzeichen, Gerichtsentscheidungen, "
    "Fristen oder Tatsachen.\n"
    "- Wenn die Chunks eine Frage nicht ausreichend beantworten, formuliere "
    "einen vorsichtigen Claim mit niedrigem confidence_score (≤ 0.4).\n"
    "- Verwende hohe confidence_score-Werte nur, wenn die bereitgestellten "
    "Quellen die Aussage klar tragen.\n"
    "- Trenne Tatsachenbehauptungen, rechtliche Auslegung und Empfehlungen.\n"
    "- Empfehlungen dürfen nur aus rechtlich gestützten Claims folgen.\n\n"
    "Return a JSON array of claim objects:\n"
    '[ { "claim_text": "...", "confidence_score": 0.8, "claim_type": "fact", '
    '"question": "..." }, ... ]\n\n'
    "Gib ausschließlich gültiges JSON zurück. Kein Prosatext. Keine "
    "Markdown-Formatierung."
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
    from app.core.config import settings as _s

    chunk_context = "\n\n---\n\n".join(
        f"[{c.get('hierarchy_path', '?')}]: {c.get('text_content', '')}"
        for c in chunks[:_s.MAX_CHUNKS_FOR_FINAL]
    )

    user_content = (
        "Questions:\n"
        + "\n".join(f"- {q}" for q in questions[:5])
        + "\n\nRelevant legal chunks:\n"
        + chunk_context[:_s.MAX_CHUNK_CONTEXT_CHARS]
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
                {"role": "user", "content": user_content[:_s.MAX_CHUNK_CONTEXT_CHARS // 2]},
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
    "Du bist ein strenger Qualitätsprüfer für eine evidenzgebundene "
    "Reasoning-Engine im deutschen Sozialrecht. Du erhältst Claims und die "
    "Quellen-Chunks, auf denen sie beruhen sollen.\n\n"
    "Aufgabe: Prüfe für jeden Claim, ob die angegebenen Quellen die Aussage "
    "wirklich tragen.\n\n"
    "Für jeden Claim:\n"
    "- Prüfe, ob der Quellentext die Aussage ausdrücklich oder mit hoher "
    "rechtlicher Plausibilität unterstützt.\n"
    "- Prüfe, ob der Claim zu weit geht, unzulässig verallgemeinert oder "
    "Tatsachen / Paragraphen / Rechtsfolgen ergänzt, die nicht belegt sind.\n"
    "- Wenn der Claim nur teilweise unterstützt wird, senke den "
    "confidence_score deutlich und erkläre kurz warum.\n"
    "- Wenn der Claim nicht unterstützt wird, setze verified auf false und "
    "senke den confidence_score auf höchstens 0.4.\n"
    "- Erfinde keine neuen Quellen, Paragraphen, Tatsachen oder "
    "Begründungen.\n"
    "- Ändere den claim_text nicht inhaltlich; prüfe ihn nur.\n\n"
    "Each output item must have:\n"
    '- "claim_text" (str): original claim\n'
    '- "confidence_score" (float 0.0-1.0): adjusted confidence\n'
    '- "claim_type" (str): one of "fact", "interpretation", "recommendation"\n'
    '- "verified" (bool): whether the source supports the claim\n'
    '- "reasoning" (str): brief explanation in German\n\n'
    "Return a JSON array:\n"
    '[ { "claim_text": "...", "confidence_score": 0.7, "claim_type": "fact", '
    '"verified": true, "reasoning": "..." }, ... ]\n\n'
    "Gib ausschließlich gültiges JSON zurück. Kein Prosatext. Keine "
    "Markdown-Formatierung. Keine zusätzlichen Schlüssel."
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
    from app.core.config import settings as _s

    chunk_text = "\n\n---\n\n".join(
        f"[{c.get('hierarchy_path', '?')}]: {c.get('text_content', '')}"
        for c in chunks[:_s.MAX_CHUNKS_FOR_FINAL]
    )

    claims_text = "\n".join(
        f"{i + 1}. [{c.get('claim_type', '?')}] {c.get('claim_text', '')}"
        for i, c in enumerate(claims)
    )

    user_content = f"Claims to verify:\n{claims_text}\n\nSource chunks:\n{chunk_text[:_s.MAX_CHUNK_CONTEXT_CHARS]}"

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

_OUTPUT_SYSTEM = (
    "Du bist ein sorgfältiger Experte für deutsches Sozialrecht. Dir wird "
    "eine Liste verifizierter Claims übergeben. Erstelle daraus eine "
    "strukturierte rechtliche Einschätzung in genau 6 Abschnitten.\n\n"
    "Section keys (in English, as JSON object keys) must be:\n"
    '- "sachverhalt" (str): summary of the facts\n'
    '- "rechtliche_wuerdigung" (str): legal assessment citing statutes\n'
    '- "ergebnis" (str): the result / conclusion\n'
    '- "handlungsempfehlung" (str): actionable recommendations\n'
    '- "entwurf" (str): a draft letter / response\n'
    '- "unsicherheiten" (str): uncertainties or missing information\n\n'
    "Wichtige Regeln:\n"
    "- Schreibe alle Abschnittsinhalte auf Deutsch.\n"
    "- Verwende nur die verifizierten Claims als Grundlage.\n"
    "- Stelle unsichere oder nicht belegte Punkte ausdrücklich als unsicher "
    "dar.\n"
    "- Erfinde keine Paragraphen, Aktenzeichen, Fristen, Tatsachen oder "
    "Rechtsfolgen.\n"
    "- Zitiere Vorschriften nur, wenn sie in den Claims belastbar enthalten "
    "sind.\n"
    "- Cite statutes in the format '§ X Abs. Y Satz Z', soweit diese Angaben "
    "vorliegen.\n"
    "- Die rechtliche Würdigung soll verständlich, aber nicht vereinfachend "
    "verfälschend sein.\n"
    "- Die Handlungsempfehlung soll konkrete nächste Schritte enthalten, "
    "aber keine verbindliche anwaltliche Beratung behaupten.\n"
    "- Der Entwurf soll höflich, sachlich und behördentauglich sein. Wenn "
    "Informationen fehlen, nutze Platzhalter wie [Datum], [Aktenzeichen], "
    "[Name] oder [konkrete Begründung ergänzen].\n\n"
    "Return a single JSON object:\n"
    '{ "sachverhalt": "...", "rechtliche_wuerdigung": "...", "ergebnis": "...", '
    '"handlungsempfehlung": "...", "entwurf": "...", "unsicherheiten": "..." }\n\n'
    "Gib ausschließlich gültiges JSON zurück. Kein Prosatext. Keine "
    "Markdown-Formatierung. Keine zusätzlichen Schlüssel."
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
    from app.core.config import settings as _s

    claims_text = "\n".join(
        f"- [{c.get('claim_type', '?')}] (verified={c.get('verified', False)}, "
        f"confidence={c.get('confidence_score', 0.0):.2f}) {c.get('claim_text', '')}"
        for c in verified_claims
    )

    user_content = f"Verified claims:\n{claims_text[:_s.MAX_FINAL_INPUT_CHARS]}"

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
                {"role": "user", "content": user_content[:_s.MAX_FINAL_INPUT_CHARS // 2]},
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
