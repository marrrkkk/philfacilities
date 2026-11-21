from __future__ import annotations

import io

from openpyxl import load_workbook

from ..contracts import (
    FacilityCandidate,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ResourceData,
    SchoolData,
    ValidationIssue,
    ValidationResult,
)
from .common import (
    RequiredColumnsError,
    clean_text,
    first_present,
    jsonify,
    normalise_code,
    normalise_header,
    normalise_ownership,
    parse_bool,
    parse_float,
    parse_int,
    read_csv_rows,
    require_column_groups,
    require_columns,
)

SCHOOL_ID_ALIASES = ["school_id", "schoolid", "school_id_no", "beis_school_id"]
SCHOOL_NAME_ALIASES = ["school_name", "schoolname", "name_of_school"]
OWNERSHIP_ALIASES = ["sector", "ownership", "school_sector"]
PSGC_ALIASES = ["psgc_code", "barangay_psgc", "barangay_code"]
LAT_ALIASES = ["latitude", "lat", "y"]
LON_ALIASES = ["longitude", "lon", "lng", "x"]
PRECISION_ALIASES = ["coordinate_precision", "location_precision", "precision"]
METHOD_ALIASES = ["coordinate_method", "location_method", "method"]
SCHOOL_YEAR_ALIASES = ["school_year", "reference_school_year", "sy"]


def _xlsx_rows(
    content: bytes,
    sheet_name: str | None = None,
    header_aliases: list[list[str]] | None = None,
) -> tuple[list[str], list[dict]]:
    groups = header_aliases or [SCHOOL_ID_ALIASES, SCHOOL_NAME_ALIASES]
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheet = None
        if sheet_name:
            sheet = workbook[sheet_name] if sheet_name in workbook.sheetnames else None
        if sheet is None:
            for candidate in workbook.worksheets:
                if candidate.title.lower() in {"masterlist", "schools", "school masterlist"}:
                    sheet = candidate
                    break
        if sheet is None:
            sheet = workbook.worksheets[0]
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    header_index = None
    headers: list[str] = []
    for index, row in enumerate(rows[:20]):
        normalised = [normalise_header(value) for value in row]
        if all(set(normalised) & set(aliases) for aliases in groups):
            header_index = index
            headers = normalised
            break
    if header_index is None:
        raise RequiredColumnsError(
            f"DepEd workbook {sheet.title!r}: could not locate a header row containing "
            f"{', '.join('/'.join(aliases[:2]) for aliases in groups)}."
        )
    result = []
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        payload = {
            headers[i]: jsonify(value)
            for i, value in enumerate(row)
            if i < len(headers) and headers[i]
        }
        payload["_sheet"] = sheet.title
        payload["_row"] = offset
        if any(value not in (None, "") for value in payload.values()):
            result.append(payload)
    return headers, result


def _read_rows(
    content: bytes,
    filename: str,
    sheet_name: str | None = None,
    header_aliases: list[list[str]] | None = None,
):
    if filename.lower().endswith(".csv"):
        return read_csv_rows(content)
    return _xlsx_rows(content, sheet_name, header_aliases)


