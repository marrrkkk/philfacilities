"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { List, Loader2, Map as MapIcon, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import {
  getFacilityMap,
  type FacilityMapCluster,
  type FacilityMapPoint,
  type FacilityMapPointsResponse,
} from "@/lib/api";
import {
  ACCESS_LABELS,
  INCLUSION_CLASS_LABELS,
  PRECISION_LABELS,
  titleCase,
} from "@/lib/format";
import { configureMapLibreWorker } from "@/lib/maplibre";
import { BASEMAP_STYLE } from "@/lib/map-style";
import { cn } from "@/lib/utils";

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

const EMPTY_MAP: FacilityMapPointsResponse = {
  bbox: "",
  zoom: 0,
  total: 0,
  mode: "points",
  points: [],
  clusters: [],
  cell_deg: null,
  truncated: false,
};

function viewportOf(map: MapLibreMap): { bbox: string; zoom: number } {
  const bounds = map.getBounds();
  return {
    bbox: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]
      .map((value) => value.toFixed(5))
      .join(","),
    zoom: Math.round(map.getZoom()),
  };
}

const CATEGORY_OPTIONS = [
  ["school", "Schools"],
  ["health_facility", "Health"],
  ["government_office", "Government offices"],
  ["library", "Libraries"],
  ["museum", "Museums"],
  ["community_facility", "Community"],
  ["emergency_facility", "Emergency"],
  ["social_welfare_facility", "Social welfare"],
  ["public_market", "Markets"],
  ["transport_facility", "Transport"],
  ["utility_facility", "Utilities"],
  ["environmental_monitoring", "Environmental monitoring"],
  ["public_space", "Public spaces"],
  ["cultural_facility", "Cultural"],
  ["agricultural_facility", "Agriculture"],
  ["justice_facility", "Justice"],
  ["housing_service", "Housing"],
] as const;

const OWNERSHIP_TYPE_OPTIONS = [
  "NATIONAL_GOVERNMENT",
  "LOCAL_GOVERNMENT",
  "GOCC",
  "PUBLIC_EDUCATIONAL_INSTITUTION",
  "OTHER_PUBLIC_BODY",
  "GOVERNMENT_UNSPECIFIED",
  "PRIVATE_CORPORATE",
  "PRIVATE_INDIVIDUAL_OR_PARTNERSHIP",
  "NGO_NON_PROFIT",
  "COOPERATIVE",
  "RELIGIOUS_FAITH_BASED",
  "PUBLIC_PRIVATE_JOINT",
  "PRIVATE_UNSPECIFIED",
  "UNKNOWN",
] as const;

