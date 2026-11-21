from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import TypeAdapter
from scalar_fastapi import AgentScalarConfig, Layout, Theme, add_scalar_reference
from sqlalchemy import text

from . import __version__
from .api.router import api_router
from .config import get_settings
from .db import engine
from .examples import ERROR_EXAMPLES, SCHEMA_EXAMPLES
from .middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    install_error_handlers,
)
from .scalar_theme import CUSTOM_CSS
from .schemas import ErrorBody

settings = get_settings()

DESCRIPTION = """
PhilFacilities is an independent, source-linked registry of Philippine facilities
across 16 categories (schools, health facilities, government offices, libraries,
public spaces, and others). This API exposes canonical facility records, original
source identifiers, dated domain observations, provenance, and measured quality
signals. Authoritative typed profiles exist mainly for schools and health facilities,
where rights-cleared official sources exist; other categories are largely
discovery-layer records served by the generic facility endpoints. Use
`/v1/taxonomy` for the authoritative category list and `/v1/statistics#by_category`
for published counts, and `/v1/fields` to see how populated each field is.

**Read the fields carefully.** `updated_at` is when PhilFacilities changed its canonical
record, not when an agency updated a source. Source publication dates, reference periods,
retrieval times, and processing times are separate fields on every source record.

No authentication is required for the public read endpoints in this release. Only
records linked to a rights-cleared, publication-approved source release are exposed;
restricted, internal-only, quarantined, and blocked source records are excluded. Any
remaining synthetic demonstration records are labelled with `is_synthetic: true` and
must not be treated as official government records.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine.dispose()


app = FastAPI(
    title="PhilFacilities API",
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    # Swagger UI and ReDoc are replaced by Scalar at the same /docs URL.
    docs_url=None,
    redoc_url=None,
    openapi_tags=[
        {"name": "facilities", "description": "Canonical facility search, detail, and provenance."},
        {"name": "schools", "description": "DepEd-linked school profiles and observations."},
        {
            "name": "health",
            "description": "Health facility profiles, licenses, and accreditations.",
        },
        {"name": "geography", "description": "Versioned PSA PSGC geography."},
        {"name": "sources", "description": "Datasets, releases, quality, changes, and downloads."},
        {"name": "taxonomy", "description": "Controlled facility vocabularies and display labels."},
        {"name": "system", "description": "Service health."},
    ],
    contact={"name": "PhilFacilities", "url": "https://github.com/philfacilities"},
    license_info={"name": "Apache-2.0 (code only; data rights vary by source)"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=[
        "ETag",
        "X-Request-ID",
        "X-Response-Time-Ms",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
    ],
)
app.add_middleware(RateLimitMiddleware, limit=settings.rate_limit_per_minute)
app.add_middleware(RequestContextMiddleware)
install_error_handlers(app)

app.include_router(api_router, prefix="/v1")

# FastAPI's inferred 422 schema (HTTPValidationError) does not match what the
# error handlers actually return. Publish the one flat ErrorBody shape on every
# error response so the generated client and Scalar docs match the runtime.
ERROR_RESPONSES = {
    "400": "Invalid filter or request parameter.",
    "404": "No publication-approved resource with that identifier.",
    "422": "One or more query parameters are invalid.",
    "429": "Too many requests. Retry after the current window.",
    "500": "An unexpected error occurred.",
}
_application_openapi = app.openapi

READING_NOTES = (
    "**Publication gate:** only rights-cleared, publication-approved records are "
    "returned. **Freshness:** `updated_at` is a PhilFacilities edit time, not an "
    "agency update time. **Coordinates:** WGS 84 and often approximate; read "
    "`location.precision` before presenting a point as a building. **Coverage:** "
    "`GET /v1/fields` reports how populated each field is (synthetic examples in "
    "the schemas are labelled and are not official records)."
)


def _openapi_with_error_responses():
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = _application_openapi()
    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    schemas["ErrorBody"] = TypeAdapter(ErrorBody).json_schema(
        ref_template="#/components/schemas/{model}"
    )
    # get_openapi() deep-cleans nulls from the whole document. Re-inject the
    # labelled examples so the null/empty-collection convention stays visible.
    for name, examples in SCHEMA_EXAMPLES.items():
        if name in schemas:
            schemas[name]["examples"] = deepcopy(examples)
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            existing_description = operation.get("description", "")
            operation["description"] = (
                existing_description + "\n\n" + READING_NOTES
                if existing_description
                else READING_NOTES
            )
            for status, description in ERROR_RESPONSES.items():
                response = {
                    "description": description,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorBody"},
                            "example": ERROR_EXAMPLES[status],
                        }
                    },
                }
                if status == "422":
                    operation["responses"][status] = response
                else:
                    operation["responses"].setdefault(status, response)
    app.openapi_schema = schema
    return schema


app.openapi = _openapi_with_error_responses


add_scalar_reference(
    app,
    route="/docs",
    title="PhilFacilities API Reference",
    layout=Layout.MODERN,
    theme=Theme.DEFAULT,
    custom_css=CUSTOM_CSS,
    telemetry=False,
    agent=AgentScalarConfig(disabled=True),
)


@app.get("/healthz", tags=["system"], summary="Service health")
def healthz():
    database = "ok"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"
    status = "ok" if database == "ok" else "degraded"
    return {
        "status": status,
        "service": "philfacilities-api",
        "version": __version__,
        "database": database,
        "environment": settings.env,
    }


@app.get("/v1", tags=["system"], summary="API index")
def api_index():
    return {
        "name": "PhilFacilities API",
        "version": __version__,
        "documentation": "/docs",
        "openapi": "/openapi.json",
        "resources": {
            "facilities": "/v1/facilities",
            "within": "/v1/facilities/within",
            "nearby": "/v1/facilities/nearby",
            "schools": "/v1/schools",
            "health_facilities": "/v1/health-facilities",
            "accreditations": "/v1/accreditations",
            "geographies": "/v1/geographies",
            "sources": "/v1/sources",
            "quality": "/v1/quality/summary",
            "statistics": "/v1/statistics",
            # by_category already contains every taxonomy category; surface it
            # here instead of introducing a second, hard-coded category list.
            "category_counts": "/v1/statistics#by_category",
            "taxonomy": "/v1/taxonomy",
            "fields": "/v1/fields",
            "downloads": "/v1/downloads/facilities.csv",
        },
        "notice": (
            "Only publication-approved source records are exposed. Remaining synthetic "
            "records, if any, are labelled is_synthetic=true."
        ),
    }
