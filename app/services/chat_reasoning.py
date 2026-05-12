"""Chat reasoning service — iterative conversation with the reasoning engine.

For the **first message** in a conversation that has documents, this triggers the
full 7-stage pipeline and captures the structured output as the assistant's response.

For **subsequent messages**, it performs focused RAG retrieval against the legal
corpus using the conversation context, then generates a grounded response that
references any uploaded documents and retrieved legal sources.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from app.core.config import settings
from app.core.pipeline import PipelineState, run_pipeline
from app.core.router import OpenRouterClient
from app.services.retrieval import retrieve_chunks_combined
from app.utils.text import normalize_text
from app.utils.tokens import trim_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chat system prompt
# ---------------------------------------------------------------------------

_CHAT_SYSTEM_PROMPT = (
    "Du bist ein sachkundiger, sorgfältiger und präziser Assistent für "
    "deutsches Sozialrecht (insbesondere SGB II, SGB X, SGB XII). Du hilfst "
    "Bürgern, behördliche Schreiben von Jobcenter, Sozialamt und anderen "
    "Behörden zu verstehen und rechtlich einzuordnen.\n\n"
    "Deine Antworten sind:\n"
    "- sachlich, präzise und gut nachvollziehbar\n"
    "- auf Deutsch\n"
    "- kurz und verständlich (kein Juristenkauderwelsch, aber fachlich korrekt)\n"
    "- streng an den bereitgestellten Dokumenten, dem Gesprächskontext und "
    "den bereitgestellten Rechtsquellen orientiert\n"
    "- klar getrennt in: was aus dem Dokument hervorgeht, was rechtlich "
    "naheliegt und was unsicher bleibt\n"
    "- explizit vorsichtig, wenn Informationen oder Quellen nicht ausreichen\n\n"
    "Wichtige Regeln:\n"
    "- Erfinde keine Tatsachen, Paragraphen, Fristen, Aktenzeichen, "
    "Behördenhandlungen oder Rechtsfolgen.\n"
    "- Stelle Vermutungen niemals als feststehende Tatsachen dar.\n"
    "- Belege rechtliche Aussagen nach Möglichkeit mit den bereitgestellten "
    "Rechtsquellen.\n"
    "- Wenn die Quellenlage nicht ausreicht, sage das klar und deutlich.\n"
    "- Wenn eine Information für die rechtliche Bewertung fehlt, benenne "
    "konkret, welche Information fehlt.\n"
    "- Gib keine übertriebene Sicherheit vor; benenne Unsicherheiten offen.\n"
    "- Formuliere praxisnah und bürgerverständlich.\n"
    "- Wenn sinnvoll, nenne als nächsten Schritt, welche Unterlagen, Daten "
    "oder Angaben noch benötigt werden.\n\n"
    "Du zitierst Paragraphen im Format '§ 31 Abs. 1 Satz 2 SGB II'.\n"
    "Wenn du etwas nicht weißt oder die Quellen nicht ausreichen, sagst du "
    "das klar."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_first_message_pipeline(
    document_texts: list[str],
) -> AsyncGenerator[str, None]:
    """Execute the full 7-stage pipeline on combined document texts.

    Yields SSE-formatted events, then a final event with section keys
    and the full ``final_output`` dict.

    Parameters
    ----------
    document_texts :
        Normalized texts of all documents attached to the conversation.
        They are joined with double newlines.
    """
    combined_text = "\n\n".join(document_texts)
    state = PipelineState(input_text=combined_text)

    async for sse_event in run_pipeline(state):
        yield sse_event

    # Yield a compact final event matching the existing analyze endpoint format.
    final_payload = {
        "sections": list(state.final_output.keys()),
        "final_output": state.final_output,
    }
    yield f"data: {json.dumps(final_payload, ensure_ascii=False)}\n\n"


async def generate_chat_response(
    messages: list[dict[str, str]],
    *,
    document_texts: list[str] | None = None,
    conversation_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Generate a grounded chat response using RAG retrieval and conversation context.

    For each user message, this:
    1. Builds a search query from the message + document context.
    2. Retrieves relevant legal chunks from pgvector.
    3. Constructs a prompt with conversation history, documents, and chunks.
    4. Calls the LLM and streams the response character by character (SSE tokens).

    Parameters
    ----------
    messages :
        The full conversation history as OpenAI-style ``{role, content}`` dicts.
        The last message must be from the user.
    document_texts :
        Normalized texts of all attached documents (optional).
    conversation_id :
        Optional identifier for logging.
    """
    client = _get_client()
    last_message = messages[-1]["content"] if messages else ""

    # ── Build retrieval query ──────────────────────────────────────────
    search_query = last_message
    if document_texts:
        doc_snippet = "\n".join(
            trim_text(t, 800) for t in document_texts[:3]
        )
        search_query = f"Nutzerfrage: {last_message}\n\nDokumentauszug:\n{doc_snippet}"

    # ── Retrieve relevant legal chunks ─────────────────────────────────
    try:
        chunks = await retrieve_chunks_combined(
            issues=[],
            questions=[search_query],
            normalized_text=document_texts[0][:1200] if document_texts else last_message[:1200],
            client=client,
        )
    except Exception:
        logger.exception("Chat retrieval failed for conversation %s", conversation_id)
        chunks = []

    # ── Build the LLM prompt ───────────────────────────────────────────
    llm_messages: list[dict[str, str]] = []

    # System prompt with legal context
    system_parts = [_CHAT_SYSTEM_PROMPT]

    if document_texts:
        doc_context = _build_document_context(document_texts)
        system_parts.append(f"\n\nDem Nutzer liegen folgende Dokumente vor:\n{doc_context}")

    if chunks:
        chunk_context = _build_chunk_context(chunks)
        system_parts.append(f"\n\nRelevante Rechtsquellen aus dem lokalen Corpus:\n{chunk_context}")
        system_parts.append(
            "\n\nNutze diese Rechtsquellen, um die Fragen des Nutzers zu beantworten. "
            "Zitiere Paragraphen mit exaktem Wortlaut aus den Quellen. "
            "Wenn eine Frage nicht beantwortet werden kann, weise darauf hin."
        )

    llm_messages.append({"role": "system", "content": "\n".join(system_parts)})

    # Conversation history (trimmed to budget)
    history = _trim_history(messages, max_chars=settings.MAX_FINAL_INPUT_CHARS)
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
        logger.exception("Chat LLM call failed for conversation %s", conversation_id)
        error_payload = {
            "error": "chat_llm_failed",
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
        "conversation_id": conversation_id,
        "full_response": response_text,
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


def _build_document_context(document_texts: list[str]) -> str:
    """Build a concise document context for the system prompt."""
    parts: list[str] = []
    total_chars = 0
    max_doc_chars = settings.MAX_CHUNK_CONTEXT_CHARS // 2

    for i, text in enumerate(document_texts, 1):
        trimmed = trim_text(text, min(max_doc_chars, 3000))
        parts.append(f"Dokument {i}:\n{trimmed}")
        total_chars += len(trimmed)
        if total_chars >= max_doc_chars:
            break

    return "\n\n---\n\n".join(parts)


def _build_chunk_context(chunks: list[dict[str, Any]]) -> str:
    """Build a context string from retrieved legal chunks."""
    parts: list[str] = []
    max_chunks = min(len(chunks), settings.MAX_CHUNKS_FOR_FINAL)
    total_chars = 0

    for i, chunk in enumerate(chunks[:max_chunks]):
        hierarchy = chunk.get("hierarchy_path", chunk.get("hierarchy", "?"))
        text = chunk.get("text_content", chunk.get("text", ""))
        trimmed = trim_text(text, settings.MAX_CHUNK_CONTEXT_CHARS // max_chunks)
        parts.append(f"[Chunk {i + 1}] {hierarchy}\n{trimmed}")
        total_chars += len(trimmed)
        if total_chars >= settings.MAX_CHUNK_CONTEXT_CHARS:
            break

    return "\n\n---\n\n".join(parts)


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
