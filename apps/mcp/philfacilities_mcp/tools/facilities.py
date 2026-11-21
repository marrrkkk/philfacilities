"""Facility search, detail, provenance and nearby tools."""

from __future__ import annotations

import asyncio
from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..client import API_ROUTES, ApiClient, ApiResult, api_result

Q = Annotated[str | None, Field(description="Free text search over facility names and addresses.")]
CODE = Annotated[
    str | None,
    Field(description="A PSGC code. Leading zeros are significant; pass it as a string."),
]


def register(mcp: MCPServer, api: ApiClient, annotations: ToolAnnotations) -> None:
    @mcp.tool(
        name="search_facilities",
        title="Search facilities",
        description=(
            "Find published facilities by name, place, type or source. Returns summaries with "
            "is_synthetic, location precision and source counts, plus total/has_more/next_cursor "
            "for paging. Use get_facility for one full record. Codes must be strings to preserve "
            "leading zeros. Call get_taxonomy first for valid type/ownership/access codes."
        ),
        annotations=annotations,
    )
    async def search_facilities(
        q: Q = None,
        facility_type: Annotated[
            str | None, Field(description="Facility category code from get_taxonomy.")
        ] = None,
        subtype: Annotated[str | None, Field(description="Category subtype label or code.")] = None,
        function: Annotated[str | None, Field(description="Facility function or service.")] = None,
        inclusion_class: Annotated[
            str | None, Field(description="Inclusion class code from get_taxonomy.")
        ] = None,
        ownership_type: Annotated[str | None, Field(description="Ownership type code.")] = None,
        operator_type: Annotated[str | None, Field(description="Operator type code.")] = None,
        public_access_class: Annotated[
            str | None, Field(description="Public access class code.")
        ] = None,
        region_code: CODE = None,
        province_code: CODE = None,
        municipality_code: CODE = None,
        barangay_code: CODE = None,
        psgc: CODE = None,
        source: Annotated[
            str | None, Field(description="Dataset slug to restrict to one source.")
        ] = None,
        location_precision: Annotated[
            str | None, Field(description="One of the LocationOut precision values.")
        ] = None,
        limit: Annotated[
            int, Field(description="Page size (default 20, maximum 100).", ge=1, le=100)
        ] = 20,
        cursor: Annotated[
            str | None, Field(description="Opaque next_cursor from a previous call.")
        ] = None,
    ) -> ApiResult:
        return api_result(
            await api.get(
                API_ROUTES["facilities"],
                {
                    "q": q,
                    "type": facility_type,
                    "subtype": subtype,
                    "function": function,
                    "inclusion_class": inclusion_class,
                    "ownership_type": ownership_type,
                    "operator_type": operator_type,
                    "public_access_class": public_access_class,
                    "region_code": region_code,
                    "province_code": province_code,
                    "municipality_code": municipality_code,
                    "barangay_code": barangay_code,
                    "psgc": psgc,
                    "source": source,
                    "location_precision": location_precision,
                    "limit": limit,
                    "cursor": cursor,
                },
            )
        )

    @mcp.tool(
        name="get_facility",
        title="Get one facility",
        description=(
            "Full published detail for one facility, accepted as a UUID or slug. Includes the "
            "current location with its precision and method, domain profiles, quality warnings "
            "and source references. Detail is deliberately a separate call from search."
        ),
        annotations=annotations,
    )
    async def get_facility(
        facility_id: Annotated[str, Field(description="Facility UUID or slug.")],
    ) -> ApiResult:
        return api_result(
            await api.get(
                API_ROUTES["facility"].format(facility_id=facility_id),
            )
        )

    @mcp.tool(
        name="get_facility_provenance",
        title="Get facility provenance",
        description=(
            "Source records and field-level claims behind one published facility: agency, "
            "dataset, release, source record ID, reference period, retrieval time, rights, "
            "licence, attribution, raw and normalised values, and review status. Use this when "
            "a fact needs evidence. Conflicting claims are kept, not merged."
        ),
        annotations=annotations,
    )
    async def get_facility_provenance(
        facility_id: Annotated[str, Field(description="Facility UUID or slug.")],
        attribute: Annotated[
            str | None, Field(description="Only return claims for this canonical attribute.")
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum field assertions (1-1000).", ge=1, le=1000)
        ] = 200,
    ) -> ApiResult:
        sources, assertions = await asyncio.gather(
            api.get(API_ROUTES["facility_sources"].format(facility_id=facility_id)),
            api.get(
                API_ROUTES["facility_assertions"].format(facility_id=facility_id),
                {"attribute": attribute, "limit": limit},
            ),
        )
        return api_result(
            {"facility_id": facility_id, "sources": sources, "assertions": assertions}
        )

    @mcp.tool(
        name="find_nearby_facilities",
        title="Find nearby facilities",
        description=(
            "Published facilities within a radius of a latitude/longitude point, nearest first. "
            "Returns summaries with location precision, not distances or routes. Coordinates "
            "are often centroids or geocoded points, so proximity is approximate. The result "
            "may be truncated; reduce the radius or narrow with a type/name filter."
        ),
        annotations=annotations,
    )
    async def find_nearby_facilities(
        lat: Annotated[float, Field(description="Centre latitude (-90 to 90).", ge=-90, le=90)],
        lon: Annotated[
            float, Field(description="Centre longitude (-180 to 180).", ge=-180, le=180)
        ],
        radius_m: Annotated[
            int, Field(description="Search radius in metres (default 5000).", ge=1)
        ] = 5000,
        q: Q = None,
        facility_type: Annotated[str | None, Field(description="Facility category code.")] = None,
        limit: Annotated[
            int, Field(description="Maximum results (default 50).", ge=1, le=500)
        ] = 50,
    ) -> ApiResult:
        return api_result(
            await api.get(
                API_ROUTES["nearby"],
                {
                    "lat": lat,
                    "lon": lon,
                    "radius_m": radius_m,
                    "q": q,
                    "type": facility_type,
                    "limit": limit,
                },
            )
        )
