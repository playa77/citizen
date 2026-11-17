"""Read-only MCP server over modules, corpus and deadline catalog (WP-116).

A deliberately small, dependency-free implementation of the Model Context
Protocol's stdio transport: newline-delimited JSON-RPC 2.0 on stdin/stdout,
methods ``initialize``, ``notifications/initialized``, ``ping``,
``tools/list`` and ``tools/call``. No resources, prompts, sampling or
server-initiated requests — the surface is a catalog, not an agent.

Tools (all read-only; nothing is written, no LLM is called):

``list_modules``     installed modules: id, version, tier, enabled, origin, title
``get_module``       public manifest parts, deadline catalog, document types,
                     dossier checklist, errata of one module
``deadline_catalog`` deadline specs of every enabled module (or one)
``corpus_status``    corpus source catalog with chunk counts (database)
``get_statute``      text of one § of an ingested law (database)
``check_citations``  parse citations in a text, optionally verify them

Purpose posture (D-020/D-035): the server exposes reference data for
citizen-side self-help tools; it analyses no documents and gives no advice.
Every tool result is module data or statute text, not AI-generated content
(no Art. 50 disclosure applies). The database-backed tools degrade to an
``isError`` result when the database is unreachable.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-116: initial version.

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_NAME = "citizen"
INSTRUCTIONS = (
    "Read-only reference data of Citizen, a citizen-side preparation assistant for German "
    "legal matters in the person's own case: installed legal-area modules, their deadline "
    "catalogs (deadlines are computed only by Citizen's deterministic Fristen core), corpus "
    "readiness, statute text, and citation checks. This is legal information, not legal "
    "advice; it does not replace an advice centre or a lawyer."
)

# JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ToolError(Exception):
    """A tool failed in an expected way (reported as ``isError`` content)."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[Any]]

    def listing(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
        }


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _manifest(module_id: str) -> Any:
    from app.modules.runtime import module_registry

    manifest = module_registry().get(module_id)
    if manifest is None:
        raise ToolError(f"MODULE_UNKNOWN: no installed module {module_id!r}")
    return manifest


def _summary(manifest: Any) -> dict[str, Any]:
    from app.modules.runtime import module_registry

    registry = module_registry()
    return {
        "id": manifest.id,
        "version": manifest.version,
        "tier": manifest.tier,
        "enabled": registry.is_enabled(manifest.id),
        "is_default": manifest.id == registry.default_module,
        "origin": manifest.origin,
        "title": dict(manifest.title),
    }


async def _list_modules(_: dict[str, Any]) -> Any:
    from app.modules.runtime import module_registry

    registry = module_registry()
    return {
        "default_module": registry.default_module,
        "modules": [_summary(registry.modules[m]) for m in sorted(registry.modules)],
    }


async def _get_module(args: dict[str, Any]) -> Any:
    from app.dossier.module_content import public_dossier_checklist
    from app.modules.catalog import (
        document_types,
        module_deadlines,
        public_compliance,
        public_scope,
    )
    from app.modules.errata import module_errata

    manifest = _manifest(str(args["module_id"]))
    return {
        **_summary(manifest),
        "core_api": manifest.core_api,
        "scope": public_scope(manifest),
        "legacy_aliases": list(manifest.legacy_aliases),
        "deadlines": module_deadlines(manifest.id),
        "document_types": document_types(manifest),
        "dossier_checklist": public_dossier_checklist(manifest.id),
        "compliance": public_compliance(manifest),
        "errata": [e.as_dict() for e in module_errata(manifest)],
    }


async def _deadline_catalog(args: dict[str, Any]) -> Any:
    from app.modules.catalog import module_deadlines
    from app.modules.runtime import module_registry

    registry = module_registry()
    if args.get("module_id"):
        ids = [_manifest(str(args["module_id"])).id]
    else:
        ids = sorted(registry.enabled)
    return {
        "note": (
            "Deadline specs only. Concrete deadlines need the letter's date and the "
            "Fristen core (Citizen /api/v1); never compute them from this catalog by hand."
        ),
        "modules": [
            {
                "module_id": mid,
                "version": registry.modules[mid].version,
                "deadlines": module_deadlines(mid),
            }
            for mid in ids
        ],
    }


