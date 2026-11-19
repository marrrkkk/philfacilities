"""Controlled school-facility labels shared by adapters and cleanup passes.

OpenStreetMap education layers publish the raw ``amenity`` or ``building``
value as the subtype (``school``, ``university``, ``kindergarten``). Those are
source tags, not the controlled school vocabulary. This module maps the tags
that establish a category and clears the rest instead of guessing a school
level or sector.
"""

from __future__ import annotations

from philfacilities_api.taxonomy import CATEGORY_SUBTYPES

CANONICAL_SCHOOL_SUBTYPES = frozenset(CATEGORY_SUBTYPES["school"])

# Raw label -> controlled subtype. Keys are case/space/underscore folded.
SCHOOL_SUBTYPE_ALIASES: dict[str, str] = {
    "school": "OTHER_SCHOOL",
    "elementary school": "OTHER_SCHOOL",
    "primary school": "OTHER_SCHOOL",
    "secondary school": "OTHER_SCHOOL",
    "high school": "OTHER_SCHOOL",
    "integrated school": "OTHER_SCHOOL",
    "kindergarten": "OTHER_SCHOOL",
    "preschool": "OTHER_SCHOOL",
    "pre school": "OTHER_SCHOOL",
    "public school": "OTHER_SCHOOL",
    "private school": "PRIVATE_SCHOOL",
    "public elementary school": "PUBLIC_ELEMENTARY_SCHOOL",
    "public secondary school": "PUBLIC_SECONDARY_SCHOOL",
    "university": "HIGHER_EDUCATION_INSTITUTION",
    "college": "HIGHER_EDUCATION_INSTITUTION",
    "higher education institution": "HIGHER_EDUCATION_INSTITUTION",
    "training institution": "TRAINING_INSTITUTION",
    "technical school": "TRAINING_INSTITUTION",
    "vocational school": "TRAINING_INSTITUTION",
}

# OSM tags that describe another kind of place and do not establish a school
# class. The canonical facility may still be a school because another source
# says so, but the tag itself is not evidence.
NON_SCHOOL_LABELS = frozenset(
    {
        "bar",
        "data facility",
        "events venue",
        "fast food",
        "food court",
        "local government office",
        "place of worship",
        "public library",
        "stage",
        "theatre",
        "toilets",
    }
)


def _fold(value: str | None) -> str:
    return " ".join(
        (value or "").replace("_", " ").replace("-", " ").replace("/", " ").split()
    ).lower()


def classify_school_subtype(value: str | None) -> tuple[bool, str | None]:
    """Return ``(known, controlled_subtype)`` for a raw school label.

    ``known`` is true when the label carries a decision: a mapped school class
    or an explicit non-school tag that should be cleared. Unknown labels stay
    unknown for review rather than being silently discarded.
    """

    if value is None:
        return True, None
    stripped = value.strip()
    if not stripped:
        return True, None
    if stripped in CANONICAL_SCHOOL_SUBTYPES:
        return True, stripped
    folded = _fold(stripped)
    if folded in SCHOOL_SUBTYPE_ALIASES:
        return True, SCHOOL_SUBTYPE_ALIASES[folded]
    if folded in NON_SCHOOL_LABELS:
        return True, None
    return False, None
