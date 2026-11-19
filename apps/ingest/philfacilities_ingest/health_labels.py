"""Controlled health-facility labels shared by adapters and cleanup passes.

PhilHealth benefit-package PDFs mix three different things in their category
columns: a physical facility class (``Hospital``), a hospital service level
(``LEVEL 1``), and a benefit package or profession (``Postpartum``,
``GAMOT Package Providers``, ``dentist``). Only the first belongs on
``facility_subtype``; everything else stays on the health profile or the
accreditation row.
"""

from __future__ import annotations

from philfacilities_api.taxonomy import CATEGORY_SUBTYPES

# Canonical health subtypes. ``INFIRMARY`` is part of the taxonomy because the
# DOH NHFR publishes it as a specific class.
CANONICAL_HEALTH_SUBTYPES = frozenset(CATEGORY_SUBTYPES["health_facility"])

# Raw label -> controlled subtype. Keys are case/space/underscore folded.
HEALTH_SUBTYPE_ALIASES: dict[str, str] = {
    "hospital": "HOSPITAL",
    "infirmary": "INFIRMARY",
    "rural health unit": "RURAL_HEALTH_UNIT",
    "barangay health station": "BARANGAY_HEALTH_STATION",
    "clinic": "CLINIC",
    "medical clinic": "CLINIC",
    "health and medical clinic": "CLINIC",
    "social hygiene clinic": "CLINIC",
    "ambulatory surgical clinic": "CLINIC",
    "ambulatory surgical clinics": "CLINIC",
    "yakap clinic": "CLINIC",
    "yakap clinics": "CLINIC",
    "laboratory": "LABORATORY",
    "clinical laboratory": "LABORATORY",
    "general clinic laboratory": "LABORATORY",
    "drug testing laboratory": "LABORATORY",
    "covid 19 testing laboratory": "LABORATORY",
    "covid 19 testing laboratories": "LABORATORY",
    "dialysis": "DIALYSIS_CENTER",
    "dialysis center": "DIALYSIS_CENTER",
    "dialysis clinic": "DIALYSIS_CENTER",
    "freestanding dialysis clinic": "DIALYSIS_CENTER",
    "freestanding dialysis clinics": "DIALYSIS_CENTER",
    "dental laboratory": "LABORATORY",
    "laboratory for drinking water analysis": "LABORATORY",
    "clinical laboratory for molecular pathology": "LABORATORY",
    "laboratory for chemical analysis for dialysis wate": "LABORATORY",
    "special clinical laboratory": "LABORATORY",
    "research and teaching laboratory": "LABORATORY",
    "medical outpatient clinic": "CLINIC",
    "school clinic": "CLINIC",
    "detention facility clinic": "CLINIC",
    "bagong urgent care and ambulatory service": "CLINIC",
    "medical facility for overseas workers & seafarers": "CLINIC",
    "stem cell treatment clinics": "CLINIC",
    "birthing home": "BIRTHING_HOME",
    "birthing centre": "BIRTHING_HOME",
    "birthing center": "BIRTHING_HOME",
    "pharmacy": "PHARMACY",
    "drugstore": "PHARMACY",
    "other health facility": "OTHER_HEALTH_FACILITY",
    # Facility classes with no dedicated controlled subtype. The exact source
    # label stays on the health profile.
    "blood bank": "OTHER_HEALTH_FACILITY",
    "blood center": "OTHER_HEALTH_FACILITY",
    "blood service facility": "OTHER_HEALTH_FACILITY",
    "cancer treatment facility": "OTHER_HEALTH_FACILITY",
    "cancer treatment facilities": "OTHER_HEALTH_FACILITY",
    "psychiatric care facility": "OTHER_HEALTH_FACILITY",
    "newborn screening center": "OTHER_HEALTH_FACILITY",
    "animal bite treatment center": "CLINIC",
    "animal bite center": "CLINIC",
    "kidney transplant facility": "OTHER_HEALTH_FACILITY",
    "community isolation units": "OTHER_HEALTH_FACILITY",
    "doh designated hiv treatment hubs": "OTHER_HEALTH_FACILITY",
    "drug abuse treatment and rehabilitation centers": "OTHER_HEALTH_FACILITY",
    "drug abuse treatment and rehab centers": "OTHER_HEALTH_FACILITY",
    "hospice": "OTHER_HEALTH_FACILITY",
    "tb dots centers": "OTHER_HEALTH_FACILITY",
    "community health center": "CLINIC",
    "primary health care": "CLINIC",
    "primary health care center": "CLINIC",
    "puericulture": "CLINIC",
    "puericulture center": "CLINIC",
    "puericulture centre": "CLINIC",
}

