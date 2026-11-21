# Adding a source

> **Purpose** — The end-to-end checklist for adding a source adapter without special-casing the CLI or pipeline.
> **See also** — [Ingestion](ingestion.md) for pipeline mechanics · [Sources](sources.md) for the research register · [Data policy](data-policy.md) for the publication decision

A new source needs a rights/access decision, one adapter module, one registry entry, and one connector registration. The CLI, runner, and pipeline are generic: **do not add a `load-<source>` command or a source-specific branch to `pipeline/`.** The [source register](sources.md) records what was researched; the [data policy](data-policy.md) decides whether the exact release may be acquired and published. Code registration is not a publication decision.

## 1. Checklist

1. Record the access method, terms, rights basis, and publication decision.
2. Add a `RealSource` entry to `sources/registry_data.py`.
3. Add `sources/<source>.py` with an adapter implementing `parse → validate → normalize`.
4. Register the acquisition route in `sources/catalog.py`.
5. Add a deterministic fixture and parser/validation tests.
6. Run `source validate`, then `source run --dry-run`, then `source run`.
7. Record the release evidence in the source register and rights register.

## 2. Record the source evidence first

Before writing code, establish:

- the original official publisher and exact release;
- the official URL and acquisition route (public file, API, directory, GIS service) reachable without login, agreement, FOI, CAPTCHA, or a human step;
- source publication date and reference period;
- observed fields, identifiers, and record count;
- coverage scope (national, regional, participating-LGU, selected-LGU, single-LGU);
- ownership/operator/accreditation semantics;
- terms, licence, or explicit prohibition finding;
- personal-data, privacy, and security review;
- the publication decision and its basis.

Add the source to [Sources](sources.md) and the rights register [`DATA-LICENSES.md`](../DATA-LICENSES.md). A homepage, catalogue entry, or search result is not a verified release.

## 3. Add source metadata

In `apps/ingest/philfacilities_ingest/sources/registry_data.py`, add a `RealSource` to `REAL_SOURCES`:

```python
"foo-directory": RealSource(
    key="foo-directory",
    agency_code="foo",
    agency_name="Foo Agency",
    dataset_slug="foo-directory",
    dataset_name="Foo Agency service directory",
    source_url="https://example.gov.ph/directory.csv",
    access_method="public_file",
    update_pattern="monthly",
    rights=RIGHTS_APPROVED_ATTRIBUTION,
    rights_basis="Public directory with no explicit prohibition; attribution retained.",
    attribution_text="Foo Agency",
    personal_data_status="Institutional fields only; personal contacts withheld.",
    requested_publication_status=PUBLICATION_APPROVED,
),
```

Use rights constants from `philfacilities_api.rights`, not free-form approval language. A source requiring login, agreement, FOI, CAPTCHA, or carrying an explicit restriction belongs in the `skipped` group with a controlled reason from `skip_reasons.py`; it must never be silently approved. The group is derived: blocked publication state or human-only access → `skipped`; otherwise `approved`. A missing licence or terms page is not an explicit prohibition: a public, official, verified release is recorded as `publicly_available_verified` and published with attribution, provenance, and a takedown route.

`RealSource` also carries `minimum_acceptance_rate` and `minimum_acceptance_rows` (defaults `0.90` / `20`). Keep defaults unless the verified source shape justifies a different floor, and record why.

## 4. Write the adapter

Create `apps/ingest/philfacilities_ingest/sources/foo.py`. The adapter only parses preserved bytes, validates them, and returns normalized candidates. It never downloads and never invents values. Check headings/columns inside `parse()` with `require_columns()` from `.common` and raise an error naming missing fields.

```python
from ..contracts import (
    FacilityCandidate,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ValidationResult,
)
from .common import clean_text, require_columns


class FooDirectoryAdapter:
    source_code = "foo"
    parser_version = "foo-directory-1.0.0"
    schema_version = "foo-directory-v1"

    def __init__(self, spec: ReleaseSpec) -> None:
        self.spec = spec

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        rows = []
        records = read_csv(spec.content)
        require_columns(records, {"id", "name", "address"})
        for line_number, record in enumerate(records, start=2):
            rows.append(
                ParsedRow(
                    source_record_key=f"FOO-{record['id']}",
                    row_reference=f"line:{line_number}",
                    raw_payload=record,
                    normalized_payload=record,
                )
            )
        return ParsedRelease(
            rows=rows, parser_version=self.parser_version, schema_version=self.schema_version
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        # Reject rows with missing required fields; record issues with row
        # references. Do not drop a source value silently.
        ...

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates = []
        for row in parsed.rows:
            payload = row.normalized_payload
            location = LocationData()
            if payload.get("latitude") and payload.get("longitude"):
                location = LocationData(
                    latitude=float(payload["latitude"]),
                    longitude=float(payload["longitude"]),
                    precision="map_geocoded",
                )
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    row_reference=row.row_reference,
                    source_entity_id=payload["id"],
                    display_name=clean_text(payload["name"]),
                    facility_type="government_office",
                    facility_subtype=None,
                    ownership="government",
                    record_status="active",
                    location=location,
                    inclusion_class="GOVERNMENT_FACILITY",
                )
            )
        return candidates
```

