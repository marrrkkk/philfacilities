import { NextResponse, type NextRequest } from "next/server";

/**
 * Content Security Policy for the web application.
 *
 * A fresh nonce is generated for every document request and stored on the
 * request headers so Next.js can attach it to framework, page, and inline
 * scripts. The same policy is set on the response. Pages that rely on the
 * nonce must be dynamically rendered; the root layout awaits `connection()`
 * for that reason.
 *
 * The API, basemap, and development HMR endpoints are the only external
 * origins allowed. Production keeps the demo's OpenStreetMap default unless
 * the deployment sets a licensed tile provider.
 */
function originOf(value: string | undefined, fallback: string): string {
  const candidate = value?.trim() || fallback;
  try {
    return new URL(candidate).origin;
  } catch {
    return new URL(fallback).origin;
  }
}

const API_ORIGIN = originOf(
  process.env.NEXT_PUBLIC_API_URL ?? process.env.API_BASE_URL,
  "http://127.0.0.1:8010",
);

const TILE_ORIGIN = originOf(
  process.env.NEXT_PUBLIC_MAP_TILE_URL,
  "https://tile.openstreetmap.org",
);

function buildPolicy(nonce: string, request: NextRequest): string {
  const isDev = process.env.NODE_ENV === "development";
  const httpOrigin = request.nextUrl.origin;
  const wsOrigin = httpOrigin.replace(/^http/, "ws");

  const scriptSources = ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'"];
  if (isDev) scriptSources.push("'unsafe-eval'");

  const connectSources = ["'self'", API_ORIGIN, TILE_ORIGIN];
  if (isDev) connectSources.push(wsOrigin);

  const directives = [
    "default-src 'self'",
    `script-src ${scriptSources.join(" ")}`,
    `style-src 'self' 'nonce-${nonce}'`,
    // MapLibre positions its canvas and controls with inline style mutations.
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data: blob: " + TILE_ORIGIN,
    "font-src 'self'",
    "worker-src 'self' blob:",
    `connect-src ${connectSources.join(" ")}`,
    "media-src 'none'",
    "object-src 'none'",
    "frame-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "manifest-src 'self'",
    ...(isDev ? [] : ["upgrade-insecure-requests"]),
  ];

  return directives.join("; ");
}

export function proxy(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const policy = buildPolicy(nonce, request);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", policy);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico|vendor/).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
