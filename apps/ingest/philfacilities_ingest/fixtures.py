"""Deterministic, clearly-labelled synthetic fixtures.

These fixtures exercise the complete pipeline without pretending to be official
government releases. Every name, identifier, code, and coordinate is synthetic.
The pipeline marks their datasets `is_synthetic=True` and the API/UI label them.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

from openpyxl import Workbook

SYNTHETIC_NOTICE = (
    "SYNTHETIC DEMONSTRATION DATA — NOT AN OFFICIAL GOVERNMENT RELEASE. "
    "Names, codes, identifiers, and coordinates are invented for product testing."
)
FIXTURE_PUBLISHED_AT = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
FIXTURE_RETRIEVED_AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


@dataclass(frozen=True)
class SyntheticGeography:
    code: str
    name: str
    level: str
    parent: str | None
    urban_rural: str | None = None
    island_region: str | None = None


REGIONS = [
    SyntheticGeography(
        "9900000000",
        "Synthetic Region A (demo)",
        "region",
        None,
        island_region="Demo Island Group A",
    ),
    SyntheticGeography(
        "9800000000",
        "Synthetic Region B (demo)",
        "region",
        None,
        island_region="Demo Island Group B",
    ),
]
PROVINCES = [
    SyntheticGeography("9901000000", "Synthetic Province A1 (demo)", "province", "9900000000"),
    SyntheticGeography("9902000000", "Synthetic Province A2 (demo)", "province", "9900000000"),
    SyntheticGeography("9801000000", "Synthetic Province B1 (demo)", "province", "9800000000"),
    SyntheticGeography("9802000000", "Synthetic Province B2 (demo)", "province", "9800000000"),
]
MUNICIPALITIES = [
    SyntheticGeography(
        "9901001000", "Synthetic City A1-1 (demo)", "municipality", "9901000000", "urban"
    ),
    SyntheticGeography(
        "9901002000", "Synthetic Municipality A1-2 (demo)", "municipality", "9901000000", "rural"
    ),
    SyntheticGeography(
        "9902001000", "Synthetic City A2-1 (demo)", "municipality", "9902000000", "urban"
    ),
    SyntheticGeography(
        "9902002000", "Synthetic Municipality A2-2 (demo)", "municipality", "9902000000", "rural"
    ),
    SyntheticGeography(
        "9801001000", "Synthetic City B1-1 (demo)", "municipality", "9801000000", "urban"
    ),
    SyntheticGeography(
        "9801002000", "Synthetic Municipality B1-2 (demo)", "municipality", "9801000000", "rural"
    ),
    SyntheticGeography(
        "9802001000", "Synthetic City B2-1 (demo)", "municipality", "9802000000", "urban"
    ),
    SyntheticGeography(
        "9802002000", "Synthetic Municipality B2-2 (demo)", "municipality", "9802000000", "rural"
    ),
]
BARANGAYS = [
    SyntheticGeography(
        f"{municipality.code[:7]}{index:03d}",
        f"Synthetic Barangay {municipality.name.split()[2]} {index} (demo)",
        "barangay",
        municipality.code,
    )
    for municipality in MUNICIPALITIES
    for index in (1, 2)
]
ALL_UNITS = [*REGIONS, *PROVINCES, *MUNICIPALITIES, *BARANGAYS]
BARANGAY_CODES = [unit.code for unit in BARANGAYS]

# Approximate, deliberately coarse points inside the Philippines. They are demo coordinates,
# not claims about any real facility.
DEMO_POINTS = [
    (14.5995, 120.9842),
    (14.6760, 121.0437),
    (16.4023, 120.5960),
    (10.3157, 123.8854),
    (7.1907, 125.4553),
    (8.4542, 124.6319),
    (17.5747, 120.3869),
    (13.1391, 123.7438),
]


def _canonicalise_zip(content: bytes) -> bytes:
    """Rewrite an OOXML package with fixed ZIP metadata.

    openpyxl writes archive entry timestamps from the wall clock, so otherwise byte-identical
    workbooks produce different checksums each time they are generated. Deterministic fixture
    bytes are required to prove ingestion idempotency.
    """

    source = zipfile.ZipFile(io.BytesIO(content))
    sink = io.BytesIO()
    try:
        with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for entry in source.infolist():
                info = zipfile.ZipInfo(entry.filename, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                payload = source.read(entry.filename)
                if entry.filename == "docProps/core.xml":
                    # openpyxl overwrites dcterms:modified during save; pin it for hashing.
                    payload = re.sub(
                        rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>",
                        b'<dcterms:modified xsi:type="dcterms:W3CDTF">'
                        b"2026-11-01T09:00:00Z</dcterms:modified>",
                        payload,
                    )
                target.writestr(info, payload)
    finally:
        source.close()
    return sink.getvalue()


def _workbook_bytes(sheets: dict[str, list[list[object]]]) -> bytes:
    workbook = Workbook()
    workbook.properties.created = FIXTURE_PUBLISHED_AT.replace(tzinfo=None)
    workbook.properties.modified = FIXTURE_PUBLISHED_AT.replace(tzinfo=None)
    workbook.properties.creator = "PhilFacilities synthetic fixture generator"
    workbook.properties.lastModifiedBy = "PhilFacilities synthetic fixture generator"
    workbook.properties.title = "Synthetic demonstration fixture"
    workbook.properties.description = SYNTHETIC_NOTICE
    first = True
    for title, rows in sheets.items():
        sheet = workbook.active if first else workbook.create_sheet()
        sheet.title = title
        first = False
        for row in rows:
            sheet.append(row)
    sink = io.BytesIO()
    workbook.save(sink)
    workbook.close()
    return _canonicalise_zip(sink.getvalue())


def psgc_workbook(rename_first_barangay: str | None = None) -> bytes:
    header = [
        "psgc_code",
        "name",
        "geographic_level",
        "parent_psgc_code",
        "correspondence_code",
        "old_name",
        "city_class",
        "income_classification",
        "urban_rural",
        "island_region",
    ]
    groups = {
        "Regions": REGIONS,
        "Provinces": PROVINCES,
        "Cities": MUNICIPALITIES,
        "Barangays": BARANGAYS,
    }
    sheets: dict[str, list[list[object]]] = {}
    for title, units in groups.items():
        rows: list[list[object]] = [header]
        for unit in units:
            name = unit.name
            old_name = ""
            if rename_first_barangay and unit.code == BARANGAYS[0].code:
                name = rename_first_barangay
                old_name = unit.name
            rows.append(
                [
                    unit.code,
                    name,
                    unit.level,
                    unit.parent or "",
                    "",
                    old_name,
                    "Demo class" if unit.level == "municipality" else "",
                    "Demo income class" if unit.level in {"province", "municipality"} else "",
                    unit.urban_rural or "",
                    unit.island_region or "",
                ]
            )
        sheets[title] = rows
    sheets["Readme"] = [
        [SYNTHETIC_NOTICE],
        ["This workbook exists only to test the PhilFacilities PSGC ingestion pipeline."],
        ["It is not a PSA release and must never be presented as one."],
    ]
    return _workbook_bytes(sheets)


def deped_masterlist() -> bytes:
    header = [
        "school_id",
        "school_name",
        "sector",
        "school_management",
        "annex_status",
        "offers_es",
        "offers_jhs",
        "offers_shs",
        "latitude",
        "longitude",
        "coordinate_precision",
        "coordinate_method",
        "barangay_psgc",
        "address",
        "school_year",
    ]
    rows: list[list[object]] = [header]
    for index in range(12):
        lat, lon = DEMO_POINTS[index % len(DEMO_POINTS)]
        precision = (
            "source_gps"
            if index % 3 == 0
            else ("barangay_centroid" if index % 3 == 1 else "unknown")
        )
        use_coordinates = index % 4 != 3
        rows.append(
            [
                f"SYN-DEPED-{index + 1:04d}",
                f"Synthetic Demo School {index + 1:02d}",
                "Public" if index % 5 else "Private",
                "DepEd-managed" if index % 5 else "Private",
                "" if index % 4 else "Annex",
                "Yes",
                "Yes" if index % 2 == 0 else "No",
                "Yes" if index % 3 == 0 else "No",
                round(lat + index * 0.001, 6) if use_coordinates else "",
                round(lon + index * 0.001, 6) if use_coordinates else "",
                precision if use_coordinates else "unknown",
                "Synthetic demo point" if use_coordinates else "",
                BARANGAY_CODES[index % len(BARANGAY_CODES)],
                f"{index + 1} Synthetic Demo Street, Demo Barangay",
                "2024-2025",
            ]
        )
    return _workbook_bytes({"Masterlist": rows, "Readme": [[SYNTHETIC_NOTICE]]})


def deped_enrollment() -> bytes:
    header = ["school_id", "school_year", "grade_level", "sex", "learner_count"]
    rows: list[list[object]] = [header]
    for year_index, school_year in enumerate(("2023-2024", "2024-2025")):
        for index in range(12):
            base = 100 + index * 17 + year_index * 9
            rows.append(
                [
                    f"SYN-DEPED-{index + 1:04d}",
                    school_year,
                    "total",
                    "all",
                    base,
                ]
            )
            rows.append(
                [
                    f"SYN-DEPED-{index + 1:04d}",
                    school_year,
                    "Grade 1",
                    "female",
                    base // 2,
                ]
            )
    return _workbook_bytes({"Enrollment": rows, "Readme": [[SYNTHETIC_NOTICE]]})


def deped_resources() -> bytes:
    header = ["school_id", "school_year", "resource_category", "resource_code", "value", "unit"]
    rows: list[list[object]] = [header]
    resources = [
        ("facility", "classrooms_total", 20 + 2, "rooms"),
        ("facility", "toilets_functional", 8, "units"),
        ("wash", "water_supply", 1, "boolean"),
    ]
    for index in range(12):
        for category, code, value, unit in resources:
            rows.append(
                [
                    f"SYN-DEPED-{index + 1:04d}",
                    "2024-2025",
                    category,
                    code,
                    value + index,
                    unit,
                ]
            )
    return _workbook_bytes({"Facilities": rows, "Readme": [[SYNTHETIC_NOTICE]]})


def doh_csv() -> bytes:
    header = [
        "facility_id",
        "facility_name",
        "facility_category",
        "ownership",
        "service_capability_level",
        "bed_capacity",
        "latitude",
        "longitude",
        "coordinate_precision",
        "coordinate_method",
        "psgc_code",
        "address",
        "license_number",
        "license_status",
        "license_valid_until",
    ]
    rows: list[list[str]] = [header]
    for index in range(6):
        lat, lon = DEMO_POINTS[index]
        rows.append(
            [
                f"SYN-DOH-{index + 1:04d}",
                f"Synthetic Demo Health Facility {index + 1:02d}",
                "Hospital" if index % 2 == 0 else "Rural Health Unit",
                "Government" if index % 2 == 0 else "Private",
                "Level 1" if index % 2 == 0 else "Primary care",
                str(25 + index * 10),
                str(round(lat + 0.01, 6)),
                str(round(lon + 0.01, 6)),
                "map_geocoded" if index % 3 else "source_gps",
                "Synthetic demo geocoder",
                BARANGAY_CODES[index],
                f"{index + 1} Synthetic Health Street, Demo Barangay",
                f"SYN-LIC-{index + 1:04d}",
                "Synthetic active",
                "2027-12-31",
            ]
        )
    lines = [",".join(header)]
    for row in rows[1:]:
        lines.append(",".join(f'"{cell}"' for cell in row))
    return ("\n".join(lines) + "\n").encode("utf-8")


def philhealth_pdf(layout: str = "demo") -> bytes:
    """Generate a synthetic PhilHealth-style PDF.

    ``layout="official"`` mirrors the observed 30 September 2026 hospital/infirmary
    header names and region/province separator rows so the real-world layout stays
    covered without committing or redistributing the agency PDF.
    """

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if layout not in {"demo", "official"}:
        raise ValueError(f"Unsupported PhilHealth fixture layout: {layout}")

    sink = io.BytesIO()
    document = SimpleDocTemplate(sink, pagesize=A4, invariant=1)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(
            "Synthetic Demo Accredited Hospitals (not an official PhilHealth release)",
            styles["Title"],
        ),
        Paragraph(SYNTHETIC_NOTICE, styles["BodyText"]),
        Spacer(1, 12),
        Paragraph("Provider category: Hospital / Infirmary (synthetic demo)", styles["Heading2"]),
        Spacer(1, 8),
    ]
    if layout == "official":
        data = [
            [
                "",
                "NAME OF HEALTH FACILITY",
                "BEDS",
                "CAT",
                "TEL_NO",
                "EMAIL",
                "STREET",
                "MUNICIPALITY",
                "EXPIRE DATE",
                "SEC",
            ],
            ["SYNTHETIC REGION A (DEMO)", None, None, None, None, None, None, None, None, None],
            ["SYNTHETIC PROVINCE A1 (DEMO)", None, None, None, None, None, None, None, None, None],
        ]
    else:
        data = [
            [
                "Facility Name",
                "Bed Count",
                "Category",
                "Telephone",
                "Email",
                "Street",
                "Municipality",
                "Expiry Date",
                "SEC",
            ]
        ]
    for index in range(4):
        row = [
            f"Synthetic Demo Accredited Hospital {index + 1:02d}",
            str(50 + index * 25),
            "Hospital",
            f"02-555-01{index:02d}",
            f"demo{index + 1}@example.invalid",
            f"{index + 10} Synthetic Accreditation Avenue",
            f"Synthetic City {index + 1} (demo)",
            "12/31/2027",
            "G" if index % 2 == 0 else "P",
        ]
        if layout == "official":
            data.append([str(index + 1), *row])
        else:
            data.append(row)
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00226e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d8e6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)
    story.extend(
        [
            Spacer(1, 12),
            Paragraph(
                "Accreditation date basis: 30 September 2026 (synthetic demo).", styles["BodyText"]
            ),
            Paragraph(
                "This PDF is fabricated for parser and UI testing. It must not be "
                "redistributed as a PhilHealth source document.",
                styles["BodyText"],
            ),
        ]
    )
    document.build(story)
    return sink.getvalue()


@dataclass(frozen=True)
class FixtureFile:
    name: str
    content: bytes


def all_fixtures() -> list[FixtureFile]:
    return [
        FixtureFile("synthetic-psgc-2026-q3.xlsx", psgc_workbook()),
        FixtureFile("synthetic-deped-masterlist-2024-2025.xlsx", deped_masterlist()),
        FixtureFile("synthetic-deped-enrollment-2023-2025.xlsx", deped_enrollment()),
        FixtureFile("synthetic-deped-resources-2024-2025.xlsx", deped_resources()),
        FixtureFile("synthetic-doh-facilities-2026.csv", doh_csv()),
        FixtureFile("synthetic-philhealth-hospitals-2026-09-30.pdf", philhealth_pdf()),
    ]
