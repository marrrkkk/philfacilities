import type { Metadata } from "next";

import { MapExplorer } from "@/components/map/map-explorer";

export const metadata: Metadata = {
  title: "Map",
  description:
    "Explore source-linked Philippine schools and health facilities with precision-aware map markers and an accessible text list.",
};

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function MapPage({ searchParams }: { searchParams: SearchParams }) {
  const raw = await searchParams;
  return (
    <MapExplorer
      initialType={first(raw.type)}
      initialQuery={first(raw.q)}
      initialOwnership={first(raw.ownership)}
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
