import Link from "next/link";
import { SlidersHorizontal } from "lucide-react";

import { Breadcrumbs, EmptyState, Pagination } from "@/components/breadcrumbs";
import { FacilityCard } from "@/components/facility-card";
import { SearchForm } from "@/components/search-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import {
  getTaxonomy,
  listAllGeographies,
  listFacilities,
  listSources,
  type AdministrativeUnitOut,
  type DatasetOut,
  type TaxonomyResponse,
} from "@/lib/api";
import { formatNumber, PRECISION_OPTIONS, titleCase } from "@/lib/format";
import { queryString } from "@/lib/query";
import {
  labelFor,
  subtypeOptions,
  termLabels,
  type TermLabels,
} from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

const PRECISIONS: Array<[string, string]> = [["", "Any precision"], ...PRECISION_OPTIONS];

export default async function DirectoryPage({ searchParams }: { searchParams: SearchParams }) {
  const raw = await searchParams;
  const q = first(raw.q).trim();
  const type = first(raw.type);
  const subtype = first(raw.subtype);
  const inclusion = first(raw.inclusion_class);
  const ownership = first(raw.ownership);
  const ownershipType = first(raw.ownership_type);
  const operatorType = first(raw.operator_type);
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

  const query = {
    q: q || undefined,
    type: type || undefined,
    subtype: subtype || undefined,
    inclusion_class: inclusion || undefined,
    ownership: ownership || undefined,
    ownership_type: ownershipType || undefined,
    operator_type: operatorType || undefined,
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
    cursor,
    limit: 20,
  };

  let result = null;
  let taxonomy: TaxonomyResponse | null = null;
  let regions: AdministrativeUnitOut[] = [];
  let provinces: AdministrativeUnitOut[] = [];
  let municipalities: AdministrativeUnitOut[] = [];
  let barangays: AdministrativeUnitOut[] = [];
  let sources: DatasetOut[] = [];
  let error: string | null = null;

  try {
    [result, taxonomy, regions, provinces, municipalities, sources] = await Promise.all([
      listFacilities(query),
      getTaxonomy().catch(() => null),
      listAllGeographies({ level: "region" }).catch(() => []),
      listAllGeographies({ level: "province" }).catch(() => []),
      listAllGeographies({ level: "municipality" }).catch(() => []),
      listSources().catch(() => []),
    ]);
    if (municipality) {
      barangays = await listAllGeographies({
        level: "barangay",
        parent: municipality,
      }).catch(() => []);
    }
  } catch (caught) {
    error = caught instanceof Error ? caught.message : "The directory could not be loaded.";
  }

  const agencies = [...new Map(sources.map((item) => [item.agency_code, item.agency])).entries()];
  const categories = taxonomy?.categories ?? [];
  const categoryLabelMap = termLabels(taxonomy?.categories);
  const inclusionLabels: TermLabels = termLabels(taxonomy?.inclusion_classes);
  const ownershipTypeLabels: TermLabels = termLabels(taxonomy?.ownership_types);
  const operatorTypeLabels: TermLabels = termLabels(taxonomy?.operator_types);
  const kindLabels: TermLabels = termLabels(taxonomy?.facility_kinds);
  const accessLabels: TermLabels = termLabels(taxonomy?.access_classes);
  const subtypes = subtypeOptions(taxonomy);
  const subtypeByCategory = new Map<string, typeof subtypes>();
  for (const option of subtypes) {
    const list = subtypeByCategory.get(option.categoryCode) ?? [];
    list.push(option);
    subtypeByCategory.set(option.categoryCode, list);
  }
  const selectedSubtype = subtypes.find((item) => item.code === subtype);

  const unitName = (code: string) =>
    [...regions, ...provinces, ...municipalities, ...barangays].find(
      (item) => item.psgc_code === code,
    )?.name ?? code;
  const provinceParents = new Map(provinces.map((item) => [item.psgc_code, item.parent_psgc_code]));
  const provinceOptions = provinces.filter(
    (item) => !region || item.parent_psgc_code === region,
  );
  const municipalityOptions = municipalities.filter(
    (item) =>
      (!province || item.parent_psgc_code === province) &&
      (!region || provinceParents.get(item.parent_psgc_code ?? "") === region),
  );
  const barangayOptions = barangays;

  const activeFilters = [
    q ? { label: `Search: ${q}` } : null,
    type ? { label: labelFor(categoryLabelMap, type) } : null,
    subtype
      ? { label: `Subtype: ${selectedSubtype?.label ?? titleCase(subtype)}` }
      : null,
    inclusion ? { label: `Inclusion: ${labelFor(inclusionLabels, inclusion)}` } : null,
    ownership ? { label: `Ownership: ${titleCase(ownership)}` } : null,
    ownershipType
      ? { label: `Ownership type: ${labelFor(ownershipTypeLabels, ownershipType)}` }
      : null,
    operatorType
      ? { label: `Operator type: ${labelFor(operatorTypeLabels, operatorType)}` }
      : null,
    facilityKind ? { label: `Facility kind: ${labelFor(kindLabels, facilityKind)}` } : null,
    publicAccess ? { label: `Access: ${labelFor(accessLabels, publicAccess)}` } : null,
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

  const paginationParams = {
    q: q || undefined,
    type: type || undefined,
    subtype: subtype || undefined,
    inclusion_class: inclusion || undefined,
    ownership: ownership || undefined,
    ownership_type: ownershipType || undefined,
    operator_type: operatorType || undefined,
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

  const mapParams = {
    ...paginationParams,
    // The map only shows records with coordinates, so a "no coordinates"
    // directory result cannot produce a useful mapped subset.
    has_coordinates: hasCoordinates === "true" ? "true" : undefined,
  };

  return (
    <div className="container-page py-10">
      <Breadcrumbs items={[{ label: "Directory" }]} />
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
                <Input
                  id="filter-q"
                  name="q"
                  defaultValue={q}
                  placeholder="Name, address, locality, source ID"
                />
              </div>
              <div>
                <Label htmlFor="filter-type">Facility category</Label>
                <Select id="filter-type" name="type" defaultValue={type}>
                  <option value="">All categories</option>
                  {categories.map((category) => (
                    <option key={category.code} value={category.code}>
                      {category.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-subtype">Subtype</Label>
                <Select id="filter-subtype" name="subtype" defaultValue={subtype}>
                  <option value="">Any subtype</option>
                  {[...subtypeByCategory.entries()].map(([categoryCode, options]) => (
                    <optgroup
                      key={categoryCode}
                      label={categoryLabelMap[categoryCode] ?? titleCase(categoryCode)}
                    >
                      {options.map((option) => (
                        <option key={option.code} value={option.code}>
                          {option.label}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-inclusion">Inclusion class</Label>
                <Select id="filter-inclusion" name="inclusion_class" defaultValue={inclusion}>
                  <option value="">Any inclusion class</option>
                  {(taxonomy?.inclusion_classes ?? []).map((term) => (
                    <option key={term.code} value={term.code}>
                      {term.label}
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
                  <option value="">Any ownership type</option>
                  {(taxonomy?.ownership_types ?? []).map((term) => (
                    <option key={term.code} value={term.code}>
                      {term.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-operator-type">Operator type</Label>
                <Select
                  id="filter-operator-type"
                  name="operator_type"
                  defaultValue={operatorType}
                >
                  <option value="">Any operator type</option>
                  {(taxonomy?.operator_types ?? []).map((term) => (
                    <option key={term.code} value={term.code}>
                      {term.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-kind">Facility kind</Label>
                <Select id="filter-kind" name="facility_kind" defaultValue={facilityKind}>
                  <option value="">Any facility kind</option>
                  {(taxonomy?.facility_kinds ?? []).map((term) => (
                    <option key={term.code} value={term.code}>
                      {term.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="filter-access">Public access</Label>
                <Select id="filter-access" name="public_access_class" defaultValue={publicAccess}>
                  <option value="">Any access state</option>
                  {(taxonomy?.access_classes ?? []).map((term) => (
                    <option key={term.code} value={term.code}>
                      {term.label}
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
                <Select
                  id="filter-barangay"
                  name="barangay_code"
                  defaultValue={barangay}
                  disabled={!municipality}
                >
                  <option value="">
                    {municipality ? "All barangays" : "Choose a city or municipality first"}
                  </option>
                  {barangayOptions.map((item) => (
                    <option key={item.psgc_code} value={item.psgc_code}>
                      {item.name}
                    </option>
                  ))}
                </Select>
                <p className="mt-1 font-sans text-xs text-[#5a5a58]">
                  Barangay choices are loaded for the selected city or municipality.
                </p>
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
          <div className="flex flex-col gap-2 border-b border-[#d1d8e6] pb-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="eyebrow text-[#0038a8]">Facility directory</p>
              <h1 className="mt-2 font-display text-4xl font-extrabold tracking-tight">
                {result ? formatNumber(result.total) : "—"} matching records
              </h1>
              <p className="mt-2 font-sans text-sm text-[#5a5a58]">
                Search across canonical names, localities, and agency source identifiers. Every
                result is also available as a text profile.
              </p>
            </div>
            <Link
              href={`/map${queryString(mapParams)}`}
              className={cn(buttonVariants({ variant: "outline" }))}
            >
              View on map
            </Link>
          </div>

          <div className="mt-5">
            <SearchForm
              defaultQuery={q}
              defaultType={type}
              compact
              categories={categories}
              preserve={{
                subtype,
                inclusion_class: inclusion,
                ownership,
                ownership_type: ownershipType,
                operator_type: operatorType,
                facility_kind: facilityKind,
                public_access_class: publicAccess,
                region_code: region,
                province_code: province,
                municipality_code: municipality,
                barangay_code: barangay,
                source,
                has_coordinates: hasCoordinates,
                location_precision: precision,
                reference_period_start: referencePeriodStart,
                reference_period_end: referencePeriodEnd,
                updated_since: updatedSince,
              }}
            />
          </div>

          {activeFilters.length > 0 ? (
            <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Active filters">
              <span className="font-ui text-xs font-bold uppercase tracking-wide text-[#5a5a58]">
                Active:
              </span>
              {activeFilters.map((filter) => (
                <Badge key={filter.label} tone="muted" className="normal-case tracking-normal">
                  {filter.label}
                </Badge>
              ))}
            </div>
          ) : null}

          <div className="mt-6">
            {error ? (
              <Alert tone="danger">
                <AlertTitle>The directory could not be loaded</AlertTitle>
                <AlertDescription>
                  {error}. Check that the API is running at the configured API base URL, then try
                  again.
                </AlertDescription>
              </Alert>
            ) : result && result.items.length > 0 ? (
              <>
                <div className="border-t border-[#d1d8e6]">
                  {result.items.map((facility) => (
                    <FacilityCard
                      key={facility.id}
                      facility={facility}
                      categoryLabel={labelFor(categoryLabelMap, facility.facility_type)}
                      subtypeLabel={
                        subtypes.find((item) => item.code === facility.facility_subtype)?.label
                      }
                    />
                  ))}
                </div>
                <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <p className="font-sans text-xs text-[#5a5a58]">
                    Showing {formatNumber(result.items.length)} of {formatNumber(result.total)}
                    {result.has_more ? " · more pages available" : " · end of results"}
                  </p>
                  <Badge tone="muted">
                    {result.limit} per page · cursor pagination
                  </Badge>
                </div>
                <Pagination
                  nextCursor={result.next_cursor}
                  basePath="/directory"
                  params={paginationParams}
                />
              </>
            ) : (
              <EmptyState title="No published records match these filters">
                Try a broader search, clear the ownership or precision filter, or{" "}
                <Link href="/directory" className="text-[#0038a8] underline">
                  reset the directory
                </Link>
                . A missing result is not evidence that a facility does not exist.
              </EmptyState>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
