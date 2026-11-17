import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AlertTriangle, ExternalLink, MapPin } from "lucide-react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { LocationMap } from "@/components/map/location-map";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  getFacility,
  getFacilityAssertions,
  getFacilityChanges,
  getHealthDetail,
  getSchoolDetail,
  getTaxonomy,
  type AttributeAssertionOut,
  type FacilityDetail,
  type HealthDetailResponse,
  type SchoolDetailResponse,
} from "@/lib/api";
import {
  formatDate,
  formatDateTime,
  formatNumber,
  isPreciseLocation,
  PRECISION_DESCRIPTIONS,
  PRECISION_LABELS,
  titleCase,
} from "@/lib/format";
import { labelFor, subtypeOptions, termLabels } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

type Params = Promise<{ id: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { id } = await params;
  try {
    const facility = await getFacility(id);
    return {
      title: facility.display_name,
      description: `Source-linked profile for ${facility.display_name}, a ${facility.facility_type.replaceAll("_", " ")} in the PhilFacilities registry.`,
    };
  } catch {
    return { title: "Facility not found" };
  }
}

function DataRow({
  label,
  children,
  stacked = false,
}: {
  label: string;
  children: React.ReactNode;
  stacked?: boolean;
}) {
  return (
    <div
      className={cn(
        "grid gap-1 border-b border-[#d1d8e6] py-3 last:border-b-0",
        !stacked && "sm:grid-cols-[12rem_1fr] sm:gap-4",
      )}
    >
      <dt className="font-ui text-xs font-bold uppercase tracking-wide text-[#5a5a58]">{label}</dt>
      <dd className="min-w-0 break-words font-sans text-sm">{children}</dd>
    </div>
  );
}

