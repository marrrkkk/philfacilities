"""Department of Trade and Industry Negosyo Center directory adapter.

The public Negosyo Center finder is backed by two unauthenticated JSON endpoints:
a region overview and a paginated by-region listing. The listing supplies the
center name, postal address, region/province/city labels and an active flag. It
does not supply coordinates, PSGC codes, ownership, operator, hours or access
conditions.

A Negosyo Center is a government business-advisory service unit. Many are hosted
inside city halls, SUCs or other partner premises, so this adapter records the
center as a ``facility_unit`` and does not create or classify the host building.
Ownership and operator remain unspecified because the directory does not state
them. Directory presence and the source active flag are not treated as proof of
current operation or walk-in availability.

Contact fields are retained only in the private preserved artifact; the normalized
public payload excludes phone and email values.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from ..acquisition import AcquisitionError, HttpAcquirer
from ..contracts import (
    FacilityCandidate,
    FunctionData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ValidationIssue,
    ValidationResult,
)
from .common import clean_text, normalise_code

FINDER_URL = "https://negosyocenter.dti.gov.ph/negosyo-center-directory"
OVERVIEW_URL = "https://negosyocenter.dti.gov.ph/api/negosyo-centers/regions-overview"
BY_REGION_URL = "https://negosyocenter.dti.gov.ph/api/negosyo-centers/by-region"
TERMS_URL = "https://negosyocenter.dti.gov.ph/terms-and-conditions"
PUBLIC_FIELDS = ("id", "region", "province", "city", "name", "address", "is_active")


def _decode_json(result: Any, url: str) -> Any:
    if result.status_code >= 400:
        raise AcquisitionError(
            f"DTI Negosyo Center endpoint {url} returned HTTP {result.status_code}.",
            result=result,
        )
    try:
        return json.loads(result.content)
    except json.JSONDecodeError as exc:
        raise AcquisitionError(
            f"DTI Negosyo Center endpoint {url} did not return valid JSON.",
            result=result,
        ) from exc


def fetch_negosyo_centers(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Fetch every region page and build a preserved JSON acquisition artifact."""

    overview_result = acquirer.fetch(OVERVIEW_URL)
    overview = _decode_json(overview_result, OVERVIEW_URL)
    if not isinstance(overview, list) or not overview:
        raise AcquisitionError(
            "DTI Negosyo Center region overview contained no regions.",
            result=overview_result,
        )
    regions = [
        clean_text(entry.get("region"))
        for entry in overview
        if isinstance(entry, dict) and clean_text(entry.get("region"))
    ]
    if not regions:
        raise AcquisitionError(
            "DTI Negosyo Center region overview did not expose region names.",
            result=overview_result,
        )

    records: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    pages = 0
    for region in regions:
        page = 1
        while True:
            query = urlencode({"region": region, "page": page, "per_page": 100})
            url = f"{BY_REGION_URL}?{query}"
            result = acquirer.fetch(url)
            payload = _decode_json(result, url)
            if not isinstance(payload, dict):
                raise AcquisitionError(
                    f"DTI Negosyo Center region page {url} was not a paginated object.",
                    result=result,
                )
            pages += 1
            for record in payload.get("data") or []:
                if not isinstance(record, dict):
                    continue
                identifier = record.get("id")
                if identifier in seen_ids:
                    continue
                seen_ids.add(identifier)
                records.append({key: record.get(key) for key in (*PUBLIC_FIELDS, "phone", "email")})
            if page >= int(payload.get("last_page") or 1):
                break
            page += 1

    if not records:
        raise AcquisitionError("DTI Negosyo Center directory returned no records.")

    artifact = {
        "finder_url": FINDER_URL,
        "overview_url": OVERVIEW_URL,
        "by_region_url": BY_REGION_URL,
        "terms_url": TERMS_URL,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "regions": regions,
        "pages_fetched": pages,
        "record_count": len(records),
        "note": (
            "Public DTI Negosyo Center directory artifact. Contact fields are retained "
            "only in this private raw release; normalized public rows expose institutional "
            "name, address and geographic labels only. No coordinates are present."
        ),
        "records": records,
    }
    metadata = {
        "regions": len(regions),
        "pages_fetched": pages,
        "records": len(records),
        "finder_url": FINDER_URL,
    }
    return json.dumps(artifact, indent=2, ensure_ascii=False).encode("utf-8"), metadata


