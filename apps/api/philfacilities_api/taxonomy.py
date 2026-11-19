"""Ownership-inclusive facility taxonomy and controlled vocabularies.

This module is the single Python source of truth for the v3.0 expansion. Database
check constraints and API literals mirror these values. It deliberately separates:

* what kind of physical entity a record represents (``facility_kind``);
* why the record qualifies for the registry (``inclusion_class``);
* who owns, operates, manages, hosts, funds, regulates or accredits it
  (``facility_roles``);
* what the place is for (``facility_functions`` / category / subtype);
* what is delivered there (``facility_services``);
* the conditions of entry (``public_access_class``).

The taxonomy is descriptive, not a claim of national completeness. A category may
exist here before a verified source has been acquired for it.
"""

from __future__ import annotations

from typing import Final

TAXONOMY_VERSION: Final = "3.0"

# ---------------------------------------------------------------------------
# Inclusion classes
# ---------------------------------------------------------------------------

GOVERNMENT_FACILITY: Final = "GOVERNMENT_FACILITY"
PRIVATE_PUBLIC_SERVICE_PROVIDER: Final = "PRIVATE_PUBLIC_SERVICE_PROVIDER"
PUBLIC_ACCESS_VENUE: Final = "PUBLIC_ACCESS_VENUE"
DISCOVERY_CANDIDATE: Final = "DISCOVERY_CANDIDATE"

PUBLIC_INCLUSION_CLASSES: Final = (
    GOVERNMENT_FACILITY,
    PRIVATE_PUBLIC_SERVICE_PROVIDER,
    PUBLIC_ACCESS_VENUE,
)
INCLUSION_CLASSES: Final = (*PUBLIC_INCLUSION_CLASSES, DISCOVERY_CANDIDATE)

# Legacy coarse ownership value. ``ownership_type`` carries the granular class.
OWNERSHIP_VALUES: Final = ("government", "private", "unknown")

INCLUSION_CLASS_LABELS: Final[dict[str, str]] = {
    GOVERNMENT_FACILITY: "Government facility",
    PRIVATE_PUBLIC_SERVICE_PROVIDER: "Private public-service provider",
    PUBLIC_ACCESS_VENUE: "Public-access venue",
    DISCOVERY_CANDIDATE: "Unclassified record",
}

# ---------------------------------------------------------------------------
# Facility kinds
# ---------------------------------------------------------------------------

FACILITY: Final = "facility"
SITE: Final = "site"
BUILDING: Final = "building"
FACILITY_UNIT: Final = "facility_unit"
INFRASTRUCTURE_ASSET: Final = "infrastructure_asset"
PROJECT: Final = "project"

FACILITY_KINDS: Final = (FACILITY, SITE, BUILDING, FACILITY_UNIT, INFRASTRUCTURE_ASSET, PROJECT)

FACILITY_KIND_LABELS: Final[dict[str, str]] = {
    FACILITY: "Facility",
    SITE: "Site or campus",
    BUILDING: "Building",
    FACILITY_UNIT: "Facility unit or service counter",
    INFRASTRUCTURE_ASSET: "Infrastructure asset",
    PROJECT: "Project",
}

# ---------------------------------------------------------------------------
# Ownership / operator granularity
# ---------------------------------------------------------------------------

NATIONAL_GOVERNMENT: Final = "NATIONAL_GOVERNMENT"
LOCAL_GOVERNMENT: Final = "LOCAL_GOVERNMENT"
GOCC: Final = "GOCC"
PUBLIC_EDUCATIONAL_INSTITUTION: Final = "PUBLIC_EDUCATIONAL_INSTITUTION"
OTHER_PUBLIC_BODY: Final = "OTHER_PUBLIC_BODY"
GOVERNMENT_UNSPECIFIED: Final = "GOVERNMENT_UNSPECIFIED"
PRIVATE_CORPORATE: Final = "PRIVATE_CORPORATE"
PRIVATE_INDIVIDUAL_OR_PARTNERSHIP: Final = "PRIVATE_INDIVIDUAL_OR_PARTNERSHIP"
NGO_NON_PROFIT: Final = "NGO_NON_PROFIT"
COOPERATIVE: Final = "COOPERATIVE"
RELIGIOUS_FAITH_BASED: Final = "RELIGIOUS_FAITH_BASED"
PUBLIC_PRIVATE_JOINT: Final = "PUBLIC_PRIVATE_JOINT"
PRIVATE_UNSPECIFIED: Final = "PRIVATE_UNSPECIFIED"
UNKNOWN: Final = "UNKNOWN"

