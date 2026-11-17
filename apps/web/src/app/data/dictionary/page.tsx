import type { Metadata } from "next";
import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiBaseUrl } from "@/lib/api";

export const metadata: Metadata = {
  title: "Data dictionary",
  description:
    "Field definitions, missing-value semantics, coordinate precision, provenance, identity-match statuses, and publication caveats for PhilFacilities data.",
};

const facilityFields = [
  ["id", "UUID", "Stable PhilFacilities identifier; not derived from a name or agency ID."],
  ["slug", "string or null", "Human-readable URL identifier. Not an identity key."],
  ["display_name", "string", "Name used for display; may be a normalized source value."],
  ["official_name", "string or null", "Name recorded as official by a source, when supplied."],
  ["facility_type", "controlled string", "Broad category: school, health facility, government office, community facility, library, museum, transport, utility, and related categories."],
  ["facility_subtype", "string or null", "Category-specific subtype. Null means the source did not establish one."],
  ["facility_kind", "controlled string", "facility, site, building, facility_unit, infrastructure_asset, or project."],
  ["inclusion_class", "controlled string", "Government facility, private public-service provider, public-access venue, or internal discovery candidate."],
  ["ownership", "government, private, unknown", "Source-reported ownership. Unknown is not assumed public."],
  ["ownership_type, operator_type", "controlled string", "Specific public, private, joint, or unknown owner/operator type; ownership and operation are separate."],
  ["public_access_class", "controlled string", "PUBLIC_FREE, PUBLIC_PAID_OR_CONDITIONAL, SERVICE_USERS_ONLY, APPOINTMENT_ONLY, MEMBERS_STUDENTS_ONLY, STAFF_ONLY, RESTRICTED, or UNKNOWN."],
  ["functions", "string array", "Function codes recorded for the facility, such as HEALTHCARE or EVACUATION_SITE."],
  ["record_status", "controlled string", "Registry presence, not real-time operational status."],
  ["publication_status", "public or internal", "Only public records appear in the public API."],
  ["is_synthetic", "boolean", "True for generated demonstration records."],
  ["created_at, updated_at", "timestamp", "PhilFacilities record times, not agency update times."],
  ["source_count", "integer", "Number of linked source records supporting the canonical record."],
];

const precisionValues = [
  ["gps_verified", "Independently verified GPS point."],
  ["field_verified", "Verified on the ground; method may not be GPS."],
  ["source_gps", "GPS coordinates supplied by the source."],
  ["map_geocoded", "Coordinates derived by geocoding an address."],
  ["barangay_centroid", "Area-level point for a barangay, not a building."],
  ["unknown", "Coordinates may exist, but the source supplied no precision."],
];

const provenanceFields = [
  ["agency, agency_code", "Publishing agency and short code."],
  ["dataset, dataset_slug", "Dataset name and stable slug."],
  ["release_id, release_label", "Specific source release used."],
  ["source_record_id", "Agency record key preserved as text."],
  ["source_record_uuid", "PhilFacilities identifier for the preserved source row."],
  ["row_reference", "Row number or PDF page reference in the source file."],
  ["source_published_at", "When the agency published the release, if known."],
  ["reference_period_start, reference_period_end", "Period the data describes."],
  ["retrieved_at, processed_at", "Acquisition time and ETL completion time."],
  ["match_method, match_status", "How and how confidently the source record was linked."],
  ["match_confidence", "Numeric confidence for the recorded link method."],
  ["rights_status, publication_status", "Dataset redistribution state and publication gate."],
  ["license_identifier, attribution_text", "Recorded licence and required attribution."],
  ["is_synthetic", "Whether the source dataset is synthetic."],
];

