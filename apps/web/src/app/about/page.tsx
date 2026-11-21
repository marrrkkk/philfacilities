import type { Metadata } from "next";
import Link from "next/link";
import { GitPullRequest, Scale, ShieldCheck } from "lucide-react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "About",
  description:
    "PhilFacilities mission, product principles, source governance, licensing boundaries, and correction workflow.",
};

const principles = [
  {
    title: "Source truth is preserved",
    body: "Original source files and source values are never overwritten. Canonical records link back to the exact release and row or page reference.",
  },
  {
    title: "Every important value is attributable",
    body: "Agency, dataset, release, retrieval time, reference period, and source record identifier travel with the value.",
  },
  {
    title: "Unknown is not false",
    body: "Missing operational status, coordinates, capacity, or services remain unknown. They are never converted to zero, false, or inactive.",
  },
  {
    title: "No silent merges",
    body: "Ambiguous matches require review. Automatic links are limited to stable agency identifiers; uncertain candidates retain their evidence.",
  },
  {
    title: "No misleading freshness",
    body: "Source publication date, reference period, retrieval time, processing time, and canonical-record update time are distinct.",
  },
  {
    title: "Code rights are not data rights",
    body: "The repository is open source. Each source dataset has its own redistribution decision, recorded before any download is exposed.",
  },
  {
    title: "The API outlives the UI",
    body: "Data, schema, documentation, and API remain independently useful to researchers, civic technologists, and public agencies.",
  },
  {
    title: "A map is not the whole product",
    body: "Every mapped result is also discoverable as text. Low-precision coordinates are not presented as building pins.",
  },
];