export function MapExplorer({
  initialType = "",
  initialQuery = "",
  initialInclusionClass = "",
  initialOwnership = "",
  initialOwnershipType = "",
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
  initialType?: string;
  initialQuery?: string;
  initialInclusionClass?: string;
  initialOwnership?: string;
  initialOwnershipType?: string;
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
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [basemapError, setBasemapError] = useState<string | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);
  const [mapResponse, setMapResponse] = useState<FacilityMapPointsResponse>(EMPTY_MAP);
  const [viewport, setViewport] = useState<{ bbox: string; zoom: number } | null>(null);
  const [selected, setSelected] = useState<FacilityMapPoint | null>(null);
  const [type, setType] = useState(initialType);
  const [inclusionClass, setInclusionClass] = useState(initialInclusionClass);
  const [ownershipType, setOwnershipType] = useState(initialOwnershipType);
  const [accessClass, setAccessClass] = useState(initialAccessClass);
  const [kind, setKind] = useState(initialKind);
  const [query, setQuery] = useState(initialQuery);
  const [mobileView, setMobileView] = useState<"map" | "list">("map");

  // The "has coordinates" filter is a database-level constraint that this
  // endpoint cannot express, so render an explicit empty state instead of
  // issuing a query whose results would all be filtered out client-side.
  const noCoordinates = initialHasCoordinates === "false";
  const mapData = noCoordinates ? EMPTY_MAP : mapResponse;
  const isLoading = noCoordinates ? false : loading;

  const mapDataRef = useRef(mapData);
  useEffect(() => {
    mapDataRef.current = mapData;
  }, [mapData]);

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
        center: [122.0, 12.5],
        zoom: 5.2,
        attributionControl: { compact: true },
      });
      mapRef.current = map;
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("error", () => {
        setBasemapError(
          "The basemap could not load. The text result list remains available and is not map-only.",
        );
      });

      map.on("load", () => {
        if (!map) return;
        map.addSource("facilities", { type: "geojson", data: EMPTY });
        map.addLayer({
          id: "facility-clusters",
          type: "circle",
          source: "facilities",
          filter: ["==", ["get", "kind"], "cluster"],
          paint: {
            "circle-color": "#0038a8",
            "circle-radius": [
              "step",
              ["get", "count"],
              18,
              10,
              24,
              100,
              30,
              1000,
              36,
              10000,
              42,
            ],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
            "circle-opacity": 0.92,
          },
        });
        map.addLayer({
          id: "facility-cluster-count",
          type: "symbol",
          source: "facilities",
          filter: ["==", ["get", "kind"], "cluster"],
          layout: {
            "text-field": ["to-string", ["get", "count"]],
            "text-size": ["step", ["get", "count"], 10, 1000, 11, 10000, 12],
            "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
            "text-allow-overlap": true,
          },
          paint: { "text-color": "#ffffff" },
        });
        map.addLayer({
          id: "facility-points",
          type: "circle",
          source: "facilities",
          filter: ["==", ["get", "kind"], "point"],
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

        map.on("click", "facility-clusters", (event) => {
          const feature = event.features?.[0];
          if (!feature || !map) return;
          const longitude = Number(feature.properties?.longitude);
          const latitude = Number(feature.properties?.latitude);
          if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return;
          map.easeTo({
            center: [longitude, latitude],
            zoom: Math.min(map.getZoom() + 2, 18),
          });
        });
        map.on("click", "facility-points", (event) => {
          const id = String(event.features?.[0]?.properties?.id ?? "");
          const match = (mapDataRef.current.points ?? []).find((point) => point.id === id);
          if (match) setSelected(match);
        });
        map.on("mouseenter", "facility-clusters", () => {
          if (map) map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "facility-clusters", () => {
          if (map) map.getCanvas().style.cursor = "";
        });
        map.on("mouseenter", "facility-points", () => {
          if (map) map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "facility-points", () => {
          if (map) map.getCanvas().style.cursor = "";
        });

        setReady(true);
        setViewport(viewportOf(map));
      });

      map.on("moveend", () => {
        if (!map) return;
        if (debounceRef.current) clearTimeout(debounceRef.current);
        const next = viewportOf(map);
        debounceRef.current = setTimeout(() => {
          if (disposed) return;
          setViewport((current) =>
            current && current.bbox === next.bbox && current.zoom === next.zoom ? current : next,
          );
        }, 250);
      });
    }

    void init();
    return () => {
      disposed = true;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      map?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (initialHasCoordinates === "false" || !ready || !viewport) return;
    const controller = new AbortController();
    const timeout = setTimeout(() => {
      setLoading(true);
      setDataError(null);
      const params: Record<string, string | number | undefined> = {
        bbox: viewport.bbox,
        zoom: viewport.zoom,
        type: type || undefined,
        q: query.trim() || undefined,
        inclusion_class: inclusionClass || undefined,
        ownership: initialOwnership || undefined,
        ownership_type: ownershipType || undefined,
        public_access_class: accessClass || undefined,
        facility_kind: kind || undefined,
        region_code: initialRegion || undefined,
        province_code: initialProvince || undefined,
        municipality_code: initialMunicipality || undefined,
        barangay_code: initialBarangay || undefined,
        source: initialSource || undefined,
        location_precision: initialPrecision || undefined,
        reference_period_start: initialReferencePeriodStart || undefined,
        reference_period_end: initialReferencePeriodEnd || undefined,
        updated_since: initialUpdatedSince || undefined,
      };
      getFacilityMap(params, { signal: controller.signal })
        .then((data) => {
          if (controller.signal.aborted) return;
          setMapResponse(data);
          setSelected((current) =>
            current && (data.points ?? []).some((point) => point.id === current.id)
              ? current
              : null,
          );
        })
        .catch((caught) => {
          if (controller.signal.aborted) return;
          setDataError(
            caught instanceof Error ? caught.message : "The map query failed. Try again.",
          );
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 250);
    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [
    accessClass,
    inclusionClass,
    initialBarangay,
    initialHasCoordinates,
    initialMunicipality,
    initialOwnership,
    initialPrecision,
    initialProvince,
    initialReferencePeriodEnd,
    initialReferencePeriodStart,
    initialRegion,
    initialSource,
    initialUpdatedSince,
    kind,
    ownershipType,
    query,
    ready,
    type,
    viewport,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const source = map.getSource("facilities") as GeoJSONSource | undefined;
    if (!source) return;
    const features = [
      ...(mapData.points ?? []).map((point) => ({
        type: "Feature" as const,
        id: point.id,
        properties: {
          kind: "point",
          id: point.id,
          name: point.name,
          facility_type: point.facility_type,
          inclusion_class: point.inclusion_class,
          precision: point.precision,
        },
        geometry: {
          type: "Point" as const,
          coordinates: [point.longitude, point.latitude],
        },
      })),
      ...(mapData.clusters ?? []).map((cluster, index) => ({
        type: "Feature" as const,
        id: `cluster-${index}`,
        properties: {
          kind: "cluster",
          count: cluster.count,
          label: cluster.label,
          longitude: cluster.longitude,
          latitude: cluster.latitude,
        },
        geometry: {
          type: "Point" as const,
          coordinates: [cluster.longitude, cluster.latitude],
        },
      })),
    ];
    source.setData({ type: "FeatureCollection", features });
  }, [mapData, ready]);

  function focusPoint(point: FacilityMapPoint) {
    setSelected(point);
    setMobileView("map");
    const map = mapRef.current;
    if (map) {
      map.easeTo({ center: [point.longitude, point.latitude], zoom: Math.max(map.getZoom(), 12) });
    }
  }

  function focusCluster(cluster: FacilityMapCluster) {
    setMobileView("map");
    mapRef.current?.easeTo({
      center: [cluster.longitude, cluster.latitude],
      zoom: Math.min((mapRef.current?.getZoom() ?? 6) + 2, 18),
    });
  }

  const selectedNeedsAreaLabel = selected?.precision === "barangay_centroid";
  const points = mapData.points ?? [];
  const clusters = mapData.clusters ?? [];

  return (
    <div className="relative flex h-[calc(100dvh-var(--header-height))] min-h-[36rem] flex-col border-t border-[#d1d8e6] lg:flex-row">
      {/* Keep the map mounted at full size on mobile. Hiding it with display:none
          makes MapLibre recalculate a collapsed viewport and refetch a bbox that
          excludes the current results, which empties the list. The results panel
          is overlaid instead. */}
      <div className="relative min-h-[24rem] flex-1">
        <div ref={containerRef} className="h-full w-full bg-[#e6ebf4]" />
        <div className="absolute left-3 top-3 z-10 w-[min(23rem,calc(100%-1.5rem))] border border-[#d1d8e6] bg-white p-3 shadow-[4px_4px_0_0_rgba(0,56,168,0.18)]">
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
                onChange={(event) => setType(event.target.value)}
              >
                <option value="">All categories</option>
                {CATEGORY_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
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
                {Object.entries(INCLUSION_CLASS_LABELS).map(([value, label]) => (
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
                {OWNERSHIP_TYPE_OPTIONS.map((value) => (
                  <option key={value} value={value}>
                    {titleCase(value)}
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
                {Object.entries(ACCESS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="col-span-2">
              <label htmlFor="map-kind" className="sr-only">
                Facility kind
              </label>
              <Select id="map-kind" value={kind} onChange={(event) => setKind(event.target.value)}>
                <option value="">All facility kinds</option>
                <option value="facility">Facility</option>
                <option value="site">Site or compound</option>
                <option value="building">Building</option>
                <option value="facility_unit">Facility unit</option>
                <option value="infrastructure_asset">Infrastructure asset</option>
                <option value="project">Project</option>
              </Select>
            </div>
          </div>
          <p className="mt-2 flex items-center justify-between gap-2 font-ui text-xs text-[#5a5a58]">
            <span>
              {isLoading ? (
                <span className="inline-flex items-center gap-1">
                  <Loader2 aria-hidden="true" className="size-3 animate-spin" /> Updating
                </span>
              ) : (
                `${mapData.total.toLocaleString()} mapped records in view`
              )}
            </span>
            <span>
              {mapData.mode === "clusters"
                ? `${clusters.length} server clusters`
                : "Individual markers"}
            </span>
          </p>
        </div>
        {dataError || basemapError ? (
          <div
            role="alert"
            className="absolute inset-x-3 top-28 z-20 border-l-4 border-[#9a6700] bg-[#fff8e1] p-3 font-sans text-xs text-[#3d2b00] shadow-lg lg:hidden"
          >
            {dataError ?? basemapError}{" "}
            <Link href="/directory" className="underline">
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
                  {selected.name}
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
              {titleCase(selected.facility_type)} ·{" "}
              {INCLUSION_CLASS_LABELS[selected.inclusion_class] ??
                titleCase(selected.inclusion_class)}{" "}
              · {PRECISION_LABELS[selected.precision] ?? titleCase(selected.precision)}
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
          Unknown and barangay-centroid positions are drawn as softer, area-level markers. Do not
          treat them as exact building locations.
        </div>
      </div>

      <aside
        aria-label="Map results list"
        className={cn(
          "absolute inset-x-0 bottom-12 top-0 z-20 flex w-full flex-col border-l border-[#d1d8e6] bg-white lg:static lg:inset-auto lg:z-auto lg:max-w-[27rem]",
          mobileView === "map" && "hidden lg:flex",
        )}
      >
        <div className="border-b border-[#d1d8e6] p-4">
          <div className="flex items-center justify-between gap-2">
            <h1 className="font-display text-2xl font-extrabold">Map results</h1>
            <Badge tone="muted">{mapData.total.toLocaleString()}</Badge>
          </div>
          <p className="mt-1 font-sans text-xs leading-relaxed text-[#5a5a58]">
            The same records are listed here. Map selection never replaces the text result list.
          </p>
          {mapData.mode === "clusters" ? (
            <p className="mt-2 font-sans text-xs leading-relaxed text-[#5a5a58]">
              This view holds too many markers, so records are grouped into count circles. Select
              a circle or zoom in to load individual facilities.
            </p>
          ) : null}
          {dataError || basemapError ? (
            <p role="alert" className="mt-3 border-l-4 border-[#9a6700] bg-[#fff8e1] p-2 font-sans text-xs text-[#3d2b00]">
              {dataError ?? basemapError}{" "}
              <Link href="/directory" className="underline">
                Use the directory
              </Link>
            </p>
          ) : null}
        </div>
        <div className="flex-1 overflow-y-auto">
          {mapData.mode === "clusters" ? (
            clusters.length === 0 ? (
              <p className="p-6 font-sans text-sm text-[#5a5a58]">
                No geocoded records are visible at this position. Pan or zoom the map, clear the
                filter, or use the full directory for records without coordinates.
              </p>
            ) : (
              <ul className="divide-y divide-[#d1d8e6]">
                {clusters.map((cluster) => (
                  <li key={`${cluster.latitude}-${cluster.longitude}`}>
                    <button
                      type="button"
                      onClick={() => focusCluster(cluster)}
                      className="w-full p-4 text-left hover:bg-[#f4f7fc]"
                    >
                      <span className="flex flex-wrap items-center gap-1.5">
                        <Badge tone="default">{cluster.label}</Badge>
                      </span>
                      <span className="mt-2 block font-display text-lg font-bold leading-tight">
                        Zoom into this area
                      </span>
                      <span className="mt-1 block font-sans text-xs text-[#5a5a58]">
                        Select to load the facilities inside this cluster.
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )
          ) : points.length === 0 ? (
            <p className="p-6 font-sans text-sm text-[#5a5a58]">
              No geocoded records are visible at this position. Pan or zoom the map, clear the
              filter, or use the full directory for records without coordinates.
            </p>
          ) : (
            <ul className="divide-y divide-[#d1d8e6]">
              {points.map((point) => (
                <li key={point.id}>
                  <button
                    type="button"
                    onClick={() => focusPoint(point)}
                    className={cn(
                      "w-full p-4 text-left hover:bg-[#f4f7fc]",
                      selected?.id === point.id && "bg-[#e8f1ff]",
                    )}
                  >
                    <span className="flex flex-wrap items-center gap-1.5">
                      <Badge tone="outline">{titleCase(point.facility_type)}</Badge>
                      <Badge
                        tone={
                          point.inclusion_class === "GOVERNMENT_FACILITY" ? "default" : "outline"
                        }
                      >
                        {INCLUSION_CLASS_LABELS[point.inclusion_class] ??
                          titleCase(point.inclusion_class)}
                      </Badge>
                    </span>
                    <span className="mt-2 block font-display text-lg font-bold leading-tight">
                      {point.name}
                    </span>
                    <span className="mt-1 block font-sans text-xs text-[#5a5a58]">
                      {PRECISION_LABELS[point.precision] ?? titleCase(point.precision)}
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
          <List aria-hidden="true" className="size-4" /> List ({mapData.total.toLocaleString()})
        </button>
      </div>
    </div>
  );
}
