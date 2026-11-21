import type { Metadata } from "next";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { type QualitySummary, type SourceMonitoringOut, apiBaseUrl, getHealth, getQualitySummary, listMonitoring } from "@/lib/api";
import { formatDateTime, formatNumber, ingestionRunTone, titleCase } from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Status",
  description:
    "Measured API and ingestion status for the PhilFacilities demonstration environment.",
};

type Health = Awaited<ReturnType<typeof getHealth>>;

export default async function StatusPage() {
  let health: Health | null = null;
  let quality: QualitySummary | null = null;
  let monitoring: SourceMonitoringOut[] = [];
  let error: string | null = null;
  try {
    [health, quality, monitoring] = await Promise.all([
      getHealth(),
      getQualitySummary(),
      listMonitoring(),
    ]);
  } catch (caught) {
    error = caught instanceof Error ? caught.message : "Status could not be measured.";
  }

  return (
    <div className="container-page py-10">
      <Breadcrumbs items={[{ label: "Status" }]} />
      <p className="eyebrow rule-label text-[#0038a8]">Measured status</p>
      <h1 className="mt-4 font-display text-4xl font-extrabold tracking-tight sm:text-5xl">
        Service and data status
      </h1>
      <p className="mt-3 max-w-3xl font-sans text-base leading-relaxed text-[#5a5a58]">
        Only measured service probes and ingestion records are shown. A successful API response is
        not a claim that source data is complete or current.
      </p>

      {error ? (
        <Alert tone="danger" className="mt-6">
          <AlertTitle>Status could not be measured</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent>
            <p className="eyebrow text-[#5a5a58]">API</p>
            <p className="mt-2 flex items-center gap-2 font-display text-2xl font-bold">
              <span
                aria-hidden="true"
                className={`size-3 ${health?.status === "ok" ? "bg-[#1f6b3a]" : "bg-[#b42318]"}`}
              />
              {health ? titleCase(health.status) : "Unavailable"}
            </p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">
              {health ? `${health.service} v${health.version}` : "No health response"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="eyebrow text-[#5a5a58]">Database</p>
            <p className="mt-2 font-display text-2xl font-bold">
              {health ? titleCase(health.database) : "Unknown"}
            </p>
            <p className="mt-1 font-sans text-xs text-[#5a5a58]">
              Environment: {health?.environment ?? "Unknown"}
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
              {quality
                ? `${formatNumber(quality.published_facility_count)} published facilities`
                : "No quality summary"}
            </p>
          </CardContent>
        </Card>
      </div>

      {health?.status !== "ok" ? (
        <Alert tone="warning" className="mt-6">
          <AlertTitle>Degraded service</AlertTitle>
          <AlertDescription>
            The API or its database probe is not healthy. Directory and map results may be
            incomplete or unavailable. The text directory remains the primary fallback.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_20rem]">
        <section className="min-w-0">
          <h2 className="font-display text-2xl font-extrabold">Latest ingestion runs</h2>
          <p className="mt-2 font-sans text-sm text-[#5a5a58]">
            Status describes the last measured pipeline run. A published run can still contain
            warnings, and a failed run does not publish partial records.
          </p>
          <div className="mt-4 table-scroll min-w-0 border border-[#d1d8e6]" role="region" aria-label="Latest ingestion runs" tabIndex={0}>
            <table className="w-full min-w-[44rem] border-collapse text-left font-sans text-sm">
              <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                <tr>
                  <th className="border-b border-[#d1d8e6] p-3">Dataset</th>
                  <th className="border-b border-[#d1d8e6] p-3">Status</th>
                  <th className="border-b border-[#d1d8e6] p-3">Finished</th>
                  <th className="border-b border-[#d1d8e6] p-3">Report</th>
                </tr>
              </thead>
              <tbody>
                {(quality?.last_successful_runs ?? []).map((run) => (
                  <tr key={run.dataset}>
                    <td className="border-b border-[#d1d8e6] p-3 font-ui text-sm font-bold">
                      {run.dataset}
                    </td>
                    <td className="border-b border-[#d1d8e6] p-3">
                      <Badge tone={ingestionRunTone(run.status)}>
                        {titleCase(run.status)}
                      </Badge>
                    </td>
                    <td className="border-b border-[#d1d8e6] p-3 text-xs">
                      {formatDateTime(run.finished_at)}
                    </td>
                    <td className="border-b border-[#d1d8e6] p-3 font-mono text-[10px]">
                      <span className="block max-w-[18rem] truncate" title={run.report_path ?? undefined}>
                        {run.report_path}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!quality?.last_successful_runs?.length ? (
              <p className="p-4 font-sans text-sm text-[#5a5a58]">No ingestion runs are recorded.</p>
            ) : null}
          </div>
        </section>

        <section className="mt-10 min-w-0">
          <h2 className="font-display text-2xl font-extrabold">Source acquisition monitoring</h2>
          <p className="mt-2 font-sans text-sm text-[#5a5a58]">
            The latest append-only check per source. A blocked or failed check is preserved as
            evidence and does not remove the last published release.
          </p>
          <div className="mt-4 table-scroll min-w-0 border border-[#d1d8e6]" role="region" aria-label="Source acquisition monitoring" tabIndex={0}>
            <table className="w-full min-w-[46rem] border-collapse text-left font-sans text-sm">
              <thead className="bg-[#f4f7fc] font-ui text-xs uppercase tracking-wide text-[#5a5a58]">
                <tr>
                  <th className="border-b border-[#d1d8e6] p-3">Source</th>
                  <th className="border-b border-[#d1d8e6] p-3">Last check</th>
                  <th className="border-b border-[#d1d8e6] p-3">HTTP</th>
                  <th className="border-b border-[#d1d8e6] p-3">Last success</th>
                  <th className="border-b border-[#d1d8e6] p-3">Latest release</th>
                  <th className="border-b border-[#d1d8e6] p-3">Latest run</th>
                </tr>
              </thead>
              <tbody>
                {monitoring.map((item) => (
                  <tr key={item.dataset_id}>
                    <td className="border-b border-[#d1d8e6] p-3">
                      <span className="font-ui text-sm font-bold">{item.dataset_name}</span>
                      <span className="mt-1 block text-xs text-[#5a5a58]">{item.agency}</span>
                    </td>
                    <td className="border-b border-[#d1d8e6] p-3 text-xs">
                      {formatDateTime(item.last_checked_at)}
                      <span className="mt-1 block">
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
                      </span>
                    </td>
                    <td className="border-b border-[#d1d8e6] p-3 text-xs">
                      {item.http_status ?? "—"}
                    </td>
                    <td className="border-b border-[#d1d8e6] p-3 text-xs">
                      {formatDateTime(item.last_successful_at)}
                    </td>
                    <td className="border-b border-[#d1d8e6] p-3 text-xs">
                      {item.latest_release_label ?? "None"}
                      {item.latest_release_rows != null ? (
                        <span className="mt-1 block text-[#5a5a58]">
                          {formatNumber(item.latest_release_rows)} rows
                        </span>
                      ) : null}
                    </td>
                    <td className="border-b border-[#d1d8e6] p-3 text-xs">
                      {item.latest_run_status ? (
                        <>
                          <Badge
                            tone={ingestionRunTone(item.latest_run_status)}
                          >
                            {titleCase(item.latest_run_status)}
                          </Badge>
                          {item.latest_run_at ? (
                            <span className="mt-1 block text-[#5a5a58]">
                              {formatDateTime(item.latest_run_at)}
                            </span>
                          ) : null}
                          <span className="mt-1 block text-[#5a5a58]">
                            {item.latest_run_acceptance_rate != null
                              ? `${(item.latest_run_acceptance_rate * 100).toFixed(1)}% accepted`
                              : "Acceptance unknown"}
                            {" · "}
                            {item.latest_run_rejection_rate != null
                              ? `${(item.latest_run_rejection_rate * 100).toFixed(1)}% rejected`
                              : "Rejection unknown"}
                            {item.latest_run_duration_ms != null
                              ? ` · ${(item.latest_run_duration_ms / 1000).toFixed(1)} s`
                              : ""}
                          </span>
                        </>
                      ) : (
                        "No run recorded"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {monitoring.length === 0 ? (
              <p className="p-4 font-sans text-sm text-[#5a5a58]">No source checks are recorded.</p>
            ) : null}
          </div>
        </section>
        <aside className="min-w-0 space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Identity review</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 font-sans text-sm">
              <p className="font-display text-2xl font-bold">
                {formatNumber(quality?.match_candidates_by_status?.pending ?? 0)} pending
              </p>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-[#5a5a58]">
                {(["pending", "accepted", "rejected", "merged"] as const).map((status) => (
                  <div key={status} className="flex justify-between gap-2">
                    <dt>{titleCase(status)}</dt>
                    <dd className="font-mono">
                      {formatNumber(quality?.match_candidates_by_status?.[status] ?? 0)}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="text-xs leading-relaxed text-[#5a5a58]">
                Cross-source identity candidates are never merged automatically. Review actions
                are operator-only, and rejected pairs are retained so they are not re-queued for
                the same algorithm version.
              </p>
              <a
                href={`${apiBaseUrl()}/v1/quality/match-candidates?status=pending`}
                className="block font-ui font-bold text-[#0038a8] underline"
              >
                Pending candidates JSON
              </a>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Data caveats</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="list-disc space-y-2 pl-4 font-sans text-sm leading-relaxed text-[#5a5a58]">
                {(quality?.caveats ?? [
                  "No quality caveats are available because the summary could not be measured.",
                ]).map((caveat) => (
                  <li key={caveat}>{caveat}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Direct probes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-sans text-sm">
              <a
                href={`${apiBaseUrl()}/healthz`}
                className="block font-ui font-bold text-[#0038a8] underline"
              >
                API health JSON
              </a>
              <a
                href={`${apiBaseUrl()}/v1/quality/summary`}
                className="block font-ui font-bold text-[#0038a8] underline"
              >
                Quality summary JSON
              </a>
              <p className="text-xs text-[#5a5a58]">
                These probes are read-only and may be rate-limited.
              </p>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
