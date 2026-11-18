"""Pure text normalization shared by source adapters and identity matching.

The helpers in this module deliberately have no database or model imports so a
source adapter can canonicalize an identifier without pulling in the ingestion
pipeline. ``normalize_name`` remains re-exported from ``matching`` for existing
callers.
"""

from __future__ import annotations

import re

_SAINT_TOKENS = {
    "st": "saint",
    "sta": "santa",
    "sto": "santo",
}

# Legal-form tokens that do not distinguish one school from another. They are
# stripped only from the end of a name, so a school actually named e.g.
# "Company Street Academy" keeps its distinguishing token.
_LEGAL_SUFFIXES = frozenset(
    {
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "ltd",
        "limited",
        "opc",
    }
)

# Tokens that distinguish one campus/branch from another. A name with an extra
# one of these is related, but is not the same identity as the shorter name.
_DISTINGUISHING_TOKENS = frozenset(
    {
        "annex",
        "branch",
        "campus",
        "extension",
        "main",
        "site",
        "north",
        "south",
        "east",
        "west",
        "upper",
        "lower",
        "new",
        "old",
        "i",
        "ii",
        "iii",
        "iv",
        "v",
        "vi",
    }
)

# Generic address words that do not identify a particular place. City and
# barangay names are added to this set by the caller when it knows the local
# administrative hierarchy.
_ADDRESS_STOPWORDS = frozenset(
    {
        "ave",
        "avenue",
        "bldg",
        "blk",
        "block",
        "brgy",
        "building",
        "cor",
        "corner",
        "city",
        "district",
        "door",
        "floor",
        "highway",
        "lot",
        "municipality",
        "national",
        "poblacion",
        "province",
        "purok",
        "road",
        "sitio",
        "street",
        "unit",
        "zone",
    }
)


def normalize_name(value: str | None) -> str:
    """Case-fold and collapse punctuation/whitespace for deterministic comparison."""

    if not value:
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def facility_name_key(value: str | None) -> str:
    """Normalize a facility name for identity comparison.

    Sources vary punctuation, saint abbreviations (``St.``/``Saint``) and legal
    forms (``Inc.``, ``Corporation``). Folding those variants lets the matcher
    recognise one institution without treating genuinely different campus names
    as equal.
    """

    if not value:
        return ""
    tokens = normalize_name(value.casefold().replace("&", " and ")).split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    tokens = [_SAINT_TOKENS.get(token, token) for token in tokens]
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


# Conventional school-type abbreviations used by DepEd and EBEIS. They are
# expanded only for school names and only when the source wrote the token in
# uppercase, so a facility name containing the word "is" is left alone.
_SCHOOL_TYPE_TOKENS = {
    "is": "integrated school",
    "es": "elementary school",
    "cs": "central school",
    "nhs": "national high school",
    "shs": "senior high school",
    "jhs": "junior high school",
    "sped": "special education",
    "els": "elementary school",
    "gs": "grade school",
    "hs": "high school",
}


def _uppercase_tokens(value: str | None) -> set[str]:
    tokens: set[str] = set()
    for token in (value or "").split():
        letters = [character for character in token if character.isalpha()]
        if not letters:
            continue
        if token.upper() == token:
            tokens.add(re.sub(r"[^a-z0-9]+", "", token.casefold()))
    return tokens


def school_name_key(value: str | None) -> str:
    """Normalize a school name, expanding conventional type abbreviations.

    EBEIS often publishes the same school as ``Awag IS`` in one row and
    ``Awag Integrated School`` in its twin. Expanding only uppercase tokens
    keeps the general facility key conservative for names such as
    ``ES Transportation``.
    """

    base = facility_name_key(value)
    if not base:
        return ""
    uppercase = _uppercase_tokens(value)
    expanded: list[str] = []
    for token in base.split():
        replacement = _SCHOOL_TYPE_TOKENS.get(token) if token in uppercase else None
        if replacement:
            expanded.extend(replacement.split())
        else:
            expanded.append(token)
    return " ".join(expanded)


# Subtype labels come from independent agency vocabularies. One college is
# published as ``college`` by OSM, ``HIGHER_EDUCATION_INSTITUTION`` by CHED and
# ``OTHER_SCHOOL`` by DepEd. Comparing the raw labels would reject the pair
# before the identity evidence is scored. Known labels map to a broad level
# family; vague labels such as ``school`` or ``other school`` carry no level
# information and therefore cannot contradict another label.
_SUBTYPE_FAMILIES: dict[str, dict[str, str]] = {
    "school": {
        "higher education": "tertiary",
        "higher education institution": "tertiary",
        "hei": "tertiary",
        "college": "tertiary",
        "university": "tertiary",
        "tertiary": "tertiary",
        "elementary": "primary",
        "elementary school": "primary",
        "primary": "primary",
        "primary school": "primary",
        "grade school": "primary",
        "high school": "secondary",
        "secondary": "secondary",
        "secondary school": "secondary",
        "junior high school": "secondary",
        "senior high school": "secondary",
        "national high school": "secondary",
        "integrated school": "k12",
        "k 12": "k12",
        "kindergarten": "early_childhood",
        "preschool": "early_childhood",
        "early childhood": "early_childhood",
        "special education": "special_education",
        "sped": "special_education",
        "technical vocational": "vocational",
        "vocational": "vocational",
        "tvet": "vocational",
    },
}

