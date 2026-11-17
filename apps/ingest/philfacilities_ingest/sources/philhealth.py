from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser

import pdfplumber

from ..contracts import (
    AccreditationData,
    FacilityCandidate,
    HealthData,
    LocationData,
    ParsedRelease,
    ParsedRow,
    ReleaseSpec,
    ValidationIssue,
    ValidationResult,
)
from .common import (
    RequiredColumnsError,
    clean_text,
    first_present,
    normalise_header,
    parse_date,
    parse_int,
)

NAME_ALIASES = [
    "name_of_health_facility",
    "name_of_facility",
    "facility_name",
    "name",
    "hospital_name",
    "institution",
]
MUNICIPALITY_ALIASES = ["municipality", "city_municipality", "city", "municipality_city"]
EXPIRY_ALIASES = [
    "expire_date",
    "expiry_date",
    "expiration_date",
    "valid_until",
    "accreditation_expiry",
    "validity",
]
BED_ALIASES = ["bed_count", "beds", "no_of_beds", "number_of_beds"]
CATEGORY_ALIASES = [
    "category",
    "cat",
    "hospital_category",
    "accreditation_category",
    "facility_category",
]
STREET_ALIASES = ["street", "address", "street_address"]
SECTOR_ALIASES = ["sec", "sector", "sector_code"]
STATUS_ALIASES = ["status", "accreditation_status"]
TELEPHONE_ALIASES = ["telephone", "tel_no", "tel", "contact"]
EMAIL_ALIASES = ["email", "e_mail"]

# Benefit-package releases can describe the service being accredited without
# establishing the facility's physical subtype. Never overwrite an existing
# facility subtype from these rows; the category is still retained on the
# health profile and accreditation.
ACCREDITATION_ONLY_CATEGORIES = {"antenatal"}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _is_provider_header(cells: list[object]) -> bool:
    """Recognise a PhilHealth provider table header.

    Several current EMCB PDFs omit the accreditation-expiry column. Name plus
    municipality/category is enough context to distinguish the provider table
    from unrelated text tables in the same document.
    """

    normalised = {normalise_header(cell) for cell in cells}
    has_name = bool(normalised & set(NAME_ALIASES))
    has_context = bool(normalised & set(MUNICIPALITY_ALIASES + EXPIRY_ALIASES + CATEGORY_ALIASES))
    return has_name and has_context


def _rows_from_tables(
    tables: list[tuple[int, list[list[object]]]],
) -> list[dict]:
    """Flatten provider tables, carrying the last header into split tables.

    pdfplumber splits a single visual table into multiple table objects whenever
    page rules interrupt it. Only the first fragment repeats the header, so
    parsing each table independently would silently drop most rows. A carried
    header is only reused when the column count matches; otherwise a different
    two-column annex (for example expiry/sector) would be misread as providers.
    """

    results: list[dict] = []
    headers: list[str] = []
    ordinals: dict[int, int] = {}
    for page_number, table in tables:
        header_index = None
        for index, row in enumerate(table[:8]):
            if _is_provider_header(row):
                header_index = index
                headers = [normalise_header(cell) for cell in row]
                break
        if header_index is None and (not headers or not table or len(table[0]) != len(headers)):
            continue
        start = 0 if header_index is None else header_index + 1
        for row_index, row in enumerate(table[start:], start=start + 1):
            if not any(clean_text(cell) for cell in row):
                continue
            payload = {
                headers[i]: clean_text(cell)
                for i, cell in enumerate(row)
                if i < len(headers) and headers[i]
            }
            if not any(payload.get(alias) for alias in NAME_ALIASES):
                # Region headings and other rule-separated single-cell rows are
                # layout, not provider records.
                continue
            payload["_page"] = page_number
            payload["_row"] = row_index
            ordinals[page_number] = ordinals.get(page_number, 0) + 1
            payload["_ordinal"] = ordinals[page_number]
            results.append(payload)
    return results


def _expiry_half_rows(
    tables: list[tuple[int, list[list[object]]]],
) -> dict[int, list[dict]]:
    """Extract the separate expiry/sector half used by some wide PDFs.

    The Antenatal PDF is a two-up landscape print: pages 1-120 carry the
    provider columns and pages 121-240 carry only EXPIRE DATE and SEC for the
    same rows in the same order. This is layout, not a second dataset.
    """

    pages: dict[int, list[dict]] = {}
    expiry_mode = False
    for page_number, table in tables:
        if not table:
            continue
        normalised = {normalise_header(cell) for cell in table[0]}
        has_expiry = bool(normalised & set(EXPIRY_ALIASES))
        has_sector = bool(normalised & set(SECTOR_ALIASES))
        has_name = bool(normalised & set(NAME_ALIASES))
        if has_expiry and has_sector and not has_name:
            expiry_mode = True
            data = table[1:]
        elif expiry_mode:
            # pdfplumber may split the two-column annex into fragments that only
            # repeat the header on the first fragment of a page.
            data = table
        else:
            continue
        for row in data:
            if len(row) != 2:
                continue
            expiry = clean_text(row[0])
            sector = clean_text(row[1])
            if expiry or sector:
                pages.setdefault(page_number, []).append({"expire_date": expiry, "sec": sector})
    return pages