const redistributionValues = [
  ["unknown", "No rights review has been completed. Do not republish."],
  ["review_required", "Access or reuse terms are unresolved; publication stays blocked."],
  ["approved_public_redistribution", "Terms permit public redistribution."],
  ["approved_with_attribution", "Publication is permitted with the recorded attribution text."],
  [
    "publicly_available_verified",
    "Verified and publicly available with no explicit prohibition; only reviewed institutional fields are published.",
  ],
  ["restricted_non_redistributable", "Records may be retained internally but not republished."],
  ["denied", "The source has denied the intended reuse."],
  ["expired", "A previously recorded permission is no longer current."],
];

const matchStatuses = [
  ["pending", "Deterministic evidence exists, but no reviewer has decided."],
  ["accepted", "A reviewer confirmed the duplicate. Merging is still a separate explicit step."],
  ["rejected", "A reviewer rejected the candidate. The pair is retained and not re-queued for the same algorithm version."],
  ["merged", "The accepted source facility was retired into the surviving candidate facility with audit history."],
];

const schoolFields = [
  ["deped_school_id", "DepEd school identifier preserved as text."],
  ["sector, school_management, annex_status", "Source values; not normalized policy categories."],
  ["offers_es, offers_jhs, offers_shs", "Tri-state: true, false, or null for unknown."],
  ["reference_school_year", "School year the profile describes."],
  ["enrollment_total", "Latest total when an observation exists; otherwise null."],
  ["enrollment[]", "Dated observations by school year, grade level, and sex."],
  ["resources[]", "Dated ICT/WASH/resource observations with numeric or text values."],
];

const healthFields = [
  ["doh_facility_id", "DOH source identifier preserved as text."],
  ["facility_category", "Source category, not a normalized service capability."],
  ["service_capability_level", "Source capability string when supplied."],
  ["bed_capacity", "Source bed count. Null is unknown, not zero."],
  ["licenses[]", "Time-bounded licences with issuing authority and source status."],
  ["accreditations[]", "Time-bounded PhilHealth or other accreditation rows."],
];

