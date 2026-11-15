"""Social Security System (SSS) branch-locator adapter.

The SSS branch locator is backed by three unauthenticated JSON endpoints used by
the public locator page: a region list, a per-region branch list, and a per-branch
detail call. The branch list supplies only branch codes and names; the detail call
supplies the institutional address. Some detail responses also contain a contact
person, a telephone/fax string and a branch e-mail address. Those are personal or
contact fields and are retained only in the private preserved artifact. The
normalized public payload exposes the branch name, address and region only.

Presence in the locator is registry evidence, not proof that a branch is currently
open, that its published address is current, or that walk-in service is available.
No coordinates, PSGC codes or office hours are present in the source.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from ..acquisition import AcquisitionError, HttpAcquirer
from ..contracts import (
    FacilityCandidate,
    FunctionData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    RoleData,
    ValidationIssue,
    ValidationResult,
)
from .common import clean_text, normalise_code

LOCATOR_URL = "https://www.sss.gov.ph/sss-branch-locator/"
REGION_LIST_URL = "https://member.sss.gov.ph/member/sss/branchloc/get-region-list"
BRANCH_LIST_URL = "https://member.sss.gov.ph/member/sss/branchloc/get-branch-list"
BRANCH_DETAILS_URL = "https://member.sss.gov.ph/member/sss/branchloc/get-branch-details"
PUBLIC_FIELDS = ("branchCode", "branchName", "branchAddr", "regionCode", "regionName")


def _decode_json(result: Any, url: str) -> dict[str, Any]:
    if result.status_code >= 400:
        raise AcquisitionError(
            f"SSS branch-locator endpoint {url} returned HTTP {result.status_code}.",
            result=result,
        )
    try:
        payload = json.loads(result.content)
    except json.JSONDecodeError as exc:
        raise AcquisitionError(
            f"SSS branch-locator endpoint {url} did not return valid JSON.",
            result=result,
        ) from exc
    if not isinstance(payload, dict):
        raise AcquisitionError(
            f"SSS branch-locator endpoint {url} returned an unexpected payload.",
            result=result,
        )
    return payload


def fetch_sss_branches(acquirer: HttpAcquirer) -> tuple[bytes, dict[str, Any]]:
    """Fetch the SSS branch list and every available branch detail.

    The public branch list carries null address fields, so each branch needs its
    own detail request. A single missing detail is preserved as an acquisition
    warning rather than silently converting the branch into an addressless record.
    """

    region_payload = _decode_json(acquirer.fetch(REGION_LIST_URL), REGION_LIST_URL)
    regions = [
        {
            "regionCode": clean_text(item.get("regionCode")),
            "regionName": clean_text(item.get("regionName")),
        }
        for item in region_payload.get("regionListRes") or []
        if isinstance(item, dict) and clean_text(item.get("regionCode"))
    ]
    if not regions:
        raise AcquisitionError("SSS branch locator returned no region list.")

    branches: dict[str, dict[str, Any]] = {}
    list_requests = 0
    for region in regions:
        result = acquirer.fetch(
            BRANCH_LIST_URL, method="POST", data={"regionCode": region["regionCode"]}
        )
        list_requests += 1
        payload = _decode_json(result, BRANCH_LIST_URL)
        for item in payload.get("branchListRes") or []:
            if not isinstance(item, dict):
                continue
            code = normalise_code(item.get("branchCode"))
            name = clean_text(item.get("branchName"))
            if not code or not name:
                continue
            branches.setdefault(
                code,
                {
                    "branchCode": code,
                    "branchName": name,
                    "branchAddr": None,
                    "branchContact": None,
                    "branchContactPerson": None,
                    "branchEmail": None,
                    "regionCode": region["regionCode"],
                    "regionName": region["regionName"],
                },
            )

    detail_requests = 0
    detail_failures: list[dict[str, str]] = []
    for code, branch in branches.items():
        url = f"{BRANCH_DETAILS_URL}?branchCode={quote(code)}"
        try:
            payload = _decode_json(acquirer.fetch(url), url)
        except AcquisitionError as exc:
            detail_failures.append({"branchCode": code, "error": str(exc)})
            continue
        detail_requests += 1
        details = payload.get("branchDetsRes") or []
        if not details or not isinstance(details[0], dict):
            detail_failures.append({"branchCode": code, "error": "no detail record"})
            continue
        detail = details[0]
        for field in (
            "branchName",
            "branchAddr",
            "branchContact",
            "branchContactPerson",
            "branchEmail",
        ):
            value = clean_text(detail.get(field))
            if value:
                branch[field] = value

    if not branches:
        raise AcquisitionError("SSS branch locator returned no branch records.")

    artifact = {
        "locator_url": LOCATOR_URL,
        "region_list_url": REGION_LIST_URL,
        "branch_list_url": BRANCH_LIST_URL,
        "branch_details_url": BRANCH_DETAILS_URL,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "regions": regions,
        "list_requests": list_requests,
        "detail_requests": detail_requests,
        "detail_failures": detail_failures,
        "record_count": len(branches),
        "note": (
            "Public SSS branch-locator artifact. Contact-person, e-mail and "
            "telephone/fax fields are retained only in this private raw release; "
            "normalized public rows expose branch name, address and region only. "
            "No coordinates, PSGC codes, hours or operational status are present."
        ),
        "records": sorted(branches.values(), key=lambda item: item["branchCode"]),
    }
    metadata = {
        "regions": len(regions),
        "list_requests": list_requests,
        "detail_requests": detail_requests,
        "detail_failures": len(detail_failures),
        "records": len(branches),
        "locator_url": LOCATOR_URL,
    }
    return json.dumps(artifact, indent=2, ensure_ascii=False).encode("utf-8"), metadata


class SssBranchAdapter:
    source_code = "sss"
    parser_version = "sss-branch-locator-json-1.0.0"
    schema_version = "sss-branch-locator-json-v1"
    expected_columns = {"required": {"branchCode", "branchName"}}  # noqa: RUF012

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
            raise ValueError("SSS branch-locator release is not a JSON artifact.") from exc
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("SSS branch-locator artifact contains no records.")
        rows: list[ParsedRow] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            code = normalise_code(record.get("branchCode"))
            name = clean_text(record.get("branchName"))
            if not code or not name:
                continue
            public_record = {key: record.get(key) for key in PUBLIC_FIELDS}
            rows.append(
                ParsedRow(
                    source_record_key=f"SSS:{code}",
                    row_reference=f"sss-json:{index}",
                    raw_payload=record,
                    normalized_payload=public_record,
                )
            )
        if not rows:
            raise ValueError("SSS branch-locator artifact contained no usable branch records.")
        return ParsedRelease(
            rows=rows,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
            warnings=[
                {
                    "code": "contact_fields_withheld",
                    "message": (
                        "Contact-person, e-mail and telephone/fax values remain in the "
                        "private preserved artifact but are excluded from the normalized "
                        "public payload."
                    ),
                },
                {
                    "code": "no_coordinates",
                    "message": (
                        "The SSS locator supplies postal addresses and region labels only; "
                        "no coordinates or PSGC codes were invented."
                    ),
                },
                {
                    "code": "directory_not_operational_status",
                    "message": (
                        "Locator presence is not proof of current operation, office hours "
                        "or walk-in availability."
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
            name = clean_text(payload.get("branchName"))
            address = clean_text(payload.get("branchAddr"))
            key = row.source_record_key
            if not name:
                issues.append(
                    ValidationIssue(
                        "missing_branch_name",
                        "fatal",
                        "An SSS branch row has no branch name.",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_branch_code",
                        "error",
                        f"SSS branch key {key} appears more than once.",
                        {"source_record_key": key},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            seen.add(key)
            if not address:
                issues.append(
                    ValidationIssue(
                        "missing_branch_address",
                        "warning",
                        f"SSS branch {name} has no address in the recovered detail record.",
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
            code = normalise_code(payload.get("branchCode"))
            name = clean_text(payload.get("branchName"))
            if not code or not name:
                continue
            address = clean_text(payload.get("branchAddr"))
            region = clean_text(payload.get("regionName"))
            display_name = f"SSS {name} Branch"
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    source_entity_id=row.source_record_key,
                    row_reference=row.row_reference,
                    display_name=display_name[:300],
                    facility_type="government_office",
                    facility_subtype="PUBLIC_SERVICE_CENTER",
                    facility_kind="facility",
                    inclusion_class="GOVERNMENT_FACILITY",
                    ownership="government",
                    ownership_type="GOCC",
                    operator_type="GOCC",
                    public_access_class="SERVICE_USERS_ONLY",
                    access_conditions=(
                        "SSS branch serving members, employers and covered persons. The "
                        "locator does not state office hours or walk-in rules."
                    ),
                    record_status="unknown",
                    location=LocationData(
                        address_text=address or None,
                        precision="unknown",
                    ),
                    functions=[
                        FunctionData(
                            function_code="SOCIAL_SECURITY_SERVICE",
                            source_value="SSS branch",
                            designation_status="unknown",
                            evidence={
                                "source": "SSS branch locator",
                                "branch_code": code,
                                "region": region,
                                "address": address,
                            },
                        )
                    ],
                    roles=[
                        RoleData(
                            role_type="OPERATOR",
                            entity_name="Social Security System",
                            entity_type="GOCC",
                            evidence={"basis": "Official SSS branch locator"},
                        )
                    ],
                )
            )
        return candidates