async def _corpus_status(_: dict[str, Any]) -> Any:
    from app.db.session import async_session_factory
    from app.services.corpus import CORPUS_SOURCE_METADATA
    from app.services.corpus_readiness import chunk_counts_by_source_type

    try:
        async with async_session_factory() as session:
            counts = await chunk_counts_by_source_type(session)
    except Exception as exc:
        raise ToolError(f"database unavailable: {type(exc).__name__}") from exc
    return {
        "sources": [
            {
                "source_type": key,
                "name": meta.get("name"),
                "origin": meta.get("source"),
                "chunk_count": counts.get(key, 0),
            }
            for key, meta in CORPUS_SOURCE_METADATA.items()
        ]
    }


async def _get_statute(args: dict[str, Any]) -> Any:
    from sqlalchemy import select

    from app.citations.laws import normalise_law
    from app.db.models import LegalChunk, LegalSource
    from app.db.session import async_session_factory

    law, source_type = normalise_law(str(args["law"]))
    if source_type is None:
        raise ToolError(f"law {law!r} is not in the corpus catalog")
    paragraph = str(args["paragraph"]).strip().lstrip("§").strip()
    marker = f"§ {paragraph}"
    try:
        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(LegalChunk.hierarchy_path, LegalChunk.text_content, LegalSource.title)
                    .join(LegalSource, LegalSource.id == LegalChunk.source_id)
                    .where(LegalSource.source_type == source_type)
                    .where(LegalSource.is_active.is_(True))
                    .where(
                        LegalChunk.hierarchy_path.like(f"%> {marker} >%")
                        | LegalChunk.hierarchy_path.like(f"%> {marker}")
                    )
                    .order_by(LegalChunk.hierarchy_path)
                    .limit(200)
                )
            ).all()
    except Exception as exc:
        raise ToolError(f"database unavailable: {type(exc).__name__}") from exc
    if not rows:
        raise ToolError(f"{marker} {law} is not in the ingested corpus")
    return {
        "law": law,
        "paragraph": paragraph,
        "source_title": rows[0].title,
        "units": [{"path": r.hierarchy_path, "text": r.text_content} for r in rows],
    }


async def _check_citations(args: dict[str, Any]) -> Any:
    from app.citations.parser import parse_citations

    text = str(args["text"])
    if len(text) > 200_000:
        raise ToolError("text longer than 200000 characters")
    citations = parse_citations(text)
    if not args.get("verify", True) or not citations:
        return {"citations": [c.as_dict() for c in citations], "corpus_checked": False}
    from app.citations.verify import verify_citations
    from app.db.session import async_session_factory

    try:
        async with async_session_factory() as session:
            return {
                "citations": await verify_citations(session, citations),
                "corpus_checked": True,
            }
    except Exception as exc:
        raise ToolError(f"database unavailable: {type(exc).__name__}") from exc


_MODULE_ID = {"type": "string", "pattern": "^[a-z][a-z0-9_]{1,63}$"}

TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            "list_modules",
            "List the installed legal-area modules with version, tier and enablement.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            _list_modules,
        ),
        Tool(
            "get_module",
            "Public facts of one module: scope, deadline catalog, document types, "
            "appointment checklist, published errata.",
            {
                "type": "object",
                "properties": {"module_id": _MODULE_ID},
                "required": ["module_id"],
                "additionalProperties": False,
            },
            _get_module,
        ),
        Tool(
            "deadline_catalog",
            "Deadline specifications (type, duration, legal basis) of the enabled modules "
            "or of one module. Specs, not computed dates.",
            {
                "type": "object",
                "properties": {"module_id": _MODULE_ID},
                "additionalProperties": False,
            },
            _deadline_catalog,
        ),
        Tool(
            "corpus_status",
            "Corpus source catalog with the number of ingested chunks per source.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            _corpus_status,
        ),
        Tool(
            "get_statute",
            "Text of one § of an ingested German law, e.g. law 'SGB X', paragraph '44'.",
            {
                "type": "object",
                "properties": {
                    "law": {"type": "string", "minLength": 2, "maxLength": 20},
                    "paragraph": {"type": "string", "pattern": "^§?\\s*\\d{1,4}[a-z]?$"},
                },
                "required": ["law", "paragraph"],
                "additionalProperties": False,
            },
            _get_statute,
        ),
        Tool(
            "check_citations",
            "Find § / Art. / ECLI / BSG docket citations in a text and check them against "
            "the ingested corpus.",
            {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1, "maxLength": 200000},
                    "verify": {"type": "boolean", "default": True},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            _check_citations,
        ),
    )
}