class DtiNegosyoCenterAdapter:
    source_code = "dti-negosyo"
    parser_version = "dti-negosyo-json-1.0.0"
    schema_version = "dti-negosyo-json-v1"
    expected_columns = {"required": {"id", "name", "region", "province", "city"}}  # noqa: RUF012

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def discover(self, input_path: str | None) -> ReleaseSpec:
        return self.spec

    def acquire(self, spec: ReleaseSpec) -> bytes:
        return spec.content

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        try:
            payload = json.loads(spec.content)
        except json.JSONDecodeError as exc:
            raise ValueError("DTI Negosyo Center release is not a JSON artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("DTI Negosyo Center artifact contains no records.")
        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            public_record = {key: record.get(key) for key in PUBLIC_FIELDS}
            source_id = normalise_code(record.get("id"))
            if not source_id:
                continue
            rows.append(
                ParsedRow(
                    source_record_key=f"DTI-NC:{source_id}",
                    row_reference=f"dti-json:{index}",
                    raw_payload=record,
                    normalized_payload=public_record,
                )
            )
        if not rows:
            raise ValueError("DTI Negosyo Center artifact contained no usable center records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "no_coordinates",
                    "message": (
                        "The DTI directory supplies postal addresses and administrative "
                        "labels only; no coordinates or PSGC codes were invented."
                    ),
                },
                {
                    "code": "contact_fields_withheld",
                    "message": (
                        "Phone and email values remain in the private preserved artifact "
                        "but are excluded from the normalized public payload."
                    ),
                },
                {
                    "code": "ownership_not_stated",
                    "message": (
                        "The directory does not state the owner, operator or host of each "
                        "center. The center is classified as a government service unit with "
                        "unspecified ownership/operator; no host building was classified."
                    ),
                },
                {
                    "code": "directory_not_operational_status",
                    "message": (
                        "The source active flag is preserved as registry evidence. It is not "
                        "treated as proof of current operation, hours or walk-in access."
                    ),
                },
            ],
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        seen: set[str] = set()
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("name"))
            region = clean_text(payload.get("region"))
            address = clean_text(payload.get("address"))
            key = row.source_record_key
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_center_name",
                        "fatal",
                        "A DTI Negosyo Center row has no center name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_center_id",
                        "error",
                        f"Negosyo Center key {key} appears more than once.",
                        {"source_record_key": key},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            if not region:
                issues.append(
                    ValidationIssue(
                        "missing_region",
                        "warning",
                        f"Negosyo Center {name} has no region label.",
                        row_reference=row.row_reference,
                    )
                )
            if not address:
                issues.append(
                    ValidationIssue(
                        "missing_address",
                        "warning",
                        f"Negosyo Center {name} has no postal address.",
                        row_reference=row.row_reference,
                    )
                )
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates: list[FacilityCandidate] = []
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(payload.get("name"))
            if not name:
                continue
            region = clean_text(payload.get("region"))
            province = clean_text(payload.get("province"))
            city = clean_text(payload.get("city"))
            address = clean_text(payload.get("address"))
            address_text = address or ", ".join(part for part in (city, province, region) if part)
            active = payload.get("is_active")
            record_status = (
                "active_in_registry"
                if active is True
                else "inactive_in_registry"
                if active is False
                else "unknown"
            )
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="government_office",
                    facility_subtype="NEGOSYO_CENTER",
                    facility_kind="facility_unit",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="GOVERNMENT_UNSPECIFIED",
                    operator_type="GOVERNMENT_UNSPECIFIED",
                    public_access_class="UNKNOWN",
                    access_conditions=None,
                    record_status=record_status,
                    location=LocationData(
                        address_text=address_text or None,
                        precision="unknown",
                    ),
                    functions=[
                        FunctionData(
                            function_code="BUSINESS_ADVISORY",
                            source_value="Negosyo Center",
                            designation_status=(
                                "active_in_registry" if active is True else "unknown"
                            ),
                            evidence={
                                "source": "DTI Negosyo Center finder",
                                "source_id": row.source_record_key,
                                "region": region,
                                "province": province,
                                "city": city,
                                "source_is_active": active,
                                "address": address,
                            },
                        )
                    ],
                )
            )
        return candidates
