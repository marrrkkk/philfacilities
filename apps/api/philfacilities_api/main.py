from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import __version__
from .api.router import api_router
from .config import get_settings
from .db import engine
from .middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    install_error_handlers,
)

settings = get_settings()

DESCRIPTION = """
PhilFacilities is an independent, source-linked registry of Philippine schools and
health facilities. This API exposes canonical facility records, original source
identifiers, dated domain observations, provenance, and measured quality signals.

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
    openapi_tags=[
        {"name": "facilities", "description": "Canonical facility search, detail, and provenance."},
        {"name": "schools", "description": "DepEd-linked school profiles and observations."},
        {
            "name": "health",
            "description": "Health facility profiles, licenses, and accreditations.",
        },
        {"name": "geography", "description": "Versioned PSA PSGC geography."},
        {"name": "sources", "description": "Datasets, releases, quality, changes, and downloads."},
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
    expose_headers=["ETag", "X-Request-ID", "X-Response-Time-Ms"],
)
app.add_middleware(RateLimitMiddleware, limit=settings.rate_limit_per_minute)
app.add_middleware(RequestContextMiddleware)
install_error_handlers(app)

app.include_router(api_router, prefix="/v1")


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
            "downloads": "/v1/downloads/facilities.csv",
        },
        "notice": (
            "Only publication-approved source records are exposed. Remaining synthetic "
            "records, if any, are labelled is_synthetic=true."
        ),
    }