OWNERSHIP_TYPES: Final = (
    NATIONAL_GOVERNMENT,
    LOCAL_GOVERNMENT,
    GOCC,
    PUBLIC_EDUCATIONAL_INSTITUTION,
    OTHER_PUBLIC_BODY,
    GOVERNMENT_UNSPECIFIED,
    PRIVATE_CORPORATE,
    PRIVATE_INDIVIDUAL_OR_PARTNERSHIP,
    NGO_NON_PROFIT,
    COOPERATIVE,
    RELIGIOUS_FAITH_BASED,
    PUBLIC_PRIVATE_JOINT,
    PRIVATE_UNSPECIFIED,
    UNKNOWN,
)

GOVERNMENT_OWNERSHIP_TYPES: Final = frozenset(
    {
        NATIONAL_GOVERNMENT,
        LOCAL_GOVERNMENT,
        GOCC,
        PUBLIC_EDUCATIONAL_INSTITUTION,
        OTHER_PUBLIC_BODY,
        GOVERNMENT_UNSPECIFIED,
    }
)
PRIVATE_OWNERSHIP_TYPES: Final = frozenset(
    {
        PRIVATE_CORPORATE,
        PRIVATE_INDIVIDUAL_OR_PARTNERSHIP,
        NGO_NON_PROFIT,
        COOPERATIVE,
        RELIGIOUS_FAITH_BASED,
        PUBLIC_PRIVATE_JOINT,
        PRIVATE_UNSPECIFIED,
    }
)

OPERATOR_TYPES: Final = OWNERSHIP_TYPES

OWNERSHIP_TYPE_LABELS: Final[dict[str, str]] = {
    NATIONAL_GOVERNMENT: "National government",
    LOCAL_GOVERNMENT: "Local government",
    GOCC: "Government-owned or controlled corporation",
    PUBLIC_EDUCATIONAL_INSTITUTION: "Public educational institution",
    OTHER_PUBLIC_BODY: "Other public body",
    GOVERNMENT_UNSPECIFIED: "Government (unspecified)",
    PRIVATE_CORPORATE: "Private corporation",
    PRIVATE_INDIVIDUAL_OR_PARTNERSHIP: "Private individual or partnership",
    NGO_NON_PROFIT: "Non-government or non-profit organization",
    COOPERATIVE: "Cooperative",
    RELIGIOUS_FAITH_BASED: "Religious or faith-based organization",
    PUBLIC_PRIVATE_JOINT: "Public-private joint",
    PRIVATE_UNSPECIFIED: "Private (unspecified)",
    UNKNOWN: "Unknown",
}

# ---------------------------------------------------------------------------
# Public access
# ---------------------------------------------------------------------------

PUBLIC_FREE: Final = "PUBLIC_FREE"
PUBLIC_PAID_OR_CONDITIONAL: Final = "PUBLIC_PAID_OR_CONDITIONAL"
SERVICE_USERS_ONLY: Final = "SERVICE_USERS_ONLY"
APPOINTMENT_ONLY: Final = "APPOINTMENT_ONLY"
MEMBERS_STUDENTS_ONLY: Final = "MEMBERS_STUDENTS_ONLY"
STAFF_ONLY: Final = "STAFF_ONLY"
RESTRICTED: Final = "RESTRICTED"
ACCESS_UNKNOWN: Final = "UNKNOWN"

ACCESS_CLASSES: Final = (
    PUBLIC_FREE,
    PUBLIC_PAID_OR_CONDITIONAL,
    SERVICE_USERS_ONLY,
    APPOINTMENT_ONLY,
    MEMBERS_STUDENTS_ONLY,
    STAFF_ONLY,
    RESTRICTED,
    ACCESS_UNKNOWN,
)

ACCESS_CLASS_LABELS: Final[dict[str, str]] = {
    PUBLIC_FREE: "Public, free",
    PUBLIC_PAID_OR_CONDITIONAL: "Public, paid or conditional",
    SERVICE_USERS_ONLY: "Service users only",
    APPOINTMENT_ONLY: "Appointment only",
    MEMBERS_STUDENTS_ONLY: "Members or students only",
    STAFF_ONLY: "Staff only",
    RESTRICTED: "Restricted",
    ACCESS_UNKNOWN: "Unknown",
}

# ---------------------------------------------------------------------------
# Record lifecycle
# ---------------------------------------------------------------------------

