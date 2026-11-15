#!/usr/bin/env node
/**
 * MapLibre GL JS v6 loads its worker from a sibling module by default. Next.js
 * (Turbopack) rewrites that module URL and does not emit the worker beside the
 * hashed client bundle, so the map silently fails to load any source.
 *
 * Copy the worker into the public tree under its package version and point
 * MapLibre at that stable, same-origin URL with setWorkerUrl().
 */
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";

const require = createRequire(import.meta.url);
const packageJsonPath = require.resolve("maplibre-gl/package.json");
const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf8"));
const version = packageJson.version;
const source = join(dirname(packageJsonPath), "dist", "maplibre-gl-worker.mjs");
const publicRoot = resolve(import.meta.dirname, "..", "public", "vendor", "maplibre-gl");
const destination = join(publicRoot, version);

if (!existsSync(source)) {
  throw new Error(`MapLibre worker asset is missing: ${source}`);
}

if (existsSync(publicRoot)) {
  for (const entry of readdirSync(publicRoot)) {
    if (entry !== version) {
      rmSync(join(publicRoot, entry), { recursive: true, force: true });
    }
  }
}

mkdirSync(destination, { recursive: true });
cpSync(source, join(destination, "maplibre-gl-worker.mjs"));
console.log(`Copied MapLibre ${version} worker to public/vendor/maplibre-gl/${version}/`);