Use shared helpers in `validators.py` rather than local copies: `coordinate_in_philippines` / `coordinate_issue` (plausibility only), `psgc_shape_issue`, `missing_required_fields`, `duplicate_values`. Keep untouched source values in `raw_payload` and document every normalization in the module docstring. Missing is not zero, false, or inactive; registry presence is not operational status.

## 5. Register acquisition

In `_build_catalog()` in `sources/catalog.py`, register a connector. Most one-file sources use `SingleFileConnector` through the local `_single` helper:

```python
connectors["foo-directory"] = _single(
    "foo-directory",
    url=REAL_SOURCES["foo-directory"].source_url,
    adapter=FooDirectoryAdapter,
    filename=_dated("foo-directory", "csv"),
    release_label=_label("FOO-DIRECTORY"),
    max_bytes=25 * 1024 * 1024,
    notes="Public Foo Agency directory; retain attribution.",
)
```

No acquisition code is needed for this shape. Use a source-specific connector under `sources/connectors/` only for real paging, a catalogue of multiple releases, a PDF index, WFS layers, or a non-standard signature. Add a `CheckSpec` when the source needs an HTTP probe or catalogue marker:

```python
"foo-directory": CheckSpec(
    url=REAL_SOURCES["foo-directory"].source_url,
    expected_marker="Office Name",
),
```

A source requiring a login, agreement, FOI, CAPTCHA, or other human step is registered as `skipped` with a controlled reason and alternate route; the runner returns `status=skipped` rather than pretending to acquire data. Use `UnavailableConnector` only when there is no automated public route at all. Do not create manual or blocked queues.

## 6. Add a fixture and tests

At minimum, test that:

- parser output is deterministic and preserves the original payload;
- validation rejects missing required fields and records row references;
- normalization does not invent a coordinate, PSGC code, ownership, or status;
- `source validate <key> --fixture <path>` succeeds.

Put tests in `apps/ingest/tests/` (usually `test_parsers.py` or a source-specific module), using deterministic fixtures — never live downloads:

```bash
uv run pytest apps/ingest/tests/test_parsers.py -q
uv run pytest apps/ingest/tests/test_adapter_contract.py -q
```

## 7. Validate before writing

```bash
uv run philfacilities-ingest source list | grep foo-directory
uv run philfacilities-ingest source validate foo-directory \
  --fixture var/raw/foo/foo-directory-2026-11-16.csv
uv run philfacilities-ingest source run foo-directory \
  --input var/raw/foo/foo-directory-2026-11-16.csv --dry-run
```

`source validate` runs `parse → validate → normalize` and prints counts and issues without a write transaction. `--dry-run` also acquires through the connector and preserves the raw artifact but does not apply candidates.

## 8. Load and record evidence

```bash
uv run philfacilities-ingest source run foo-directory
uv run philfacilities-ingest source check foo-directory
```

Then record in [Sources](sources.md) and `DATA-LICENSES.md`:

- URL, agency, dataset/release, reference period, publication date, retrieval time, checksum, parser/schema versions, and rights basis;
- the publication gate and attribution shown in the run report;
- actual parsed/accepted/rejected counts and known exclusions;
- quality issues, coordinate precision, and coverage limits.

If the source is skipped, record the controlled reason, detail, official alternate route, and next retry; do not load it and do not send it to a human queue. For a large source, run `scripts/ingest_benchmark.py` before and after and store the JSON under `docs/operations/evidence/`.

## 9. Common mistakes

- Adding a `load-foo` CLI command — the generic `source run foo` already exists.
- Putting acquisition in the adapter — the connector owns URLs, retries, bounds, and signatures.
- Creating a separate registry/catalog table — `REAL_SOURCES` plus `sources/catalog.py` is the single registry.
- Coercing an unknown PSGC code or coordinate into a plausible value.
- Treating an empty value as zero or `false`.
- Publishing because a file is public — publication requires the recorded decision in [Data policy](data-policy.md).
- Publishing personal contact fields because they are present.
- Using the source publisher as the facility owner or operator without evidence.
