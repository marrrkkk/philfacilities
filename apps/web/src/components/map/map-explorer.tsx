"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { List, Loader2, Map as MapIcon, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import {
  apiBaseUrl,
  type AdministrativeUnitOut,
  type FacilitySummary,
  type TaxonomyResponse,
} from "@/lib/api";
import {
  PRECISION_LABELS,
  PRECISION_OPTIONS,
} from "@/lib/format";
import { queryString } from "@/lib/query";
import { configureMapLibreWorker } from "@/lib/maplibre";
import { BASEMAP_STYLE } from "@/lib/map-style";
import { labelFor, subtypeOptions, termLabels } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

const OWNERSHIP_VALUES: Array<[string, string]> = [
  ["", "Any ownership"],
  ["government", "Government"],
  ["private", "Private"],
  ["unknown", "Unknown"],
];

type Filters = {
  type: string;
  subtype: string;
  q: string;
  inclusion_class: string;
  ownership: string;
  ownership_type: string;
  operator_type: string;
  public_access_class: string;
  facility_kind: string;
  region_code: string;
  province_code: string;
  municipality_code: string;
  barangay_code: string;
  source: string;
  location_precision: string;
  has_coordinates: string;
  reference_period_start: string;
  reference_period_end: string;
  updated_since: string;
};

function signatureOf(filters: Filters) {
  return JSON.stringify(filters);
}