function FieldTable({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: [string, string, string];
  rows: string[][];
}) {
  return (
    <div className="mt-5 min-w-0 overflow-hidden border border-[#d1d8e6]">
      <div className="table-scroll" role="region" aria-label={caption} tabIndex={0}>
        <table className="w-full min-w-[42rem] border-collapse text-left font-sans text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
            <tr>
              {columns.map((column) => (
                <th key={column} scope="col" className="border-b border-[#d1d8e6] p-3">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row[0]} className="align-top hover:bg-[#f9fbff]">
                <th scope="row" className="border-b border-[#d1d8e6] p-3 font-mono text-xs font-semibold text-[#0a0a0a]">
                  {row[0]}
                </th>
                <td className="border-b border-[#d1d8e6] p-3 text-xs text-[#5a5a58]">{row[1]}</td>
                <td className="border-b border-[#d1d8e6] p-3 text-[#5a5a58]">{row[2]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function DataDictionaryPage() {
  const base = apiBaseUrl();

  return (
    <div className="container-page py-10">
      <Breadcrumbs items={[{ label: "Data & Sources", href: "/data" }, { label: "Data dictionary" }]} />
      <div className="flex flex-wrap items-center gap-2">
        <p className="eyebrow rule-label text-[#0038a8]">Data dictionary</p>
        <Badge tone="success">Real sources + labelled fixtures</Badge>
      </div>
      <h1 className="mt-4 max-w-4xl font-display text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
        Every field, its meaning, and what the data cannot tell you.
      </h1>
      <p className="mt-4 max-w-3xl font-sans text-base leading-relaxed text-[#5a5a58]">
        This dictionary describes the public API, downloads, and facility profiles. The OpenAPI
        document remains the machine-readable contract. Published records trace to a registered
        source release; any remaining synthetic fixtures are labelled <code>is_synthetic=true</code>.
      </p>

      <div className="mt-6 flex flex-wrap gap-3">
        <a
          href={`${base}/docs`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-10 items-center gap-2 border border-[#0038a8] bg-[#0038a8] px-4 font-ui text-[15px] font-bold text-white no-underline"
        >
          Interactive API docs <ExternalLink aria-hidden="true" className="size-4" />
        </a>
        <a
          href={`${base}/openapi.json`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-10 items-center gap-2 border border-[#d1d8e6] bg-white px-4 font-ui text-[15px] font-bold text-[#0a0a0a] no-underline"
        >
          OpenAPI JSON <ExternalLink aria-hidden="true" className="size-4" />
        </a>
        <Link
          href="/data"
          className="inline-flex h-10 items-center gap-2 border border-[#d1d8e6] bg-white px-4 font-ui text-[15px] font-bold text-[#0a0a0a] no-underline"
        >
          Dataset catalogue
        </Link>
      </div>

      <Alert tone="warning" className="mt-6">
        <AlertTitle>Missing is not zero, false, or inactive</AlertTitle>
        <AlertDescription>
          A null value means the source did not supply a usable value. It never means zero
          enrollment, zero beds, closed, or not operating. Registry presence is not real-time
          operational status.
        </AlertDescription>
      </Alert>

      <section className="mt-10" aria-labelledby="reading-rules">
        <h2 id="reading-rules" className="font-display text-2xl font-extrabold">
          Reading rules
        </h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Four different times</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-sans text-sm leading-relaxed text-[#5a5a58]">
              <p>
                <code>source_published_at</code> is the agency&apos;s publication time. The
                reference period is what the data describes. <code>retrieved_at</code> is when
                PhilFacilities acquired the file. <code>processed_at</code> is when ETL finished.
              </p>
              <p>
                <code>updated_at</code> is when PhilFacilities changed its canonical record. It is
                not an agency update.
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Codes and coordinates</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-sans text-sm leading-relaxed text-[#5a5a58]">
              <p>
                PSGC values are strings and may contain leading zeros. Do not parse them as
                integers.
              </p>
              <p>
                Coordinates are WGS 84. Read <code>location.precision</code> before presenting a
                point as a building location. Area-level points stay labelled.
              </p>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="mt-10" aria-labelledby="facility-fields">
        <h2 id="facility-fields" className="font-display text-2xl font-extrabold">
          Canonical facility
        </h2>
        <p className="mt-2 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          Endpoint: <code>GET /v1/facilities/&#123;id-or-slug&#125;</code>. Bulk downloads expose a
          flattened subset and keep <code>is_synthetic</code> and publication status visible.
        </p>
        <FieldTable
          caption="Canonical facility fields"
          columns={["Field", "Type", "Meaning"]}
          rows={facilityFields}
        />
      </section>

      <section className="mt-10" aria-labelledby="location-precision">
        <h2 id="location-precision" className="font-display text-2xl font-extrabold">
          Coordinate precision
        </h2>
        <FieldTable
          caption="Coordinate precision values"
          columns={["Precision", "Type", "Meaning"]}
          rows={precisionValues.map(([value, meaning]) => [value, "enum", meaning])}
        />
      </section>

      <section className="mt-10" aria-labelledby="provenance">
        <h2 id="provenance" className="font-display text-2xl font-extrabold">
          Provenance and releases
        </h2>
        <p className="mt-2 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          Endpoint: <code>GET /v1/facilities/&#123;id-or-slug&#125;/sources</code>. Every canonical
          record keeps original source identifiers and release context.
        </p>
        <FieldTable
          caption="Source evidence fields"
          columns={["Field", "Type", "Meaning"]}
          rows={provenanceFields.map(([field, meaning]) => [field, "mixed", meaning])}
        />
        <div className="mt-6">
          <h3 className="font-display text-xl font-extrabold">Redistribution status</h3>
          <FieldTable
            caption="Redistribution status values"
            columns={["Status", "Type", "Meaning"]}
            rows={redistributionValues.map(([value, meaning]) => [value, "enum", meaning])}
          />
        </div>
      </section>

      <section className="mt-10" aria-labelledby="identity-queue">
        <h2 id="identity-queue" className="font-display text-2xl font-extrabold">
          Identity matching and review
        </h2>
        <p className="mt-2 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          The matcher proposes candidates using exact normalized names, the same current PSGC unit,
          compatible facility types, and different agencies. It never merges automatically.
          Endpoint: <code>GET /v1/quality/match-candidates?status=pending</code>.
        </p>
        <FieldTable
          caption="Identity match candidate statuses"
          columns={["Status", "Type", "Meaning"]}
          rows={matchStatuses.map(([value, meaning]) => [value, "enum", meaning])}
        />
        <p className="mt-3 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          Reviewer decisions are applied with the ingestion CLI. Rejected pairs are retained so the
          same candidate is not generated repeatedly. Merging is a separate explicit operation that
          moves evidence to the surviving facility, retires the duplicate as an internal tombstone,
          and records change events on both records.
        </p>
      </section>

      <section className="mt-10" aria-labelledby="domain-fields">
        <h2 id="domain-fields" className="font-display text-2xl font-extrabold">
          School and health fields
        </h2>
        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          <div className="min-w-0">
            <h3 className="font-display text-xl font-extrabold">Schools</h3>
            <FieldTable
              caption="School fields"
              columns={["Field", "Type", "Meaning"]}
              rows={schoolFields.map(([field, meaning]) => [field, "mixed", meaning])}
            />
          </div>
          <div className="min-w-0">
            <h3 className="font-display text-xl font-extrabold">Health facilities</h3>
            <FieldTable
              caption="Health facility fields"
              columns={["Field", "Type", "Meaning"]}
              rows={healthFields.map(([field, meaning]) => [field, "mixed", meaning])}
            />
          </div>
        </div>
        <p className="mt-4 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          Licences and accreditations are time-bounded records, not a real-time guarantee that a
          service is available or reimbursable. School offerings are tri-state: true, false, or null
          for unknown.
        </p>
      </section>

      <section className="mt-10" aria-labelledby="quality-history">
        <h2 id="quality-history" className="font-display text-2xl font-extrabold">
          Quality issues and change history
        </h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Quality issues</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-sans text-sm leading-relaxed text-[#5a5a58]">
              <p>
                <code>GET /v1/quality/summary</code> reports measured counts.{" "}
                <code>GET /v1/quality/issues</code> lists issue codes, severity, evidence, and open
                or resolved status.
              </p>
              <p>
                A clean summary is not a proof of correctness. Counts describe processed records,
                not the real-world facility universe.
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Change history</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-sans text-sm leading-relaxed text-[#5a5a58]">
              <p>
                <code>GET /v1/facilities/&#123;id&#125;/history</code> returns append-oriented change
                events. <code>GET /v1/changes?since=</code> is the cursor-paginated feed.
              </p>
              <p>
                Merge events record the source and surviving facility IDs. Corrections create new
                events rather than rewriting earlier evidence.
              </p>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="mt-10 border-t border-[#d1d8e6] pt-8" aria-labelledby="caveats">
        <h2 id="caveats" className="font-display text-2xl font-extrabold">
          Publication caveats
        </h2>
        <ul className="mt-4 max-w-3xl space-y-2 font-sans text-sm leading-relaxed text-[#5a5a58]">
          <li>Published records are a partial, source-specific subset. The dataset catalogue lists the sources currently represented; DepEd EBEIS canonical rows remain internal and official PSA/DepEd/DOH files remain blocked or unacquired.</li>
          <li>Source-data rights are separate from the Apache-2.0 code licence. Check the source release before reuse.</li>
          <li>The map uses demonstration tiles; a production provider and licence are not selected.</li>
          <li>Production backups, monitoring, WAF/TLS, and an external security review are not configured.</li>
          <li>Spatial queries and pagination are capped server-side; clients must handle structured errors and provide a text alternative to the map.</li>
        </ul>
        <p className="mt-4 font-sans text-sm leading-relaxed text-[#5a5a58]">
          The repository copy of this dictionary is{" "}
          <code>docs/data-dictionary.md</code>. Operational procedures are in the{" "}
          <Link href="/about" className="underline">
            about and governance page
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
