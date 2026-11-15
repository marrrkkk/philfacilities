import type { StyleSpecification } from "maplibre-gl";

export const OSM_ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors';

const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const DEFAULT_MAX_ZOOM = 19;

function envValue(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

const configuredTileUrl = envValue(process.env.NEXT_PUBLIC_MAP_TILE_URL);

/**
 * Basemap configuration.
 *
 * The defaults are OpenStreetMap's public raster tiles, which are suitable only
 * for local evaluation and the synthetic demo. A deployment must set both
 * `NEXT_PUBLIC_MAP_TILE_URL` and `NEXT_PUBLIC_MAP_TILE_ATTRIBUTION` to a licensed
 * provider; see `docs/decisions/0006-basemap-provider.md`. `NEXT_PUBLIC_*` values
 * are inlined at build time, so set them before `pnpm build`.
 *
 * When a custom tile URL is set without attribution, the attribution is left
 * empty rather than borrowing OpenStreetMap's credit. That is a configuration
 * error the deployment checklist must catch.
 */
export const BASEMAP_TILE_URL = configuredTileUrl ?? OSM_TILE_URL;

export const BASEMAP_ATTRIBUTION =
  envValue(process.env.NEXT_PUBLIC_MAP_TILE_ATTRIBUTION) ??
  (configuredTileUrl ? "" : OSM_ATTRIBUTION);

export const BASEMAP_MAX_ZOOM = (() => {
  const parsed = Number(envValue(process.env.NEXT_PUBLIC_MAP_TILE_MAXZOOM));
  return Number.isInteger(parsed) && parsed > 0 && parsed <= 24 ? parsed : DEFAULT_MAX_ZOOM;
})();

export const BASEMAP_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    basemap: {
      type: "raster",
      tiles: [BASEMAP_TILE_URL],
      tileSize: 256,
      attribution: BASEMAP_ATTRIBUTION,
      maxzoom: BASEMAP_MAX_ZOOM,
    },
  },
  layers: [
    {
      id: "basemap",
      type: "raster",
      source: "basemap",
    },
  ],
};