def _merge_expiry_half(rows: list[dict], expiry_pages: dict[int, list[dict]]) -> None:
    """Attach aligned expiry/sector rows when both halves match page-for-page."""

    if not rows or not expiry_pages:
        return
    provider_pages: dict[int, list[dict]] = {}
    for row in rows:
        provider_pages.setdefault(int(row["_page"]), []).append(row)
    left = sorted(provider_pages)
    right = sorted(expiry_pages)
    if len(left) != len(right):
        return
    if any(
        len(provider_pages[left_page]) != len(expiry_pages[right_page])
        for left_page, right_page in zip(left, right, strict=True)
    ):
        return
    for left_page, right_page in zip(left, right, strict=True):
        for provider, expiry in zip(
            provider_pages[left_page], expiry_pages[right_page], strict=True
        ):
            provider.setdefault("expire_date", expiry["expire_date"])
            provider.setdefault("sec", expiry["sec"])


def _row_key(
    category: str,
    name: str,
    municipality: str | None,
    expiry: date | None,
    page: int,
    row: int,
) -> str:
    # The row number keeps every physical source row distinct, even when two rows
    # repeat the same facility values. Collapsing them would silently discard an
    # original source record and can create duplicate source links on retry.
    base = "|".join(
        [
            category,
            name.lower(),
            (municipality or "").lower(),
            expiry.isoformat() if expiry else "",
            str(page),
            str(row),
        ]
    )
    readable = (
        f"philhealth:{_slug(category)}:{_slug(name)[:60]}:{_slug(municipality or 'unknown')[:30]}"
    )
    return f"{readable}:{hashlib.sha256(base.encode()).hexdigest()[:10]}"


class PhilHealthPdfAdapter:
    source_code = "philhealth"
    parser_version = "philhealth-pdf-1.2.0"
    schema_version = "philhealth-accredited-pdf-v1"

    def __init__(self, spec: ReleaseSpec, provider_category: str = "Hospital") -> None:
        self.spec = spec
        self.provider_category = provider_category
        self._has_expiry_field = False

    def _table_rows(self, content: bytes) -> list[dict]:
        tables: list[tuple[int, list[list[object]]]] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables():
                    tables.append((page_number, table))
        rows = _rows_from_tables(tables)
        _merge_expiry_half(rows, _expiry_half_rows(tables))
        return rows

    def parse(self, spec: ReleaseSpec) -> ParsedRelease:
        rows = self._table_rows(spec.content)
        if not rows:
            raise RequiredColumnsError(
                "PhilHealth PDF: no table rows matched the documented provider schema."
            )
        parsed = []
        for row in rows:
            name = clean_text(first_present(row, NAME_ALIASES))
            if not name:
                continue
            municipality = clean_text(first_present(row, MUNICIPALITY_ALIASES))
            expiry = parse_date(first_present(row, EXPIRY_ALIASES))
            category = clean_text(first_present(row, CATEGORY_ALIASES)) or self.provider_category
            parsed.append(
                ParsedRow(
                    source_record_key=_row_key(
                        category,
                        name,
                        municipality,
                        expiry,
                        int(row.get("_page", 0)),
                        int(row.get("_row", 0)),
                    ),
                    row_reference=f"page:{row.get('_page')}:row:{row.get('_row')}",
                    raw_payload=row,
                    normalized_payload=row,
                )
            )
        if not parsed:
            raise RequiredColumnsError("PhilHealth PDF: no facility name could be extracted.")
        self._has_expiry_field = any(
            first_present(row.normalized_payload, EXPIRY_ALIASES) not in (None, "")
            for row in parsed
        )
        return ParsedRelease(
            rows=parsed,
            parser_version=self.parser_version,
            schema_version=self.schema_version,
        )

    def validate(self, parsed: ParsedRelease) -> ValidationResult:
        issues: list[ValidationIssue] = []
        rejected = 0
        for row in parsed.rows:
            payload = row.normalized_payload
            if not clean_text(first_present(payload, NAME_ALIASES)):
                issues.append(
                    ValidationIssue(
                        "missing_facility_name",
                        "fatal",
                        "Missing facility name",
                        row_reference=row.row_reference,
                    )
                )
                rejected += 1
                continue
            expiry = parse_date(first_present(payload, EXPIRY_ALIASES))
            if self._has_expiry_field and not expiry:
                issues.append(
                    ValidationIssue(
                        "unparsed_expiry",
                        "error",
                        "Accreditation expiry could not be parsed",
                        {"raw": first_present(payload, EXPIRY_ALIASES)},
                        row.row_reference,
                    )
                )
                rejected += 1
                continue
            beds = parse_int(first_present(payload, BED_ALIASES))
            if beds is not None and beds < 0:
                issues.append(
                    ValidationIssue(
                        "negative_bed_count",
                        "fatal",
                        "Bed count cannot be negative",
                        {"value": beds},
                        row.row_reference,
                    )
                )
                rejected += 1
        return ValidationResult(
            issues=issues, accepted_rows=len(parsed.rows) - rejected, rejected_rows=rejected
        )

    def normalize(self, parsed: ParsedRelease) -> list[FacilityCandidate]:
        candidates = []
        for row in parsed.rows:
            payload = row.normalized_payload
            name = clean_text(first_present(payload, NAME_ALIASES))
            if not name:
                continue
            municipality = clean_text(first_present(payload, MUNICIPALITY_ALIASES))
            street = clean_text(first_present(payload, STREET_ALIASES))
            category = (
                clean_text(first_present(payload, CATEGORY_ALIASES)) or self.provider_category
            )
            subtype = (
                None
                if self.provider_category.casefold() in ACCREDITATION_ONLY_CATEGORIES
                else category
            )
            expiry = parse_date(first_present(payload, EXPIRY_ALIASES))
            address = ", ".join(part for part in (street, municipality) if part) or None
            candidates.append(
                FacilityCandidate(
                    source_record_key=row.source_record_key,
                    # A facility can appear in several benefit-package PDFs. Use a
                    # category-independent agency key so those rows enrich one
                    # canonical record without cross-agency auto-merging.
                    source_entity_id=(
                        f"philhealth:{_slug(name)}:{_slug(municipality or 'unknown')}"
                    ),
                    row_reference=row.row_reference,
                    display_name=name,
                    facility_type="health_facility",
                    facility_subtype=subtype,
                    ownership="unknown",
                    record_status="active_in_registry",
                    location=LocationData(address_text=address),
                    health=HealthData(
                        facility_category=category,
                        bed_capacity=parse_int(first_present(payload, BED_ALIASES)),
                    ),
                    accreditations=[
                        AccreditationData(
                            authority="PhilHealth",
                            provider_category=self.provider_category,
                            benefit_package=self.provider_category,
                            accreditation_category=category,
                            bed_count=parse_int(first_present(payload, BED_ALIASES)),
                            sector_code=clean_text(first_present(payload, SECTOR_ALIASES)),
                            source_status=clean_text(first_present(payload, STATUS_ALIASES)),
                            valid_until=expiry,
                            source_as_of=self.spec.reference_period_end,
                            telephone=clean_text(first_present(payload, TELEPHONE_ALIASES)),
                            email=clean_text(first_present(payload, EMAIL_ALIASES)),
                            street_address=street,
                            municipality=municipality,
                            page_reference=row.row_reference,
                        )
                    ],
                )
            )
        return candidates


