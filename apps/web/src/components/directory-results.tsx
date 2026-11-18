"use client";

import Link from "next/link";

import { EmptyState, Pagination } from "@/components/breadcrumbs";
import {
  DirectorySearchBar,
  useDirectorySearch,
  type DirectoryFilterParams,
} from "@/components/directory-search";
import { FacilityCard } from "@/components/facility-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { formatNumber } from "@/lib/format";
import { queryString } from "@/lib/query";
import { cn } from "@/lib/utils";

export function DirectoryResults({
  filterParams,
  activeFilters,
}: {
  filterParams: DirectoryFilterParams;
  activeFilters: string[];
}) {
  const { query, result, error, isSearching } = useDirectorySearch();
  const currentParams = { ...filterParams, q: query || undefined };
  const mapParams = {
    ...currentParams,
    // The map only shows records with coordinates, so a "no coordinates"
    // directory result cannot produce a useful mapped subset.
    has_coordinates: filterParams.has_coordinates === "true" ? "true" : undefined,
  };
  const filters = query ? [`Search: ${query}`, ...activeFilters] : activeFilters;

  return (
    <>
      <div className="flex flex-col gap-2 border-b border-[#d1d8e6] pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow text-[#0038a8]">Facility directory</p>
          <h1 className="mt-2 font-display text-4xl font-extrabold tracking-tight">
            {result ? formatNumber(result.total) : "—"} matching records
            {isSearching ? (
              <span aria-hidden="true" className="ml-3 font-sans text-sm font-normal text-[#5a5a58]">
                Searching…
              </span>
            ) : null}
          </h1>
          <p className="mt-2 font-sans text-sm text-[#5a5a58]">
            Search across canonical names, localities, and agency source identifiers. Every
            result is also available as a text profile.
          </p>
        </div>
        <Link
          href={`/map${queryString(mapParams)}`}
          className={cn(buttonVariants({ variant: "outline" }))}
        >
          View on map
        </Link>
      </div>

      <div className="mt-5">
        <DirectorySearchBar />
      </div>

      {filters.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Active filters">
          <span className="font-ui text-xs font-bold uppercase tracking-wide text-[#5a5a58]">
            Active:
          </span>
          {filters.map((label) => (
            <Badge key={label} tone="muted" className="normal-case tracking-normal">
              {label}
            </Badge>
          ))}
        </div>
      ) : null}

      <p role="status" aria-live="polite" className="sr-only">
        {isSearching
          ? "Updating directory results."
          : result
            ? `Directory updated: ${formatNumber(result.total)} records.`
            : ""}
      </p>

      <div className="mt-6" aria-busy={isSearching}>
        {error ? (
          <Alert tone="danger">
            <AlertTitle>The directory could not be loaded</AlertTitle>
            <AlertDescription>
              {error}. Check that the API is running at the configured API base URL, then try
              again.
            </AlertDescription>
          </Alert>
        ) : result && result.items.length > 0 ? (
          <>
            <div className="border-t border-[#d1d8e6]">
              {result.items.map((facility) => (
                <FacilityCard key={facility.id} facility={facility} />
              ))}
            </div>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p className="font-sans text-xs text-[#5a5a58]">
                Showing {formatNumber(result.items.length)} of {formatNumber(result.total)}
                {result.has_more ? " · more pages available" : " · end of results"}
              </p>
              <Badge tone="muted">{result.limit} per page · cursor pagination</Badge>
            </div>
            <Pagination
              nextCursor={result.next_cursor}
              basePath="/directory"
              params={currentParams}
            />
          </>
        ) : (
          <EmptyState title="No published records match these filters">
            Try a broader search, clear the ownership or precision filter, or{" "}
            <Link href="/directory" className="text-[#0038a8] underline">
              reset the directory
            </Link>
            . A missing result is not evidence that a facility does not exist.
          </EmptyState>
        )}
      </div>
    </>
  );
}
