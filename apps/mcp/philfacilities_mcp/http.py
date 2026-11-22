"""Hosted Streamable HTTP entrypoint: ``uv run philfacilities-mcp-http``.

The transport is stateless: each JSON-RPC message is one POST with a JSON reply.
There are no sessions, no GET event stream and no server-initiated messages,
which is all a read-only data server needs and keeps it safe behind any load
balancer. Host and Origin are validated to prevent DNS rebinding.
"""

from __future__ import annotations

import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from .client import API_ROUTES, ApiClient
from .server import create_server
from .settings import McpSettings, get_settings


def create_http_app(
    *,
    settings: McpSettings | None = None,
    server: MCPServer | None = None,
    api: ApiClient | None = None,
    streamable_http_path: str = "/mcp",
):
    """Return a Starlette app with ``/mcp``, ``/healthz`` and ``/readyz``.

    ``streamable_http_path`` exists for mounting behind a parent app: set it to
    ``/`` and mount at ``/mcp`` so only MCP paths are captured and the parent's
    own 404 handling still applies to every other path.
    """

    settings = settings or get_settings()
    api = api or ApiClient(settings)
    server = server or create_server(settings=settings, api=api)

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
    )

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": "philfacilities-mcp",
                "version": server.version,
            }
        )

    @server.custom_route("/readyz", methods=["GET"], include_in_schema=False)
    async def readyz(_request: Request) -> JSONResponse:
        try:
            api_health = await api.get(API_ROUTES["healthz"])
        except Exception:
            return JSONResponse(
                {"status": "unavailable", "service": "philfacilities-mcp", "api": "unreachable"},
                status_code=503,
            )
        return JSONResponse(
            {
                "status": "ok" if api_health.get("database") == "ok" else "degraded",
                "service": "philfacilities-mcp",
                "api": api_health.get("status"),
                "database": api_health.get("database"),
            },
            status_code=200,
        )

    return server.streamable_http_app(
        streamable_http_path=streamable_http_path,
        stateless_http=True,
        json_response=True,
        transport_security=security,
        host=settings.mcp_host,
    )


def main() -> None:
    settings = get_settings()
    app = create_http_app(settings=settings)
    uvicorn.run(
        app,
        host=settings.mcp_host,
        port=settings.mcp_port,
        proxy_headers=True,
        forwarded_allow_ips=settings.mcp_forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()
