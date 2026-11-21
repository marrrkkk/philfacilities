import type { Metadata } from "next";

import { MapExplorer } from "@/components/map/map-explorer";
import {
  getTaxonomy,
  listAllGeographies,
  listSources,
  type AdministrativeUnitOut,
} from "@/lib/api";

export const metadata: Metadata = {
  title: "Map",
  description:
    "Explore every published PhilFacilities category with ownership, geography, source, precision, reference-period and update-time filters, precision-aware markers, and an accessible text list.",
};

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function MapPage({ searchParams }: { searchParams: SearchParams }) {
  const raw = await searchParams;
  const [taxonomy, sources, regions, provinces, municipalities] = await Promise.all([
    getTaxonomy().catch(() => null),
    listSources().catch(() => []),
    listAllGeographies({ level: "region" }).catch(() => [] as AdministrativeUnitOut[]),
    listAllGeographies({ level: "province" }).catch(() => [] as AdministrativeUnitOut[]),
    listAllGeographies({ level: "municipality" }).catch(() => [] as AdministrativeUnitOut[]),
  ]);

  return (
    <MapExplorer
      taxonomy={taxonomy}
      sources={[...new Map(sources.map((item) => [item.agency_code, item.agency])).entries()].map(
        ([code, name]) => ({ code, name }),
      )}
      regions={regions}
      provinces={provinces}
      municipalities={municipalities}
      initialType={first(raw.type)}
      initialSubtype={first(raw.subtype)}
      initialQuery={first(raw.q)}
      initialInclusionClass={first(raw.inclusion_class)}
      initialOwnership={first(raw.ownership)}
      initialOwnershipType={first(raw.ownership_type)}
      initialOperatorType={first(raw.operator_type)}
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
    />
  );
}