RECORD_STATUSES: Final = (
    "active_in_registry",
    "inactive_in_registry",
    "unknown",
    "under_review",
    "merged",
)

RECORD_STATUS_LABELS: Final[dict[str, str]] = {
    "active_in_registry": "Active in registry",
    "inactive_in_registry": "Inactive in registry",
    "unknown": "Unknown",
    "under_review": "Under review",
    "merged": "Merged",
}

# ---------------------------------------------------------------------------
# Contact channels
# ---------------------------------------------------------------------------

PHONE: Final = "phone"
EMAIL: Final = "email"
WEBSITE: Final = "website"
OPENING_HOURS: Final = "opening_hours"
OTHER_CONTACT: Final = "other"

CONTACT_TYPES: Final = (PHONE, EMAIL, WEBSITE, OPENING_HOURS, OTHER_CONTACT)

CONTACT_TYPE_LABELS: Final[dict[str, str]] = {
    PHONE: "Telephone",
    EMAIL: "Email",
    WEBSITE: "Website",
    OPENING_HOURS: "Opening hours",
    OTHER_CONTACT: "Other contact",
}

# ---------------------------------------------------------------------------
# Source authority (provenance metadata, not a facility claim)
# ---------------------------------------------------------------------------

SOURCE_AUTHORITY_OFFICIAL: Final = "official"
SOURCE_AUTHORITY_COMMUNITY: Final = "community"
SOURCE_AUTHORITY_SYNTHETIC: Final = "synthetic"
SOURCE_AUTHORITY_UNKNOWN: Final = "unknown"

SOURCE_AUTHORITY_LEVELS: Final = (
    SOURCE_AUTHORITY_OFFICIAL,
    SOURCE_AUTHORITY_COMMUNITY,
    SOURCE_AUTHORITY_SYNTHETIC,
    SOURCE_AUTHORITY_UNKNOWN,
)

# ---------------------------------------------------------------------------
# Coverage scope (source-level, not facility-level truth)
# ---------------------------------------------------------------------------

COVERAGE_NATIONAL_OFFICIAL_INVENTORY: Final = "NATIONAL_OFFICIAL_INVENTORY"
COVERAGE_NATIONAL_PARTIAL: Final = "NATIONAL_PARTIAL"
COVERAGE_REGIONAL: Final = "REGIONAL"
COVERAGE_PARTICIPATING_LGUS: Final = "PARTICIPATING_LGUS"
COVERAGE_SELECTED_LGUS: Final = "SELECTED_LGUS"
COVERAGE_SINGLE_LGU: Final = "SINGLE_LGU"
COVERAGE_DIRECTORY_SUBSET: Final = "DIRECTORY_SUBSET"
COVERAGE_DISCOVERY_LAYER: Final = "DISCOVERY_LAYER"
COVERAGE_UNKNOWN: Final = "UNKNOWN_COVERAGE"

COVERAGE_SCOPES: Final = (
    COVERAGE_NATIONAL_OFFICIAL_INVENTORY,
    COVERAGE_NATIONAL_PARTIAL,
    COVERAGE_REGIONAL,
    COVERAGE_PARTICIPATING_LGUS,
    COVERAGE_SELECTED_LGUS,
    COVERAGE_SINGLE_LGU,
    COVERAGE_DIRECTORY_SUBSET,
    COVERAGE_DISCOVERY_LAYER,
    COVERAGE_UNKNOWN,
)

# ---------------------------------------------------------------------------
# Roles and relationships
# ---------------------------------------------------------------------------

OWNER: Final = "OWNER"
OPERATOR: Final = "OPERATOR"
MANAGER: Final = "MANAGER"
HOST: Final = "HOST"
LANDLORD: Final = "LANDLORD"
FUNDER: Final = "FUNDER"
REGULATOR: Final = "REGULATOR"
LICENSOR: Final = "LICENSOR"
ACCREDITOR: Final = "ACCREDITOR"
RECOGNITION_AUTHORITY: Final = "RECOGNITION_AUTHORITY"
AFFILIATOR: Final = "AFFILIATOR"

ROLE_TYPES: Final = (
    OWNER,
    OPERATOR,
    MANAGER,
    HOST,
    LANDLORD,
    FUNDER,
    REGULATOR,
    LICENSOR,
    ACCREDITOR,
    RECOGNITION_AUTHORITY,
    AFFILIATOR,
)

