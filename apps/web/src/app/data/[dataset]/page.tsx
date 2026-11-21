import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink } from "lucide-react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  apiBaseUrl,
  getSource,
  listSourceReleases,
  type DatasetOut,
  type ReleaseOut,
} from "@/lib/api";
import { coverageScopeLabel, formatDate, formatDateTime, formatNumber, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

type Params = Promise<{ dataset: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { dataset } = await params;
  try {
    const source = await getSource(dataset);
    return { title: source.name, description: source.description ?? `Source dataset ${source.name}.` };
  } catch {
    return { title: "Dataset not found" };
  }
}

export default async function DatasetPage({ params }: { params: Params }) {
  const { dataset } = await params;
  let source: DatasetOut;
  try {
    source = await getSource(dataset);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const releases: ReleaseOut[] = await listSourceReleases(source.slug).catch(() => []);

  return (
    <div className="container-page py-10">
      <Breadcrumbs
        items={[
          { href: "/data", label: "Data & Sources" },
          { label: source.name },
        ]}
      />
      <Link
        href="/data"
        className="inline-flex items-center gap-1 font-ui text-sm font-bold text-[#0038a8]"
      >
        <ArrowLeft aria-hidden="true" className="size-4" /> Back to catalogue
      </Link>

      <div className="mt-5 flex flex-wrap gap-1.5">
        {source.is_synthetic ? <Badge tone="sun">Synthetic fixture</Badge> : null}
        <Badge tone="muted">{source.agency_code}</Badge>
        <Badge tone="muted">{coverageScopeLabel(source.coverage_scope)}</Badge>
        <Badge tone={source.redistribution_status === "not_applicable" ? "muted" : "warning"}>
          {titleCase(source.redistribution_status)}
        </Badge>
        <Badge
          tone={
            source.publication_status === "published" || source.publication_status === "approved"
              ? "success"
              : source.publication_status === "internal_only"
                ? "warning"
                : "danger"
          }
        >
          {titleCase(source.publication_status)}
        </Badge>
      </div>
      <h1 className="mt-3 max-w-4xl font-display text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
        {source.name}
      </h1>
      <p className="mt-3 max-w-3xl font-sans text-base leading-relaxed text-[#5a5a58]">
        {source.description ?? "No description is recorded for this dataset."}
      </p>

      {source.is_synthetic ? (
        <Alert tone="warning" className="mt-6">
          <AlertTitle>Synthetic fixture — not an official release</AlertTitle>
          <AlertDescription>
            This dataset is generated to test source adapters, validation, provenance, and the
            public product. Its records, identifiers, and dates are invented. It carries no
            source-data rights and must not be represented as an agency publication.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-8">
          <Card>
            <CardHeader>
              <CardTitle>Dataset metadata</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
                {[
                  ["Agency", source.agency],
                  ["Coverage scope", coverageScopeLabel(source.coverage_scope)],
                  ["Coverage note", source.coverage_note ?? "Not recorded"],
                  ["Access method", titleCase(source.access_method ?? "unknown")],
                  ["Publication gate", titleCase(source.publication_gate_status ?? "unknown")],
                  ["Publication status", titleCase(source.publication_status)],
                  ["Rights basis", source.rights_basis ?? "Not recorded"],
                  ["Attribution", source.attribution_text ?? "Not recorded"],
                  ["Personal data", titleCase(source.personal_data_status ?? "unknown")],
                  ["Schema version", source.schema_version ?? "Not recorded"],
                  ["Update pattern", source.update_pattern ?? "Not recorded"],
                  ["License / rights", source.license_identifier ?? "Not recorded"],
                  ["Source URL", source.source_url],
                  ["Terms URL", source.terms_url],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <dt className="font-ui text-xs font-bold uppercase tracking-wide text-[#5a5a58]">
                      {label}
                    </dt>
                    <dd className="mt-1 break-words font-sans text-sm">
                      {value && String(value).startsWith("http") ? (
                        <a
                          href={String(value)}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-[#0038a8] underline"
                        >
                          Open link <ExternalLink aria-hidden="true" className="size-3" />
                        </a>
                      ) : (
                        (value ?? "—")
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>

          <section>
            <h2 className="font-display text-2xl font-extrabold">Release history</h2>
            <p className="mt-2 font-sans text-sm text-[#5a5a58]">
              Retrieval time is when PhilFacilities acquired the file. It is not the agency
              publication date or the reference period.
            </p>
            <div className="mt-4 table-scroll border border-[#d1d8e6]" role="region" aria-label="Release history" tabIndex={0}>
              <table className="w-full min-w-[52rem] border-collapse text-left font-sans text-sm">
                <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                  <tr>
                    <th className="border-b border-[#d1d8e6] p-3">Release</th>
                    <th className="border-b border-[#d1d8e6] p-3">Published</th>
                    <th className="border-b border-[#d1d8e6] p-3">Reference period</th>
                    <th className="border-b border-[#d1d8e6] p-3">Retrieved</th>
                    <th className="border-b border-[#d1d8e6] p-3">Rows</th>
                    <th className="border-b border-[#d1d8e6] p-3">Status</th>
                    <th className="border-b border-[#d1d8e6] p-3">SHA-256</th>
                  </tr>
                </thead>
                <tbody>
                  {source.latest_geography_release ? (
                    <tr>
                      <td className="border-b border-[#d1d8e6] p-3">
                        {source.latest_geography_release.release_label}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {formatDate(source.latest_geography_release.published_at)}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {formatDate(source.latest_geography_release.reference_date)}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {formatDateTime(source.latest_geography_release.retrieved_at)}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">PSGC units</td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        Published
                        <span className="mt-1 block text-[#5a5a58]">
                          Geography ledger
                        </span>
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 font-mono text-[10px]">
                        Not exposed
                      </td>
                    </tr>
                  ) : null}
                  {releases.map((release) => (
                    <tr key={release.id}>
                      <td className="border-b border-[#d1d8e6] p-3">{release.source_release_label}</td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {formatDateTime(release.source_published_at)}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {formatDate(release.reference_period_start)} –{" "}
                        {formatDate(release.reference_period_end)}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {formatDateTime(release.retrieved_at)}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3">
                        {release.row_count_parsed !== null
                          ? formatNumber(release.row_count_parsed)
                          : "Unknown"}
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 text-xs">
                        {titleCase(release.ingestion_status)}
                        <span className="mt-1 block text-[#5a5a58]">
                          Publication: {titleCase(release.publication_status)}
                        </span>
                        <span className="mt-1 block text-[#5a5a58]">
                          Terms: {titleCase(release.terms_review_status)}
                        </span>
                      </td>
                      <td className="border-b border-[#d1d8e6] p-3 font-mono text-[10px]">
                        <span className="block max-w-[10rem] truncate" title={release.sha256}>
                          {release.sha256}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {releases.length === 0 && !source.latest_geography_release ? (
                <p className="p-4 font-sans text-sm text-[#5a5a58]">
                  No release records are available for this dataset.
                </p>
              ) : null}
            </div>
          </section>

          <section>
            <h2 className="font-display text-2xl font-extrabold">Known limitations</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 font-sans text-sm leading-relaxed text-[#5a5a58]">
              <li>
                The catalogue describes processed source records, not the complete real-world
                facility universe.
              </li>
              <li>
                Missing fields remain unknown. A missing count is not zero, and registry presence
                is not proof of operation.
              </li>
              <li>
                Source agency publication dates, reference periods, retrieval times, and processing
                times are preserved separately.
              </li>
              <li>
                This dataset may not be redistributed beyond the recorded publication gate. Check
                the rights status before reusing source values.
              </li>
            </ul>
          </section>
        </div>

        <aside className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Access</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 font-sans text-sm">
              <p className="text-[#5a5a58]">
                Public API records and bulk exports include only publication-approved facilities.
              </p>
              <Link href="/api" className={cn(buttonVariants({ variant: "blue" }), "w-full")}>
                API documentation
              </Link>
              <a
                href={`${apiBaseUrl()}/v1/downloads/facilities.csv`}
                className={cn(buttonVariants({ variant: "outline" }), "w-full")}
              >
                Facility CSV (approved records)
              </a>
              <a
                href={`${apiBaseUrl()}/v1/downloads/facilities.parquet`}
                className={cn(buttonVariants({ variant: "outline" }), "w-full")}
              >
                Facility Parquet (approved records)
              </a>
              <a
                href={`${apiBaseUrl()}/openapi.json`}
                className="inline-flex items-center gap-1 font-ui text-xs font-bold text-[#0038a8]"
              >
                OpenAPI contract <ExternalLink aria-hidden="true" className="size-3" />
              </a>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Rights review</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-sans text-sm text-[#5a5a58]">
              <p>
                Status:{" "}
                <strong className="text-[#0a0a0a]">{titleCase(source.redistribution_status)}</strong>
              </p>
              <p>
                Gate:{" "}
                <strong className="text-[#0a0a0a]">
                  {titleCase(source.publication_gate_status ?? "unknown")}
                </strong>
              </p>
              <p>
                Basis:{" "}
                <strong className="text-[#0a0a0a]">
                  {source.rights_basis ?? "No documented rights basis"}
                </strong>
              </p>
              {source.attribution_text ? <p>Attribution: {source.attribution_text}</p> : null}
              <p>
                A code license does not grant rights to the underlying source data. This page records
                the dataset decision; it does not infer one.
              </p>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
