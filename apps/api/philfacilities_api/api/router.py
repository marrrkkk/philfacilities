from __future__ import annotations

from fastapi import APIRouter

from . import (
    accreditations,
    facilities,
    fields,
    geography,
    health,
    population,
    schools,
    sources,
    taxonomy,
)

api_router = APIRouter()
api_router.include_router(facilities.router)
api_router.include_router(schools.router)
api_router.include_router(health.router)
api_router.include_router(accreditations.router)
api_router.include_router(geography.router)
api_router.include_router(population.router)
api_router.include_router(sources.router)
api_router.include_router(taxonomy.router)
api_router.include_router(fields.router)