LOCATED_WITHIN: Final = "LOCATED_WITHIN"
SHARED_SITE: Final = "SHARED_SITE"
HOSTED_AT: Final = "HOSTED_AT"
PARENT_OF: Final = "PARENT_OF"
SUCCESSOR_OF: Final = "SUCCESSOR_OF"
REPLACED_BY: Final = "REPLACED_BY"

RELATIONSHIP_TYPES: Final = (
    LOCATED_WITHIN,
    SHARED_SITE,
    HOSTED_AT,
    PARENT_OF,
    SUCCESSOR_OF,
    REPLACED_BY,
)

# ---------------------------------------------------------------------------
# Facility categories and subtypes
# ---------------------------------------------------------------------------

SCHOOL: Final = "school"
HEALTH_FACILITY: Final = "health_facility"
GOVERNMENT_OFFICE: Final = "government_office"
COMMUNITY_FACILITY: Final = "community_facility"
EMERGENCY_FACILITY: Final = "emergency_facility"
LIBRARY: Final = "library"
MUSEUM: Final = "museum"
SOCIAL_WELFARE_FACILITY: Final = "social_welfare_facility"
PUBLIC_MARKET: Final = "public_market"
TRANSPORT_FACILITY: Final = "transport_facility"
UTILITY_FACILITY: Final = "utility_facility"
ENVIRONMENTAL_MONITORING: Final = "environmental_monitoring"
PUBLIC_SPACE: Final = "public_space"
CULTURAL_FACILITY: Final = "cultural_facility"
AGRICULTURAL_FACILITY: Final = "agricultural_facility"
JUSTICE_FACILITY: Final = "justice_facility"
HOUSING_SERVICE: Final = "housing_service"
OTHER_QUALIFYING_FACILITY: Final = "other_qualifying_facility"

FACILITY_CATEGORIES: Final = (
    SCHOOL,
    HEALTH_FACILITY,
    GOVERNMENT_OFFICE,
    COMMUNITY_FACILITY,
    EMERGENCY_FACILITY,
    LIBRARY,
    MUSEUM,
    SOCIAL_WELFARE_FACILITY,
    PUBLIC_MARKET,
    TRANSPORT_FACILITY,
    UTILITY_FACILITY,
    ENVIRONMENTAL_MONITORING,
    PUBLIC_SPACE,
    CULTURAL_FACILITY,
    AGRICULTURAL_FACILITY,
    JUSTICE_FACILITY,
    HOUSING_SERVICE,
    OTHER_QUALIFYING_FACILITY,
)

CATEGORY_LABELS: Final[dict[str, str]] = {
    SCHOOL: "Education",
    HEALTH_FACILITY: "Healthcare",
    GOVERNMENT_OFFICE: "Government administration",
    COMMUNITY_FACILITY: "Community and civic",
    EMERGENCY_FACILITY: "Emergency and public safety",
    LIBRARY: "Library and knowledge",
    MUSEUM: "Museum and heritage",
    SOCIAL_WELFARE_FACILITY: "Social welfare",
    PUBLIC_MARKET: "Public market and commerce",
    TRANSPORT_FACILITY: "Transport",
    UTILITY_FACILITY: "Utilities and sanitation",
    ENVIRONMENTAL_MONITORING: "Environmental monitoring",
    PUBLIC_SPACE: "Public space and recreation",
    CULTURAL_FACILITY: "Culture and heritage",
    AGRICULTURAL_FACILITY: "Agriculture and fisheries",
    JUSTICE_FACILITY: "Justice and corrections",
    HOUSING_SERVICE: "Housing and settlements",
    OTHER_QUALIFYING_FACILITY: "Other qualifying facility",
}