export default function AboutPage() {
  return (
    <div className="container-page py-10">
      <Breadcrumbs items={[{ label: "About" }]} />
      <p className="eyebrow rule-label text-[#0038a8]">About the project</p>
      <h1 className="mt-4 max-w-4xl font-display text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
        Public data infrastructure should show its work.
      </h1>
      <p className="mt-4 max-w-3xl font-sans text-lg leading-relaxed text-[#3f434a]">
        PhilFacilities is an independent registry of Philippine schools and health facilities built
        around source evidence, versioned geography, and measured data quality. The product is a
        directory and map; the durable output is the dataset, provenance model, and public API.
      </p>

      <Alert tone="info" className="mt-6">
        <AlertTitle>Partial real-data environment</AlertTitle>
        <AlertDescription>
          Published records currently come from PhilHealth accredited-provider PDFs, BetterGov&apos;s
          PSGC snapshot, HOT/OSM facility extracts, and DepEd EBEIS institution-level records,
          with documented rights and attribution. The PSA PSGC workbook, DepEd machine-readable
          files, and DOH NHFR/HFSRB files remain blocked or unacquired. Labelled synthetic fixtures
          may remain for testing and are never official government records.
        </AlertDescription>
      </Alert>

      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-10">
          <section>
            <h2 className="font-display text-2xl font-extrabold">What the product covers</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {[
                ["Schools", "OSM-mapped schools and DepEd EBEIS institution-level records. School-head names and other personal fields stay private."],
                ["Health facilities", "PhilHealth accredited providers with dated package evidence, plus OSM-mapped health features and precision labels."],
                ["Geography", "BetterGov's Q2 2024 PSGC snapshot, versioned separately from agency releases and never treated as the latest PSA release."],
                ["Provenance", "Source record IDs, release labels, reference periods, retrieval and processing times, match evidence, and rights status."],
                ["Quality", "Coordinate precision, missing-field warnings, schema-drift failures, duplicate-row handling, and publication gates."],
              ].map(([title, body]) => (
                <Card key={title}>
                  <CardContent>
                    <p className="font-display text-xl font-bold">{title}</p>
                    <p className="mt-2 font-sans text-sm leading-relaxed text-[#5a5a58]">{body}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>

          <section>
            <h2 className="font-display text-2xl font-extrabold">Non-negotiable principles</h2>
            <ol className="mt-4 grid gap-4 sm:grid-cols-2">
              {principles.map((principle, index) => (
                <li key={principle.title} className="border-l-2 border-[#fcd116] pl-4">
                  <p className="font-ui text-sm font-bold">
                    {String(index + 1).padStart(2, "0")}. {principle.title}
                  </p>
                  <p className="mt-1 font-sans text-sm leading-relaxed text-[#5a5a58]">
                    {principle.body}
                  </p>
                </li>
              ))}
            </ol>
          </section>

          <section id="corrections">
            <h2 className="font-display text-2xl font-extrabold">Report a correction</h2>
            <p className="mt-3 max-w-3xl font-sans text-sm leading-relaxed text-[#5a5a58]">
              A correction should identify the canonical facility, the field at issue, the source
              release you are relying on, and (where possible) a public official document that
              supports the change. Do not send personal information about facility staff or
              learners.
            </p>
            <div className="mt-4 border border-dashed border-[#b8c2d4] bg-[#f4f7fc] p-5 font-sans text-sm text-[#5a5a58]">
              <p className="font-ui font-bold text-[#0a0a0a]">Correction intake is not yet public.</p>
              <p className="mt-2">
                The repository’s reviewed correction workflow is planned but not enabled. Until it
                is, do not treat this demonstration site as a channel for official corrections. No
                contact address is invented here.
              </p>
            </div>
          </section>

          <section id="licensing">
            <h2 className="font-display text-2xl font-extrabold">Licensing and reuse</h2>
            <div className="mt-4 space-y-4 font-sans text-sm leading-relaxed text-[#5a5a58]">
              <p className="flex gap-3">
                <Scale aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[#0038a8]" />
                <span>
                  <strong className="font-ui text-[#0a0a0a]">Code:</strong> Apache-2.0. You may
                  reuse, modify, and distribute the implementation under that license.
                </span>
              </p>
              <p className="flex gap-3">
                <ShieldCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[#0038a8]" />
                <span>
                  <strong className="font-ui text-[#0a0a0a]">Data:</strong> rights vary by source
                  and release. A public API or download endpoint is not a blanket open-data
                  license. Check the dataset’s redistribution status and terms review before reuse.
                </span>
              </p>
              <p className="flex gap-3">
                <GitPullRequest aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[#0038a8]" />
                <span>
                  <strong className="font-ui text-[#0a0a0a]">Contributions:</strong> source adapters
                  must preserve raw payloads, record parser/schema versions, validate before
                  publishing, and include fixture-based tests.
                </span>
              </p>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge tone="muted">Apache-2.0 code</Badge>
              <Badge tone="warning">No blanket data license</Badge>
              <Badge tone="success">Real sources attributed</Badge>
              <Badge tone="sun">Synthetic data labelled</Badge>
            </div>
          </section>

          <section>
            <h2 className="font-display text-2xl font-extrabold">What is deliberately not claimed</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 font-sans text-sm leading-relaxed text-[#5a5a58]">
              <li>Completeness of the national facility universe.</li>
              <li>Real-time operational availability of any school or health facility.</li>
              <li>Building-level precision for centroid or geocoded coordinates.</li>
              <li>That similar names from different agencies describe the same real-world site.</li>
              <li>That a source being publicly accessible means it can be republished.</li>
            </ul>
          </section>
        </div>

        <aside className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Architecture</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-sans text-sm text-[#5a5a58]">
              <p>Next.js App Router + Tailwind + MapLibre for the web client.</p>
              <p>FastAPI + Pydantic + SQLAlchemy for the public read API.</p>
              <p>PostgreSQL + PostGIS for canonical records and spatial queries.</p>
              <p>Python ingestion workers with source-specific adapters and immutable raw storage.</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Project status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-sans text-sm text-[#5a5a58]">
              <p>Planning baseline implemented as a working MVP in this environment.</p>
              <p>Real-source publication is blocked pending terms review and acquisition.</p>
              <p>
                <Link href="/status" className="font-ui font-bold text-[#0038a8] underline">
                  View measured service status
                </Link>
              </p>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
