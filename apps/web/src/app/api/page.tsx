import type { Metadata } from "next";
import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiBaseUrl } from "@/lib/api";

export const metadata: Metadata = {
  title: "API",
  description:
    "Public read API for source-linked Philippine facility records, provenance, geography, quality, and bulk exports.",
};

const families = [
  {
    title: "Facilities",
    endpoints: [
      "GET /v1/facilities",
      "GET /v1/facilities/{id-or-slug}",
      "GET /v1/facilities/{id-or-slug}/sources",
      "GET /v1/facilities/{id-or-slug}/history",
      "GET /v1/facilities/within?bbox=min_lon,min_lat,max_lon,max_lat",
      "GET /v1/facilities/nearby?lat=&lon=&radius_m=",
    ],
  },
  {
    title: "Schools and health",
    endpoints: [
      "GET /v1/schools",
      "GET /v1/schools/{id-or-slug}",
      "GET /v1/schools/{id-or-slug}/enrollment",
      "GET /v1/schools/{id-or-slug}/resources",
      "GET /v1/health-facilities",
      "GET /v1/health-facilities/{id-or-slug}",
      "GET /v1/health-facilities/{id-or-slug}/licenses",
      "GET /v1/health-facilities/{id-or-slug}/accreditations",
    ],
  },
  {
    title: "Geography",
    endpoints: [
      "GET /v1/geographies?level=region",
      "GET /v1/geographies/{psgc_code}",
      "GET /v1/geographies/{psgc_code}/facilities",
      "GET /v1/geography-releases",
      "GET /v1/geography-crosswalk?from_release=&to_release=",
    ],
  },
  {
    title: "Sources, quality, history",
    endpoints: [
      "GET /v1/sources",
      "GET /v1/sources/{slug}",
      "GET /v1/source-releases?dataset=",
      "GET /v1/quality/summary",
      "GET /v1/quality/issues",
      "GET /v1/quality/match-candidates?status=pending",
      "GET /v1/quality/match-candidates/{candidate_id}",
      "GET /v1/changes?since=",
      "GET /v1/statistics",
    ],
  },
  {
    title: "Downloads",
    endpoints: [
      "GET /v1/downloads/facilities.csv",
      "GET /v1/downloads/facilities.parquet",
      "GET /v1/downloads/schools.csv",
      "GET /v1/downloads/health-facilities.csv",
    ],
  },
];

