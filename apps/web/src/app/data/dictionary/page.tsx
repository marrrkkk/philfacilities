import type { Metadata } from "next";
import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
  ["inclusion_class", "controlled string", "Government facility, private public-service provider, public-access venue, or unclassified record."],
  ["ownership", "government, private, unknown", "Source-reported ownership. Unknown is not assumed public."],
  ["ownership_type, operator_type", "controlled string", "Specific public, private, joint, or unknown owner/operator type; ownership and operation are separate."],
  ["public_access_class", "controlled string", "PUBLIC_FREE, PUBLIC_PAID_OR_CONDITIONAL, SERVICE_USERS_ONLY, APPOINTMENT_ONLY, MEMBERS_STUDENTS_ONLY, STAFF_ONLY, RESTRICTED, or UNKNOWN."],
  ["functions", "string array", "Function codes recorded for the facility, such as HEALTHCARE or EVACUATION_SITE."],
  ["function_details[]", "array", "Per-source function claims with source value, designation status, validity, and optional capacity."],
  ["roles[]", "array", "Owner, operator, host, funder, regulator, and accreditor roles. Entity type and evidence are recorded separately."],
  ["services[]", "array", "Services delivered at the facility, with service code, optional name, source field, and validity."],
  ["contacts[]", "array", "Source-supplied phone, email, website, opening hours, or other contact values. Missing contact types are not inferred."],
  ["relationships[]", "array", "Explicit links to related facilities, such as a parent site or part-of relationship. Links do not merge identities."],
  ["accreditations[]", "array", "Dated, authority-specific accreditation rows. Accreditation is not ownership and not proof of current operation."],
  ["location.postal_code", "string or null", "Postal code preserved as text. Null means the source did not supply one."],
  ["record_status", "controlled string", "Registry presence, not real-time operational status."],
  ["publication_status", "public or internal", "Only public records appear in the public API."],
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

const contactTypes = [
  ["phone", "Telephone or mobile number as preserved from the source."],
  ["email", "Email address as published for the facility or its operator."],
  ["website", "Official or source-linked website, preserved as text."],
  ["opening_hours", "Source-stated opening or service hours. Not live availability."],
  ["other", "Other contact value that does not fit the typed fields."],
];

const coverageScopes = [
  ["NATIONAL_OFFICIAL_INVENTORY", "Agency-published national inventory, subject to the source's own completeness limits."],
  ["NATIONAL_PARTIAL", "National in intent but known to cover only part of the target universe."],
  ["REGIONAL", "Covers one or more regions but not the whole country."],
  ["PARTICIPATING_LGUS", "Only local government units that participate in or report to the source."],
  ["SELECTED_LGUS", "A deliberately selected set of LGUs, not a complete national list."],
  ["SINGLE_LGU", "One city or municipality only."],
  ["DIRECTORY_SUBSET", "A directory subset selected for a specific programme or purpose."],
  ["DISCOVERY_LAYER", "A discovery layer used to find candidates; it is not an official inventory."],
  ["UNKNOWN_COVERAGE", "Coverage has not been reviewed or documented."],
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
  ["sector, school_management", "Source values; not normalized policy categories."],
  ["division, district, legislative_district", "DepEd administrative areas from the SY 2020-2021 masterlist."],
  ["settlement_type", "Source settlement class: urban, partially urban, or rural."],
  ["offering_classification", "Combined source offering category retained verbatim."],
  ["offers_es, offers_jhs, offers_shs", "Tri-state: true, false, or null for unknown."],
  ["resources[]", "Dated ICT/WASH/resource observations with numeric or text values."],
];

const healthFields = [
  ["doh_facility_id", "DOH source identifier preserved as text."],
  ["facility_major_type", "NHFR major classification, such as Health Facility or Health Related Facility."],
  ["facility_type_detail", "NHFR facility type exactly as published, such as Hospital or Rural Health Unit."],
  ["facility_category", "Source category retained from the establishing release; not a normalized service capability."],
  ["ownership_subclassification", "NHFR ownership sub-classification, such as Local Government Unit or Corporation."],
  ["licensing_status", "NHFR licensing status as published: With License, Without License, or null when the source is blank."],
  ["bed_capacity", "Source bed count. Zero is a real source value; null is unknown."],
  ["licenses[]", "Time-bounded licences with issuing authority and source status."],
  ["accreditations[]", "Time-bounded PhilHealth or other accreditation rows."],
];