# ---------------------------------------------------------------------------
# JSON-RPC dispatch
# ---------------------------------------------------------------------------


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _result(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _validate_arguments(tool: Tool, arguments: Any) -> str | None:
    from jsonschema import Draft202012Validator

    errors = list(Draft202012Validator(tool.input_schema).iter_errors(arguments))
    if errors:
        return "; ".join(e.message for e in errors[:3])
    return None


async def _call_tool(params: dict[str, Any]) -> dict[str, Any]:
    tool = TOOLS[params["name"]]
    arguments = params.get("arguments") or {}
    try:
        data = await tool.handler(arguments)
    except ToolError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    text = json.dumps(data, ensure_ascii=False, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": json.loads(text),
        "isError": False,
    }


async def handle_message(message: Any) -> dict[str, Any] | None:
    """Handle one decoded JSON-RPC message; ``None`` for notifications."""
    from app.core.config import get_app_version

    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "not a JSON-RPC 2.0 message")
    method = message.get("method")
    msg_id = message.get("id")
    is_notification = "id" not in message
    if not isinstance(method, str):
        return None if is_notification else _error(msg_id, INVALID_REQUEST, "missing method")
    params = message.get("params") or {}
    if is_notification:
        return None  # notifications/initialized, cancelled, … need no answer
    try:
        if method == "initialize":
            requested = params.get("protocolVersion")
            version = (
                requested
                if requested in SUPPORTED_PROTOCOL_VERSIONS
                else SUPPORTED_PROTOCOL_VERSIONS[0]
            )
            return _result(
                msg_id,
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": get_app_version()},
                    "instructions": INSTRUCTIONS,
                },
            )
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": [t.listing() for t in TOOLS.values()]})
        if method == "tools/call":
            name = params.get("name")
            if name not in TOOLS:
                return _error(msg_id, INVALID_PARAMS, f"unknown tool {name!r}")
            problem = _validate_arguments(TOOLS[name], params.get("arguments") or {})
            if problem:
                return _error(msg_id, INVALID_PARAMS, f"invalid arguments: {problem}")
            return _result(msg_id, await _call_tool(params))
        return _error(msg_id, METHOD_NOT_FOUND, f"method {method!r} not supported")
    except Exception as exc:  # never crash the server on one bad request
        logger.exception("MCP request %r failed", method)
        return _error(msg_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")


async def handle_line(line: str) -> str | None:
    """One input line → one output line (or ``None``)."""
    line = line.strip()
    if not line:
        return None
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        return json.dumps(_error(None, PARSE_ERROR, f"parse error: {exc.msg}"))
    if isinstance(message, list):  # batch (2025-03-26 and older)
        replies = [r for r in [await handle_message(m) for m in message] if r is not None]
        return json.dumps(replies, ensure_ascii=False) if replies else None
    reply = await handle_message(message)
    return json.dumps(reply, ensure_ascii=False) if reply is not None else None


async def serve_stdio() -> None:
    """Serve until stdin closes. The registry is built (and validated) first."""
    from app.modules.runtime import module_registry

    registry = module_registry()
    logger.info(
        "Citizen MCP server ready: %d modules, enabled=%s",
        len(registry.modules),
        sorted(registry.enabled),
    )
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        reply = await handle_line(line)
        if reply is not None:
            sys.stdout.write(reply + "\n")
            sys.stdout.flush()


__all__ = ["TOOLS", "handle_line", "handle_message", "serve_stdio"]
