"""Source API router façade.

The route families were split into focused modules to keep this router small.
This module still owns the canonical ``router`` object and registers every
source-family module in the exact order of the original single file, so path
ordering and the committed OpenAPI contract are unchanged.
"""

from __future__ import annotations

from importlib import import_module

from .sources_common import router

for _module in (
    "sources_routes",
    "quality_routes",
    "statistics_routes",
    "changes_routes",
    "downloads_routes",
):
    import_module(f".{_module}", __package__)

__all__ = ["router"]
