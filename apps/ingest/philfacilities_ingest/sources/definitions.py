"""Declarative source metadata.

A source is one :class:`SourceDefinition`. It records what the catalogue says
about the source (agency, dataset, rights, acquisition limits) and how the
runner may check and acquire it. Parsing and normalization stay in the source
adapter; this module deliberately contains no source-specific logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import (
    DEFAULT_MINIMUM_ACCEPTANCE_RATE,
    DEFAULT_MINIMUM_ACCEPTANCE_ROWS,
    ReleaseSpec,
)

# Source groups used by ``source run --group``. There is no manual or blocked
# queue: a source is either acquired automatically (``approved``) or recorded as
# skipped with a machine-readable reason and retried on the public route.
GROUP_APPROVED = "approved"
GROUP_SKIPPED = "skipped"
SOURCE_GROUPS = (GROUP_APPROVED, GROUP_SKIPPED)

# Agencies that publish community-maintained data. Everything else in the
# current catalogue is a government publisher.
PUBLISHER_TYPE_BY_AGENCY = {
    "bettergov": "community",
    "osm": "community",
}


def publisher_type_for(agency_code: str) -> str:
    return PUBLISHER_TYPE_BY_AGENCY.get(agency_code, "government")


@dataclass(frozen=True)
class AgencyRef:
    code: str
    name: str
    publisher_type: str = "government"


@dataclass(frozen=True)
class DatasetRef:
    slug: str
    name: str
    authority_level: str | None = None
    coverage_scope: str | None = None
    coverage_note: str | None = None


@dataclass(frozen=True)
class RightsDecision:
    status: str
    basis: str | None = None
    attribution_text: str | None = None
    personal_data_status: str | None = None
    requested_publication_status: str | None = None
    license_identifier: str | None = None
    terms_url: str | None = None


@dataclass(frozen=True)
class AccessSpec:
    source_url: str
    method: str
    update_pattern: str | None = None


@dataclass(frozen=True)
class CheckSpec:
    """How a source check probes an endpoint.

    ``catalog`` selects the optional post-response parser for indexes that list
    several downloadable releases (currently PhilHealth). Everything else is a
    plain request plus signature/marker expectations, so ``check_sources`` needs
    no per-key branch.
    """

    url: str | None = None
    method: str = "GET"
    data: dict[str, Any] | None = None
    expected_marker: str | None = None
    catalog: str | None = None


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    group: str
    agency: AgencyRef
    dataset: DatasetRef
    rights: RightsDecision
    access: AccessSpec
    check: CheckSpec
    connector: str
    is_geography: bool = False
    note: str | None = None
    minimum_acceptance_rate: float = DEFAULT_MINIMUM_ACCEPTANCE_RATE
    minimum_acceptance_rows: int = DEFAULT_MINIMUM_ACCEPTANCE_ROWS

    def release_spec(self, **overrides: Any) -> ReleaseSpec:
        """Build a :class:`ReleaseSpec` with this source's reviewed metadata."""

        values: dict[str, Any] = {
            "agency_code": self.agency.code,
            "agency_name": self.agency.name,
            "dataset_slug": self.dataset.slug,
            "dataset_name": self.dataset.name,
            "release_label": "",
            "filename": "",
            "content": b"",
            "source_url": self.access.source_url,
            "terms_url": self.rights.terms_url,
            "redistribution_status": self.rights.status,
            "rights_basis": self.rights.basis,
            "attribution_text": self.rights.attribution_text,
            "personal_data_status": self.rights.personal_data_status,
            "requested_publication_status": self.rights.requested_publication_status,
            "access_method": self.access.method,
            "update_pattern": self.access.update_pattern,
            "license_identifier": self.rights.license_identifier,
            "authority_level": self.dataset.authority_level,
            "coverage_scope": self.dataset.coverage_scope,
            "coverage_note": self.dataset.coverage_note,
            "notes": self.note,
            "minimum_acceptance_rate": self.minimum_acceptance_rate,
            "minimum_acceptance_rows": self.minimum_acceptance_rows,
        }
        values.update(overrides)
        return ReleaseSpec(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "group": self.group,
            "agency": self.agency.code,
            "agency_name": self.agency.name,
            "dataset": self.dataset.slug,
            "dataset_name": self.dataset.name,
            "rights": self.rights.status,
            "publication": self.rights.requested_publication_status,
            "access_method": self.access.method,
            "source_url": self.access.source_url,
            "update_pattern": self.access.update_pattern,
            "connector": self.connector,
            "is_geography": self.is_geography,
            "minimum_acceptance_rate": self.minimum_acceptance_rate,
            "minimum_acceptance_rows": self.minimum_acceptance_rows,
        }
