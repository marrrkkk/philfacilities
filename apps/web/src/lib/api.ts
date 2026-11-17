import type { components } from "@philfacilities/api-client/schema";

export type FacilitySummary = components["schemas"]["FacilitySummary"];
export type FacilityDetail = components["schemas"]["FacilityDetail"];
export type FacilityListResponse = components["schemas"]["FacilityListResponse"];
export type DatasetOut = components["schemas"]["DatasetOut"];
export type QualitySummary = components["schemas"]["QualitySummary"];
export type StatisticsOut = components["schemas"]["StatisticsOut"];
export type AdministrativeUnitOut = components["schemas"]["AdministrativeUnitOut"];
export type ChangeListResponse = components["schemas"]["ChangeListResponse"];
export type FacilityQuality = components["schemas"]["FacilityQuality"];
export type SourceEvidence = components["schemas"]["SourceEvidence"];
export type AttributeAssertionOut = components["schemas"]["AttributeAssertionOut"];
export type SchoolProfileOut = components["schemas"]["SchoolProfileOut"];
export type HealthProfileOut = components["schemas"]["HealthProfileOut"];
export type AccreditationOut = components["schemas"]["AccreditationOut"];
export type EnrollmentObservationOut = components["schemas"]["EnrollmentObservationOut"];
export type ResourceObservationOut = components["schemas"]["ResourceObservationOut"];
export type LicenseOut = components["schemas"]["LicenseOut"];
export type SchoolDetailResponse = components["schemas"]["SchoolDetailResponse"];
export type HealthDetailResponse = components["schemas"]["HealthDetailResponse"];
export type ReleaseOut = components["schemas"]["ReleaseOut"];
export type QualityIssueOut = components["schemas"]["QualityIssueOut"];
export type SourceCheckOut = components["schemas"]["SourceCheckOut"];
export type SourceMonitoringOut = components["schemas"]["SourceMonitoringOut"];
export type TaxonomyResponse = components["schemas"]["TaxonomyResponse"];
export type TaxonomyTermOut = components["schemas"]["TaxonomyTermOut"];
export type ContactOut = components["schemas"]["ContactOut"];

const API_BASE =
  process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8010";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

function queryString(query?: Query): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const value = params.toString();
  return value ? `?${value}` : "";
}

export async function apiGet<T>(
  path: string,
  query?: Query,
  init?: { revalidate?: number; signal?: AbortSignal },
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}${queryString(query)}`, {
    headers: { Accept: "application/json" },
    next: init?.revalidate === undefined ? undefined : { revalidate: init.revalidate },
    cache: init?.revalidate === undefined ? "no-store" : undefined,
    signal: init?.signal,
  });
  if (!response.ok) {
    let code = "request_failed";
    let message = `The API returned ${response.status}.`;
    try {
      const body = (await response.json()) as { code?: string; message?: string };
      code = body.code ?? code;
      message = body.message ?? message;
    } catch {
      // Keep the generic message when the body is not JSON.
    }
    throw new ApiError(response.status, code, message);
  }
  return (await response.json()) as T;
}

export function listFacilities(
  query: Query,
  init?: { revalidate?: number; signal?: AbortSignal },
) {
  return apiGet<FacilityListResponse>("/v1/facilities", query, init);
}

export function getFacility(idOrSlug: string, init?: { revalidate?: number }) {
  return apiGet<FacilityDetail>(`/v1/facilities/${encodeURIComponent(idOrSlug)}`, undefined, init);
}

export function getFacilityChanges(idOrSlug: string, limit = 20) {
  return apiGet<ChangeListResponse>(
    `/v1/facilities/${encodeURIComponent(idOrSlug)}/history`,
    { limit },
  );
}

export function getFacilityAssertions(idOrSlug: string, limit = 100) {
  return apiGet<AttributeAssertionOut[]>(
    `/v1/facilities/${encodeURIComponent(idOrSlug)}/assertions`,
    { limit },
  );
}

export function getSchoolDetail(idOrSlug: string) {
  return apiGet<SchoolDetailResponse>(
    `/v1/schools/${encodeURIComponent(idOrSlug)}`,
    undefined,
    { revalidate: 30 },
  );
}

export function getHealthDetail(idOrSlug: string) {
  return apiGet<HealthDetailResponse>(
    `/v1/health-facilities/${encodeURIComponent(idOrSlug)}`,
    undefined,
    { revalidate: 30 },
  );
}

export function listSources() {
  return apiGet<DatasetOut[]>("/v1/sources", undefined, { revalidate: 60 });
}

export function getSource(slug: string) {
  return apiGet<DatasetOut>(`/v1/sources/${encodeURIComponent(slug)}`, undefined, {
    revalidate: 60,
  });
}

export function listSourceReleases(dataset: string, limit = 50) {
  return apiGet<ReleaseOut[]>(
    "/v1/source-releases",
    { dataset, limit },
    { revalidate: 60 },
  );
}

export function listMonitoring() {
  // Monitoring is append-only operational evidence; stale cached rows would
  // misreport the latest run on the status and source-register pages.
  return apiGet<SourceMonitoringOut[]>("/v1/monitoring");
}

export function listSourceChecks(limit = 50) {
  return apiGet<SourceCheckOut[]>("/v1/source-checks", { limit }, { revalidate: 60 });
}

export function getHealth() {
  return apiGet<{
    status: string;
    service: string;
    version: string;
    database: string;
    environment: string;
  }>("/healthz");
}

export function getQualitySummary() {
  return apiGet<QualitySummary>("/v1/quality/summary", undefined, { revalidate: 60 });
}

export function getStatistics() {
  return apiGet<StatisticsOut>("/v1/statistics", undefined, { revalidate: 60 });
}

export function listGeographies(query: Query) {
  return apiGet<AdministrativeUnitOut[]>("/v1/geographies", query, { revalidate: 300 });
}

/**
 * Read every page of an administrative-unit query. The API caps each response
 * at 500 rows, so callers must page when they need a complete lookup list.
 */
export async function listAllGeographies(
  query: Query,
  options: { pageSize?: number; maxRows?: number } = {},
) {
  const pageSize = options.pageSize ?? 500;
  const maxRows = options.maxRows ?? 5000;
  const rows: AdministrativeUnitOut[] = [];
  let offset = 0;
  while (rows.length < maxRows) {
    const page = await listGeographies({ ...query, limit: pageSize, offset });
    rows.push(...page);
    if (page.length < pageSize) break;
    offset += pageSize;
  }
  return rows;
}

export function getTaxonomy() {
  return apiGet<TaxonomyResponse>("/v1/taxonomy", undefined, { revalidate: 86400 });
}

export function listMapFacilities(bbox: string, limit = 300) {
  return apiGet<components["schemas"]["FacilityMapResponse"]>("/v1/facilities/within", {
    bbox,
    limit,
  });
}

export function apiBaseUrl() {
  return API_BASE;
}