_VAGUE_SUBTYPES = frozenset(
    {
        "facility",
        "n a",
        "no",
        "none",
        "not specified",
        "other",
        "school",
        "schools",
        "unknown",
        "unclassified",
        "unspecified",
        "yes",
    }
)


def subtype_family(facility_type: str | None, subtype: str | None) -> str | None:
    """Return a broad subtype family, or ``None`` when the label is vague.

    A vague label is not evidence of a different kind of place, so it stays
    compatible with every family. Unrecognised labels fall back to their
    normalized text, preserving the conservative exact-label comparison for
    facility types without a mapping.
    """

    normalized = normalize_name(subtype)
    if not normalized or normalized.startswith("other ") or normalized in _VAGUE_SUBTYPES:
        return None
    mapping = _SUBTYPE_FAMILIES.get(normalize_name(facility_type), {})
    return mapping.get(normalized, normalized)


def subtypes_compatible(
    facility_type: str | None,
    left: str | None,
    right: str | None,
) -> bool:
    """Whether two source subtype labels can describe the same facility."""

    left_family = subtype_family(facility_type, left)
    right_family = subtype_family(facility_type, right)
    return left_family is None or right_family is None or left_family == right_family


def name_similarity(
    left: str | None,
    right: str | None,
    *,
    school: bool = False,
) -> tuple[float, str]:
    """Score how likely two names denote the same named thing.

    The score never decides identity on its own; it is one evidence dimension.
    ``exact`` is the case-folded canonical key, ``containment`` is a strict
    token subset (for example a trailing ``Main``), and ``token_overlap`` is a
    high Jaccard score. Names differing in a branch/campus marker are capped
    below the auto-merge threshold. ``school`` enables the school-type
    abbreviation expansion used by EBEIS.
    """

    key = school_name_key if school else facility_name_key
    left_key = key(left)
    right_key = key(right)
    if not left_key or not right_key:
        return 0.0, "missing"
    if left_key == right_key:
        return 1.0, "exact"
    left_tokens = set(left_key.split())
    right_tokens = set(right_key.split())
    shared = left_tokens & right_tokens
    if not shared:
        return 0.0, "different"
    different = (left_tokens | right_tokens) - shared
    if different & _DISTINGUISHING_TOKENS:
        return 0.5, "distinguishing"
    if (left_tokens <= right_tokens or right_tokens <= left_tokens) and len(shared) >= 2:
        return 0.9, "containment"
    jaccard = len(shared) / len(left_tokens | right_tokens)
    if jaccard >= 0.75 and len(shared) >= 3:
        return round(0.6 + 0.4 * jaccard, 3), "token_overlap"
    return round(jaccard, 3), "weak"


def is_specific_name(value: str | None) -> bool:
    """A name is specific when it is more than a generic facility label."""

    key = facility_name_key(value)
    return len(key) >= 12 and len(key.split()) >= 2


def psgc_city_code(code: str | None) -> str | None:
    """Return the 7-digit city/municipality prefix of a 10-digit PSGC code.

    Region and province codes have zeroes in the city/municipality position and
    are rejected rather than compared as if they named a city.
    """

    if not code:
        return None
    digits = str(code).strip()
    if len(digits) != 10 or not digits.isdigit() or digits[4:7] == "000":
        return None
    return digits[:7]


def psgc_barangay_code(code: str | None) -> str | None:
    """Return a 10-digit barangay PSGC code, or ``None`` for higher levels."""

    if not code:
        return None
    digits = str(code).strip()
    if len(digits) == 10 and digits.isdigit() and not digits.endswith("000"):
        return digits
    return None


def address_tokens(value: str | None, *, administrative_names: set[str] | None = None) -> set[str]:
    """Return distinctive normalized address tokens.

    Street numbers and building names are retained. Administrative names (city,
    province, barangay) and generic words are removed when the caller supplies
    the hierarchy, so "Lucena City" alone is not treated as a shared street.
    """

    tokens = set(normalize_name(value).split())
    ignored = _ADDRESS_STOPWORDS | (administrative_names or set())
    return {token for token in tokens if len(token) >= 3 and token not in ignored}


def address_overlap(
    left: str | None,
    right: str | None,
    *,
    administrative_names: set[str] | None = None,
) -> int:
    """Count distinctive address tokens shared by two addresses."""

    return len(
        address_tokens(left, administrative_names=administrative_names)
        & address_tokens(right, administrative_names=administrative_names)
    )


def deped_prefixed_school_id(school_id: str | None) -> str | None:
    """Return the six-digit base of an EBEIS prefixed school ID, if any.

    The public EBEIS result set contains rows whose ``School ID`` is the normal
    six-digit BEIS ID with a one-digit level/school-type prefix (``1``, ``2`` or
    ``3``). For example ``1403263`` is the prefixed row for BEIS ID ``403263``.
    The prefix is not part of the official six-digit BEIS identifier, so the
    base ID must be used for canonical identity. A seven-digit value starting
    with another digit is left untouched rather than guessed.
    """

    if not school_id:
        return None
    value = str(school_id).strip()
    if len(value) == 7 and value[0] in {"1", "2", "3"} and value[1:].isdigit():
        return value[1:]
    return None