class DepEdMasterlistAdapter:
    source_code = "deped"
    parser_version = "deped-masterlist-1.0.0"
    schema_version = "deped-masterlist-2023-24-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        headers, rows = _read_rows(spec.content, spec.filename, "Masterlist")
        require_column_groups(
            headers,
            [SCHOOL_ID_ALIASES, SCHOOL_NAME_ALIASES],
            "DepEd masterlist",
        )
        parsed: list[ParsedRow] = []
        for row in rows:
            school_id = normalise_code(first_present(row, SCHOOL_ID_ALIASES))
            if not school_id:
                continue
            parsed.append(
                ParsedRow(
                    source_record_key=school_id,
                    row_reference=f"sheet:{row.get('_sheet')}:row:{row.get('_row')}",
                    raw_payload=row,
                    normalized_payload=row,
                )
            )
        return ParsedRelease(
            rows=parsed,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            school_id = normalise_code(first_present(payload, SCHOOL_ID_ALIASES))
            name = clean_text(first_present(payload, SCHOOL_NAME_ALIASES))
            if not school_id:
                issues.append(
                    ValidationIssue(
                        "missing_school_id",
                        "fatal",
                        "Missing school ID",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if school_id in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_school_id",
                        "error",
                        f"Duplicate school ID {school_id}",
                        {"school_id": school_id},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(school_id)
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_school_name",
                        "fatal",
                        f"School {school_id} has no name",
                        {"school_id": school_id},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            latitude = parse_float(first_present(payload, LAT_ALIASES))
            longitude = parse_float(first_present(payload, LON_ALIASES))
            if (latitude is None) != (longitude is None):
                issues.append(
                    ValidationIssue(
                        "partial_coordinates",
                        "warning",
                        f"School {school_id} has only one coordinate value",
                        row_reference=row.row_reference,
                    )
                )
            if latitude is not None and not -90 <= latitude <= 90:
                issues.append(
                    ValidationIssue(
                        "latitude_range",
                        "fatal",
                        f"School {school_id} latitude is out of range",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
            if longitude is not None and not -180 <= longitude <= 180:
                issues.append(
                    ValidationIssue(
                        "longitude_range",
                        "fatal",
                        f"School {school_id} longitude is out of range",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            school_id = normalise_code(first_present(payload, SCHOOL_ID_ALIASES))
            name = clean_text(first_present(payload, SCHOOL_NAME_ALIASES))
            if not school_id or not name:
                continue
            latitude = parse_float(first_present(payload, LAT_ALIASES))
            longitude = parse_float(first_present(payload, LON_ALIASES))
            precision = clean_text(first_present(payload, PRECISION_ALIASES)) or "unknown"
            method = clean_text(first_present(payload, METHOD_ALIASES))
            candidates.append(
                FacilityCandidate(
                    source_record_key=school_id,
                    source_entity_id=school_id,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="school",
                    facility_subtype=clean_text(
                        first_present(payload, ["school_type", "facility_type"])
                    ),
                    ownership=normalise_ownership(first_present(payload, OWNERSHIP_ALIASES)),
                    record_status="active_in_registry",
                    location=LocationData(
                        latitude=latitude,
                        longitude=longitude,
                        precision=precision
                        if precision
                        in {
                            "gps_verified",
                            "field_verified",
                            "source_gps",
                            "map_geocoded",
                            "barangay_centroid",
                            "unknown",
                        }
                        else "unknown",
                        method=method,
                        address_text=clean_text(
                            first_present(payload, ["address", "school_address", "street"])
                        ),
                        psgc_code=normalise_code(first_present(payload, PSGC_ALIASES)),
                    ),
                    school=SchoolData(
                        deped_school_id=school_id,
                        sector=clean_text(first_present(payload, OWNERSHIP_ALIASES)),
                        school_management=clean_text(
                            first_present(payload, ["school_management", "management"])
                        ),
                        offers_es=parse_bool(first_present(payload, ["offers_es", "elementary"])),
                        offers_jhs=parse_bool(
                            first_present(payload, ["offers_jhs", "junior_high_school"])
                        ),
                        offers_shs=parse_bool(
                            first_present(payload, ["offers_shs", "senior_high_school"])
                        ),
                    ),
                )
            )
        return candidates


class DepEdEnrollmentAdapter:
    source_code = "deped"
    parser_version = "deped-enrollment-1.0.0"
    schema_version = "deped-enrollment-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        headers, rows = _read_rows(
            spec.content,
            spec.filename,
            "Enrollment",
            [
                SCHOOL_ID_ALIASES,
                SCHOOL_YEAR_ALIASES,
                ["grade_level", "grade", "level"],
                ["learner_count", "enrolment", "enrollment"],
            ],
        )
        require_columns(
            headers,
            {"school_id", "school_year", "grade_level", "learner_count"},
            "DepEd enrollment",
        )
        grouped: dict[tuple[str, str], dict] = {}
        for row in rows:
            school_id = normalise_code(first_present(row, SCHOOL_ID_ALIASES))
            school_year = clean_text(first_present(row, SCHOOL_YEAR_ALIASES))
            if not school_id or not school_year:
                continue
            key = (school_id, school_year)
            group = grouped.setdefault(
                key,
                {
                    "school_id": school_id,
                    "school_year": school_year,
                    "rows": [],
                },
            )
            group["rows"].append(row)
        parsed_rows = []
        for (school_id, school_year), group in grouped.items():
            parsed_rows.append(
                ParsedRow(
                    source_record_key=f"{school_id}:{school_year}",
                    row_reference=f"rows:{len(group['rows'])}",
                    raw_payload=group,
                    normalized_payload=group,
                )
            )
        return ParsedRelease(
            rows=parsed_rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        rejected = 0
        for row in parsed.rows:
            for source_row in row.normalized_payload["rows"]:
                count = parse_int(
                    first_present(source_row, ["learner_count", "enrolment", "enrollment"])
                )
                if count is None:
                    issues.append(
                        ValidationIssue(
                            "missing_or_invalid_learner_count",
                            "error",
                            "Enrollment row has a missing or invalid learner count",
                            row_reference=row.row_reference,
                        )
                    )
                    rejected += 1
                    break
                if count < 0:
                    issues.append(
                        ValidationIssue(
                            "negative_learner_count",
                            "fatal",
                            "Enrollment counts cannot be negative",
                            {"value": count},
                            row.row_reference,
                        )
                    )
                    rejected += 1
                    break
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        # Enrollment counts stay in the preserved raw release and are validated
        # above; no enrollment observations are derived into canonical records.
        candidates = []
        for row in parsed.rows:
            group = row.normalized_payload
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=group["school_id"],
                    row_reference=row.row_reference,
                    display_name="",
                    facility_type="school",
                    facility_subtype=None,
                    ownership="unknown",
                    record_status="unknown",
                    location=LocationData(),
                    school=SchoolData(deped_school_id=group["school_id"]),
                )
            )
        return candidates


class DepEdResourceAdapter:
    source_code = "deped"
    parser_version = "deped-resources-1.0.0"
    schema_version = "deped-resources-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        headers, rows = _read_rows(
            spec.content,
            spec.filename,
            "Facilities",
            [
                SCHOOL_ID_ALIASES,
                SCHOOL_YEAR_ALIASES,
                ["resource_code"],
                ["value", "value_numeric"],
            ],
        )
        require_columns(
            headers,
            {"school_id", "school_year", "resource_code", "value"},
            "DepEd resources",
        )
        grouped: dict[tuple[str, str], dict] = {}
        for row in rows:
            school_id = normalise_code(first_present(row, SCHOOL_ID_ALIASES))
            school_year = clean_text(first_present(row, SCHOOL_YEAR_ALIASES))
            if not school_id or not school_year:
                continue
            group = grouped.setdefault(
                (school_id, school_year),
                {"school_id": school_id, "school_year": school_year, "rows": []},
            )
            group["rows"].append(row)
        return ParsedRelease(
            rows=[
                ParsedRow(
                    source_record_key=f"{school_id}:{school_year}",
                    row_reference=f"rows:{len(group['rows'])}",
                    raw_payload=group,
                    normalized_payload=group,
                )
                for (school_id, school_year), group in grouped.items()
            ],
            parser_version=self.parser_version,
            schema_version=self.schema_version,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues = []
        rejected = 0
        for row in parsed.rows:
            for source_row in row.normalized_payload["rows"]:
                if parse_float(first_present(source_row, ["value", "value_numeric"])) is None:
                    issues.append(
                        ValidationIssue(
                            "invalid_resource_value",
                            "error",
                            "Resource observation has a non-numeric value",
                            row_reference=row.row_reference,
                        )
                    )
                    rejected += 1
                    break
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates = []
        for row in parsed.rows:
            group = row.normalized_payload
            resources = []
            for source_row in group["rows"]:
                resources.append(
                    ResourceData(
                        school_year=group["school_year"],
                        resource_category=clean_text(
                            first_present(source_row, ["resource_category", "category"])
                        )
                        or "facility",
                        resource_code=clean_text(
                            first_present(source_row, ["resource_code", "code"])
                        )
                        or "unknown",
                        value_numeric=parse_float(
                            first_present(source_row, ["value", "value_numeric"])
                        ),
                        value_text=clean_text(
                            first_present(source_row, ["value_text", "text_value"])
                        ),
                        unit=clean_text(first_present(source_row, ["unit", "units"])),
                    )
                )
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=group["school_id"],
                    row_reference=row.row_reference,
                    display_name="",
                    facility_type="school",
                    facility_subtype=None,
                    ownership="unknown",
                    record_status="unknown",
                    location=LocationData(),
                    school=SchoolData(
                        deped_school_id=group["school_id"],
                        resources=resources,
                    ),
                )
            )
        return candidates
