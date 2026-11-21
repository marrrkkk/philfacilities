"""The single outbound HTTP path from the MCP server to the public API.

Every tool goes through :class:`ApiClient`. It does not accept arbitrary URLs,
does not hold database credentials, and converts API failures into anticipated
MCP tool errors without leaking stack traces or request internals.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from .settings import McpSettings

# Tool paths are declared once here. Contract tests check them against the
# committed OpenAPI document so an API rename cannot silently break a tool.
API_ROUTES = {
    "healthz": "/healthz",
    "facilities": "/v1/facilities",
    "facility": "/v1/facilities/{facility_id}",
    "facility_sources": "/v1/facilities/{facility_id}/sources",
    "facility_assertions": "/v1/facilities/{facility_id}/assertions",
    "nearby": "/v1/facilities/nearby",
    "geographies": "/v1/geographies",
    "population": "/v1/population",
    "sources": "/v1/sources",
    "source": "/v1/sources/{source_id}",
    "coverage": "/v1/coverage",
    "taxonomy": "/v1/taxonomy",
}

DOWNLOAD_PATHS = {
    "facilities_csv": "/v1/downloads/facilities.csv",
    "facilities_parquet": "/v1/downloads/facilities.parquet",
    "schools_csv": "/v1/downloads/schools.csv",
    "health_facilities_csv": "/v1/downloads/health-facilities.csv",
}


class ApiResult(TypedDict):
    """One tool result: an API response passed through without reshaping.

    The API returns objects for some endpoints and arrays for others. A single
    envelope keeps every tool's output schema an object, which MCP hosts expect.
    """

    result: dict[str, Any] | list[Any]


def api_result(payload: dict[str, Any] | list[Any]) -> ApiResult:
    return {"result": payload}


def _path_pattern(path: str) -> re.Pattern[str]:
    """Turn an OpenAPI path template into a matcher for concrete requests."""

    return re.compile("^" + re.sub(r"\{[^}]+\}", r"[^/]+", path) + "$")


_ALLOWED_PATTERNS = tuple(
    _path_pattern(path) for path in {*API_ROUTES.values(), *DOWNLOAD_PATHS.values()}
)


def _query(params: dict[str, Any] | None) -> dict[str, Any]:
    """Drop unset arguments but keep meaningful false/zero values."""

    return {key: value for key, value in (params or {}).items() if value is not None}


class ApiClient:
    """A small wrapper over ``httpx.AsyncClient`` scoped to the API base URL."""

    def __init__(
        self,
        settings: McpSettings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=settings.request_timeout_seconds,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "application/json",
            },
        )

    async def __aenter__(self) -> ApiClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET a public API path and return its decoded JSON body."""

        if not any(pattern.fullmatch(path) for pattern in _ALLOWED_PATTERNS):
            raise ToolError("That API path is not exposed by this MCP server.")
        try:
            response = await self._http.get(path, params=_query(params))
        except httpx.TimeoutException:
            raise ToolError("The PhilFacilities API timed out. Try again.") from None
        except httpx.TransportError:
            raise ToolError("The PhilFacilities API is unavailable. Try again.") from None
        except ValueError:
            # A malformed parameter must not surface as a crash.
            raise ToolError("The PhilFacilities API rejected that request.") from None

        if response.status_code >= 400:
            raise ToolError(_error_message(response))
        try:
            return response.json()
        except ValueError:
            raise ToolError("The PhilFacilities API returned an unreadable response.") from None


def _error_message(response: httpx.Response) -> str:
    """Render the API error envelope as a short, model-readable message."""

    code = f"http_{response.status_code}"
    message = "The request was rejected by the PhilFacilities API."
    request_id = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        code = str(body.get("code") or code)
        message = str(body.get("message") or message)
        if body.get("request_id"):
            request_id = f" (request_id={body['request_id']})"
    return f"{code}: {message}{request_id}"
