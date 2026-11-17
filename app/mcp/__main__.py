"""Entry point: ``python -m app.mcp`` (stdio MCP server, WP-116)."""

import asyncio
import logging
import sys

from app.mcp.server import serve_stdio

if __name__ == "__main__":
    # stdout carries the protocol; every log line goes to stderr.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    asyncio.run(serve_stdio())
