import type { Metadata } from "next";
import Link from "next/link";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type DatasetOut,
  type SourceMonitoringOut,
  listMonitoring,
  listSources,
} from "@/lib/api";
import { formatDateTime, titleCase } from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Source register",
  description:
    "Agency, dataset, release, access method, rights status, and monitoring state for every source in the PhilFacilities register.",
};

function rightsTone(status: string): "success" | "warning" | "danger" | "muted" {
  if (status === "approved_public_redistribution" || status === "approved_with_attribution") {
    return "success";
  }
  if (status === "restricted_non_redistributable" || status === "denied" || status === "expired") {
    return "danger";
  }
  if (status === "review_required" || status === "unknown") return "warning";
  return "muted";
}

function publicationTone(status: string): "success" | "warning" | "danger" | "muted" {
  if (status === "published") return "success";
  if (status === "approved") return "success";
  if (status === "internal_only") return "warning";
  if (status === "blocked" || status === "quarantined") return "danger";
  return "muted";
}

export default async function SourcesPage() {
  let sources: DatasetOut[] = [];
  let monitoring: SourceMonitoringOut[] = [];
  let error: string | null = null;
  let monitoringError: string | null = null;
  try {
    sources = await listSources();
  } catch (caught) {
    error = caught instanceof Error ? caught.message : "The source register is unavailable.";
  }
  try {
    monitoring = await listMonitoring();
  } catch (caught) {
    monitoringError =
      caught instanceof Error ? caught.message : "Source monitoring is unavailable.";
  }

  const byAgency = new Map<string, DatasetOut[]>();
  for (const source of sources) {
    const list = byAgency.get(source.agency) ?? [];
    list.push(source);
    byAgency.set(source.agency, list);
  }
  const published = sources.filter((source) => source.publication_status === "published").length;
  const restricted = sources.filter(
    (source) => source.redistribution_status === "restricted_non_redistributable",
  ).length;

  return (
    <div className="container-page py-10">
      <Breadcrumbs items={[{ label: "Sources" }]} />
      <p className="eyebrow rule-label text-[#0038a8]">Source register</p>
      <h1 className="mt-4 max-w-3xl font-display text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
        Agencies, releases, access paths, and rights.
      </h1>
      <p className="mt-4 max-w-3xl font-sans text-base leading-relaxed text-[#5a5a58]">
        This register is the human-readable view of the ingestion catalogue. Each release keeps its
        original acquisition method, terms review status, and redistribution decision. A source
        being publicly viewable does not make it freely redistributable.
      </p>

      {error ? (
        <Alert tone="danger" className="mt-6">
          <AlertTitle>The source register could not be loaded</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent>
            <p className="eyebrow text-[#5a5a58]">Registered datasets</p>
            <p className="mt-2 font-display text-3xl font-extrabold">{sources.length}</p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">
              {published} with a published release
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="eyebrow text-[#5a5a58]">Restricted sources</p>
            <p className="mt-2 font-display text-3xl font-extrabold">{restricted}</p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">
              Retained internally; never returned by the public API
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="eyebrow text-[#5a5a58]">Monitored sources</p>
            <p className="mt-2 font-display text-3xl font-extrabold">{monitoring.length}</p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">
              Latest measured check, not a promise of agency freshness
            </p>
          </CardContent>
        </Card>
      </div>

      <Alert tone="info" className="mt-6">
        <AlertTitle>Rights and access are separate</AlertTitle>
        <AlertDescription>
          Official PSA, DepEd, and DOH files still require human download, terms acceptance, or an
          institutional agreement. Where a source blocks automated access, the check is recorded as
          blocked and the previous successful release is retained. No access control, CAPTCHA, or
          agreement has been bypassed or accepted on the operator&apos;s behalf.
        </AlertDescription>
      </Alert>

      <section className="mt-10" aria-labelledby="monitoring-heading">
        <div className="flex flex-wrap items-end justify-between gap-2 border-b border-[#d1d8e6] pb-3">
          <div>
            <h2 id="monitoring-heading" className="font-display text-2xl font-extrabold">
              Acquisition monitoring
            </h2>
            <p className="mt-1 font-sans text-sm text-[#5a5a58]">
              Every row is the latest append-only source check. Blocked or failed checks never
              delete an earlier published release.
            </p>
          </div>
          <Link href="/status" className="font-ui text-sm font-bold text-[#0038a8]">
            Full status page
          </Link>
        </div>
        {monitoringError ? (
          <Alert tone="warning" className="mt-4">
            <AlertTitle>Monitoring could not be loaded</AlertTitle>
            <AlertDescription>{monitoringError}</AlertDescription>
          </Alert>
        ) : null}
        <div className="mt-4 table-scroll border border-[#d1d8e6]" role="region" aria-label="Source monitoring" tabIndex={0}>
          <table className="w-full min-w-[52rem] border-collapse text-left font-sans text-sm">
            <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
              <tr>
                <th className="border-b border-[#d1d8e6] p-3">Dataset</th>
                <th className="border-b border-[#d1d8e6] p-3">Access method</th>
                <th className="border-b border-[#d1d8e6] p-3">Check status</th>
                <th className="border-b border-[#d1d8e6] p-3">Last checked</th>
                <th className="border-b border-[#d1d8e6] p-3">Last successful acquisition</th>
                <th className="border-b border-[#d1d8e6] p-3">Latest published release</th>
                <th className="border-b border-[#d1d8e6] p-3">Warning</th>
              </tr>
            </thead>
            <tbody>
              {monitoring.map((item) => (
                <tr key={item.dataset_id} className="align-top">
                  <td className="border-b border-[#d1d8e6] p-3">
                    <Link href={`/data/${item.dataset_slug}`} className="font-ui font-bold text-[#0038a8] underline">
                      {item.dataset_name}
                    </Link>
                    <span className="mt-1 block text-xs text-[#5a5a58]">{item.agency}</span>
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3 text-xs">
                    {titleCase(item.access_method ?? "unknown")}
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3">
                    <Badge
                      tone={
                        item.check_status === "ok" || item.check_status === "not_modified"
                          ? "success"
                          : item.check_status
                            ? "warning"
                            : "muted"
                      }
                    >
                      {titleCase(item.check_status ?? "not checked")}
                    </Badge>
                    {item.http_status ? (
                      <span className="mt-1 block text-xs text-[#5a5a58]">HTTP {item.http_status}</span>
                    ) : null}
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3 text-xs">
                    {formatDateTime(item.last_checked_at)}
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3 text-xs">
                    {formatDateTime(item.last_successful_at)}
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3 text-xs">
                    {item.latest_release_label ?? "None"}
                    {item.latest_release_rows != null ? (
                      <span className="mt-1 block text-[#5a5a58]">
                        {item.latest_release_rows.toLocaleString()} rows ·{" "}
                        {formatDateTime(item.latest_release_at)}
                      </span>
                    ) : null}
                  </td>
                  <td className="border-b border-[#d1d8e6] p-3 text-xs text-[#5a5a58]">
                    {item.warning ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {monitoring.length === 0 && !monitoringError ? (
            <p className="p-4 font-sans text-sm text-[#5a5a58]">No source checks are recorded.</p>
          ) : null}
        </div>
      </section>

      <div className="mt-10 space-y-8">
        {[...byAgency.entries()].map(([agency, datasets]) => (
          <section key={agency} aria-labelledby={`agency-${datasets[0]?.agency_code}`}>
            <div className="flex flex-wrap items-end justify-between gap-2 border-b border-[#d1d8e6] pb-3">
              <div>
                <h2
                  id={`agency-${datasets[0]?.agency_code}`}
                  className="font-display text-2xl font-extrabold"
                >
                  {agency}
                </h2>
                <p className="mt-1 font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                  Code: {datasets[0]?.agency_code}
                </p>
              </div>
              <Badge tone={datasets.some((item) => item.is_synthetic) ? "sun" : "muted"}>
                {datasets.some((item) => item.is_synthetic) ? "Synthetic fixtures" : "Source datasets"}
              </Badge>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {datasets.map((source) => (
                <Card key={source.id}>
                  <CardHeader>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge tone={rightsTone(source.redistribution_status)}>
                        {titleCase(source.redistribution_status)}
                      </Badge>
                      <Badge tone={publicationTone(source.publication_status)}>
                        {titleCase(source.publication_status)}
                      </Badge>
                      <Badge tone="muted">{titleCase(source.access_method ?? "unknown")}</Badge>
                    </div>
                    <CardTitle className="mt-3 text-xl">
                      <Link href={`/data/${source.slug}`} className="hover:underline">
                        {source.name}
                      </Link>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 font-sans text-sm text-[#5a5a58]">
                    <p>{source.description ?? "No description recorded."}</p>
                    <p>
                      Latest release:{" "}
                      <strong className="text-[#0a0a0a]">
                        {source.latest_release?.label ??
                          source.latest_geography_release?.release_label ??
                          "None"}
                      </strong>
                    </p>
                    <p>
                      Retrieved:{" "}
                      {formatDateTime(
                        source.latest_release?.retrieved_at ??
                          source.latest_geography_release?.retrieved_at ??
                          null,
                      )}
                    </p>
                    <p>
                      Rights basis: {source.rights_basis ?? "No documented basis recorded"}
                    </p>
                    <p>
                      License: {source.license_identifier ?? "No license recorded"}
                    </p>
                    {source.attribution_text ? (
                      <p className="border-l-2 border-[#0038a8] pl-3">
                        Attribution: {source.attribution_text}
                      </p>
                    ) : null}
                    {source.personal_data_status ? (
                      <p>Personal data: {titleCase(source.personal_data_status)}</p>
                    ) : null}
                    {source.source_url ? (
                      <a
                        href={source.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-block font-ui text-sm font-bold text-[#0038a8] underline"
                      >
                        Official source page
                      </a>
                    ) : (
                      <p className="font-ui text-xs font-bold uppercase tracking-wide text-[#5a5a58]">
                        No public source URL recorded
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        ))}
        {sources.length === 0 && !error ? (
          <p className="border border-dashed border-[#b8c2d4] bg-[#f4f7fc] p-6 font-sans text-sm text-[#5a5a58]">
            No sources are registered.
          </p>
        ) : null}
      </div>
    </div>
  );
}
