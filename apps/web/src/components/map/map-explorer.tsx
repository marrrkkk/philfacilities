"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { List, Loader2, Map as MapIcon, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { apiBaseUrl, type FacilitySummary } from "@/lib/api";
import { PRECISION_LABELS, titleCase } from "@/lib/format";
import { configureMapLibreWorker } from "@/lib/maplibre";
import { BASEMAP_STYLE } from "@/lib/map-style";
import { cn } from "@/lib/utils";

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

export function MapExplorer({
  initialType = "",
  initialQuery = "",
  initialOwnership = "",
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
  initialOwnership?: string;
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
  const [error, setError] = useState<string | null>(null);
  const [facilities, setFacilities] = useState<FacilitySummary[]>([]);
  const [selected, setSelected] = useState<FacilitySummary | null>(null);
  const [type, setType] = useState(initialType);
  const [query, setQuery] = useState(initialQuery);
  const [mobileView, setMobileView] = useState<"map" | "list">("map");
  const [truncated, setTruncated] = useState(false);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (initialHasCoordinates === "false") return [];
    return facilities.filter((facility) => {
      if (type && facility.facility_type !== type) return false;
      if (initialOwnership && facility.ownership !== initialOwnership) return false;
      if (initialRegion && facility.geography.region_code !== initialRegion) return false;
      if (initialProvince && facility.geography.province_code !== initialProvince) return false;
      if (initialMunicipality && facility.geography.municipality_code !== initialMunicipality)
        return false;
      if (initialBarangay && facility.geography.barangay_code !== initialBarangay) return false;
      if (initialPrecision && facility.location.precision !== initialPrecision) return false;
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
    facilities,
    initialBarangay,
    initialHasCoordinates,
    initialMunicipality,
    initialOwnership,
    initialPrecision,
    initialProvince,
    initialRegion,
    query,
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
              ["==", ["get", "facility_type"], "school"],
              "#0038a8",
              "#0f766e",
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
      for (const [key, value] of Object.entries({
        type: initialType,
        q: initialQuery,
        ownership: initialOwnership,
        region_code: initialRegion,
        province_code: initialProvince,
        municipality_code: initialMunicipality,
        barangay_code: initialBarangay,
        source: initialSource,
        location_precision: initialPrecision,
        has_coordinates: initialHasCoordinates === "true" ? "true" : undefined,
        reference_period_start: initialReferencePeriodStart || undefined,
        reference_period_end: initialReferencePeriodEnd || undefined,
        updated_since: initialUpdatedSince || undefined,
      })) {
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
        setSelected((current) =>
          current ? (data.items.find((item) => item.id === current.id) ?? null) : null,
        );
      } catch (caught) {
        if (!disposed) {
          setError(caught instanceof Error ? caught.message : "The map query failed.");
        }
      } finally {
        if (!disposed) setLoading(false);
      }
    }

    void init();
    return () => {
      disposed = true;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      map?.remove();
      mapRef.current = null;
    };
  }, [
    initialBarangay,
    initialHasCoordinates,
    initialMunicipality,
    initialOwnership,
    initialPrecision,
    initialProvince,
    initialQuery,
    initialReferencePeriodEnd,
    initialReferencePeriodStart,
    initialRegion,
    initialSource,
    initialType,
    initialUpdatedSince,
  ]);

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

  const selectedNeedsAreaLabel = selected?.location.precision === "barangay_centroid";

  return (
    <div className="flex h-[calc(100dvh-var(--header-height))] min-h-[36rem] flex-col border-t border-[#d1d8e6] lg:flex-row">
      <div
        className={cn(
          "relative min-h-[24rem] flex-1",
          mobileView === "list" && "hidden lg:block",
        )}
      >
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
            <label htmlFor="map-type" className="sr-only">
              Facility type
            </label>
            <Select
              id="map-type"
              value={type}
              onChange={(event) => setType(event.target.value)}
              className="max-w-[9rem]"
            >
              <option value="">All</option>
              <option value="school">Schools</option>
              <option value="health_facility">Health</option>
            </Select>
          </div>
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
        </div>
        {error ? (
          <div
            role="alert"
            className="absolute inset-x-3 top-28 z-20 border-l-4 border-[#9a6700] bg-[#fff8e1] p-3 font-sans text-xs text-[#3d2b00] shadow-lg lg:hidden"
          >
            {error}{" "}
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
              {titleCase(selected.facility_type)} · {PRECISION_LABELS[selected.location.precision]}
              {selected.is_synthetic ? " · Synthetic" : ""}
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
              <Link href="/directory" className="underline">
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
                    <span className="flex items-center gap-1.5">
                      <Badge tone={facility.facility_type === "school" ? "default" : "outline"}>
                        {facility.facility_type === "school" ? "School" : "Health"}
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