export function MapExplorer({
  taxonomy,
  sources,
  regions,
  provinces,
  municipalities,
  initialType = "",
  initialSubtype = "",
  initialQuery = "",
  initialInclusionClass = "",
  initialOwnership = "",
  initialOwnershipType = "",
  initialOperatorType = "",
  initialAccessClass = "",
  initialKind = "",
  initialRegion = "",
  initialProvince = "",
  initialMunicipality = "",
  initialBarangay = "",
  initialSource = "",
  initialPrecision = "",
  initialHasCoordinates = "",
  initialReferencePeriodStart = "",
  initialReferencePeriodEnd = "",
  initialUpdatedSince = "",
}: {
  taxonomy: TaxonomyResponse | null;
  sources: Array<{ code: string; name: string }>;
  regions: AdministrativeUnitOut[];
  provinces: AdministrativeUnitOut[];
  municipalities: AdministrativeUnitOut[];
  initialType?: string;
  initialSubtype?: string;
  initialQuery?: string;
  initialInclusionClass?: string;
  initialOwnership?: string;
  initialOwnershipType?: string;
  initialOperatorType?: string;
  initialAccessClass?: string;
  initialKind?: string;
  initialRegion?: string;
  initialProvince?: string;
  initialMunicipality?: string;
  initialBarangay?: string;
  initialSource?: string;
  initialPrecision?: string;
  initialHasCoordinates?: string;
  initialReferencePeriodStart?: string;
  initialReferencePeriodEnd?: string;
  initialUpdatedSince?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadedSignatureRef = useRef<string>("");
  const loadViewportRef = useRef<() => void>(() => {});
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [facilities, setFacilities] = useState<FacilitySummary[]>([]);
  const [selected, setSelected] = useState<FacilitySummary | null>(null);
  const [mobileView, setMobileView] = useState<"map" | "list">("map");
  const [truncated, setTruncated] = useState(false);

  const [type, setType] = useState(initialType);
  const [subtype, setSubtype] = useState(initialSubtype);
  const [query, setQuery] = useState(initialQuery);
  const [inclusionClass, setInclusionClass] = useState(initialInclusionClass);
  const [ownership, setOwnership] = useState(initialOwnership);
  const [ownershipType, setOwnershipType] = useState(initialOwnershipType);
  const [operatorType, setOperatorType] = useState(initialOperatorType);
  const [accessClass, setAccessClass] = useState(initialAccessClass);
  const [kind, setKind] = useState(initialKind);
  const [region, setRegion] = useState(initialRegion);
  const [province, setProvince] = useState(initialProvince);
  const [municipality, setMunicipality] = useState(initialMunicipality);
  const [barangay, setBarangay] = useState(initialBarangay);
  const [source, setSource] = useState(initialSource);
  const [precision, setPrecision] = useState(initialPrecision);
  const [referencePeriodStart, setReferencePeriodStart] = useState(initialReferencePeriodStart);
  const [referencePeriodEnd, setReferencePeriodEnd] = useState(initialReferencePeriodEnd);
  const [updatedSince, setUpdatedSince] = useState(initialUpdatedSince);
  const [barangays, setBarangays] = useState<AdministrativeUnitOut[]>([]);

  const categories = taxonomy?.categories ?? [];
  const subtypes = subtypeOptions(taxonomy);
  const categoryLabels = termLabels(taxonomy?.categories);
  const inclusionLabels = termLabels(taxonomy?.inclusion_classes);
  const ownershipTypeLabels = termLabels(taxonomy?.ownership_types);
  const accessLabels = termLabels(taxonomy?.access_classes);

  const provincesByCode = useMemo(
    () => new Map(provinces.map((item) => [item.psgc_code, item])),
    [provinces],
  );
  const provinceOptions = useMemo(
    () => provinces.filter((item) => !region || item.parent_psgc_code === region),
    [provinces, region],
  );
  const municipalityOptions = useMemo(
    () =>
      municipalities.filter((item) => {
        if (province) return item.parent_psgc_code === province;
        if (!region) return true;
        return provincesByCode.get(item.parent_psgc_code ?? "")?.parent_psgc_code === region;
      }),
    [municipalities, province, region, provincesByCode],
  );

  const filters: Filters = useMemo(
    () => ({
      type,
      subtype,
      q: query,
      inclusion_class: inclusionClass,
      ownership,
      ownership_type: ownershipType,
      operator_type: operatorType,
      public_access_class: accessClass,
      facility_kind: kind,
      region_code: region,
      province_code: province,
      municipality_code: municipality,
      barangay_code: barangay,
      source,
      location_precision: precision,
      has_coordinates: initialHasCoordinates,
      reference_period_start: referencePeriodStart,
      reference_period_end: referencePeriodEnd,
      updated_since: updatedSince,
    }),
    [
      accessClass,
      barangay,
      inclusionClass,
      initialHasCoordinates,
      kind,
      municipality,
      operatorType,
      ownership,
      ownershipType,
      precision,
      province,
      query,
      referencePeriodEnd,
      referencePeriodStart,
      region,
      source,
      subtype,
      type,
      updatedSince,
    ],
  );
  const filterSignature = signatureOf(filters);
  const filtersRef = useRef(filters);
  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  useEffect(() => {
    if (!municipality) return;
    const controller = new AbortController();
    async function loadBarangays() {
      const rows: AdministrativeUnitOut[] = [];
      let offset = 0;
      try {
        while (rows.length < 2000) {
          const response = await fetch(
            `${apiBaseUrl()}/v1/geographies?level=barangay&parent=${encodeURIComponent(
              municipality,
            )}&limit=500&offset=${offset}`,
            { headers: { Accept: "application/json" }, signal: controller.signal },
          );
          if (!response.ok) break;
          const page = (await response.json()) as AdministrativeUnitOut[];
          rows.push(...page);
          if (page.length < 500) break;
          offset += 500;
        }
        if (!controller.signal.aborted) setBarangays(rows);
      } catch {
        // A missing barangay lookup must not block the map or the text list.
      }
    }
    void loadBarangays();
    return () => controller.abort();
  }, [municipality]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (initialHasCoordinates === "false") return [];
    return facilities.filter((facility) => {
      if (type && facility.facility_type !== type) return false;
      if (subtype && facility.facility_subtype !== subtype) return false;
      if (inclusionClass && facility.inclusion_class !== inclusionClass) return false;
      if (ownership && facility.ownership !== ownership) return false;
      if (ownershipType && facility.ownership_type !== ownershipType) return false;
      if (operatorType && facility.operator_type !== operatorType) return false;
      if (accessClass && facility.public_access_class !== accessClass) return false;
      if (kind && facility.facility_kind !== kind) return false;
      if (region && facility.geography.region_code !== region) return false;
      if (province && facility.geography.province_code !== province) return false;
      if (municipality && facility.geography.municipality_code !== municipality) return false;
      if (barangay && facility.geography.barangay_code !== barangay) return false;
      if (precision && facility.location.precision !== precision) return false;
      if (!needle) return true;
      return [
        facility.display_name,
        facility.geography.region_name,
        facility.geography.province_name,
        facility.geography.municipality_name,
        facility.geography.barangay_name,
        facility.facility_subtype ?? "",
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [
    accessClass,
    barangay,
    facilities,
    inclusionClass,
    initialHasCoordinates,
    kind,
    municipality,
    operatorType,
    ownership,
    ownershipType,
    precision,
    province,
    query,
    region,
    subtype,
    type,
  ]);

  const visibleRef = useRef(visible);
  useEffect(() => {
    visibleRef.current = visible;
  }, [visible]);

  useEffect(() => {
    let disposed = false;
    let map: MapLibreMap | null = null;

    async function init() {
      const maplibregl = await import("maplibre-gl");
      configureMapLibreWorker(maplibregl);
      if (disposed || !containerRef.current) return;
      map = new maplibregl.Map({
        container: containerRef.current,
        style: BASEMAP_STYLE,
        center: [121.6, 14.9],
        zoom: 7.2,
        attributionControl: { compact: true },
      });
      mapRef.current = map;
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("error", () => {
        setError(
          "The basemap could not load. The text result list remains available and is not map-only.",
        );
      });

      map.on("load", () => {
        if (!map) return;
        map.addSource("facilities", {
          type: "geojson",
          data: EMPTY,
          cluster: true,
          clusterRadius: 46,
          clusterMaxZoom: 12,
        });
        map.addLayer({
          id: "clusters",
          type: "circle",
          source: "facilities",
          filter: ["has", "point_count"],
          paint: {
            "circle-color": "#0038a8",
            "circle-radius": ["step", ["get", "point_count"], 18, 10, 24, 50, 32],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
            "circle-opacity": 0.92,
          },
        });
        map.addLayer({
          id: "cluster-count",
          type: "symbol",
          source: "facilities",
          filter: ["has", "point_count"],
          layout: {
            "text-field": ["get", "point_count_abbreviated"],
            "text-size": 12,
            "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          },
          paint: { "text-color": "#ffffff" },
        });
        map.addLayer({
          id: "unclustered-point",
          type: "circle",
          source: "facilities",
          filter: ["!", ["has", "point_count"]],
          paint: {
            "circle-color": [
              "case",
              ["==", ["get", "inclusion_class"], "GOVERNMENT_FACILITY"],
              "#0038a8",
              ["==", ["get", "inclusion_class"], "PRIVATE_PUBLIC_SERVICE_PROVIDER"],
              "#0f766e",
              "#9a6700",
            ],
            "circle-radius": [
              "case",
              ["==", ["get", "precision"], "barangay_centroid"],
              9,
              ["==", ["get", "precision"], "unknown"],
              8,
              6,
            ],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
            "circle-opacity": [
              "case",
              ["in", ["get", "precision"], ["literal", ["barangay_centroid", "unknown"]]],
              0.65,
              1,
            ],
          },
        });

        map.on("click", "clusters", async (event) => {
          const feature = event.features?.[0];
          if (!feature || !map) return;
          const clusterId = Number(feature.properties?.cluster_id);
          const source = map.getSource("facilities") as GeoJSONSource;
          const zoom = await source.getClusterExpansionZoom(clusterId);
          const coordinates =
            feature.geometry.type === "Point" ? feature.geometry.coordinates : null;
          map.easeTo({
            center: coordinates ? [coordinates[0], coordinates[1]] : undefined,
            zoom,
          });
        });
        map.on("click", "unclustered-point", (event) => {
          const id = event.features?.[0]?.properties?.id;
          const match = visibleRef.current.find((facility) => facility.id === id);
          if (match) setSelected(match);
        });
        map.on("mouseenter", "clusters", () => {
          if (map) map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "clusters", () => {
          if (map) map.getCanvas().style.cursor = "";
        });
        map.on("mouseenter", "unclustered-point", () => {
          if (map) map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "unclustered-point", () => {
          if (map) map.getCanvas().style.cursor = "";
        });

        setReady(true);
        void loadViewport();
      });

      map.on("moveend", () => {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => void loadViewport(), 400);
      });
    }

    async function loadViewport() {
      if (!map) return;
      const current = filtersRef.current;
      loadedSignatureRef.current = signatureOf(current);
      const bounds = map.getBounds();
      const west = bounds.getWest();
      const south = bounds.getSouth();
      const east = bounds.getEast();
      const north = bounds.getNorth();
      if ((east - west) * (north - south) > 24) {
        setError("Zoom in to load records; the viewport is larger than the map query limit.");
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      const bbox = [west, south, east, north].map((value) => value.toFixed(5)).join(",");
      const params = new URLSearchParams({ bbox, limit: "500" });
      for (const [key, value] of Object.entries(current)) {
        if (value) params.set(key, value);
      }
      try {
        const response = await fetch(
          `${apiBaseUrl()}/v1/facilities/within?${params.toString()}`,
          { headers: { Accept: "application/json" } },
        );
        if (!response.ok) {
          const body = (await response.json().catch(() => null)) as { message?: string } | null;
          throw new Error(body?.message ?? `The map query returned ${response.status}.`);
        }
        const data = (await response.json()) as {
          items: FacilitySummary[];
          truncated: boolean;
        };
        if (disposed) return;
        setFacilities(data.items);
        setTruncated(data.truncated);
        setSelected((currentSelected) =>
          currentSelected
            ? (data.items.find((item) => item.id === currentSelected.id) ?? null)
            : null,
        );
      } catch (caught) {
        if (!disposed) {
          setError(caught instanceof Error ? caught.message : "The map query failed.");
        }
      } finally {
        if (!disposed) setLoading(false);
      }
    }

    loadViewportRef.current = loadViewport;
    void init();
    return () => {
      disposed = true;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      map?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!ready || loadedSignatureRef.current === filterSignature) return;
    const handle = setTimeout(() => loadViewportRef.current(), 250);
    return () => clearTimeout(handle);
  }, [filterSignature, ready]);

  useEffect(() => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) params.set(key, value);
    }
    const search = params.toString();
    const nextUrl = search ? `/map?${search}` : "/map";
    if (`${window.location.pathname}${window.location.search}` !== nextUrl) {
      window.history.replaceState(null, "", nextUrl);
    }
  }, [filters]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const source = map.getSource("facilities") as GeoJSONSource | undefined;
    if (!source) return;
    source.setData({
      type: "FeatureCollection",
      features: visible.flatMap((facility) => {
        const latitude = facility.location.latitude;
        const longitude = facility.location.longitude;
        if (latitude == null || longitude == null) return [];
        return [
          {
            type: "Feature" as const,
            id: facility.id,
            properties: {
              id: facility.id,
              facility_type: facility.facility_type,
              inclusion_class: facility.inclusion_class,
              precision: facility.location.precision,
              name: facility.display_name,
            },
            geometry: {
              type: "Point" as const,
              coordinates: [longitude, latitude],
            },
          },
        ];
      }),
    });
  }, [visible, ready]);

  function focusFacility(facility: FacilitySummary) {
    setSelected(facility);
    setMobileView("map");
    const map = mapRef.current;
    const latitude = facility.location.latitude;
    const longitude = facility.location.longitude;
    if (map && latitude != null && longitude != null) {
      map.easeTo({
        center: [longitude, latitude],
        zoom: Math.max(map.getZoom(), 12),
      });
    }
  }

  function resetFilters() {
    setType("");
    setSubtype("");
    setQuery("");
    setInclusionClass("");
    setOwnership("");
    setOwnershipType("");
    setOperatorType("");
    setAccessClass("");
    setKind("");
    setRegion("");
    setProvince("");
    setMunicipality("");
    setBarangay("");
    setBarangays([]);
    setSource("");
    setPrecision("");
    setReferencePeriodStart("");
    setReferencePeriodEnd("");
    setUpdatedSince("");
  }

  const selectedNeedsAreaLabel = selected?.location.precision === "barangay_centroid";
  const selectedCategory = selected ? labelFor(categoryLabels, selected.facility_type) : "";
  const selectedSubtype = selected?.facility_subtype
    ? subtypes.find((item) => item.code === selected.facility_subtype)?.label
    : undefined;
  const directoryHref = `/directory${queryString(filters)}`;

  return (
    <div className="flex h-[calc(100dvh-var(--header-height))] min-h-[36rem] flex-col border-t border-[#d1d8e6] lg:flex-row">
      <div
        className={cn(
          "relative min-h-[24rem] flex-1",
          mobileView === "list" && "hidden lg:block",
        )}
      >
        <div ref={containerRef} className="h-full w-full bg-[#e6ebf4]" />
        <form
          className="absolute left-3 top-3 z-10 max-h-[calc(100%-1.5rem)] w-[min(23rem,calc(100%-1.5rem))] overflow-y-auto border border-[#d1d8e6] bg-white p-3 shadow-[4px_4px_0_0_rgba(0,56,168,0.18)]"
          aria-label="Map filters"
          onSubmit={(event) => event.preventDefault()}
        >
          <div className="flex gap-2">
            <label htmlFor="map-search" className="sr-only">
              Filter mapped records
            </label>
            <div className="relative flex-1">
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-[#5a5a58]"
              />
              <Input
                id="map-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Filter this view"
                className="pl-8"
              />
            </div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div>
              <label htmlFor="map-type" className="sr-only">
                Facility category
              </label>
              <Select
                id="map-type"
                value={type}
                onChange={(event) => {
                  setType(event.target.value);
                  setSubtype("");
                }}
              >
                <option value="">All categories</option>
                {categories.map((category) => (
                  <option key={category.code} value={category.code}>
                    {category.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="map-subtype" className="sr-only">
                Facility subtype
              </label>
              <Select
                id="map-subtype"
                value={subtype}
                onChange={(event) => setSubtype(event.target.value)}
              >
                <option value="">Any subtype</option>
                {subtypes
                  .filter((item) => !type || item.categoryCode === type)
                  .map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
              </Select>
            </div>
            <div>
              <label htmlFor="map-inclusion" className="sr-only">
                Inclusion class
              </label>
              <Select
                id="map-inclusion"
                value={inclusionClass}
                onChange={(event) => setInclusionClass(event.target.value)}
              >
                <option value="">All inclusion classes</option>
                {(taxonomy?.inclusion_classes ?? []).map((term) => (
                  <option key={term.code} value={term.code}>
                    {term.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="map-access" className="sr-only">
                Public access
              </label>
              <Select
                id="map-access"
                value={accessClass}
                onChange={(event) => setAccessClass(event.target.value)}
              >
                <option value="">All access classes</option>
                {(taxonomy?.access_classes ?? []).map((term) => (
                  <option key={term.code} value={term.code}>
                    {term.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <details className="mt-2 border-t border-[#d1d8e6] pt-2">
            <summary className="cursor-pointer font-ui text-xs font-bold uppercase tracking-wide text-[#0038a8]">
              Location, source, and time filters
            </summary>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="map-region" className="sr-only">
                  Region
                </label>
                <Select
                  id="map-region"
                  value={region}
                  onChange={(event) => {
                    setRegion(event.target.value);
                    setProvince("");
                    setMunicipality("");
                    setBarangay("");
                    setBarangays([]);
                  }}
                >
                  <option value="">All regions</option>
                  {regions.map((item) => (
                    <option key={item.psgc_code} value={item.psgc_code}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label htmlFor="map-province" className="sr-only">
                  Province
                </label>
                <Select
                  id="map-province"
                  value={province}
                  onChange={(event) => {
                    setProvince(event.target.value);
                    setMunicipality("");
                    setBarangay("");
                    setBarangays([]);
                  }}
                >
                  <option value="">All provinces</option>
                  {provinceOptions.map((item) => (
                    <option key={item.psgc_code} value={item.psgc_code}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label htmlFor="map-municipality" className="sr-only">
                  City or municipality
                </label>
                <Select
                  id="map-municipality"
                  value={municipality}
                  onChange={(event) => {
                    setMunicipality(event.target.value);
                    setBarangay("");
                    setBarangays([]);
                  }}
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
                <label htmlFor="map-barangay" className="sr-only">
                  Barangay
                </label>
                <Select
                  id="map-barangay"
                  value={barangay}
                  onChange={(event) => setBarangay(event.target.value)}
                  disabled={!municipality}
                >
                  <option value="">
                    {municipality ? "All barangays" : "Choose a city or municipality"}
                  </option>
                  {barangays.map((item) => (
                    <option key={item.psgc_code} value={item.psgc_code}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="col-span-2">
                <label htmlFor="map-source" className="sr-only">
                  Source agency
                </label>
                <Select
                  id="map-source"
                  value={source}
                  onChange={(event) => setSource(event.target.value)}
                >
                  <option value="">Any source agency</option>
                  {sources.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label htmlFor="map-precision" className="sr-only">
                  Location precision
                </label>
                <Select
                  id="map-precision"
                  value={precision}
                  onChange={(event) => setPrecision(event.target.value)}
                >
                  <option value="">Any precision</option>
                  {PRECISION_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label htmlFor="map-ownership" className="sr-only">
                  Ownership
                </label>
                <Select
                  id="map-ownership"
                  value={ownership}
                  onChange={(event) => setOwnership(event.target.value)}
                >
                  {OWNERSHIP_VALUES.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label htmlFor="map-ownership-type" className="sr-only">
                  Ownership type
                </label>
                <Select
                  id="map-ownership-type"
                  value={ownershipType}
                  onChange={(event) => setOwnershipType(event.target.value)}
                >
                  <option value="">All ownership types</option>
                  {(taxonomy?.ownership_types ?? []).map((term) => (
                    <option key={term.code} value={term.code}>
                      {term.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label htmlFor="map-operator-type" className="sr-only">
                  Operator type
                </label>
                <Select
                  id="map-operator-type"
                  value={operatorType}
                  onChange={(event) => setOperatorType(event.target.value)}
                >
                  <option value="">All operator types</option>
                  {(taxonomy?.operator_types ?? []).map((term) => (
                    <option key={term.code} value={term.code}>
                      {term.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="col-span-2">
                <label htmlFor="map-kind" className="sr-only">
                  Facility kind
                </label>
                <Select
                  id="map-kind"
                  value={kind}
                  onChange={(event) => setKind(event.target.value)}
                >
                  <option value="">All facility kinds</option>
                  {(taxonomy?.facility_kinds ?? []).map((term) => (
                    <option key={term.code} value={term.code}>
                      {term.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label htmlFor="map-reference-start" className="sr-only">
                  Reference period start
                </label>
                <Input
                  id="map-reference-start"
                  type="date"
                  value={referencePeriodStart.slice(0, 10)}
                  onChange={(event) => setReferencePeriodStart(event.target.value)}
                  aria-label="Reference period start"
                />
              </div>
              <div>
                <label htmlFor="map-reference-end" className="sr-only">
                  Reference period end
                </label>
                <Input
                  id="map-reference-end"
                  type="date"
                  value={referencePeriodEnd.slice(0, 10)}
                  onChange={(event) => setReferencePeriodEnd(event.target.value)}
                  aria-label="Reference period end"
                />
              </div>
              <div className="col-span-2">
                <label htmlFor="map-updated-since" className="sr-only">
                  Updated since
                </label>
                <Input
                  id="map-updated-since"
                  type="date"
                  value={updatedSince.slice(0, 10)}
                  onChange={(event) => setUpdatedSince(event.target.value)}
                  aria-label="Canonical record updated since"
                />
              </div>
            </div>
          </details>

          <p className="mt-2 flex items-center justify-between gap-2 font-ui text-xs text-[#5a5a58]">
            <span>
              {loading ? (
                <span className="inline-flex items-center gap-1">
                  <Loader2 aria-hidden="true" className="size-3 animate-spin" /> Updating
                </span>
              ) : (
                `${visible.length} mapped records in view`
              )}
            </span>
            <span>{truncated ? "Capped at 500" : "Bounded viewport query"}</span>
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Link
              href={directoryHref}
              className="font-ui text-xs font-bold text-[#0038a8] underline"
            >
              Open as directory results
            </Link>
            <button
              type="button"
              onClick={resetFilters}
              className="font-ui text-xs font-bold text-[#5a5a58] underline"
            >
              Reset filters
            </button>
          </div>
        </form>
        {error ? (
          <div
            role="alert"
            className="absolute inset-x-3 top-28 z-20 border-l-4 border-[#9a6700] bg-[#fff8e1] p-3 font-sans text-xs text-[#3d2b00] shadow-lg lg:left-auto lg:right-3 lg:w-80"
          >
            {error}{" "}
            <Link href={directoryHref} className="underline">
              Use the directory
            </Link>
          </div>
        ) : null}
        {selected ? (
          <div className="absolute bottom-3 left-3 right-3 z-10 max-w-md border border-[#d1d8e6] bg-white p-4 shadow-lg sm:right-auto">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-ui text-xs font-bold uppercase tracking-wide text-[#0038a8]">
                  Selected facility
                </p>
                <h2 className="mt-1 font-display text-xl font-bold leading-tight">
                  {selected.display_name}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="border border-[#d1d8e6] px-2 py-1 font-ui text-xs font-bold"
                aria-label="Close selected facility"
              >
                Close
              </button>
            </div>
            <p className="mt-2 font-sans text-sm text-[#5a5a58]">
              {selectedCategory}
              {selectedSubtype ? ` · ${selectedSubtype}` : ""} ·{" "}
              {labelFor(inclusionLabels, selected.inclusion_class)} ·{" "}
              {PRECISION_LABELS[selected.location.precision] ?? selected.location.precision}
              {selected.is_synthetic ? " · Synthetic" : ""}
            </p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">
              Ownership: {labelFor(ownershipTypeLabels, selected.ownership_type)} · Access:{" "}
              {labelFor(accessLabels, selected.public_access_class, "Unknown")}
            </p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">
              {[
                selected.geography.barangay_name,
                selected.geography.municipality_name,
                selected.geography.province_name,
              ]
                .filter(Boolean)
                .join(", ") || "Administrative geography not linked"}
            </p>
            {selectedNeedsAreaLabel ? (
              <p className="mt-2 border-l-2 border-[#9a6700] pl-2 font-sans text-xs text-[#6b4a00]">
                This marker represents a barangay centroid, not a building-level pin.
              </p>
            ) : null}
            <Link
              href={`/facilities/${selected.slug ?? selected.id}`}
              className={cn(buttonVariants({ variant: "blue", size: "sm" }), "mt-3")}
            >
              Open full profile
            </Link>
          </div>
        ) : null}
        <div className="absolute bottom-3 right-3 z-10 hidden max-w-[16rem] border border-[#d1d8e6] bg-white/95 p-2 font-sans text-[11px] leading-snug text-[#5a5a58] lg:block">
          <p className="font-ui text-[10px] font-bold uppercase tracking-wide text-[#0a0a0a]">
            Marker colour
          </p>
          <p className="mt-1 flex items-center gap-1">
            <span aria-hidden="true" className="inline-block size-2.5 bg-[#0038a8]" /> Government
          </p>
          <p className="flex items-center gap-1">
            <span aria-hidden="true" className="inline-block size-2.5 bg-[#0f766e]" /> Private
            public-service provider
          </p>
          <p className="flex items-center gap-1">
            <span aria-hidden="true" className="inline-block size-2.5 bg-[#9a6700]" /> Public-access
            venue
          </p>
          <p className="mt-1">
            Unknown and barangay-centroid positions are softer, area-level markers. Do not treat
            them as exact building locations.
          </p>
        </div>
      </div>

      <aside
        aria-label="Map results list"
        className={cn(
          "flex w-full flex-col border-l border-[#d1d8e6] bg-white lg:max-w-[27rem]",
          mobileView === "map" && "hidden lg:flex",
        )}
      >
        <div className="border-b border-[#d1d8e6] p-4">
          <div className="flex items-center justify-between gap-2">
            <h1 className="font-display text-2xl font-extrabold">Map results</h1>
            <Badge tone="muted">{visible.length}</Badge>
          </div>
          <p className="mt-1 font-sans text-xs leading-relaxed text-[#5a5a58]">
            The same records are listed here. Map selection never replaces the text result list.
          </p>
          {error ? (
            <p role="alert" className="mt-3 border-l-4 border-[#9a6700] bg-[#fff8e1] p-2 font-sans text-xs text-[#3d2b00]">
              {error}{" "}
              <Link href={directoryHref} className="underline">
                Use the directory
              </Link>
            </p>
          ) : null}
        </div>
        <div className="flex-1 overflow-y-auto">
          {visible.length === 0 ? (
            <p className="p-6 font-sans text-sm text-[#5a5a58]">
              No geocoded records are visible at this position. Pan or zoom the map, clear the
              filter, or use the full directory for records without coordinates.
            </p>
          ) : (
            <ul className="divide-y divide-[#d1d8e6]">
              {visible.map((facility) => (
                <li key={facility.id}>
                  <button
                    type="button"
                    onClick={() => focusFacility(facility)}
                    className={cn(
                      "w-full p-4 text-left hover:bg-[#f4f7fc]",
                      selected?.id === facility.id && "bg-[#e8f1ff]",
                    )}
                  >
                    <span className="flex flex-wrap items-center gap-1.5">
                      <Badge tone="outline">
                        {labelFor(categoryLabels, facility.facility_type)}
                      </Badge>
                      <Badge
                        tone={
                          facility.inclusion_class === "GOVERNMENT_FACILITY"
                            ? "default"
                            : "outline"
                        }
                      >
                        {labelFor(inclusionLabels, facility.inclusion_class)}
                      </Badge>
                      {facility.is_synthetic ? <Badge tone="sun">Synthetic</Badge> : null}
                    </span>
                    <span className="mt-2 block font-display text-lg font-bold leading-tight">
                      {facility.display_name}
                    </span>
                    <span className="mt-1 block font-sans text-xs text-[#5a5a58]">
                      {facility.geography.municipality_name ??
                        facility.geography.province_name ??
                        facility.geography.region_name ??
                        "Geography unknown"}
                      {" · "}
                      {PRECISION_LABELS[facility.location.precision] ??
                        facility.location.precision}
                      {" · "}
                      {facility.source_count} source
                      {facility.source_count === 1 ? "" : "s"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <div className="fixed bottom-0 left-0 right-0 z-20 flex border-t border-[#d1d8e6] bg-white lg:hidden">
        <button
          type="button"
          onClick={() => setMobileView("map")}
          className={cn(
            "flex h-12 flex-1 items-center justify-center gap-2 font-ui text-sm font-bold",
            mobileView === "map" ? "bg-[#0038a8] text-white" : "bg-white text-[#0a0a0a]",
          )}
          aria-pressed={mobileView === "map"}
        >
          <MapIcon aria-hidden="true" className="size-4" /> Map
        </button>
        <button
          type="button"
          onClick={() => setMobileView("list")}
          className={cn(
            "flex h-12 flex-1 items-center justify-center gap-2 font-ui text-sm font-bold",
            mobileView === "list" ? "bg-[#0038a8] text-white" : "bg-white text-[#0a0a0a]",
          )}
          aria-pressed={mobileView === "list"}
        >
          <List aria-hidden="true" className="size-4" /> List ({visible.length})
        </button>
      </div>
    </div>
  );
}