# Labels that are explicitly not a facility class. They become unknown
# (``None``) rather than a misleading subtype.
NON_FACILITY_LABELS = frozenset(
    {
        "alternative",
        "ambulance service provider",
        "animal bite package providers",
        "antenatal",
        "audiologist",
        "blood donation",
        "cancer screening test providers",
        "community health worker",
        "community healthcare worker",
        "counselling",
        "covid 19 home isolation benefit package providers",
        "dentist",
        "doctor",
        "doctor and pharmacy",
        "doctors",
        "family planning providers",
        "first aid",
        "gamot package providers",
        "health aide",
        "level 1",
        "level 2",
        "level 3",
        "maternity care providers",
        "midwife",
        "occupational therapist",
        "optometrist",
        "optometry benefit package providers",
        "oral health benefit package providers",
        "outpatient malaria package providers",
        "paramedic",
        "physiotherapist",
        "postpartum",
        "psychotherapist",
        "rehabilitation",
        "sample collection",
        "services",
        "severe acute malnutrition package providers",
        "speech therapist",
        "transvaginal ultrasound",
        "veterinary",
        "yes",
    }
)

# Labels that may describe a real facility but do not establish one controlled
# class. They are cleared from ``facility_subtype`` and kept on the health
# profile for review rather than guessed from the facility name.
AMBIGUOUS_LABELS = frozenset(
    {
        # PhilHealth's "INF/DISP" applies to hospitals and clinics alike and
        # does not establish whether the place is an infirmary or a dispensary.
        "inf disp",
        # A truncated source label; the name is not evidence of the class.
        "centre",
    }
)

# Raw values that describe a building or a service point, not a health
# facility class. They can appear when an OSM feature is imported through both
# a health and an education/community layer.
NON_HEALTH_LABELS = frozenset(
    {
        "local government office",
        "office and rescue",
        "school",
        "university",
        "vaccination center",
        "vaccination centre",
    }
)


def _fold(value: str | None) -> str:
    return " ".join(
        (value or "").replace("_", " ").replace("-", " ").replace("/", " ").split()
    ).lower()


def classify_health_subtype(value: str | None) -> tuple[bool, str | None]:
    """Return ``(known, controlled_subtype)`` for a raw health label.

    ``known`` is true only when the label carries a decision: either a mapped
    controlled subtype or an explicit non-facility label that should be
    cleared. An unrecognised label is left alone so a future review can map it;
    silently clearing it would discard evidence.
    """

    if value is None:
        return True, None
    stripped = value.strip()
    if not stripped:
        return True, None
    if stripped.upper() in CANONICAL_HEALTH_SUBTYPES:
        return True, stripped.upper()
    folded = _fold(stripped)
    if folded in HEALTH_SUBTYPE_ALIASES:
        return True, HEALTH_SUBTYPE_ALIASES[folded]
    if folded.endswith("specialty clinic"):
        return True, "CLINIC"
    if folded in NON_FACILITY_LABELS or folded in AMBIGUOUS_LABELS:
        return True, None
    if folded in NON_HEALTH_LABELS:
        return True, None
    return False, None
