import type { Metadata } from "next";
import Link from "next/link";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  type DatasetOut,
  type QualitySummary,
  getQualitySummary,
  listSources,
} from "@/lib/api";
import { formatDateTime, formatNumber, titleCase, coverageScopeLabel } from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Data & Sources",
  description:
    "Dataset catalogue, source agencies, release history, redistribution status, and measured data quality.",
};

export default async function DataPage() {
  let sources: DatasetOut[] = [];
  let quality: QualitySummary | null = null;
  let error: string | null = null;
  try {
    [sources, quality] = await Promise.all([listSources(), getQualitySummary()]);
  } catch (caught) {
    error = caught instanceof Error ? caught.message : "The source catalogue is unavailable.";
  }

  return (
    <div className="container-page py-10">
      <Breadcrumbs items={[{ label: "Data & Sources" }]} />
      <p className="eyebrow rule-label text-[#0038a8]">Data catalogue</p>
      <h1 className="mt-4 max-w-3xl font-display text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
        What is in the registry, where it came from, and what may be published.
      </h1>
      <p className="mt-4 max-w-3xl font-sans text-base leading-relaxed text-[#5a5a58]">
        Code is open source. Source data is not automatically open data. Each dataset carries its
        own agency, release, reference period, terms review status, and redistribution decision.
      </p>
      <div className="mt-4">
        <Link
          href="/data/dictionary"
          className="inline-flex h-10 items-center border border-[#0038a8] bg-white px-4 font-ui text-[15px] font-bold text-[#0038a8] no-underline"
        >
          Read the data dictionary
        </Link>
      </div>

      {error ? (
        <Alert tone="danger" className="mt-6">
          <AlertTitle>The catalogue could not be loaded</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent>
            <p className="eyebrow text-[#5a5a58]">Datasets</p>
            <p className="mt-2 font-display text-3xl font-extrabold">{formatNumber(sources.length)}</p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">Across registered agencies</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="eyebrow text-[#5a5a58]">Published facilities</p>
            <p className="mt-2 font-display text-3xl font-extrabold">
              {formatNumber(quality?.published_facility_count)}
            </p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">From published releases</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="eyebrow text-[#5a5a58]">As of</p>
            <p className="mt-2 font-ui text-sm font-bold">
              {quality ? formatDateTime(quality.as_of) : "Unknown"}
            </p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">
              Generated from measured API records, not editorial estimates.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="mt-10 overflow-hidden border border-[#d1d8e6]">
        <div className="table-scroll" role="region" aria-label="Dataset catalogue" tabIndex={0}>
          <table className="w-full min-w-[64rem] border-collapse text-left font-sans text-sm">
            <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
              <tr>
                <th className="border-b border-[#d1d8e6] p-3">Dataset</th>
                <th className="border-b border-[#d1d8e6] p-3">Agency</th>
                <th className="border-b border-[#d1d8e6] p-3">Latest release</th>
                <th className="border-b border-[#d1d8e6] p-3">Coverage</th>
                <th className="border-b border-[#d1d8e6] p-3">Reference period</th>
                <th className="border-b border-[#d1d8e6] p-3">Rows parsed</th>
                <th className="border-b border-[#d1d8e6] p-3">Rights status</th>
                <th className="border-b border-[#d1d8e6] p-3">Publication</th>
                <th className="border-b border-[#d1d8e6] p-3">Labels</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <tr key={source.id} className="h-32 align-top hover:bg-[#f9fbff]">
                  <td className="border-b border-[#d1d8e6] p-3">
                    <Link
                      href={`/data/${source.slug}`}
                      title={source.name}
                      className="line-clamp-2 font-ui text-sm font-bold text-[#0038a8] underline"
                    >
                      {source.name}
                    </Link>
                    <span className="mt-1 line-clamp-2 text-xs text-[#5a5a58]">
                      {source.description ?? source.access_method ?? "No description"}
                    </span>
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3">
                    <span className="line-clamp-2">{source.agency}</span>
                    <span className="mt-1 block text-xs text-[#5a5a58]">
                      {source.source_url ? (
                        <a href={source.source_url} className="underline" rel="noreferrer" target="_blank">
                          Official source
                        </a>
                      ) : (
                        "No public URL recorded"
                      )}
                    </span>
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3 text-xs">
                    <span className="line-clamp-2">
                      {source.latest_release?.label ??
                        source.latest_geography_release?.release_label ??
                        "No release"}
                    </span>
                    <span className="mt-1 block text-[#5a5a58]">
                      {source.latest_release?.ingestion_status
                        ? titleCase(source.latest_release.ingestion_status)
                        : source.latest_geography_release
                          ? "Published (geography ledger)"
                          : "Unknown status"}
                    </span>
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3 text-xs">
                    {coverageScopeLabel(source.coverage_scope)}
                    {source.coverage_note ? (
                      <span
                        title={source.coverage_note}
                        className="mt-1 line-clamp-3 max-w-[18rem] text-[#5a5a58]"
                      >
                        {source.coverage_note}
                      </span>
                    ) : null}
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3 text-xs">
                    {source.latest_release?.reference_period_start ??
                      source.latest_geography_release?.reference_date ??
                      "—"}{" "}
                    – {source.latest_release?.reference_period_end ?? "—"}
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3">
                    {source.latest_release?.row_count_parsed !== undefined &&
                    source.latest_release?.row_count_parsed !== null
                      ? formatNumber(source.latest_release.row_count_parsed)
                      : "Unknown"}
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3">
                    <Badge tone={source.redistribution_status === "not_applicable" ? "muted" : "warning"}>
                      {titleCase(source.redistribution_status)}
                    </Badge>
                    <span className="mt-1 block text-xs text-[#5a5a58]">
                      <span className="line-clamp-2">
                        {source.license_identifier ?? "No license recorded"}
                      </span>
                    </span>
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3">
                    <Badge
                      tone={
                        source.publication_status === "published" ||
                        source.publication_status === "approved"
                          ? "success"
                          : source.publication_status === "internal_only"
                            ? "warning"
                            : "danger"
                      }
                    >
                      {titleCase(source.publication_status)}
                    </Badge>
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3">
                    <div className="flex flex-wrap gap-1">
                      {source.is_synthetic ? <Badge tone="sun">Synthetic</Badge> : null}
                      <Badge tone="muted">{titleCase(source.access_method ?? "unknown")}</Badge>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {sources.length === 0 && !error ? (
          <p className="p-6 font-sans text-sm text-[#5a5a58]">No datasets are registered.</p>
        ) : null}
      </div>

      <section className="mt-10 grid border border-[#d1d8e6] bg-white lg:grid-cols-[0.85fr_1.15fr]">
        <div className="flex flex-col border-b border-[#d1d8e6] p-4 lg:border-b-0 lg:border-r">
          <h2 className="font-display text-xl font-bold">Publication rules</h2>
          <ul className="mt-3 space-y-2 font-sans text-sm text-[#5a5a58]">
            {[
              "Only releases that pass their publication gate reach the directory and API.",
              "Attribution and reuse terms stay with each dataset.",
              "Reference, publication, and retrieval dates are separate; missing values stay null.",
            ].map((rule) => (
              <li key={rule} className="flex gap-3">
                <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 bg-[#0038a8]" />
                <span>{rule}</span>
              </li>
            ))}
          </ul>
          <Link
            href="/data/dictionary"
            className="mt-auto pt-4 font-ui text-sm font-bold text-[#0038a8] no-underline"
          >
            Field definitions →
          </Link>
        </div>
        <div className="p-4">
          <h2 className="font-display text-xl font-bold">Rights states</h2>
          <dl className="mt-3 grid gap-x-6 gap-y-2 font-sans text-sm sm:grid-cols-2">
            {[
              ["unknown", "No rights review."],
              ["review_required", "Terms unresolved; blocked."],
              ["approved_public_redistribution", "Public redistribution allowed."],
              ["approved_with_attribution", "Allowed with recorded attribution."],
              ["publicly_available_verified", "Verified public data; reviewed fields only."],
              ["restricted_non_redistributable", "Internal use only."],
              ["denied", "Reuse denied by source."],
              ["expired", "Permission no longer current."],
            ].map(([status, description]) => (
              <div key={status}>
                <dt className="font-ui text-xs font-bold uppercase tracking-wide text-[#0a0a0a]">
                  {titleCase(status)}
                </dt>
                <dd className="mt-0.5 text-[#5a5a58]">{description}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </div>
  );
}
