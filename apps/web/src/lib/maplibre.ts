import type * as MapLibre from "maplibre-gl";

/**
 * MapLibre v6 normally discovers its worker relative to the imported module.
 * Next.js/Turbopack does not preserve that relationship, so the worker must be
 * served from a known same-origin URL. The predev/prebuild scripts copy the
 * matching worker version into `public/vendor/maplibre-gl/`.
 */
export const MAPLIBRE_WORKER_ROOT = "/vendor/maplibre-gl";

export function configureMapLibreWorker(maplibregl: typeof MapLibre): void {
  maplibregl.setWorkerUrl(
    `${MAPLIBRE_WORKER_ROOT}/${maplibregl.getVersion()}/maplibre-gl-worker.mjs`,
  );
}