function Section({
  id,
  title,
  description,
  children,
}: {
  id?: string;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 border-t border-[#d1d8e6] pt-8">
      <h2 className="font-display text-2xl font-extrabold tracking-tight sm:text-3xl">{title}</h2>
      {description ? (
        <p className="mt-2 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          {description}
        </p>
      ) : null}
      <div className="mt-5">{children}</div>
    </section>
  );
}

export default async function FacilityPage({ params }: { params: Params }) {
  const { id } = await params;

  let facility: FacilityDetail;
  try {
    facility = await getFacility(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const [typed, changes, assertions, taxonomy] = await Promise.all([
    facility.facility_type === "school"
      ? getSchoolDetail(id).catch(() => null)
      : getHealthDetail(id).catch(() => null),
    getFacilityChanges(id).catch(() => null),
    getFacilityAssertions(id).catch(() => [] as AttributeAssertionOut[]),
    getTaxonomy().catch(() => null),
  ]);

  const school = typed && "enrollment" in typed ? (typed as SchoolDetailResponse) : null;
  const health = typed && "licenses" in typed ? (typed as HealthDetailResponse) : null;
  const categoryLabels = termLabels(taxonomy?.categories);
  const subtypeLabels = new Map(subtypeOptions(taxonomy).map((item) => [item.code, item.label]));
  const inclusionLabels = termLabels(taxonomy?.inclusion_classes);
  const ownershipLabels = termLabels(taxonomy?.ownership_types);
  const operatorLabels = termLabels(taxonomy?.operator_types);
  const accessLabels = termLabels(taxonomy?.access_classes);
  const kindLabels = termLabels(taxonomy?.facility_kinds);
  const recordStatusLabels = termLabels(taxonomy?.record_statuses);
  const contactLabels = termLabels(taxonomy?.contact_types);
  const categoryLabel = labelFor(categoryLabels, facility.facility_type);
  const subtypeLabel = facility.facility_subtype
    ? (subtypeLabels.get(facility.facility_subtype) ?? titleCase(facility.facility_subtype))
    : null;
  const inclusionLabel = labelFor(inclusionLabels, facility.inclusion_class);
  const ownershipLabel = labelFor(ownershipLabels, facility.ownership_type);
  const operatorLabel = labelFor(operatorLabels, facility.operator_type);
  const accessLabel = labelFor(accessLabels, facility.public_access_class);
  const kindLabel = labelFor(kindLabels, facility.facility_kind);
  const recordStatusLabel = labelFor(recordStatusLabels, facility.record_status);
  const contacts = facility.contacts ?? [];
  const functionDetails = facility.function_details ?? [];
  const relationships = facility.relationships ?? [];
  const accreditations = facility.accreditations ?? [];
  const geography = facility.geography;
  const place = [geography.barangay_name, geography.municipality_name, geography.province_name, geography.region_name]
    .filter(Boolean)
    .join(", ");
  const showMap =
    facility.location.latitude != null &&
    facility.location.longitude != null &&
    facility.location.precision !== "unknown";
  const latitude = facility.location.latitude;
  const longitude = facility.location.longitude;
  const sources = facility.sources ?? [];
  const warnings = facility.quality.warnings ?? [];

  return (
    <div className="container-page py-10">
      <Breadcrumbs
        items={[
          { href: "/directory", label: "Directory" },
          { label: facility.display_name },
        ]}
      />

      <header className="border-b border-[#d1d8e6] pb-8">
        <div className="flex flex-wrap gap-1.5">
          <Badge tone={facility.facility_type === "school" ? "default" : "outline"}>
            {categoryLabel}
          </Badge>
          {subtypeLabel ? <Badge tone="muted">{subtypeLabel}</Badge> : null}
          <Badge tone={facility.inclusion_class === "GOVERNMENT_FACILITY" ? "default" : "outline"}>
            {inclusionLabel}
          </Badge>
          <Badge tone="muted">{ownershipLabel}</Badge>
          {facility.public_access_class !== "UNKNOWN" ? (
            <Badge tone="outline">{accessLabel}</Badge>
          ) : null}
          {facility.is_synthetic ? <Badge tone="sun">Synthetic demo record</Badge> : null}
        </div>
        <h1 className="mt-3 max-w-4xl font-display text-4xl font-extrabold leading-[1.02] tracking-tight sm:text-5xl">
          {facility.display_name}
        </h1>
        {facility.official_name && facility.official_name !== facility.display_name ? (
          <p className="mt-2 font-sans text-base text-[#5a5a58]">
            Official name: <span className="text-[#0a0a0a]">{facility.official_name}</span>
          </p>
        ) : null}
        <p className="mt-3 flex items-start gap-2 font-sans text-base text-[#5a5a58]">
          <MapPin aria-hidden="true" className="mt-1 size-4 shrink-0 text-[#0038a8]" />
          <span>
            {facility.location.address_text ?? "Address not supplied"}
            {facility.location.postal_code ? `, ${facility.location.postal_code}` : ""} ·{" "}
            {place || "Administrative geography not linked"}
          </span>
        </p>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 font-ui text-xs text-[#5a5a58]">
          <span>Canonical ID: <code>{facility.id}</code></span>
          <span>Record created {formatDateTime(facility.created_at)}</span>
          <span>Canonical record updated {formatDateTime(facility.updated_at)}</span>
        </div>
      </header>

      {facility.is_synthetic ? (
        <Alert tone="warning" className="mt-6">
          <AlertTitle>Synthetic demonstration record</AlertTitle>
          <AlertDescription>
            This facility, its identifiers, coordinates, dates, and observations were generated for
            product testing. It is not an official government record and must not be cited as one.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_20rem]">
        <div className="min-w-0 space-y-10">
          <Section
            title="Registry classification"
            description="Inclusion class, ownership and access are separate facts. A licence, accreditation or public funding does not make a private provider government-owned."
          >
            <dl>
              <DataRow label="Category">{categoryLabel}</DataRow>
              <DataRow label="Subtype">{subtypeLabel ?? "Not supplied"}</DataRow>
              <DataRow label="Facility kind">{kindLabel}</DataRow>
              <DataRow label="Inclusion class">{inclusionLabel}</DataRow>
              <DataRow label="Ownership">
                {titleCase(facility.ownership)}
                <span className="ml-2 text-[#5a5a58]">({ownershipLabel})</span>
              </DataRow>
              <DataRow label="Operator type">{operatorLabel}</DataRow>
              <DataRow label="Public access">
                {accessLabel}
                {facility.access_conditions ? (
                  <p className="mt-1 text-[#5a5a58]">{facility.access_conditions}</p>
                ) : null}
              </DataRow>
              <DataRow label="Functions">
                {(facility.functions ?? []).length > 0
                  ? (facility.functions ?? []).map((value) => titleCase(value)).join(", ")
                  : "No function recorded"}
              </DataRow>
              <DataRow label="Registry status">
                {recordStatusLabel} · {titleCase(facility.publication_status)}
              </DataRow>
            </dl>
          </Section>

          {functionDetails.length > 0 ? (
            <Section
              title="Functions recorded by sources"
              description="A function describes what a place is for. It is recorded per source claim with its own validity period and designation status; it is not a live service guarantee."
            >
              <div
                className="table-scroll border border-[#d1d8e6]"
                role="region"
                aria-label="Source-recorded functions"
                tabIndex={0}
              >
                <table className="w-full min-w-[40rem] border-collapse text-left font-sans text-sm">
                  <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                    <tr>
                      <th className="border-b border-[#d1d8e6] p-3">Function</th>
                      <th className="border-b border-[#d1d8e6] p-3">Source value</th>
                      <th className="border-b border-[#d1d8e6] p-3">Designation</th>
                      <th className="border-b border-[#d1d8e6] p-3">Capacity</th>
                      <th className="border-b border-[#d1d8e6] p-3">Valid from</th>
                      <th className="border-b border-[#d1d8e6] p-3">Valid to</th>
                    </tr>
                  </thead>
                  <tbody>
                    {functionDetails.map((actor, index) => (
                      <tr key={`${actor.function_code}-${actor.source_record_id ?? index}`}>
                        <td className="border-b border-[#d1d8e6] p-3 font-ui text-sm font-bold">
                          {titleCase(actor.function_code)}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3">
                          {actor.source_value ?? "—"}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3">
                          {actor.designation_status
                            ? titleCase(actor.designation_status)
                            : "Not stated"}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3">
                          {actor.capacity_value !== null && actor.capacity_value !== undefined
                            ? `${formatNumber(actor.capacity_value)} ${actor.capacity_unit ?? ""}`.trim()
                            : "—"}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3 text-xs">
                          {formatDate(actor.valid_from)}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3 text-xs">
                          {formatDate(actor.valid_to)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          ) : null}

          {contacts.length > 0 ? (
            <Section
              title="Contacts and visiting information"
              description="Contact values are source-supplied and may be stale. Missing contact types are not inferred. Opening hours describe the source publication, not live availability."
            >
              <dl>
                {contacts.map((contact, index) => {
                  const typeLabel = labelFor(contactLabels, contact.contact_type);
                  const isEmail = contact.contact_type === "email";
                  const isWebsite = contact.contact_type === "website";
                  const isPhone = contact.contact_type === "phone";
                  const href = isEmail
                    ? `mailto:${contact.value}`
                    : isWebsite
                      ? /^https?:\/\//i.test(contact.value)
                        ? contact.value
                        : `https://${contact.value}`
                      : isPhone
                        ? `tel:${contact.value.replace(/[^\d+]/g, "")}`
                        : null;
                  return (
                    <DataRow
                      key={`${contact.contact_type}-${contact.value}-${index}`}
                      label={contact.label ? `${typeLabel} · ${contact.label}` : typeLabel}
                    >
                      {href ? (
                        <a
                          href={href}
                          className="text-[#0038a8] underline"
                          rel={isWebsite ? "noreferrer" : undefined}
                          target={isWebsite ? "_blank" : undefined}
                        >
                          {contact.value}
                        </a>
                      ) : (
                        contact.value
                      )}
                      {contact.valid_from || contact.valid_to ? (
                        <p className="mt-1 text-xs text-[#5a5a58]">
                          Valid {formatDate(contact.valid_from)} – {formatDate(contact.valid_to)}
                        </p>
                      ) : null}
                      {contact.source_field ? (
                        <p className="mt-1 font-mono text-xs text-[#5a5a58]">
                          Source field: {contact.source_field}
                        </p>
                      ) : null}
                      {contact.review_status && contact.review_status !== "accepted" ? (
                        <p className="mt-1 text-xs text-[#5a5a58]">
                          Review status: {titleCase(contact.review_status)}
                        </p>
                      ) : null}
                    </DataRow>
                  );
                })}
              </dl>
            </Section>
          ) : null}

          {accreditations.length > 0 ? (
            <Section
              title="Accreditations"
              description="Accreditation is a dated, authority-specific record. A licence or accreditation does not make a private provider government-owned, and it is not proof of current operating availability."
            >
              <div
                className="table-scroll border border-[#d1d8e6]"
                role="region"
                aria-label="Accreditations"
                tabIndex={0}
              >
                <table className="w-full min-w-[48rem] border-collapse text-left font-sans text-sm">
                  <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                    <tr>
                      <th className="border-b border-[#d1d8e6] p-3">Authority</th>
                      <th className="border-b border-[#d1d8e6] p-3">Category</th>
                      <th className="border-b border-[#d1d8e6] p-3">Benefit package</th>
                      <th className="border-b border-[#d1d8e6] p-3">Beds</th>
                      <th className="border-b border-[#d1d8e6] p-3">Source status</th>
                      <th className="border-b border-[#d1d8e6] p-3">Source as of</th>
                      <th className="border-b border-[#d1d8e6] p-3">Valid until</th>
                      <th className="border-b border-[#d1d8e6] p-3">Reference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accreditations.map((row) => (
                      <tr key={row.id}>
                        <td className="border-b border-[#d1d8e6] p-3 font-ui text-sm font-bold">
                          {row.authority}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3">
                          {row.accreditation_category ?? row.provider_category}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3">
                          {row.benefit_package ?? "—"}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3">
                          {row.bed_count !== null && row.bed_count !== undefined
                            ? formatNumber(row.bed_count)
                            : "Unknown"}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3">
                          {row.source_status ?? "Unknown"}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3 text-xs">
                          {formatDate(row.source_as_of)}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3 text-xs">
                          {formatDate(row.valid_until)}
                        </td>
                        <td className="border-b border-[#d1d8e6] p-3 font-mono text-xs">
                          {row.page_reference ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          ) : null}

          {relationships.length > 0 ? (
            <Section
              title="Related facilities"
              description="Relationships are explicit source or registry links between records. They are not merged identities, and each linked record remains separately sourced."
            >
              <ul className="space-y-2">
                {relationships.map((relationship, index) => (
                  <li
                    key={`${relationship.relationship_type}-${relationship.related_facility_id}-${index}`}
                    className="border border-[#d1d8e6] bg-white p-4"
                  >
                    <p className="font-ui text-xs font-bold uppercase tracking-wide text-[#5a5a58]">
                      {titleCase(relationship.relationship_type)}
                    </p>
                    <Link
                      href={`/facilities/${
                        relationship.related_facility_slug ?? relationship.related_facility_id
                      }`}
                      className="mt-1 inline-block font-display text-lg font-bold text-[#0038a8] underline"
                    >
                      {relationship.related_facility_name ?? relationship.related_facility_id}
                    </Link>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          {(facility.roles ?? []).length > 0 || (facility.services ?? []).length > 0 ? (
            <Section
              title="Roles and services"
              description="Owner, operator, host, funder, regulator and accreditor are recorded separately from the facility itself."
            >
              {(facility.roles ?? []).length > 0 ? (
                <div>
                  <h3 className="font-display text-xl font-bold">Roles</h3>
                  <dl className="mt-3">
                    {(facility.roles ?? []).map((role, index) => (
                      <DataRow
                        key={`${role.role_type}-${role.entity_name}-${index}`}
                        label={titleCase(role.role_type)}
                      >
                        {role.entity_name}
                        {role.entity_type ? (
                          <span className="ml-2 text-[#5a5a58]">
                            ({titleCase(role.entity_type)})
                          </span>
                        ) : null}
                        {role.evidence?.basis ? (
                          <p className="mt-1 text-xs text-[#5a5a58]">
                            Evidence: {String(role.evidence.basis)}
                          </p>
                        ) : null}
                      </DataRow>
                    ))}
                  </dl>
                </div>
              ) : null}
              {(facility.services ?? []).length > 0 ? (
                <div className="mt-6">
                  <h3 className="font-display text-xl font-bold">Services</h3>
                  <dl className="mt-3">
                    {(facility.services ?? []).map((service, index) => (
                      <DataRow
                        key={`${service.service_code}-${service.source_field ?? "unknown"}-${index}`}
                        label={service.service_name ?? titleCase(service.service_code)}
                      >
                        {service.service_code}
                        {service.source_field ? (
                          <span className="ml-2 text-xs text-[#5a5a58]">
                            Source field: {service.source_field}
                          </span>
                        ) : null}
                      </DataRow>
                    ))}
                  </dl>
                </div>
              ) : null}
            </Section>
          ) : null}

          <Section
            title="Location and geography"
            description="Coordinates are shown only with their source precision. A barangay centroid is an area reference, not a building pin."
          >
            <dl>
              <DataRow label="Address (source text)">
                {facility.location.address_text ?? "Not supplied"}
              </DataRow>
              <DataRow label="Postal code">
                {facility.location.postal_code ?? "Not supplied"}
              </DataRow>
              <DataRow label="Barangay">
                {geography.barangay_name ?? "Unknown"}
                {geography.barangay_code ? (
                  <span className="ml-2 font-mono text-xs text-[#5a5a58]">
                    PSGC {geography.barangay_code}
                  </span>
                ) : null}
              </DataRow>
              <DataRow label="Municipality / city">
                {geography.municipality_name ?? "Unknown"}
              </DataRow>
              <DataRow label="Province">{geography.province_name ?? "Unknown / not applicable"}</DataRow>
              <DataRow label="Region">{geography.region_name ?? "Unknown"}</DataRow>
              <DataRow label="PSGC code">
                {geography.barangay_code ? (
                  <span className="font-mono text-xs">{geography.barangay_code}</span>
                ) : (
                  "Not linked"
                )}
              </DataRow>
              <DataRow label="PSGC release">{geography.psgc_release ?? "No linked release"}</DataRow>
              <DataRow label="Location precision">
                <span className="font-ui text-sm font-bold">
                  {PRECISION_LABELS[facility.location.precision] ?? facility.location.precision}
                </span>
                <p className="mt-1 text-[#5a5a58]">
                  {PRECISION_DESCRIPTIONS[facility.location.precision] ??
                    PRECISION_DESCRIPTIONS.unknown}
                </p>
                {facility.location.method ? (
                  <p className="mt-1 text-xs text-[#5a5a58]">Method: {facility.location.method}</p>
                ) : null}
              </DataRow>
              <DataRow label="Raw coordinates">
                {facility.location.latitude !== null && facility.location.longitude !== null
                  ? `${facility.location.latitude}, ${facility.location.longitude}`
                  : "Unknown"}
              </DataRow>
            </dl>

            <div className="mt-5">
              {showMap && latitude != null && longitude != null ? (
                <LocationMap
                  latitude={latitude}
                  longitude={longitude}
                  precision={facility.location.precision}
                  name={facility.display_name}
                />
              ) : (
                <Alert tone="info">
                  <AlertTitle>No map is shown for this record</AlertTitle>
                  <AlertDescription>
                    {facility.location.latitude === null
                      ? "This record has no source coordinates. Missing coordinates remain unknown; no location was inferred."
                      : "Coordinates exist but their precision is unknown, so they are not promoted to a building pin."}
                  </AlertDescription>
                </Alert>
              )}
            </div>
          </Section>

          {school ? (
            <>
              <Section
                title="School profile"
                description="School characteristics are source observations tied to a school year. They are not a live operational status."
              >
                <dl>
                  <DataRow label="DepEd school ID">{school.facility.school?.deped_school_id ?? "Unknown"}</DataRow>
                  <DataRow label="Sector / ownership">
                    {school.facility.school?.sector ?? titleCase(facility.ownership)}
                  </DataRow>
                  <DataRow label="School management">
                    {school.facility.school?.school_management ?? "Unknown"}
                  </DataRow>
                  <DataRow label="Annex status">
                    {school.facility.school?.annex_status ?? "Unknown"}
                  </DataRow>
                  <DataRow label="Reference school year">
                    {school.facility.school?.reference_school_year ?? "Unknown"}
                  </DataRow>
                  <DataRow label="Offers">
                    {[
                      school.facility.school?.offers_es ? "Elementary" : null,
                      school.facility.school?.offers_jhs ? "Junior high school" : null,
                      school.facility.school?.offers_shs ? "Senior high school" : null,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "Unknown"}
                  </DataRow>
                </dl>
              </Section>

              <Section
                title="Enrollment observations"
                description="Each row keeps its school year, grade level, sex dimension, observation time, and source record. Missing counts are not filled with zero."
              >
                {school.enrollment.length > 0 ? (
                  <div className="table-scroll border border-[#d1d8e6]" role="region" aria-label="Enrollment observations" tabIndex={0}>
                    <table className="w-full min-w-[36rem] border-collapse text-left font-sans text-sm">
                      <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                        <tr>
                          <th className="border-b border-[#d1d8e6] p-3">School year</th>
                          <th className="border-b border-[#d1d8e6] p-3">Grade level</th>
                          <th className="border-b border-[#d1d8e6] p-3">Sex</th>
                          <th className="border-b border-[#d1d8e6] p-3">Learners</th>
                          <th className="border-b border-[#d1d8e6] p-3">Observed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {school.enrollment.map((row) => (
                          <tr key={`${row.school_year}-${row.grade_level}-${row.sex}-${row.source_record_id}`}>
                            <td className="border-b border-[#d1d8e6] p-3">{row.school_year}</td>
                            <td className="border-b border-[#d1d8e6] p-3">{row.grade_level}</td>
                            <td className="border-b border-[#d1d8e6] p-3">{titleCase(row.sex)}</td>
                            <td className="border-b border-[#d1d8e6] p-3">{formatNumber(row.learner_count)}</td>
                            <td className="border-b border-[#d1d8e6] p-3 text-xs text-[#5a5a58]">
                              {formatDateTime(row.observed_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="font-sans text-sm text-[#5a5a58]">
                    No enrollment observations are published for this facility.
                  </p>
                )}
              </Section>

              <Section
                title="Facility observations"
                description="Dated source observations such as classrooms, toilets, and water supply. A zero means the source reported zero; missing values stay unset."
              >
                {school.resources.length > 0 ? (
                  <div className="table-scroll border border-[#d1d8e6]" role="region" aria-label="Facility observations" tabIndex={0}>
                    <table className="w-full min-w-[32rem] border-collapse text-left font-sans text-sm">
                      <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                        <tr>
                          <th className="border-b border-[#d1d8e6] p-3">School year</th>
                          <th className="border-b border-[#d1d8e6] p-3">Category</th>
                          <th className="border-b border-[#d1d8e6] p-3">Resource</th>
                          <th className="border-b border-[#d1d8e6] p-3">Value</th>
                          <th className="border-b border-[#d1d8e6] p-3">Unit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {school.resources.map((row) => (
                          <tr key={`${row.school_year}-${row.resource_code}-${row.source_record_id}`}>
                            <td className="border-b border-[#d1d8e6] p-3">{row.school_year}</td>
                            <td className="border-b border-[#d1d8e6] p-3">{titleCase(row.resource_category)}</td>
                            <td className="border-b border-[#d1d8e6] p-3">{titleCase(row.resource_code)}</td>
                            <td className="border-b border-[#d1d8e6] p-3">
                              {row.value_numeric !== null
                                ? formatNumber(row.value_numeric)
                                : row.value_text ?? "Unknown"}
                            </td>
                            <td className="border-b border-[#d1d8e6] p-3">{row.unit ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="font-sans text-sm text-[#5a5a58]">
                    No facility observations are published for this facility.
                  </p>
                )}
              </Section>
            </>
          ) : null}

          {health ? (
            <>
              <Section
                title="Health facility profile"
                description="Registry category and capacity are source values. Do not infer real-time service availability from registry presence."
              >
                <dl>
                  <DataRow label="DOH NHFR ID">{health.facility.health?.doh_facility_id ?? "Not supplied"}</DataRow>
                  <DataRow label="Facility category">
                    {health.facility.health?.facility_category ?? "Unknown"}
                  </DataRow>
                  <DataRow label="Service capability">
                    {health.facility.health?.service_capability_level ?? "Unknown"}
                  </DataRow>
                  <DataRow label="Bed capacity">
                    {health.facility.health?.bed_capacity !== null &&
                    health.facility.health?.bed_capacity !== undefined
                      ? formatNumber(health.facility.health.bed_capacity)
                      : "Unknown"}
                  </DataRow>
                </dl>
              </Section>

              <Section
                title="Licenses"
                description="Licensing data is separate from PhilHealth accreditation and from real-time operating status."
              >
                {health.licenses.length > 0 ? (
                  <div className="table-scroll border border-[#d1d8e6]" role="region" aria-label="Licenses" tabIndex={0}>
                    <table className="w-full min-w-[38rem] border-collapse text-left font-sans text-sm">
                      <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                        <tr>
                          <th className="border-b border-[#d1d8e6] p-3">Authority</th>
                          <th className="border-b border-[#d1d8e6] p-3">License number</th>
                          <th className="border-b border-[#d1d8e6] p-3">Source status</th>
                          <th className="border-b border-[#d1d8e6] p-3">Valid until</th>
                        </tr>
                      </thead>
                      <tbody>
                        {health.licenses.map((license) => (
                          <tr key={license.id}>
                            <td className="border-b border-[#d1d8e6] p-3">{license.issuing_authority}</td>
                            <td className="border-b border-[#d1d8e6] p-3">{license.license_number ?? "Unknown"}</td>
                            <td className="border-b border-[#d1d8e6] p-3">{license.source_status ?? "Unknown"}</td>
                            <td className="border-b border-[#d1d8e6] p-3">{formatDate(license.valid_until)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="font-sans text-sm text-[#5a5a58]">
                    No license records are published for this facility.
                  </p>
                )}
              </Section>
            </>
          ) : null}

          <Section
            id="provenance"
            title="Field-level source claims"
            description="Each row is a claim one source record made about one canonical field. Claims can disagree; the registry does not silently merge them. This table is limited to the most recent claims."
          >
            {assertions.length > 0 ? (
              <>
                <div className="table-scroll border border-[#d1d8e6]" role="region" aria-label="Field-level source claims" tabIndex={0}>
                  <table className="w-full min-w-[52rem] border-collapse text-left font-sans text-sm">
                    <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                      <tr>
                        <th className="border-b border-[#d1d8e6] p-3">Field</th>
                        <th className="border-b border-[#d1d8e6] p-3">Claimed value</th>
                        <th className="border-b border-[#d1d8e6] p-3">Source</th>
                        <th className="border-b border-[#d1d8e6] p-3">Record / release</th>
                        <th className="border-b border-[#d1d8e6] p-3">Asserted</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assertions.slice(0, 50).map((claim) => (
                        <tr key={claim.id}>
                          <td className="border-b border-[#d1d8e6] p-3 font-mono text-xs">
                            {claim.attribute}
                            {claim.source_field && claim.source_field !== claim.attribute ? (
                              <span className="mt-1 block text-[#5a5a58]">
                                source field: {claim.source_field}
                              </span>
                            ) : null}
                          </td>
                          <td className="border-b border-[#d1d8e6] p-3">
                            {claim.normalized_value ?? claim.raw_value ?? "Unknown"}
                          </td>
                          <td className="border-b border-[#d1d8e6] p-3">
                            <span className="font-ui text-sm font-bold">{claim.source.agency}</span>
                            <span className="mt-1 block text-xs text-[#5a5a58]">
                              {claim.source.dataset}
                            </span>
                          </td>
                          <td className="border-b border-[#d1d8e6] p-3 text-xs">
                            <code>{claim.source.source_record_id}</code>
                            <span className="mt-1 block text-[#5a5a58]">
                              {claim.source.release_label}
                            </span>
                          </td>
                          <td className="border-b border-[#d1d8e6] p-3 text-xs">
                            {formatDateTime(claim.asserted_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {assertions.length > 50 ? (
                  <p className="mt-3 font-sans text-xs text-[#5a5a58]">
                    Showing 50 of {assertions.length} loaded claims. Use the API assertions
                    endpoint with an attribute filter for the full set.
                  </p>
                ) : null}
              </>
            ) : (
              <p className="font-sans text-sm text-[#5a5a58]">
                No field-level claims are published for this record. The source table below still
                lists the linked source records.
              </p>
            )}
          </Section>

          <Section
            id="sources"
            title="Where this information comes from"
            description="Source publication time, reference period, retrieval time, and processing time are distinct. The canonical record's updated time is not an agency update."
          >
            <div className="table-scroll border border-[#d1d8e6]" role="region" aria-label="Source evidence" tabIndex={0}>
              <table className="w-full min-w-[56rem] border-collapse text-left font-sans text-sm">
                <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                  <tr>
                    <th className="border-b border-[#d1d8e6] p-3">Agency / dataset</th>
                    <th className="border-b border-[#d1d8e6] p-3">Source record</th>
                    <th className="border-b border-[#d1d8e6] p-3">Release</th>
                    <th className="border-b border-[#d1d8e6] p-3">Reference period</th>
                    <th className="border-b border-[#d1d8e6] p-3">Published</th>
                    <th className="border-b border-[#d1d8e6] p-3">Retrieved</th>
                    <th className="border-b border-[#d1d8e6] p-3">Rights</th>
                    <th className="border-b border-[#d1d8e6] p-3">Match</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((source) => (
                    <tr key={source.id}>
                      <td className="border-b border-[#d1d8e6] p-3">
                        <span className="font-ui text-sm font-bold">{source.agency}</span>
                        <span className="mt-1 block text-xs text-[#5a5a58]">
                          <Link href={`/data/${source.dataset_slug}`} className="underline">
                            {source.dataset}
                          </Link>
                          {source.is_synthetic ? " · Synthetic fixture" : ""}
                        </span>
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3">
                        <code className="text-xs">{source.source_record_id}</code>
                        <span className="mt-1 block text-xs text-[#5a5a58]">{source.row_reference}</span>
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">{source.release_label}</td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {formatDate(source.reference_period_start)} – {formatDate(source.reference_period_end)}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">{formatDateTime(source.source_published_at)}</td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">{formatDateTime(source.retrieved_at)}</td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {titleCase(source.rights_status)}
                        <span className="mt-1 block text-[#5a5a58]">
                          Publication: {titleCase(source.publication_status)}
                        </span>
                        {source.attribution_text ? (
                          <span className="mt-1 block text-[#5a5a58]">{source.attribution_text}</span>
                        ) : null}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {titleCase(source.match_status)}
                        <span className="mt-1 block text-[#5a5a58]">
                          {source.match_method} · {Math.round(source.match_confidence * 100)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section
            id="quality"
            title="Data quality and unresolved caveats"
            description="Warnings are generated from measured record properties, not editorial confidence."
          >
            {warnings.length > 0 ? (
              <ul className="space-y-2">
                {warnings.map((warning) => (
                  <li key={`${warning.code}-${warning.message}`}>
                    <Alert tone={warning.severity === "info" ? "info" : "warning"}>
                      <AlertTitle className="flex items-center gap-2">
                        <AlertTriangle aria-hidden="true" className="size-4" />
                        {titleCase(warning.code)}
                      </AlertTitle>
                      <AlertDescription>{warning.message}</AlertDescription>
                    </Alert>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="font-sans text-sm text-[#5a5a58]">
                No record-level quality warnings are open for this facility. This does not prove the
                source is complete.
              </p>
            )}
            <dl className="mt-4">
              <DataRow label="Identity status">{titleCase(facility.quality.identity_status)}</DataRow>
              <DataRow label="Location precision">
                {PRECISION_LABELS[facility.quality.location_precision] ?? facility.quality.location_precision}
              </DataRow>
              <DataRow label="Linked source records">{facility.quality.source_count}</DataRow>
            </dl>
          </Section>

          <Section
            id="history"
            title="Canonical record history"
            description="Only measured changes to the PhilFacilities record are shown. Source agency updates are represented by new releases, not this timeline."
          >
            {changes && changes.items.length > 0 ? (
              <ol className="border-l-2 border-[#d1d8e6] pl-5">
                {changes.items.map((event) => (
                  <li key={event.id} className="relative pb-6 last:pb-0">
                    <span
                      aria-hidden="true"
                      className="absolute -left-[1.7rem] top-1.5 size-3 border-2 border-white bg-[#0038a8]"
                    />
                    <p className="font-ui text-sm font-bold">{titleCase(event.change_type)}</p>
                    <p className="mt-1 font-sans text-xs text-[#5a5a58]">
                      {formatDateTime(event.changed_at)} · {event.changed_by}
                    </p>
                    {event.attribute_name ? (
                      <p className="mt-1 font-sans text-sm">
                        {event.attribute_name}: {JSON.stringify(event.old_value)} →{" "}
                        {JSON.stringify(event.new_value)}
                      </p>
                    ) : (
                      <pre className="mt-2 overflow-x-auto border border-[#d1d8e6] bg-[#f4f7fc] p-2 font-mono text-xs" tabIndex={0} aria-label="Change event value">
                        {JSON.stringify(event.new_value, null, 2)}
                      </pre>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="font-sans text-sm text-[#5a5a58]">
                No history events are available for this record.
              </p>
            )}
          </Section>
        </div>

        <aside className="min-w-0 space-y-5 lg:sticky lg:top-[calc(var(--header-height)+1.5rem)] lg:self-start">
          <Card>
            <CardHeader>
              <CardTitle>At a glance</CardTitle>
            </CardHeader>
            <CardContent>
              <dl>
                <DataRow label="Source-reported status" stacked>
                  {recordStatusLabel}
                  <p className="mt-1 text-xs text-[#5a5a58]">
                    Registry presence does not establish operational availability.
                  </p>
                </DataRow>
                <DataRow label="Ownership" stacked>{ownershipLabel}</DataRow>
                <DataRow label="Location precision" stacked>
                  {PRECISION_LABELS[facility.location.precision] ?? facility.location.precision}
                </DataRow>
                <DataRow label="Linked sources" stacked>{facility.source_count}</DataRow>
                <DataRow label="Published contacts" stacked>{contacts.length}</DataRow>
                <DataRow label="PSGC release" stacked>{geography.psgc_release ?? "Not linked"}</DataRow>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Use this record carefully</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 font-sans text-sm text-[#5a5a58]">
              {isPreciseLocation(facility.location.precision) ? (
                <p>The point is source-supplied. It is not an independently surveyed building footprint.</p>
              ) : (
                <p>This record does not support a building-level location claim.</p>
              )}
              <p>
                Enrollment, capacity, and licensing values are dated source observations, not live
                status.
              </p>
              <Link
                href="/about#corrections"
                className="inline-flex items-center gap-1 font-ui text-sm font-bold text-[#0038a8]"
              >
                Report a correction <ExternalLink aria-hidden="true" className="size-3.5" />
              </Link>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
