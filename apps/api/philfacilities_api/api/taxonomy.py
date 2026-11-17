from __future__ import annotations

from fastapi import APIRouter, Request

from ..middleware import conditional_json
from ..schemas import TaxonomyCategoryOut, TaxonomyResponse, TaxonomyTermOut
from ..taxonomy import (
    ACCESS_CLASS_LABELS,
    ACCESS_CLASSES,
    CATEGORY_LABELS,
    CATEGORY_SUBTYPES,
    CONTACT_TYPE_LABELS,
    CONTACT_TYPES,
    FACILITY_CATEGORIES,
    FACILITY_KIND_LABELS,
    FACILITY_KINDS,
    INCLUSION_CLASS_LABELS,
    INCLUSION_CLASSES,
    OPERATOR_TYPES,
    OWNERSHIP_TYPE_LABELS,
    OWNERSHIP_TYPES,
    RECORD_STATUS_LABELS,
    RECORD_STATUSES,
    SUBTYPE_LABELS,
    TAXONOMY_VERSION,
)

router = APIRouter(tags=["taxonomy"])


def _terms(codes, labels: dict[str, str]) -> list[TaxonomyTermOut]:
    return [TaxonomyTermOut(code=code, label=labels.get(code, code)) for code in codes]


@router.get(
    "/taxonomy",
    response_model=TaxonomyResponse,
    summary="Controlled vocabularies and display labels",
)
def get_taxonomy(request: Request):
    """Return the controlled codes, labels, and category-to-subtype mapping.

    Clients should use this reference instead of hardcoding a private copy of
    the vocabulary. It is static for a given API release and safe to cache.
    """

    payload = TaxonomyResponse(
        version=TAXONOMY_VERSION,
        categories=[
            TaxonomyCategoryOut(
                code=category,
                label=CATEGORY_LABELS.get(category, category),
                subtypes=_terms(CATEGORY_SUBTYPES.get(category, ()), SUBTYPE_LABELS),
            )
            for category in FACILITY_CATEGORIES
        ],
        facility_kinds=_terms(FACILITY_KINDS, FACILITY_KIND_LABELS),
        inclusion_classes=_terms(INCLUSION_CLASSES, INCLUSION_CLASS_LABELS),
        ownership_types=_terms(OWNERSHIP_TYPES, OWNERSHIP_TYPE_LABELS),
        operator_types=_terms(OPERATOR_TYPES, OWNERSHIP_TYPE_LABELS),
        access_classes=_terms(ACCESS_CLASSES, ACCESS_CLASS_LABELS),
        record_statuses=_terms(RECORD_STATUSES, RECORD_STATUS_LABELS),
        contact_types=_terms(CONTACT_TYPES, CONTACT_TYPE_LABELS),
    )
    return conditional_json(request, payload.model_dump(mode="json"), max_age=86400)