@dataclass(frozen=True)
class PhilHealthCatalogEntry:
    filename: str
    url: str
    category: str
    date_basis: date | None
    date_basis_label: str


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def _flush(self) -> None:
        if self._href is not None:
            label = clean_text(" ".join(self._text)) or ""
            self.links.append((self._href, label))
        self._href = None
        self._text = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        # Some agency pages omit the closing </a>. Flush the previous anchor when a
        # new one starts rather than discarding both.
        self._flush()
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        # </li> also closes malformed anchors that never emitted </a>.
        if tag.lower() in {"a", "li"}:
            self._flush()

    def close(self) -> None:
        self._flush()
        super().close()


def date_from_filename(filename: str) -> tuple[date | None, str]:
    """Read the publication date encoded in a PhilHealth PDF file name."""
    stem = filename.rsplit(".", 1)[0]
    match = re.search(r"_(\d{6})$", stem)
    if not match:
        return None, "source file name carries no publication date"
    try:
        parsed = datetime.strptime(match.group(1), "%m%d%y").date()
    except ValueError:
        return None, "source file name date could not be parsed"
    return parsed, f"date encoded in source file name ({match.group(1)})"


def parse_catalog(index_html: str, *, base_url: str) -> list[PhilHealthCatalogEntry]:
    """Extract provider-category PDF links from the public PhilHealth index."""

    from urllib.parse import urljoin

    parser = _LinkParser()
    parser.feed(index_html)
    entries: list[PhilHealthCatalogEntry] = []
    seen: set[str] = set()
    for href, label in parser.links:
        if ".pdf" not in href.lower():
            continue
        filename = href.rsplit("/", 1)[-1]
        if filename in seen:
            continue
        seen.add(filename)
        date_basis, label_basis = date_from_filename(filename)
        entries.append(
            PhilHealthCatalogEntry(
                filename=filename,
                url=urljoin(base_url, href),
                category=label or filename.rsplit(".", 1)[0],
                date_basis=date_basis,
                date_basis_label=label_basis,
            )
        )
    return entries
