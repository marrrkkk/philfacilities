"""Curated, read-only tool registration."""

from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from ..client import ApiClient
from . import facilities, reference

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def register_all(mcp: MCPServer, api: ApiClient) -> None:
    """Register every v1 tool. Kept in one place so tests can assert the surface."""

    facilities.register(mcp, api, READ_ONLY)
    reference.register(mcp, api, READ_ONLY)