CATEGORY_SUBTYPES: Final[dict[str, tuple[str, ...]]] = {
    SCHOOL: (
        "PUBLIC_ELEMENTARY_SCHOOL",
        "PUBLIC_SECONDARY_SCHOOL",
        "PRIVATE_SCHOOL",
        "HIGHER_EDUCATION_INSTITUTION",
        "TRAINING_INSTITUTION",
        "OTHER_SCHOOL",
    ),
    HEALTH_FACILITY: (
        "HOSPITAL",
        "INFIRMARY",
        "RURAL_HEALTH_UNIT",
        "BARANGAY_HEALTH_STATION",
        "CLINIC",
        "LABORATORY",
        "DIALYSIS_CENTER",
        "BIRTHING_HOME",
        "PHARMACY",
        "OTHER_HEALTH_FACILITY",
    ),
    GOVERNMENT_OFFICE: (
        "BARANGAY_HALL",
        "CITY_MUNICIPAL_HALL",
        "PROVINCIAL_CAPITOL",
        "NATIONAL_AGENCY_OFFICE",
        "REVENUE_DISTRICT_OFFICE",
        "POST_OFFICE",
        "NEGOSYO_CENTER",
        "PUBLIC_SERVICE_CENTER",
        "OTHER_GOVERNMENT_OFFICE",
    ),
    COMMUNITY_FACILITY: (
        "MULTIPURPOSE_HALL",
        "BARANGAY_CENTER",
        "COVERED_COURT",
        "CIVIC_CENTER",
        "COMMUNITY_CENTER",
        "OTHER_COMMUNITY_FACILITY",
    ),
    EMERGENCY_FACILITY: (
        "FIRE_STATION",
        "POLICE_STATION",
        "EVACUATION_CENTER",
        "DRRM_CENTER",
        "COMMAND_CENTER",
        "RELIEF_WAREHOUSE",
        "OTHER_EMERGENCY_FACILITY",
    ),
    LIBRARY: (
        "REGIONAL_LIBRARY",
        "PROVINCIAL_LIBRARY",
        "CITY_LIBRARY",
        "MUNICIPAL_LIBRARY",
        "BARANGAY_READING_CENTER",
        "CONGRESSIONAL_LIBRARY",
        "LOCALLY_FUNDED_LIBRARY",
        "PRIVATE_PUBLIC_LIBRARY",
        "OTHER_LIBRARY",
    ),
    MUSEUM: (
        "NATIONAL_MUSEUM",
        "REGIONAL_MUSEUM",
        "AREA_MUSEUM",
        "SITE_MUSEUM",
        "PRIVATE_MUSEUM",
        "OTHER_MUSEUM",
    ),
    SOCIAL_WELFARE_FACILITY: (
        "CRCF",
        "NCDC",
        "SENIOR_CITIZENS_CENTER",
        "WOMEN_CENTER",
        "YOUTH_CENTER",
        "RESIDENTIAL_CARE_FACILITY",
        "OTHER_SOCIAL_WELFARE_FACILITY",
    ),
    PUBLIC_MARKET: (
        "PUBLIC_MARKET",
        "PUBLIC_SLAUGHTERHOUSE",
        "TRADING_POST",
        "OTHER_MARKET_FACILITY",
    ),
    TRANSPORT_FACILITY: (
        "AIRPORT",
        "SEAPORT",
        "FISH_PORT",
        "LAND_TERMINAL",
        "OTHER_TRANSPORT_FACILITY",
    ),
    UTILITY_FACILITY: (
        "WATER_TREATMENT_PLANT",
        "WASTEWATER_TREATMENT_PLANT",
        "SOLID_WASTE_FACILITY",
        "MATERIALS_RECOVERY_FACILITY",
        "LANDFILL",
        "POWER_FACILITY",
        "OTHER_UTILITY_FACILITY",
    ),
    ENVIRONMENTAL_MONITORING: (
        "AIR_QUALITY_MONITORING_STATION",
        "WATER_QUALITY_MONITORING_STATION",
        "WEATHER_STATION",
        "OTHER_MONITORING_STATION",
    ),
    PUBLIC_SPACE: (
        "PUBLIC_PARK",
        "PLAZA",
        "PLAYGROUND",
        "SPORTS_COMPLEX",
        "OTHER_PUBLIC_SPACE",
    ),
    CULTURAL_FACILITY: (
        "CULTURAL_CENTER",
        "ARCHIVE",
        "HERITAGE_SITE",
        "OTHER_CULTURAL_FACILITY",
    ),
    AGRICULTURAL_FACILITY: (
        "FISH_PORT",
        "AGRICULTURAL_STATION",
        "NURSERY",
        "RESEARCH_FARM",
        "SLAUGHTERHOUSE",
        "COLD_STORAGE_WAREHOUSE",
        "MEAT_CUTTING_PLANT",
        "POULTRY_DRESSING_PLANT",
        "MEAT_DISTRIBUTION_CENTER",
        "OTHER_AGRICULTURAL_FACILITY",
    ),
    JUSTICE_FACILITY: (
        "COURT",
        "PUBLIC_LEGAL_CENTER",
        "JAIL",
        "OTHER_JUSTICE_FACILITY",
    ),
    HOUSING_SERVICE: (
        "HOUSING_SERVICE_CENTER",
        "RESETTLEMENT_FACILITY",
        "OTHER_HOUSING_FACILITY",
    ),
    OTHER_QUALIFYING_FACILITY: ("OTHER_QUALIFYING_FACILITY",),
}

