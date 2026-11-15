"""PSA 2024 Census population snapshots served by the BetterGov Statistics API.

The BetterGov Philippine Data Explorer mirrors saved PSA OpenSTAT tables. This
connector treats those snapshots as a *statistical* dataset, not a facility
registry: every value retains its PSA table URL, release identifier, geographic
code and source dimension codes. It never aggregates across geography or
indicators and never fills a missing value with zero.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from philfacilities_api.models import (
    IngestionRun,
    PopulationObservation,
    Release,
    SourceRecord,
)
from philfacilities_api.rights import PUBLICATION_PUBLISHED
from sqlalchemy.orm import Session

from ..acquisition import HttpAcquirer, record_check
from ..config import IngestSettings
from ..contracts import ReleaseSpec
from ..pipeline import _existing_release, ensure_source
from ..storage import RawStore, build_store
from .registry import REAL_SOURCES, source_spec

API_ROOT = "https://statistics.bettergov.ph/api/v1"
DATASET_URL = API_ROOT + "/datasets/{dataset_id}"
VALUES_URL = API_ROOT + "/datasets/{dataset_id}/values"
QUERY_URL = API_ROOT + "/datasets/{dataset_id}/query"

# Every 2024 Census regional table that the BetterGov inventory listed as a
# complete snapshot on 15 Nov 2026. The table titles identify the region; the
# connector still verifies the response rather than trusting this list.
CENSUS_2024_DATASET_IDS: tuple[str, ...] = (
    "97ba6406111204e138a4",  # NCR
    "182e14eaaa4fa5ba5ac5",  # BARMM
    "86770de57684804b7a80",  # Region X
    "6cd21aca348d99253bf2",  # Region XI
    "a7e6bfe00dd06dfdde89",  # Region XII
    "e0f3193ded18f965820e",  # Region XIII
    "c7761a90dee3267517bf",  # Bicol
    "78177961ee5bc70de945",  # Cagayan Valley
    "778876c62164ed7d9a40",  # CALABARZON
    "bff31e8903b87f8119c1",  # Central Luzon
    "2c23084fb2da9a5c6c62",  # Central Visayas
    "b1b47f8cb7ceb5c50a97",  # CAR
    "6e8a30809cab3de44cbb",  # Eastern Visayas
    "a80671eaca74acb6a678",  # Ilocos
    "7c8faab459edea784cb6",  # MIMAROPA
    "69c38d87c9b33b2d75bc",  # NIR
    "e82867a0e826ad5873c1",  # Western Visayas
    "ee075b3e6a917d778a4e",  # Zamboanga Peninsula
)

REFERENCE_DATE = date(2024, 7, 1)
REFERENCE_PERIOD = "2024 Census of Population; reference date 01 July 2024"
PARSER_VERSION = "bettergov-population-1.0.0"
PAGE_SIZE = 200
GEO_CHUNK = 1000


@dataclass
class PopulationSnapshot:
    dataset_id: str
    title: str
    release: str
    psa_source_url: str
    source_updated_at: datetime | None
    retrieved_at: datetime | None
    unit: str | None
    dimensions: list[str]
    geographic_values: list[dict[str, str]]
    parameter_values: list[dict[str, str]]
    rows: list[dict[str, Any]]
    reported_cells: int | None

    @property
    def region_label(self) -> str:
        title = self.title
        marker = "as of 01 July 2024"
        label = title.split(marker, 1)[1] if marker in title else title
        label = label.strip(" :")
        # "National Capital Region (NCR)" etc.; keep the source wording.
        return re.sub(r"\s+", " ", label)[:80] or self.dataset_id


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _dimension_values(
    acquirer: HttpAcquirer, dataset_id: str, release: str, dimension: str
) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    offset = 0
    while True:
        query = urlencode(
            {"dimension": dimension, "release": release, "limit": PAGE_SIZE, "offset": offset}
        )
        document, _result = acquirer.get_json(f"{VALUES_URL.format(dataset_id=dataset_id)}?{query}")
        values.extend(document["data"])
        next_offset = document["pagination"].get("nextOffset")
        if next_offset is None:
            break
        offset = next_offset
    return values


def fetch_population_snapshot(
    acquirer: HttpAcquirer,
    dataset_id: str,
) -> tuple[PopulationSnapshot, list[Any]]:
    """Fetch metadata, dictionaries and every point in one regional table.

    The API caps a query at 5,000 points and 64 KiB, so the geography dimension is
    selected in bounded chunks. The returned FetchResults are kept for the
    monitoring ledger.
    """

    metadata_document, metadata_result = acquirer.get_json(
        DATASET_URL.format(dataset_id=dataset_id)
    )
    dataset = metadata_document["data"]
    if not dataset.get("ready"):
        raise ValueError(f"BetterGov dataset {dataset_id} is not a complete snapshot")
    release = dataset["release"]
    dimensions = [dimension["code"] for dimension in dataset.get("dimensions", [])]
    if "Geographic Location" not in dimensions or "Parameter" not in dimensions:
        raise ValueError(
            f"BetterGov dataset {dataset_id} has an unexpected dimension set: {dimensions}"
        )

    geographic_values = _dimension_values(acquirer, dataset_id, release, "Geographic Location")
    parameter_values = _dimension_values(acquirer, dataset_id, release, "Parameter")
    geographic_codes = [value["code"] for value in geographic_values]
    parameter_codes = [value["code"] for value in parameter_values]
    if not geographic_codes or not parameter_codes:
        raise ValueError(f"BetterGov dataset {dataset_id} returned an empty dictionary")

    rows: list[dict[str, Any]] = []
    results: list[Any] = [metadata_result]
    for start in range(0, len(geographic_codes), GEO_CHUNK):
        selection = {
            "Geographic Location": geographic_codes[start : start + GEO_CHUNK],
            "Parameter": parameter_codes,
        }
        document, result = acquirer.post_json(
            QUERY_URL.format(dataset_id=dataset_id),
            {"release": release, "selection": selection},
        )
        results.append(result)
        payload = document["data"]
        rows.extend(payload["rows"])
    if len(rows) > int(dataset.get("cells") or 0) and dataset.get("cells"):
        raise ValueError(
            f"BetterGov dataset {dataset_id} returned {len(rows)} rows for "
            f"{dataset['cells']} advertised cells"
        )

    snapshot = PopulationSnapshot(
        dataset_id=dataset_id,
        title=dataset["title"],
        release=release,
        psa_source_url=dataset["source"],
        source_updated_at=_parse_datetime(dataset.get("sourceUpdated")),
        retrieved_at=_parse_datetime(dataset.get("retrieved")),
        unit=dataset.get("unit"),
        dimensions=dimensions,
        geographic_values=geographic_values,
        parameter_values=parameter_values,
        rows=rows,
        reported_cells=int(dataset["cells"]) if dataset.get("cells") else None,
    )
    return snapshot, results


def _geographic_level(code: str, label: str) -> str:
    """Classify the source hierarchy without inventing a province for an HUC.

    PSA's OpenSTAT labels prefix each level with two dots: region ``..``,
    province ``....``, city/municipality ``......`` and barangay ``........``.
    Highly urbanised cities appear at the four-dot depth because they are not
    under a province, so that depth is reported as ``province_or_huc`` rather
    than mislabelled as either one.
    """

    depth = len(label) - len(label.lstrip("."))
    if depth >= 8:
        return "barangay"
    if depth >= 6:
        return "municipality"
    if depth >= 4:
        return "province_or_huc"
    digits = re.sub(r"\D", "", code or "")
    if len(digits) == 10 and digits.endswith("00000000"):
        return "region"
    return "unknown"


def _indicator_unit(label: str, reported_unit: str | None) -> str | None:
    normalized = label.strip().lower()
    if normalized in {"total population", "household population"}:
        return "persons"
    if normalized == "number of households":
        return "households"
    return reported_unit


def _observation_payload(snapshot: PopulationSnapshot, row: dict[str, Any]) -> dict[str, Any]:
    codes = row.get("codes") or []
    labels = row.get("labels") or []
    if len(codes) != 2:
        raise ValueError(f"Unexpected observation shape: {row}")
    geo_code, parameter_code = (str(codes[0]), str(codes[1]))
    geo_label = str(labels[0]) if labels else geo_code
    parameter_label = str(labels[1]) if len(labels) > 1 else parameter_code
    return {
        "source_record_key": f"{snapshot.dataset_id}:{geo_code}:{parameter_code}",
        "raw_payload": {
            "dataset_id": snapshot.dataset_id,
            "dataset_title": snapshot.title,
            "release": snapshot.release,
            "psa_source_url": snapshot.psa_source_url,
            "dimensions": snapshot.dimensions,
            "codes": [geo_code, parameter_code],
            "labels": [geo_label, parameter_label],
            "value": row.get("value"),
            "status": row.get("status"),
        },
        "psgc_code": geo_code,
        "geographic_level": _geographic_level(geo_code, geo_label),
        "geographic_name": geo_label.lstrip(".").strip() or geo_code,
        "indicator_code": parameter_code,
        "indicator_label": parameter_label,
        "value": Decimal(str(row["value"])) if row.get("value") is not None else None,
        "unit": _indicator_unit(parameter_label, snapshot.unit),
        "dimensions": {
            "Geographic Location": geo_label.lstrip(".").strip(),
            "Parameter": parameter_label,
        },
    }


def _raw_document(snapshot: PopulationSnapshot) -> bytes:
    document = {
        "source": "BetterGov.PH Philippine Data Explorer",
        "api": QUERY_URL.format(dataset_id=snapshot.dataset_id),
        "psa_source": snapshot.psa_source_url,
        "dataset_id": snapshot.dataset_id,
        "title": snapshot.title,
        "release": snapshot.release,
        "source_updated_at": snapshot.source_updated_at.isoformat()
        if snapshot.source_updated_at
        else None,
        "retrieved_at": snapshot.retrieved_at.isoformat() if snapshot.retrieved_at else None,
        "unit": snapshot.unit,
        "reference_date": REFERENCE_DATE.isoformat(),
        "dimensions": snapshot.dimensions,
        "geographic_values": snapshot.geographic_values,
        "parameter_values": snapshot.parameter_values,
        "warning": (
            "Saved PSA OpenSTAT snapshot reproduced without aggregation. PSA remains "
            "the authoritative source. Missing values are preserved as null."
        ),
        "rows": snapshot.rows,
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def load_population_snapshot(
    *,
    session: Session,
    settings: IngestSettings,
    snapshot: PopulationSnapshot,
    store: RawStore | None = None,
) -> dict[str, Any]:
    """Persist one regional statistical snapshot and its observation rows."""

    store = store or build_store(settings)
    raw = _raw_document(snapshot)
    release_token = re.sub(r"[^A-Za-z0-9]+", "-", snapshot.region_label).strip("-")[:60]
    spec: ReleaseSpec = source_spec(
        REAL_SOURCES["bettergov-population"],
        release_label=f"PSA-2024-CENSUS-{release_token}-{REFERENCE_DATE.isoformat()}",
        filename=f"psa-2024-census-{release_token.lower()}.json",
        content=raw,
        retrieved_at=snapshot.retrieved_at or datetime.now(UTC),
        reference_period_start=REFERENCE_DATE,
        reference_period_end=REFERENCE_DATE,
        notes=(
            f"PSA OpenSTAT table {snapshot.psa_source_url}; BetterGov release "
            f"{snapshot.release}; {REFERENCE_PERIOD}."
        ),
    )
    _agency, dataset, _gate = ensure_source(session, spec)
    preserved = store.preserve(
        agency=spec.agency_code,
        dataset=spec.dataset_slug,
        release_label=spec.release_label,
        filename=spec.filename,
        content=raw,
    )
    existing = _existing_release(session, dataset.id, preserved.sha256)
    if existing is not None and existing.ingestion_status == "published":
        return {
            "dataset": dataset.slug,
            "release_id": str(existing.id),
            "status": "skipped_duplicate",
            "observations": 0,
            "psgc_codes": 0,
        }

    run_id = uuid.uuid4()
    run = IngestionRun(
        id=run_id,
        dataset_id=dataset.id,
        started_at=datetime.now(UTC),
        status="running",
    )
    session.add(run)
    release = Release(
        dataset_id=dataset.id,
        source_release_label=spec.release_label,
        source_published_at=snapshot.source_updated_at,
        reference_period_start=REFERENCE_DATE,
        reference_period_end=REFERENCE_DATE,
        retrieved_at=spec.retrieved_at or datetime.now(UTC),
        processed_at=datetime.now(UTC),
        raw_object_uri=preserved.uri,
        sha256=preserved.sha256,
        file_format="json",
        file_size_bytes=len(raw),
        row_count_reported=snapshot.reported_cells,
        row_count_parsed=len(snapshot.rows),
        ingestion_status=PUBLICATION_PUBLISHED,
        terms_review_status=dataset.redistribution_status,
        publication_status=PUBLICATION_PUBLISHED,
        parser_version=PARSER_VERSION,
        notes=spec.notes,
    )
    session.add(release)
    session.flush()
    run.release_id = release.id

    created = 0
    null_values = 0
    statuses: dict[str, int] = {}
    psgc_codes: set[str] = set()
    seen_keys: set[str] = set()
    batch: list[tuple[SourceRecord, PopulationObservation]] = []

    def flush_batch() -> None:
        """Insert the source records before the observations that reference them.

        ``source.records`` and ``stats.population_observations`` are linked only by
        a foreign key, not an ORM relationship, so SQLAlchemy's unit of work does
        not infer a per-row insert order from the mapped classes. Flushing the
        records first makes the dependency explicit and keeps the observations
        from being emitted before their referenced records.
        """

        if not batch:
            return
        session.add_all(record for record, _observation in batch)
        session.flush()
        session.add_all(observation for _record, observation in batch)
        session.flush()
        batch.clear()

    for row in snapshot.rows:
        observation = _observation_payload(snapshot, row)
        key = observation["source_record_key"]
        if key in seen_keys:
            # The source returns one point per dimension combination; a duplicate
            # key would violate the release/source-key constraint. Preserve the
            # first occurrence and count the duplicate rather than aborting the
            # whole regional snapshot.
            statuses["duplicate_source_key"] = statuses.get("duplicate_source_key", 0) + 1
            continue
        seen_keys.add(key)
        if observation["value"] is None:
            null_values += 1
        status = str(row.get("status") or "").strip()
        if status:
            statuses[status] = statuses.get(status, 0) + 1
        record = SourceRecord(
            id=uuid.uuid4(),
            release_id=release.id,
            source_record_key=key,
            row_number_or_page=None,
            raw_payload=observation["raw_payload"],
            raw_record_hash=_record_hash(observation["raw_payload"]),
            validation_status="valid",
        )
        batch.append(
            (
                record,
                PopulationObservation(
                    release_id=release.id,
                    source_record_id=record.id,
                    source_record_key=key,
                    psgc_code=observation["psgc_code"],
                    geographic_level=observation["geographic_level"],
                    geographic_name=observation["geographic_name"],
                    indicator_code=observation["indicator_code"],
                    indicator_label=observation["indicator_label"],
                    value=observation["value"],
                    unit=observation["unit"],
                    reference_date=REFERENCE_DATE,
                    reference_period=REFERENCE_PERIOD,
                    dimensions=observation["dimensions"],
                    source_url=snapshot.psa_source_url,
                    source_updated_at=snapshot.source_updated_at,
                    retrieved_at=snapshot.retrieved_at,
                ),
            )
        )
        psgc_codes.add(observation["psgc_code"])
        created += 1
        if len(batch) >= 500:
            flush_batch()
    flush_batch()

    stats = {
        "input_rows": len(snapshot.rows),
        "parsed_rows": len(snapshot.rows),
        "accepted_rows": created,
        "rejected_rows": 0,
        "null_values": null_values,
        "psgc_codes": len(psgc_codes),
        "source_statuses": statuses,
    }
    run.status = "published"
    run.finished_at = datetime.now(UTC)
    run.stats = stats
    record_check(
        session,
        dataset=dataset,
        result=None,
        status="ok",
        message=(
            f"PSA 2024 Census snapshot {snapshot.dataset_id} loaded: "
            f"{len(snapshot.rows)} observations."
        ),
        details={
            "source_url": snapshot.psa_source_url,
            "release": snapshot.release,
            "region": snapshot.region_label,
            "cells": snapshot.reported_cells,
            "rows": len(snapshot.rows),
        },
    )
    session.commit()
    return {
        "dataset": dataset.slug,
        "release_id": str(release.id),
        "status": "published",
        "region": snapshot.region_label,
        "observations": created,
        "null_values": null_values,
        "psgc_codes": len(psgc_codes),
    }


def _record_hash(value: Any) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
