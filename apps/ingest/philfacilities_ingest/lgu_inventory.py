"""Validation for LGU facility-inventory submissions.

The template is deliberately an *intake* format, not a publication format. A valid
row is queued for review; it is not automatically public. Personal contact fields and
free-text security details are rejected before import.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from philfacilities_api.taxonomy import (
    ACCESS_CLASSES,
    CATEGORY_SUBTYPES,
    FACILITY_CATEGORIES,
    INCLUSION_CLASSES,
    OPERATOR_TYPES,
    OWNERSHIP_TYPES,
)

from .eligibility import ALLOWED_FACILITY_KINDS

REQUIRED_COLUMNS = (
    "lgu_psgc_code",
    "lgu_name",
    "facility_name",
    "facility_type",
    "facility_subtype",
    "facility_kind",
    "ownership_type",
    "operator_type",
    "address_text",
    "reference_date",
    "source_reference",
)
OPTIONAL_COLUMNS = (
    "lgu_facility_id",
    "inclusion_class",
    "public_access_class",
    "barangay_psgc_code",
    "barangay_name",
    "municipality_city",
    "province_name",
    "region_name",
    "latitude",
    "longitude",
    "coordinate_precision",
    "coordinate_method",
    "owner_name",
    "operator_name",
    "manager_name",
    "funding_source",
    "capacity_value",
    "capacity_unit",
    "operational_status_evidence",
    "status_as_of",
    "access_conditions",
    "notes",
)
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
PERSONAL_COLUMNS = frozenset(
    {
        "head_name",
        "officer_name",
        "contact_person",
        "contact_name",
        "mobile",
        "mobile_number",
        "personal_email",
        "email",
        "telephone",
        "phone",
        "fax",
    }
)
SENSITIVE_COLUMNS = frozenset(
    {
        "security_detail",
        "guard_count",
        "patrol_route",
        "radio_frequency",
        "cctv",
        "alarm_code",
        "weapon_count",
    }
)
COORDINATE_PRECISIONS = frozenset(
    {
        "gps_verified",
        "field_verified",
        "map_geocoded",
        "barangay_centroid",
        "municipality_centroid",
        "unknown",
    }
)


@dataclass
class LguInventoryIssue:
    row_number: int
    code: str
    severity: str
    message: str
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_number": self.row_number,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
        }


@dataclass
class LguInventoryValidation:
    rows: int = 0
    accepted: int = 0
    rejected: int = 0
    issues: list[LguInventoryIssue] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def read_inventory(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = [header.strip() for header in (reader.fieldnames or [])]
        rows = [
            {key.strip(): (value or "").strip() for key, value in row.items() if key is not None}
            for row in reader
        ]
    return headers, rows


def validate_inventory(path: Path) -> LguInventoryValidation:
    headers, rows = read_inventory(path)
    result = LguInventoryValidation(rows=len(rows))
    for header in headers:
        if header in PERSONAL_COLUMNS:
            result.issues.append(
                LguInventoryIssue(
                    0,
                    "personal_field_not_accepted",
                    "fatal",
                    f"Column {header!r} is personal/contact data; submit institutional "
                    "fields only.",
                    header,
                )
            )
        if header in SENSITIVE_COLUMNS:
            result.issues.append(
                LguInventoryIssue(
                    0,
                    "sensitive_security_field_not_accepted",
                    "fatal",
                    f"Column {header!r} is security-sensitive and is not accepted.",
                    header,
                )
            )
    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    if missing:
        result.issues.append(
            LguInventoryIssue(
                0,
                "missing_columns",
                "fatal",
                "Missing required columns: " + ", ".join(missing),
            )
        )
    if any(issue.severity == "fatal" for issue in result.issues):
        result.rejected = len(rows)
        return result

    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, start=2):
        row_issues: list[LguInventoryIssue] = []
        psgc = row.get("lgu_psgc_code", "")
        if not psgc or not psgc.isdigit() or len(psgc) != 10:
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "invalid_lgu_psgc",
                    "error",
                    "lgu_psgc_code must be a 10-digit PSGC string with leading zeros.",
                    "lgu_psgc_code",
                )
            )
        if not row.get("lgu_name"):
            row_issues.append(
                LguInventoryIssue(index, "missing_lgu_name", "error", "lgu_name is required.")
            )
        if not row.get("facility_name"):
            row_issues.append(
                LguInventoryIssue(
                    index, "missing_facility_name", "error", "facility_name is required."
                )
            )
        facility_type = row.get("facility_type", "")
        if facility_type not in FACILITY_CATEGORIES:
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "invalid_facility_type",
                    "error",
                    f"Unknown facility_type {facility_type!r}.",
                    "facility_type",
                )
            )
        else:
            subtype = row.get("facility_subtype", "")
            allowed = CATEGORY_SUBTYPES.get(facility_type, ())
            if subtype not in allowed:
                row_issues.append(
                    LguInventoryIssue(
                        index,
                        "invalid_facility_subtype",
                        "error",
                        f"Subtype {subtype!r} is not valid for {facility_type!r}.",
                        "facility_subtype",
                    )
                )
        if row.get("facility_kind", "") not in ALLOWED_FACILITY_KINDS:
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "invalid_facility_kind",
                    "error",
                    "facility_kind must be facility, site, building or facility_unit; "
                    "projects and infrastructure assets belong to the related-asset model.",
                    "facility_kind",
                )
            )
        ownership_type = row.get("ownership_type", "")
        if ownership_type not in OWNERSHIP_TYPES:
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "invalid_ownership_type",
                    "error",
                    f"Unknown ownership_type {ownership_type!r}.",
                    "ownership_type",
                )
            )
        operator_type = row.get("operator_type", "")
        if operator_type not in OPERATOR_TYPES:
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "invalid_operator_type",
                    "error",
                    f"Unknown operator_type {operator_type!r}.",
                    "operator_type",
                )
            )
        inclusion_class = row.get("inclusion_class", "")
        if inclusion_class and inclusion_class not in INCLUSION_CLASSES:
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "invalid_inclusion_class",
                    "error",
                    f"Unknown inclusion_class {inclusion_class!r}.",
                    "inclusion_class",
                )
            )
        access_class = row.get("public_access_class", "")
        if access_class and access_class not in ACCESS_CLASSES:
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "invalid_public_access_class",
                    "error",
                    f"Unknown public_access_class {access_class!r}.",
                    "public_access_class",
                )
            )
        barangay_psgc = row.get("barangay_psgc_code", "")
        if barangay_psgc and (
            not barangay_psgc.isdigit()
            or len(barangay_psgc) != 10
            or not barangay_psgc.startswith(psgc[:7])
        ):
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "invalid_barangay_psgc",
                    "error",
                    "barangay_psgc_code must be a 10-digit PSGC string that belongs "
                    "to the supplied LGU.",
                    "barangay_psgc_code",
                )
            )
        if not row.get("source_reference"):
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "missing_source_reference",
                    "error",
                    "source_reference is required for provenance.",
                    "source_reference",
                )
            )
        reference_date = row.get("reference_date", "")
        if not reference_date:
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "missing_reference_date",
                    "error",
                    "reference_date is required.",
                    "reference_date",
                )
            )
        else:
            try:
                date.fromisoformat(reference_date)
            except ValueError:
                row_issues.append(
                    LguInventoryIssue(
                        index,
                        "invalid_reference_date",
                        "error",
                        "reference_date must be ISO YYYY-MM-DD.",
                        "reference_date",
                    )
                )
        latitude, longitude = row.get("latitude", ""), row.get("longitude", "")
        if bool(latitude) != bool(longitude):
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "incomplete_coordinates",
                    "error",
                    "latitude and longitude must be supplied together or both left blank.",
                )
            )
        if latitude and longitude:
            try:
                lat_value, lon_value = float(latitude), float(longitude)
            except ValueError:
                row_issues.append(
                    LguInventoryIssue(
                        index, "invalid_coordinates", "error", "Coordinates are not numeric."
                    )
                )
            else:
                if not (4.2 <= lat_value <= 21.5 and 116.0 <= lon_value <= 127.0):
                    row_issues.append(
                        LguInventoryIssue(
                            index,
                            "coordinates_outside_philippines",
                            "error",
                            "Coordinates fall outside the Philippine bounding box.",
                        )
                    )
            if row.get("coordinate_precision", "") not in COORDINATE_PRECISIONS:
                row_issues.append(
                    LguInventoryIssue(
                        index,
                        "missing_coordinate_precision",
                        "error",
                        "coordinate_precision is required when coordinates are supplied.",
                        "coordinate_precision",
                    )
                )
        key = (psgc, row.get("facility_name", "").casefold())
        if key in seen:
            row_issues.append(
                LguInventoryIssue(
                    index,
                    "duplicate_facility_name_in_lgu",
                    "warning",
                    "The same facility name appears more than once in this LGU file; "
                    "review whether these are distinct sites or a duplicate.",
                )
            )
        seen.add(key)
        if row_issues:
            result.issues.extend(row_issues)
            if any(issue.severity == "error" for issue in row_issues):
                result.rejected += 1
            else:
                result.accepted += 1
        else:
            result.accepted += 1
    return result