# Flattened view for validating a source claim without first knowing its category.
FACILITY_SUBTYPES: Final = tuple(
    dict.fromkeys(subtype for subtypes in CATEGORY_SUBTYPES.values() for subtype in subtypes)
)

# Human-readable labels for clients that do not want to reproduce the taxonomy.
# Most codes read naturally when underscored words are lowercased; only acronyms
# and established programme names need an override.
_SUBTYPE_LABEL_OVERRIDES: Final[dict[str, str]] = {
    "CRCF": "Centers and residential care facilities",
    "NCDC": "NCDC",
    "DRRM_CENTER": "DRRM center",
}

SUBTYPE_LABELS: Final[dict[str, str]] = {
    subtype: _SUBTYPE_LABEL_OVERRIDES.get(subtype, subtype.replace("_", " ").capitalize())
    for subtype in FACILITY_SUBTYPES
}

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

FUNCTION_CODES: Final = (
    "GOVERNMENT_ADMINISTRATION",
    "PUBLIC_SERVICE_COUNTER",
    "BARANGAY_HALL",
    "CITY_MUNICIPAL_HALL",
    "PROVINCIAL_CAPITOL",
    "COMMUNITY_ASSEMBLY",
    "MULTIPURPOSE_HALL",
    "COVERED_COURT",
    "SPORTS_RECREATION",
    "PUBLIC_SPACE",
    "PUBLIC_LIBRARY",
    "MUSEUM",
    "ARCHIVE",
    "CULTURAL_HERITAGE",
    "EDUCATION",
    "TRAINING",
    "HEALTHCARE",
    "SOCIAL_WELFARE",
    "RESIDENTIAL_CARE",
    "PUBLIC_MARKET",
    "SLAUGHTERHOUSE",
    "FOOD_SAFETY",
    "POSTAL_SERVICE",
    "TAX_ADMINISTRATION",
    "BUSINESS_ADVISORY",
    "SOCIAL_SECURITY_SERVICE",
    "LICENSING_SERVICE",
    "FIRE_RESPONSE",
    "POLICE_SERVICE",
    "EMERGENCY_RESPONSE",
    "EVACUATION_SITE",
    "RELIEF_DISTRIBUTION",
    "DRRM_COORDINATION",
    "AIR_TRANSPORT",
    "SEA_TRANSPORT",
    "FISH_PORT",
    "LAND_TRANSPORT",
    "WATER_SERVICE",
    "WASTEWATER_SERVICE",
    "SOLID_WASTE_SERVICE",
    "POWER_SERVICE",
    "ENVIRONMENTAL_MONITORING",
    "AGRICULTURAL_SERVICE",
    "FISHERIES_SERVICE",
    "JUSTICE_SERVICE",
    "LEGAL_AID",
    "HOUSING_SERVICE",
    "OTHER_PUBLIC_SERVICE",
)

# ---------------------------------------------------------------------------
# Candidate defaults
# ---------------------------------------------------------------------------

# Categories whose records are public-access venues by default only when the
# source documents public access. Kept explicit so the rule is reviewable.
VENUE_CATEGORIES: Final = frozenset({PUBLIC_SPACE, CULTURAL_FACILITY, LIBRARY, MUSEUM})


def derive_inclusion_class(ownership: str | None) -> str:
    """Return the conservative inclusion class for a legacy ownership value.

    Unknown ownership is never guessed. It becomes an unclassified record that
    is published without asserting an owner the source never supplied.
    """

    value = (ownership or "").strip().lower()
    if value == "government":
        return GOVERNMENT_FACILITY
    if value == "private":
        return PRIVATE_PUBLIC_SERVICE_PROVIDER
    return DISCOVERY_CANDIDATE


def ownership_type_from_legacy(ownership: str | None) -> str:
    value = (ownership or "").strip().lower()
    if value == "government":
        return GOVERNMENT_UNSPECIFIED
    if value == "private":
        return PRIVATE_UNSPECIFIED
    return UNKNOWN


def is_public_class(value: str | None) -> bool:
    return value in PUBLIC_INCLUSION_CLASSES


def category_label(category: str | None) -> str:
    return CATEGORY_LABELS.get(category or "", category or "Unknown category")
