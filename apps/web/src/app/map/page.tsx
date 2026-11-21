import type { Metadata } from "next";

import { MapExplorer } from "@/components/map/map-explorer";
import {
  listGeographies,
  listSources,
  type AdministrativeUnitOut,
  type DatasetOut,
} from "@/lib/api";

export const metadata: Metadata = {
  title: "Map",
  description:
    "Explore the source-linked PhilFacilities registry with ownership-aware filters, precision-aware map markers and an accessible text list.",
};

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function MapPage({ searchParams }: { searchParams: SearchParams }) {
  const raw = await searchParams;

  const [sources, provinces] = await Promise.all([
    listSources().catch(() => [] as DatasetOut[]),
    listGeographies({ level: "province", limit: 500 }).catch(() => [] as AdministrativeUnitOut[]),
  ]);

  const sourceOptions = [
    ...new Map(sources.map((item) => [item.agency_code, item.agency])).entries(),
  ] as [string, string][];
  const provinceOptions = provinces.map((item) => [item.psgc_code, item.name] as [string, string]);

  return (
    <MapExplorer
      initialType={first(raw.type)}
      initialQuery={first(raw.q)}
      initialInclusionClass={first(raw.inclusion_class)}
      initialOwnership={first(raw.ownership)}
      initialOwnershipType={first(raw.ownership_type)}
      initialAccessClass={first(raw.public_access_class)}
      initialKind={first(raw.facility_kind)}
      initialRegion={first(raw.region_code)}
      initialProvince={first(raw.province_code)}
      initialMunicipality={first(raw.municipality_code)}
      initialBarangay={first(raw.barangay_code)}
      initialSource={first(raw.source)}
      initialPrecision={first(raw.location_precision)}
      initialHasCoordinates={first(raw.has_coordinates)}
      initialReferencePeriodStart={first(raw.reference_period_start)}
      initialReferencePeriodEnd={first(raw.reference_period_end)}
      initialUpdatedSince={first(raw.updated_since)}
      sourceOptions={sourceOptions}
      provinceOptions={provinceOptions}
    />
  );
}
