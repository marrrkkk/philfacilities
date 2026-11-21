import type { Metadata } from "next";
import Link from "next/link";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type DatasetOut,
  type QualitySummary,
  getQualitySummary,
  listSources,
} from "@/lib/api";
import { formatDateTime, formatNumber, titleCase } from "@/lib/format";

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

  const synthetic = sources.filter((source) => source.is_synthetic).length;

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
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">{synthetic} synthetic fixtures</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="eyebrow text-[#5a5a58]">Published facilities</p>
            <p className="mt-2 font-display text-3xl font-extrabold">
              {formatNumber(quality?.published_facility_count)}
            </p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">
              {formatNumber(quality?.synthetic_facility_count)} labelled synthetic
            </p>
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

      {synthetic > 0 ? (
        <Alert tone="warning" className="mt-6">
          <AlertTitle>Labelled synthetic fixtures are present</AlertTitle>
          <AlertDescription>
            This environment also contains deterministic synthetic fixtures for parser and product
            testing. They are marked in the catalogue and on every generated facility record. The
            directory and API mix them with real, rights-cleared source records; check each
            facility&apos;s provenance and publication status before reuse.
          </AlertDescription>
        </Alert>
      ) : (
        <Alert tone="success" className="mt-6">
          <AlertTitle>No synthetic facilities are published</AlertTitle>
          <AlertDescription>
            All published facility records trace to a registered real source release whose
            redistribution status permits publication. Source-specific limits still apply; see the
            rights register below.
          </AlertDescription>
        </Alert>
      )}

      <div className="mt-10 overflow-hidden border border-[#d1d8e6]">
        <div className="table-scroll" role="region" aria-label="Dataset catalogue" tabIndex={0}>
          <table className="w-full min-w-[64rem] border-collapse text-left font-sans text-sm">
            <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
              <tr>
                <th className="border-b border-[#d1d8e6] p-3">Dataset</th>
                <th className="border-b border-[#d1d8e6] p-3">Agency</th>
                <th className="border-b border-[#d1d8e6] p-3">Latest release</th>
                <th className="border-b border-[#d1d8e6] p-3">Reference period</th>
                <th className="border-b border-[#d1d8e6] p-3">Rows parsed</th>
                <th className="border-b border-[#d1d8e6] p-3">Rights status</th>
                <th className="border-b border-[#d1d8e6] p-3">Publication</th>
                <th className="border-b border-[#d1d8e6] p-3">Labels</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <tr key={source.id} className="align-top hover:bg-[#f9fbff]">
                  <td className="border-b border-[#d1d8e6] p-3">
                    <Link href={`/data/${source.slug}`} className="font-ui text-sm font-bold text-[#0038a8] underline">
                      {source.name}
                    </Link>
                    <span className="mt-1 block text-xs text-[#5a5a58]">
                      {source.description ?? source.access_method ?? "No description"}
                    </span>
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3">
                    {source.agency}
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
                    {source.latest_release?.label ??
                      source.latest_geography_release?.release_label ??
                      "No release"}
                    <span className="mt-1 block text-[#5a5a58]">
                      {source.latest_release?.ingestion_status
                        ? titleCase(source.latest_release.ingestion_status)
                        : source.latest_geography_release
                          ? "Published (geography ledger)"
                          : "Unknown status"}
                    </span>
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
                      {source.license_identifier ?? "No license recorded"}
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

      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Publication rules</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 font-sans text-sm leading-relaxed text-[#5a5a58]">
            <p>
              A dataset is downloadable only when its publication gate permits the intended
              redistribution. The legacy <code>not_applicable</code> value applied to test fixtures
              with no third-party source-data rights; the working database publishes no such
              fixture.
            </p>
            <p>
              PhilHealth PDFs are published with attribution under PhilHealth&apos;s public reuse
              statement. DepEd EBEIS is a verified public government result set; the source registry
              approves institution-level publication with attribution, while school-head names remain
              private. A verified, publicly available dataset with no explicit prohibition may also be
              published under <code>publicly_available_verified</code> when only reviewed institutional
              fields are exposed. OSM/HOT extracts are published under ODbL with visible attribution
              and bbox-centre precision labels.
            </p>
            <p>
              Source publication date, reference period, retrieval time, and processing time are
              separate. Freshness is never implied by a single “updated” label.
            </p>
            <p>
              Missing values stay unknown. No missing bed count, coordinate, or operational status
              is converted to zero or inactive.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Rights and publication vocabulary</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3 font-sans text-sm">
              {[
                ["unknown", "No rights review has been completed. Do not republish."],
                ["review_required", "Access or reuse terms are unresolved; publication stays blocked."],
                ["approved_public_redistribution", "Terms permit public redistribution."],
                ["approved_with_attribution", "Publication is permitted with the recorded attribution."],
                [
                  "publicly_available_verified",
                  "Verified and publicly available with no explicit prohibition; reviewed institutional fields only.",
                ],
                ["restricted_non_redistributable", "Records may be retained internally but not republished."],
                ["denied", "The source has denied the intended reuse."],
                ["expired", "A previously recorded permission is no longer current."],
              ].map(([status, description]) => (
                <div key={status} className="grid gap-1 sm:grid-cols-[12rem_1fr] sm:gap-3">
                  <dt className="font-ui text-xs font-bold uppercase tracking-wide text-[#0a0a0a]">
                    {titleCase(status)}
                  </dt>
                  <dd className="text-[#5a5a58]">{description}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-4 border-t border-[#d1d8e6] pt-3 text-xs text-[#5a5a58]">
              Publication states are <code>blocked</code>, <code>internal_only</code>,{" "}
              <code>quarantined</code>, <code>approved</code>, and <code>published</code>. The public
              API returns only records whose source release is published.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
