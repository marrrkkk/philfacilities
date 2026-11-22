"""Serve the read-only MCP adapter from the public API process.

Co-locating the adapter saves a second always-on dyno, but it does not change
its boundary: the MCP app still calls the public API over HTTP, holds no
database credentials, and has no independent rights logic. The API's CORS,
rate-limit, and request-context middleware continue to wrap it.

Starlette does not run a mounted child app's lifespan with the parent's, so
the API lifespan enters the MCP app's lifespan explicitly. The MCP session
manager also refuses to run twice on the same instance, so a fresh MCP app is
built for each lifespan and a small ASGI proxy keeps the mounted route pointing
at the current one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from philfacilities_mcp.http import create_http_app
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send


class MountedMCP:
    """ASGI proxy that forwards to the MCP app of the active lifespan."""

    def __init__(self) -> None:
        self.current: Starlette | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.current is None:
            response = JSONResponse(
                {"status": "unavailable", "service": "philfacilities-mcp"},
                status_code=503,
            )
            await response(scope, receive, send)
            return
        await self.current(scope, receive, send)


mounted_mcp = MountedMCP()


@asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """Build the MCP app, run its lifespan, and expose it to the mount."""
    # The parent mounts at /mcp, so the child's own route must be /.
    app = create_http_app(streamable_http_path="/")
    async with app.router.lifespan_context(app):
        mounted_mcp.current = app
        try:
            yield
        finally:
            mounted_mcp.current = None


def mount_mcp(app: FastAPI) -> None:
    """Mount MCP at /mcp only, so every other unmatched path keeps the API's
    normal 404 error envelope.
    """
    app.mount("/mcp", mounted_mcp, name="mcp")


__all__ = ["mcp_lifespan", "mount_mcp", "mounted_mcp"]
