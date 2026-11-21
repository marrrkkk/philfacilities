"""Configuration for the MCP adapter.

All variables use the repository's ``PHILFACILITIES_`` prefix. The MCP server
never reads database settings: the public API is its only data source.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class McpSettings(BaseSettings):
    """Runtime settings loaded from the environment (or a local ``.env``)."""

    model_config = SettingsConfigDict(
        env_prefix="PHILFACILITIES_",
        env_file=".env",
        extra="ignore",
    )

    # Origin of the public API. In production this should be the internal
    # service address; in development it defaults to the local API.
    api_base_url: str = "http://127.0.0.1:8010"
    request_timeout_seconds: float = 15.0
    user_agent: str = "philfacilities-mcp/0.1.0"

    # Streamable HTTP listener. Hosted deployments must override the allowlists.
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8011
    mcp_allowed_hosts: str = "127.0.0.1:*,localhost:*"
    mcp_allowed_origins: str = ""
    # Only trust X-Forwarded-* from the local TLS reverse proxy by default.
    mcp_forwarded_allow_ips: str = "127.0.0.1"

    @property
    def allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.mcp_allowed_hosts.split(",") if item.strip()]

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.mcp_allowed_origins.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> McpSettings:
    return McpSettings()
