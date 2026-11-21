"""Read-only Model Context Protocol server for PhilFacilities.

The server is a client of the public ``/v1`` API. It has no database access and
no independent copy of the publication gate, vocabularies, or response schemas.
"""

from __future__ import annotations

from .http import create_http_app
from .server import create_server

__all__ = ["create_http_app", "create_server"]