const utilityFields = [
  ["doe_facility_code", "DOE facility code preserved as text."],
  ["resource_type, technology_type", "Source resource and technology labels, not normalized generation categories."],
  ["connection_type, grid", "Source connection and grid labels, such as Luzon or off-grid."],
  ["owner_type, contract_type", "DOE owner and contract classes; not a legal-ownership determination."],
  ["installed_mw, dependable_mw", "Source capacity ratings in megawatts; null when blank."],
  ["number_of_units, date_commissioned", "Source unit count and commissioning date, preserved as stated."],
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
        <table className="w-full min-w-[36rem] border-collapse text-left font-sans text-sm">
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
      <p className="eyebrow rule-label text-[#0038a8]">Data dictionary</p>
      <h1 className="mt-4 max-w-4xl font-display text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
        Every field, its meaning, and what the data cannot tell you.
      </h1>
      <p className="mt-4 max-w-3xl font-sans text-base leading-relaxed text-[#5a5a58]">
        This dictionary covers the public API, downloads, and facility profiles. The OpenAPI document
        is the machine-readable contract. Category, ownership, access, and contact labels come from{" "}
        <code>GET /v1/taxonomy</code>, so clients need no second vocabulary.
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
          beds, closed, or not operating. Registry presence is not real-time operational status.
        </AlertDescription>
      </Alert>

      <section className="mt-10" aria-labelledby="reading-rules">
        <h2 id="reading-rules" className="font-display text-2xl font-extrabold">
          Reading rules
        </h2>
        <dl className="mt-4 grid gap-x-8 gap-y-4 border border-[#d1d8e6] bg-white p-5 font-sans text-sm sm:grid-cols-2">
          {[
            ["source_published_at", "When the agency published the release."],
            ["Reference period", "What the data describes."],
            ["retrieved_at", "When PhilFacilities acquired the file."],
            ["processed_at", "When ETL finished."],
            ["updated_at", "When PhilFacilities changed the record, not the agency."],
            ["PSGC codes", "Strings; keep leading zeros."],
            ["Coordinates", "WGS 84. Read location.precision before showing a building pin."],
            ["Area-level points", "Stay labelled; never present them as buildings."],
          ].map(([term, meaning]) => (
            <div key={term}>
              <dt className="font-ui text-xs font-bold uppercase tracking-wide text-[#0a0a0a]">
                {term}
              </dt>
              <dd className="mt-0.5 text-[#5a5a58]">{meaning}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="mt-10" aria-labelledby="facility-fields">
        <h2 id="facility-fields" className="font-display text-2xl font-extrabold">
          Canonical facility
        </h2>
        <p className="mt-2 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          Endpoint: <code>GET /v1/facilities/&#123;id-or-slug&#125;</code>. Bulk downloads expose a
          flattened subset with publication status visible.
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

      <section className="mt-10" aria-labelledby="contact-roles">
        <h2 id="contact-roles" className="font-display text-2xl font-extrabold">
          Contacts, roles, services, and relationships
        </h2>
        <p className="mt-2 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          These arrays appear in <code>GET /v1/facilities/&#123;id-or-slug&#125;</code>. Contact and
          service values are source claims, not a live channel check. Role entities are recorded
          even when they cannot be resolved to another canonical facility.
        </p>
        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          <div className="min-w-0">
            <h3 className="font-display text-xl font-extrabold">Contact types</h3>
            <FieldTable
              caption="Contact type values"
              columns={["Type", "Kind", "Meaning"]}
              rows={contactTypes.map(([value, meaning]) => [value, "enum", meaning])}
            />
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-xl">How to read these records</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-sans text-sm leading-relaxed text-[#5a5a58]">
              <p>
                <code>roles[]</code> separates owner, operator, host, funder, regulator, and
                accreditor. Ownership does not imply operation, and accreditation does not imply
                ownership.
              </p>
              <p>
                <code>services[]</code> and <code>function_details[]</code> preserve the source
                field and validity period. A service listed in a registry is not proof that it is
                available today.
              </p>
              <p>
                <code>relationships[]</code> are explicit links to other canonical records. They do
                not merge identities, and each linked facility keeps its own sources.
              </p>
            </CardContent>
          </Card>
        </div>
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

      <section className="mt-10" aria-labelledby="coverage-metadata">
        <h2 id="coverage-metadata" className="font-display text-2xl font-extrabold">
          Dataset coverage
        </h2>
        <p className="mt-2 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          Coverage belongs to the source dataset, not the facility. Read{" "}
          <code>coverage_scope</code> and <code>coverage_note</code> together; a published count is
          not the size of the real-world universe.
        </p>
        <FieldTable
          caption="Dataset coverage scopes"
          columns={["Scope", "Type", "Meaning"]}
          rows={coverageScopes.map(([value, meaning]) => [value, "enum", meaning])}
        />
      </section>

      <section className="mt-10" aria-labelledby="identity-queue">
        <h2 id="identity-queue" className="font-display text-2xl font-extrabold">
          Identity matching and review
        </h2>
        <p className="mt-2 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          The matcher proposes candidates from names, PSGC units, facility types, and agencies; it
          never merges automatically. Endpoint:{" "}
          <code>GET /v1/quality/match-candidates?status=pending</code>.
        </p>
        <FieldTable
          caption="Identity match candidate statuses"
          columns={["Status", "Type", "Meaning"]}
          rows={matchStatuses.map(([value, meaning]) => [value, "enum", meaning])}
        />
        <p className="mt-3 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          Reviewing and merging are separate explicit steps. Evidence moves to the survivor; the
          duplicate is retired with an audit trail.
        </p>
      </section>

      <section className="mt-10" aria-labelledby="domain-fields">
        <h2 id="domain-fields" className="font-display text-2xl font-extrabold">
          School, health, and utility fields
        </h2>
        <div className="mt-4 space-y-6">
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
          <div className="min-w-0">
            <h3 className="font-display text-xl font-extrabold">Power plants</h3>
            <FieldTable
              caption="Utility fields"
              columns={["Field", "Type", "Meaning"]}
              rows={utilityFields.map(([field, meaning]) => [field, "mixed", meaning])}
            />
          </div>
        </div>
        <p className="mt-4 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          Licences and accreditations are time-bounded, not proof of current service. School
          offerings are tri-state (true, false, null). Capacity is a registry rating, not metered
          output.
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
          <li>Published records are a partial, source-specific subset; some official files remain blocked or unacquired.</li>
          <li>Source-data rights are separate from the Apache-2.0 code licence. Check the release before reuse.</li>
          <li>The map uses demonstration tiles; no production provider is selected.</li>
          <li>Spatial queries and pagination are capped; handle structured errors and provide a text alternative to the map.</li>
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
