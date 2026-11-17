"""Adapter contract tests.

Every source adapter must expose the same parse -> validate -> normalize
contract, and the synthetic fixtures must round-trip through it. The dynamic
contract check also catches a new adapter module that forgets a version or a
method before the connector migration lands.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import pkgutil

import philfacilities_ingest.sources as source_package
import pytest
from philfacilities_ingest.contracts import ReleaseSpec, SourceAdapter
from philfacilities_ingest.fixtures import (
    deped_enrollment,
    deped_masterlist,
    deped_resources,
    doh_csv,
    philhealth_pdf,
)
from philfacilities_ingest.sources import deped, deped_ebeis, doh, philhealth
from philfacilities_ingest.sources.deped import (
    DepEdEnrollmentAdapter,
    DepEdMasterlistAdapter,
    DepEdResourceAdapter,
)
from philfacilities_ingest.sources.deped_ebeis import DepEdEBEISAdapter
from philfacilities_ingest.sources.doh import DOHNHFRAdapter
from philfacilities_ingest.sources.philhealth import PhilHealthPdfAdapter

EBEIS_FIXTURE = b"""
<table>
  <tr><th>School ID</th><th>School Name</th><th>Head / Position</th><th>Address</th></tr>
  <tr><td>123456</td><td>Sample Central School</td><td>JUAN DELA CRUZ</td>
      <td>Poblacion, Sample City</td></tr>
</table>
"""


def _spec(*, agency: str, slug: str, filename: str, content: bytes) -> ReleaseSpec:
    return ReleaseSpec(
        agency_code=agency,
        agency_name=f"Synthetic {agency} fixture",
        dataset_slug=slug,
        dataset_name=f"Synthetic {slug}",
        release_label="SYNTHETIC-CONTRACT-TEST",
        filename=filename,
        content=content,
        redistribution_status="not_applicable",
        access_method="fixture",
        is_synthetic=True,
    )


def _contract_cases():
    return [
        (
            "deped-masterlist",
            lambda: (
                DepEdMasterlistAdapter,
                _spec(
                    agency="deped",
                    slug="contract-deped-masterlist",
                    filename="synthetic-deped-masterlist.xlsx",
                    content=deped_masterlist(),
                ),
            ),
        ),
        (
            "deped-enrollment",
            lambda: (
                DepEdEnrollmentAdapter,
                _spec(
                    agency="deped",
                    slug="contract-deped-enrollment",
                    filename="synthetic-deped-enrollment.xlsx",
                    content=deped_enrollment(),
                ),
            ),
        ),
        (
            "deped-resources",
            lambda: (
                DepEdResourceAdapter,
                _spec(
                    agency="deped",
                    slug="contract-deped-resources",
                    filename="synthetic-deped-resources.xlsx",
                    content=deped_resources(),
                ),
            ),
        ),
        (
            "doh-nhfr",
            lambda: (
                DOHNHFRAdapter,
                _spec(
                    agency="doh",
                    slug="contract-doh",
                    filename="synthetic-doh.csv",
                    content=doh_csv(),
                ),
            ),
        ),
        (
            "philhealth-pdf",
            lambda: (
                PhilHealthPdfAdapter,
                _spec(
                    agency="philhealth",
                    slug="contract-philhealth",
                    filename="synthetic-philhealth-hospitals.pdf",
                    content=philhealth_pdf(),
                ),
            ),
        ),
        (
            "deped-ebeis",
            lambda: (
                DepEdEBEISAdapter,
                _spec(
                    agency="deped",
                    slug="contract-ebeis",
                    filename="synthetic-ebeis.html",
                    content=EBEIS_FIXTURE,
                ),
            ),
        ),
    ]


def _discovered_adapter_classes() -> dict[str, type]:
    classes: dict[str, type] = {}
    for module_info in pkgutil.iter_modules(source_package.__path__):
        module = importlib.import_module(f"{source_package.__name__}.{module_info.name}")
        for name, value in vars(module).items():
            if (
                inspect.isclass(value)
                and value.__module__.startswith(source_package.__name__)
                and hasattr(value, "parser_version")
                and hasattr(value, "parse")
            ):
                classes[f"{module_info.name}.{name}"] = value
    return classes


def test_every_adapter_declares_the_contract() -> None:
    classes = _discovered_adapter_classes()
    assert len(classes) >= 30, f"adapter discovery found only {sorted(classes)}"
    for name, adapter_class in sorted(classes.items()):
        assert isinstance(adapter_class.parser_version, str) and adapter_class.parser_version, name
        assert isinstance(adapter_class.schema_version, str) and adapter_class.schema_version, name
        assert callable(adapter_class.parse), name
        assert callable(adapter_class.validate), name
        assert callable(adapter_class.normalize), name
        # Acquisition is a connector concern. A leftover adapter method would
        # reintroduce a second, untested acquisition path.
        assert not hasattr(adapter_class, "discover"), name
        assert not hasattr(adapter_class, "acquire"), name


def test_source_adapter_protocol_has_no_acquisition_methods() -> None:
    assert not hasattr(SourceAdapter, "discover")
    assert not hasattr(SourceAdapter, "acquire")


_CONTRACT_CASES = _contract_cases()


@pytest.mark.parametrize(
    "case_id,factory", _CONTRACT_CASES, ids=[case[0] for case in _CONTRACT_CASES]
)
def test_fixture_backed_adapter_round_trip(case_id: str, factory) -> None:
    adapter_class, spec = factory()
    adapter = adapter_class(spec)

    parsed = adapter.parse(spec)
    assert parsed.rows, case_id
    assert parsed.parser_version == adapter.parser_version, case_id
    assert parsed.schema_version == adapter.schema_version, case_id

    validation = adapter.validate(parsed)
    assert validation.accepted_rows + validation.rejected_rows == len(parsed.rows), case_id
    assert validation.accepted_rows > 0, case_id

    candidates = adapter.normalize(parsed)
    assert len(candidates) == validation.accepted_rows, case_id
    parsed_keys = {row.source_record_key for row in parsed.rows}
    assert {candidate.source_record_key for candidate in candidates} <= parsed_keys, case_id


def test_adapter_parse_output_is_deterministic() -> None:
    spec = _spec(
        agency="deped",
        slug="golden-ebeis",
        filename="synthetic-ebeis.html",
        content=EBEIS_FIXTURE,
    )
    adapter = DepEdEBEISAdapter(spec)

    first = adapter.parse(spec)
    second = adapter.parse(spec)
    first_hash = hashlib.sha256(
        json.dumps(
            [
                (row.source_record_key, row.row_reference, row.raw_payload, row.normalized_payload)
                for row in first.rows
            ],
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    second_hash = hashlib.sha256(
        json.dumps(
            [
                (row.source_record_key, row.row_reference, row.raw_payload, row.normalized_payload)
                for row in second.rows
            ],
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    assert first_hash == second_hash

    first_candidates = adapter.normalize(first)
    second_candidates = adapter.normalize(second)
    assert [candidate.source_record_key for candidate in first_candidates] == [
        candidate.source_record_key for candidate in second_candidates
    ]


def test_fixture_modules_expose_adapters_under_their_public_names() -> None:
    """Guard the module/class pairs the upcoming catalog will import."""

    assert deped.DepEdMasterlistAdapter is DepEdMasterlistAdapter
    assert deped_ebeis.DepEdEBEISAdapter is DepEdEBEISAdapter
    assert doh.DOHNHFRAdapter is DOHNHFRAdapter
    assert philhealth.PhilHealthPdfAdapter is PhilHealthPdfAdapter
