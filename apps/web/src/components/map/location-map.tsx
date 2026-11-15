"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";

import { isPreciseLocation, PRECISION_DESCRIPTIONS } from "@/lib/format";
import { configureMapLibreWorker } from "@/lib/maplibre";
import { BASEMAP_STYLE } from "@/lib/map-style";

export function LocationMap({
  latitude,
  longitude,
  precision,
  name,
}: {
  latitude: number;
  longitude: number;
  precision: string;
  name: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const precise = isPreciseLocation(precision);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    let map: MapLibreMap | null = null;

    async function init() {
      try {
        const maplibregl = await import("maplibre-gl");
        configureMapLibreWorker(maplibregl);
        if (disposed || !containerRef.current) return;
        map = new maplibregl.Map({
          container: containerRef.current,
          style: BASEMAP_STYLE,
          center: [longitude, latitude],
          zoom: precise ? 14 : 11,
          attributionControl: { compact: true },
        });
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
        map.on("error", () => setFailed(true));

        if (precise) {
          new maplibregl.Marker({ color: "#0038a8" })
            .setLngLat([longitude, latitude])
            .addTo(map);
        } else {
          map.on("load", () => {
            if (!map) return;
            map.addSource("area", {
              type: "geojson",
              data: {
                type: "Feature",
                properties: {},
                geometry: { type: "Point", coordinates: [longitude, latitude] },
              },
            });
            map.addLayer({
              id: "area-circle",
              type: "circle",
              source: "area",
              paint: {
                "circle-radius": 46,
                "circle-color": "rgba(0,56,168,0.16)",
                "circle-stroke-color": "#0038a8",
                "circle-stroke-width": 2,
                "circle-stroke-opacity": 0.8,
              },
            });
          });
        }
      } catch {
        setFailed(true);
      }
    }

    void init();

    return () => {
      disposed = true;
      map?.remove();
    };
  }, [latitude, longitude, precise]);

  if (failed) {
    return (
      <div
        className="flex h-80 flex-col items-center justify-center border border-[#d1d8e6] bg-[#f4f7fc] p-6 text-center"
      >
        <p className="font-ui text-sm font-bold">The map could not be loaded</p>
        <p className="mt-2 max-w-md font-sans text-sm text-[#5a5a58]">
          Location: {latitude.toFixed(5)}, {longitude.toFixed(5)}. Use the text coordinates and the
          directory list instead; no location detail is map-only.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div
        ref={containerRef}
        role="region"
        aria-label={`${precise ? "Map" : "Area-level map"} showing ${name} at ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`}
        className="h-80 border border-[#d1d8e6] bg-[#e6ebf4]"
      />
      <p className="mt-2 font-sans text-xs leading-relaxed text-[#5a5a58]">
        {precise ? "Point location. " : "Area-level centroid, not a building pin. "}
        {PRECISION_DESCRIPTIONS[precision] ?? PRECISION_DESCRIPTIONS.unknown}
      </p>
    </div>
  );
}