export default function ApiPage() {
  const base = apiBaseUrl();

  return (
    <div className="container-page py-10">
      <Breadcrumbs items={[{ label: "API" }]} />
      <p className="eyebrow rule-label text-[#0038a8]">Public read contract</p>
      <h1 className="mt-4 max-w-3xl font-display text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
        The data and API outlive this interface.
      </h1>
      <p className="mt-4 max-w-3xl font-sans text-base leading-relaxed text-[#5a5a58]">
        The OpenAPI document is the contract. The web directory, map, and profiles consume the same
        read API that researchers and other applications can call. Every response keeps source
        evidence, reference periods, and quality warnings attached.
      </p>

      <div className="mt-6 flex flex-wrap gap-3">
        <a
          href={`${base}/docs`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-10 items-center gap-2 border border-[#0038a8] bg-[#0038a8] px-4 font-ui text-[15px] font-bold text-white no-underline"
        >
          Interactive docs <ExternalLink aria-hidden="true" className="size-4" />
        </a>
        <a
          href={`${base}/openapi.json`}
          target="_blank"
          rel="noreferrer"
          id="openapi"
          className="inline-flex h-10 items-center gap-2 border border-[#d1d8e6] bg-white px-4 font-ui text-[15px] font-bold text-[#0a0a0a] no-underline"
        >
          OpenAPI JSON <ExternalLink aria-hidden="true" className="size-4" />
        </a>
        <Link
          href="/data/dictionary"
          className="inline-flex h-10 items-center gap-2 border border-[#d1d8e6] bg-white px-4 font-ui text-[15px] font-bold text-[#0a0a0a] no-underline"
        >
          Data dictionary
        </Link>
      </div>

      <Alert tone="info" className="mt-6">
        <AlertTitle>No authentication for public reads</AlertTitle>
        <AlertDescription>
          This release exposes read-only endpoints without a key, behind a transparent rate limit.
          Do not use it to attempt to infer unpublished, private, or personal information. Published
          records trace to a registered source release; labelled synthetic fixtures remain marked{" "}
          <code>is_synthetic=true</code>.
        </AlertDescription>
      </Alert>

      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Base URL</CardTitle>
          </CardHeader>
          <CardContent>
            <code className="block break-all border border-[#d1d8e6] bg-[#f4f7fc] p-3 font-mono text-sm">
              {base}/v1
            </code>
            <dl className="mt-4 space-y-3 font-sans text-sm">
              <div>
                <dt className="font-ui text-xs font-bold uppercase tracking-wide text-[#5a5a58]">
                  Pagination
                </dt>
                <dd className="text-[#5a5a58]">
                  Cursor-based for facility lists: opaque <code>cursor</code>,{" "}
                  <code>next_cursor</code>, and <code>has_more</code>. Stable ordering by updated
                  time and canonical ID.
                </dd>
              </div>
              <div>
                <dt className="font-ui text-xs font-bold uppercase tracking-wide text-[#5a5a58]">
                  Errors
                </dt>
                <dd className="text-[#5a5a58]">
                  Consistent JSON with <code>code</code>, <code>message</code>, optional{" "}
                  <code>details</code>, and <code>request_id</code>. No SQL, file paths, credentials,
                  or stack traces are returned.
                </dd>
              </div>
              <div>
                <dt className="font-ui text-xs font-bold uppercase tracking-wide text-[#5a5a58]">
                  Caching and CORS
                </dt>
                <dd className="text-[#5a5a58]">
                  Conditional JSON responses expose ETag and request timing. CORS is restricted to
                  configured web origins; credentials are not enabled.
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <Card id="examples" className="min-w-0">
          <CardHeader>
            <CardTitle>Request examples</CardTitle>
          </CardHeader>
          <CardContent>
            <pre
              className="overflow-x-auto border border-[#d1d8e6] bg-[#0a0a0a] p-4 font-mono text-xs leading-relaxed text-white/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0038a8]"
              role="region"
              aria-label="API request examples"
              tabIndex={0}
            >
              <code>{`# Search schools with coordinates
curl "${base}/v1/facilities?type=school&has_coordinates=true&limit=5"

# One facility, by canonical slug or UUID from a search response
curl "${base}/v1/facilities/{id}"

# Facility provenance and canonical history
curl "${base}/v1/facilities/{id}/sources"
curl "${base}/v1/facilities/{id}/history"

# Bounded map query (lon/lat order)
curl "${base}/v1/facilities/within?bbox=120.9,14.5,121.1,14.7"

# Measured quality summary
curl "${base}/v1/quality/summary"`}</code>
            </pre>
            <p className="mt-3 font-sans text-xs leading-relaxed text-[#5a5a58]">
              Bounding boxes and nearby radii are capped server-side. Map clients must debounce
              viewport changes and keep a text result list available.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="mt-10">
        <h2 className="font-display text-2xl font-extrabold">Endpoint families</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {families.map((family) => (
            <Card key={family.title} className="min-w-0">
              <CardHeader>
                <CardTitle className="text-xl">{family.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5 font-mono text-xs leading-relaxed">
                  {family.endpoints.map((endpoint) => (
                    <li key={endpoint} className="break-all">
                      {endpoint}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <section className="mt-10 border-t border-[#d1d8e6] pt-8">
        <h2 className="font-display text-2xl font-extrabold">Data rights are separate from code rights</h2>
        <p className="mt-3 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
          The API software and schema are Apache-2.0 licensed. That license does not grant rights to
          republish agency source data. Download endpoints expose only publication-approved records;
          each dataset page records its redistribution status and terms review.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge tone="muted">Apache-2.0 code</Badge>
          <Badge tone="warning">Source data rights vary</Badge>
          <Badge tone="success">Real sources attributed</Badge>
          <Badge tone="sun">Synthetic records labelled</Badge>
        </div>
      </section>
    </div>
  );
}
