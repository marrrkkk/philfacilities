"""MCP server construction shared by the stdio and HTTP entrypoints."""

from __future__ import annotations

from contextlib import asynccontextmanager

from mcp.server import MCPServer

from .client import ApiClient
from .instructions import INSTRUCTIONS
from .settings import McpSettings, get_settings
from .tools import register_all

SERVER_NAME = "philfacilities"
SERVER_VERSION = "0.1.0"


def create_server(
    *,
    settings: McpSettings | None = None,
    api: ApiClient | None = None,
) -> MCPServer:
    """Build a server whose tools can only reach the public API."""

    settings = settings or get_settings()
    api = api or ApiClient(settings)

    @asynccontextmanager
    async def lifespan(_server: MCPServer):
        async with api:
            yield

    server = MCPServer(
        name=SERVER_NAME,
        title="PhilFacilities",
        version=SERVER_VERSION,
        instructions=INSTRUCTIONS,
        lifespan=lifespan,
    )
    register_all(server, api)
    return server
