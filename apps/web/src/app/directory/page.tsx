import Link from "next/link";
import { SlidersHorizontal } from "lucide-react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { DirectoryResults } from "@/components/directory-results";
import {
  DirectorySearchInput,
  DirectorySearchProvider,
} from "@/components/directory-search";
import { buttonVariants } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import {
  getGeography,
  listFacilities,
  listGeographies,
  listSources,
  type AdministrativeUnitOut,
  type DatasetOut,
} from "@/lib/api";
import { INCLUSION_CLASS_LABELS, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

const PRECISIONS = [
  ["", "Any precision"],
  ["source_gps", "Source GPS"],
  ["gps_verified", "GPS verified"],
  ["field_verified", "Field verified"],
  ["map_geocoded", "Map geocoded"],
  ["barangay_centroid", "Barangay centroid"],
  ["unknown", "Unknown"],
];

const INCLUSION_CLASSES: [string, string][] = [
  ["", "Any inclusion class"],
  ...Object.entries(INCLUSION_CLASS_LABELS),
];

const OWNERSHIP_TYPES = [
  ["", "Any ownership type"],
  ["NATIONAL_GOVERNMENT", "National government"],
  ["LOCAL_GOVERNMENT", "Local government"],
  ["GOCC", "Government-owned or controlled corporation"],
  ["PUBLIC_EDUCATIONAL_INSTITUTION", "Public educational institution"],
  ["OTHER_PUBLIC_BODY", "Other public body"],
  ["GOVERNMENT_UNSPECIFIED", "Government, unspecified"],
  ["PRIVATE_CORPORATE", "Private corporate"],
  ["NGO_NON_PROFIT", "NGO or non-profit"],
  ["COOPERATIVE", "Cooperative"],
  ["RELIGIOUS_FAITH_BASED", "Religious or faith-based"],
  ["PRIVATE_UNSPECIFIED", "Private, unspecified"],
  ["UNKNOWN", "Unknown"],
];

const FACILITY_KINDS = [
  ["", "Any facility kind"],
  ["facility", "Facility"],
  ["site", "Site or compound"],
  ["building", "Building"],
  ["facility_unit", "Facility unit or service point"],
  ["infrastructure_asset", "Infrastructure asset"],
  ["project", "Project"],
];

const ACCESS_CLASSES = [
  ["", "Any access state"],
  ["PUBLIC_FREE", "Public, free"],
  ["PUBLIC_PAID_OR_CONDITIONAL", "Public, paid or conditional"],
  ["SERVICE_USERS_ONLY", "Service users only"],
  ["APPOINTMENT_ONLY", "Appointment only"],
  ["MEMBERS_STUDENTS_ONLY", "Members or students only"],
  ["STAFF_ONLY", "Staff only"],
  ["RESTRICTED", "Restricted"],
  ["UNKNOWN", "Unknown"],
];

const CATEGORY_LABELS: Record<string, string> = {
  school: "School",
  health_facility: "Health facility",
  library: "Library",
  museum: "Museum",
  government_office: "Government office",
  community_facility: "Community facility",
  emergency_facility: "Emergency facility",
  public_market: "Public market",
  transport_facility: "Transport facility",
  cultural_facility: "Cultural facility",
  public_space: "Public space",
  social_welfare_facility: "Social welfare facility",
  utility_facility: "Utility facility",
  other_qualifying_facility: "Other qualifying facility",
};

export default async function DirectoryPage({ searchParams }: { searchParams: SearchParams }) {
  const raw = await searchParams;
  const q = first(raw.q).trim();
  const type = first(raw.type);
  const inclusion = first(raw.inclusion_class);
  const ownership = first(raw.ownership);
  const ownershipType = first(raw.ownership_type);
  const facilityKind = first(raw.facility_kind);
  const publicAccess = first(raw.public_access_class);
  const region = first(raw.region_code);
  const province = first(raw.province_code);
  const municipality = first(raw.municipality_code);
  const barangay = first(raw.barangay_code);
  const source = first(raw.source);
  const hasCoordinates = first(raw.has_coordinates);
  const precision = first(raw.location_precision);
  const referencePeriodStart = first(raw.reference_period_start);
  const referencePeriodEnd = first(raw.reference_period_end);
  const updatedSince = first(raw.updated_since);
  const cursor = first(raw.cursor) || undefined;

  const filterParams = {
    type: type || undefined,
    inclusion_class: inclusion || undefined,
    ownership: ownership || undefined,
    ownership_type: ownershipType || undefined,
    facility_kind: facilityKind || undefined,
    public_access_class: publicAccess || undefined,
    region_code: region || undefined,
    province_code: province || undefined,
    municipality_code: municipality || undefined,
    barangay_code: barangay || undefined,
    source: source || undefined,
    has_coordinates: hasCoordinates || undefined,
    location_precision: precision || undefined,
    reference_period_start: referencePeriodStart || undefined,
    reference_period_end: referencePeriodEnd || undefined,
    updated_since: updatedSince || undefined,
  };

  const query = {
    ...filterParams,
    q: q || undefined,
    cursor,
    limit: 20,
  };

  let result = null;
  let units: AdministrativeUnitOut[] = [];
  let sources: DatasetOut[] = [];
  let error: string | null = null;

  try {
    const [facilityResult, regionUnits, provinceUnits, sourceRows] = await Promise.all([
      listFacilities(query),
      listGeographies({ level: "region", limit: 500 }).catch(() => []),
      listGeographies({ level: "province", limit: 500 }).catch(() => []),
      listSources().catch(() => []),
    ]);
    result = facilityResult;
    sources = sourceRows;
    const provinceOptions = provinceUnits.filter(
      (item) => !region || item.parent_psgc_code === region,
    );
    let municipalityUnits: AdministrativeUnitOut[] = [];
    if (province) {
      municipalityUnits = await listGeographies({
        level: "municipality",
        parent: province,
        limit: 500,
      }).catch(() => []);
    } else if (region) {
      // Most regions nest municipalities under provinces, but NCR has cities
      // directly under the region. Fetch both scopes so either structure works.
      const [directMunicipalities, perProvince] = await Promise.all([
        listGeographies({
          level: "municipality",
          parent: region,
          limit: 500,
        }).catch(() => []),
        Promise.all(
          provinceOptions.map((item) =>
            listGeographies({
              level: "municipality",
              parent: item.psgc_code,
              limit: 500,
            }).catch(() => []),
          ),
        ),
      ]);
      municipalityUnits = [...directMunicipalities, ...perProvince.flat()];
    }
    let barangayUnits: AdministrativeUnitOut[] = [];
    if (municipality) {
      barangayUnits = await listGeographies({
        level: "barangay",
        parent: municipality,
        limit: 500,
      }).catch(() => []);
    }
    // Only fetch a selected unit directly when it is not already in the
    // parent-scoped option lists (for example a bookmarked municipality URL).
    const knownCodes = new Set(
      [...regionUnits, ...provinceUnits, ...municipalityUnits, ...barangayUnits].map(
        (item) => item.psgc_code,
      ),
    );
    const missingCodes = [municipality, barangay].filter(
      (code): code is string => Boolean(code) && !knownCodes.has(code),
    );
    const selectedUnits = (
      await Promise.all(
        missingCodes.map((code) => getGeography(code).catch(() => null)),
      )
    ).filter((item): item is AdministrativeUnitOut => item !== null);
    units = [
      ...regionUnits,
      ...provinceUnits,
      ...municipalityUnits,
      ...barangayUnits,
      ...selectedUnits,
    ];
  } catch (caught) {
    error = caught instanceof Error ? caught.message : "The directory could not be loaded.";
  }

  const agencies = [...new Map(sources.map((item) => [item.agency_code, item.agency])).entries()];

  const unitName = (code: string) =>
    units.find((item) => item.psgc_code === code)?.name ?? code;
  const regions = units.filter((item) => item.geographic_level === "region");
  const provinces = units.filter((item) => item.geographic_level === "province");
  const provinceOptions = provinces.filter(
    (item) => !region || item.parent_psgc_code === region,
  );
  const municipalityOptions = units.filter((item) => item.geographic_level === "municipality");
  const barangayOptions = units.filter((item) => item.geographic_level === "barangay");

  const activeFilters = [
    type ? { label: CATEGORY_LABELS[type] ?? titleCase(type) } : null,
    inclusion
      ? {
          label: `Inclusion: ${INCLUSION_CLASS_LABELS[inclusion] ?? titleCase(inclusion)}`,
        }
      : null,
    ownership ? { label: `Ownership: ${titleCase(ownership)}` } : null,
    ownershipType ? { label: `Ownership type: ${titleCase(ownershipType)}` } : null,
    facilityKind ? { label: `Facility kind: ${titleCase(facilityKind)}` } : null,
    publicAccess ? { label: `Access: ${titleCase(publicAccess)}` } : null,
    region ? { label: `Region: ${unitName(region)}` } : null,
    province ? { label: `Province: ${unitName(province)}` } : null,
    municipality ? { label: `City / municipality: ${unitName(municipality)}` } : null,
    barangay ? { label: `Barangay: ${unitName(barangay)}` } : null,
    source
      ? {
          label: `Agency: ${agencies.find(([code]) => code === source)?.[1] ?? source}`,
        }
      : null,
    hasCoordinates ? { label: hasCoordinates === "true" ? "Has coordinates" : "No coordinates" } : null,
    precision ? { label: `Precision: ${titleCase(precision)}` } : null,
    referencePeriodStart || referencePeriodEnd
      ? {
          label: `Reference period: ${referencePeriodStart || "any"} to ${
            referencePeriodEnd || "any"
          }`,
        }
      : null,
    updatedSince ? { label: `Updated since: ${updatedSince}` } : null,
  ].filter(Boolean) as { label: string }[];

  const activeFilterLabels = activeFilters.map((filter) => filter.label);

  return (
    <div className="container-page py-10">
      <Breadcrumbs items={[{ label: "Directory" }]} />
      <DirectorySearchProvider
        key={JSON.stringify({ filterParams, q, cursor })}
        initialQuery={q}
        initialResult={result}
        initialError={error}
        filterParams={filterParams}
      >
        <div className="grid gap-8 lg:grid-cols-[18rem_1fr]">
        <aside>
          <div className="border border-[#d1d8e6] bg-white p-5 lg:sticky lg:top-[calc(var(--header-height)+1.5rem)]">
            <div className="flex items-center gap-2 border-b border-[#d1d8e6] pb-3">
              <SlidersHorizontal aria-hidden="true" className="size-4 text-[#0038a8]" />
              <h2 className="font-display text-xl font-bold">Filters</h2>
            </div>
            <form method="get" action="/directory" className="mt-4 space-y-4">
              <div>
                <Label htmlFor="filter-q">Search</Label>
                <DirectorySearchInput
                  id="filter-q"
                  name="q"
                  placeholder="Name, address, locality, source ID"
                />
              </div>
              <div>
                <Label htmlFor="filter-type">Facility category</Label>
                <Select id="filter-type" name="type" defaultValue={type}>
                  <option value="">All categories</option>
                  {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-inclusion">Inclusion class</Label>
                <Select id="filter-inclusion" name="inclusion_class" defaultValue={inclusion}>
                  {INCLUSION_CLASSES.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-ownership">Ownership</Label>
                <Select id="filter-ownership" name="ownership" defaultValue={ownership}>
                  <option value="">Any ownership</option>
                  <option value="government">Government</option>
                  <option value="private">Private</option>
                  <option value="unknown">Unknown</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-ownership-type">Ownership type</Label>
                <Select id="filter-ownership-type" name="ownership_type" defaultValue={ownershipType}>
                  {OWNERSHIP_TYPES.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-kind">Facility kind</Label>
                <Select id="filter-kind" name="facility_kind" defaultValue={facilityKind}>
                  {FACILITY_KINDS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-access">Public access</Label>
                <Select id="filter-access" name="public_access_class" defaultValue={publicAccess}>
                  {ACCESS_CLASSES.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-source">Source agency</Label>
                <Select id="filter-source" name="source" defaultValue={source}>
                  <option value="">Any agency</option>
                  {agencies.map(([code, name]) => (
                    <option key={code} value={code}>
                      {name}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-region">Region</Label>
                <Select id="filter-region" name="region_code" defaultValue={region}>
                  <option value="">All regions</option>
                  {regions.map((item) => (
                    <option key={item.psgc_code} value={item.psgc_code}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-province">Province</Label>
                <Select id="filter-province" name="province_code" defaultValue={province}>
                  <option value="">All provinces</option>
                  {provinceOptions.map((item) => (
                    <option key={item.psgc_code} value={item.psgc_code}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-municipality">City / municipality</Label>
                <Select
                  id="filter-municipality"
                  name="municipality_code"
                  defaultValue={municipality}
                >
                  <option value="">All cities and municipalities</option>
                  {municipalityOptions.map((item) => (
                    <option key={item.psgc_code} value={item.psgc_code}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-barangay">Barangay</Label>
                <Select id="filter-barangay" name="barangay_code" defaultValue={barangay}>
                  <option value="">All barangays</option>
                  {barangayOptions.map((item) => (
                    <option key={item.psgc_code} value={item.psgc_code}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-coordinates">Coordinates</Label>
                <Select id="filter-coordinates" name="has_coordinates" defaultValue={hasCoordinates}>
                  <option value="">Any location state</option>
                  <option value="true">Has coordinates</option>
                  <option value="false">No coordinates</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-precision">Location precision</Label>
                <Select id="filter-precision" name="location_precision" defaultValue={precision}>
                  {PRECISIONS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-reference-start">Reference period start</Label>
                <Input
                  id="filter-reference-start"
                  name="reference_period_start"
                  type="date"
                  defaultValue={referencePeriodStart.slice(0, 10)}
                />
              </div>
              <div>
                <Label htmlFor="filter-reference-end">Reference period end</Label>
                <Input
                  id="filter-reference-end"
                  name="reference_period_end"
                  type="date"
                  defaultValue={referencePeriodEnd.slice(0, 10)}
                />
              </div>
              <div>
                <Label htmlFor="filter-updated">Updated since</Label>
                <Input
                  id="filter-updated"
                  name="updated_since"
                  type="date"
                  defaultValue={updatedSince.slice(0, 10)}
                />
              </div>
              <div className="flex gap-2 pt-1">
                <button
                  type="submit"
                  className={cn(buttonVariants({ variant: "blue" }), "flex-1")}
                >
                  Apply filters
                </button>
                <Link href="/directory" className={cn(buttonVariants({ variant: "outline" }))}>
                  Reset
                </Link>
              </div>
            </form>
            <p className="mt-4 border-t border-[#d1d8e6] pt-3 font-sans text-xs leading-relaxed text-[#5a5a58]">
              Filters apply to published records only. An empty result does not imply that no such
              facility exists; it means no matching source record is published here.
            </p>
          </div>
        </aside>

        <div>
          <DirectoryResults activeFilters={activeFilterLabels} filterParams={filterParams} />
        </div>
        </div>
      </DirectorySearchProvider>
    </div>
  );
}
