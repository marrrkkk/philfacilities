"""Geography, population, source, coverage, taxonomy and download tools."""

from __future__ import annotations

from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..client import API_ROUTES, DOWNLOAD_PATHS, ApiClient, ApiResult, api_result

CODE = Annotated[str | None, Field(description="A PSGC code as a string; leading zeros matter.")]


def register(mcp: MCPServer, api: ApiClient, annotations: ToolAnnotations) -> None:
    @mcp.tool(
        name="search_geographies",
        title="Search PSGC geographies",
        description=(
            "Look up published PSGC administrative units by name, level or parent code. "
            "Use the returned codes in facility and population searches. The PSGC snapshot "
            "is published as a saved release, not a live PSA service."
        ),
        annotations=annotations,
    )
    async def search_geographies(
        q: Annotated[str | None, Field(description="Case-insensitive name search.")] = None,
        level: Annotated[
            str | None, Field(description="region, province, municipality or barangay.")
        ] = None,
        parent: Annotated[str | None, Field(description="Parent PSGC code.")] = None,
        release: Annotated[
            str | None, Field(description="PSGC release label; default is latest.")
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum results (default 100).", ge=1, le=500)
        ] = 100,
        offset: Annotated[int, Field(description="Offset for paging.", ge=0)] = 0,
    ) -> ApiResult:
        return api_result(
            await api.get(
                API_ROUTES["geographies"],
                {
                    "q": q,
                    "level": level,
                    "parent": parent,
                    "release": release,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )

    @mcp.tool(
        name="get_population",
        title="Get population observations",
        description=(
            "Published PSA 2024 Census population observations by PSGC code, geographic level "
            "or indicator. Counts are persons or households as labelled in the source and are "
            "not facility capacity. Values are saved OpenSTAT snapshots, not live PSA data. "
            "Join to facilities by PSGC code; never merge population into a facility record."
        ),
        annotations=annotations,
    )
    async def get_population(
        psgc: CODE = None,
        level: Annotated[
            str | None,
            Field(description="region, province_or_huc, municipality or barangay."),
        ] = None,
        indicator: Annotated[
            str | None, Field(description="Indicator code or exact label.")
        ] = None,
        q: Annotated[str | None, Field(description="Search the source geographic name.")] = None,
        release_id: Annotated[
            str | None, Field(description="Restrict to one release UUID.")
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum results (default 100).", ge=1, le=500)
        ] = 100,
        offset: Annotated[int, Field(description="Offset for paging.", ge=0)] = 0,
    ) -> ApiResult:
        return api_result(
            await api.get(
                API_ROUTES["population"],
                {
                    "psgc": psgc,
                    "level": level,
                    "indicator": indicator,
                    "q": q,
                    "release_id": release_id,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )

    @mcp.tool(
        name="get_sources",
        title="Get datasets and sources",
        description=(
            "Dataset catalogue or one dataset by ID: agency, source URL, licence, redistribution "
            "status, rights basis, attribution, coverage scope, update pattern and publication "
            "state. Use this to explain where a figure came from and what it does not cover."
        ),
        annotations=annotations,
    )
    async def get_sources(
        source_id: Annotated[
            str | None, Field(description="Dataset UUID. Omit to list all datasets.")
        ] = None,
    ) -> ApiResult:
        path = (
            API_ROUTES["source"].format(source_id=source_id) if source_id else API_ROUTES["sources"]
        )
        return api_result(await api.get(path))

    @mcp.tool(
        name="get_coverage",
        title="Get registry coverage",
        description=(
            "Counts of published records by inclusion class, category, subtype, access class, "
            "ownership, region, LGU coverage and source, with coordinate availability, caveats "
            "and staleness. Use this before making any completeness claim: the registry is "
            "partial and coverage differs sharply by source and region."
        ),
        annotations=annotations,
    )
    async def get_coverage() -> ApiResult:
        return api_result(await api.get(API_ROUTES["coverage"]))

    @mcp.tool(
        name="get_taxonomy",
        title="Get controlled vocabularies",
        description=(
            "Valid codes and display labels for categories and subtypes, facility kinds, "
            "inclusion classes, ownership/operator types, access classes, record statuses and "
            "contact types. Call this instead of guessing filter codes; never hardcode a "
            "private copy of the vocabulary."
        ),
        annotations=annotations,
    )
    async def get_taxonomy() -> ApiResult:
        return api_result(await api.get(API_ROUTES["taxonomy"]))

    @mcp.tool(
        name="get_download_links",
        title="Get bulk download links",
        description=(
            "Public CSV and Parquet download URLs for facilities, schools and health facilities. "
            "These are links to the public API exports, not a promise of national coverage. "
            "Keep the source attribution and rights terms from get_sources when redistributing."
        ),
        annotations=annotations,
    )
    async def get_download_links() -> ApiResult:
        return api_result(
            {
                "downloads": dict(DOWNLOAD_PATHS),
                "note": (
                    "Bulk files are publication-gated exports of the same records available "
                    "through /v1. Coverage is partial and described by get_coverage; source "
                    "rights and attribution are listed by get_sources."
                ),
            }
        )
