import Link from "next/link";
import {
  ArrowRight,
  BookOpenCheck,
  Database,
  Map as MapIcon,
  ShieldCheck,
  Stethoscope,
  School,
} from "lucide-react";

import { SearchForm } from "@/components/search-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type DatasetOut,
  type QualitySummary,
  type StatisticsOut,
  type TaxonomyResponse,
  getQualitySummary,
  getStatistics,
  getTaxonomy,
  listSources,
} from "@/lib/api";
import { formatDateTime, formatNumber, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

async function loadHomeData() {
  try {
    const [stats, quality, sources, taxonomy] = await Promise.all([
      getStatistics(),
      getQualitySummary(),
      listSources(),
      getTaxonomy().catch(() => null),
    ]);
    return {
      stats,
      quality,
      sources,
      taxonomy: taxonomy as TaxonomyResponse | null,
      error: null as string | null,
    };
  } catch (error) {
    return {
      stats: null as StatisticsOut | null,
      quality: null as QualitySummary | null,
      sources: [] as DatasetOut[],
      taxonomy: null as TaxonomyResponse | null,
      error: error instanceof Error ? error.message : "The API is unavailable.",
    };
  }
}

const entryPoints = [
  {
    href: "/directory?type=government_office",
    icon: Database,
    label: "Government offices",
    description: "Field offices, city and municipal halls, barangay halls, and post offices.",
  },
  {
    href: "/directory?type=school",
    icon: School,
    label: "Education",
    description: "Public and private schools, universities, and training sites.",
  },
  {
    href: "/directory?type=health_facility",
    icon: Stethoscope,
    label: "Healthcare",
    description: "Hospitals, rural health units, barangay health stations, clinics, and pharmacies.",
  },
  {
    href: "/directory?type=library",
    icon: BookOpenCheck,
    label: "Libraries",
    description: "Public libraries, reading centres, and congressional libraries.",
  },
  {
    href: "/directory?type=transport_facility",
    icon: ArrowRight,
    label: "Transport",
    description: "Rail stations, ports, and terminals.",
  },
  {
    href: "/map",
    icon: MapIcon,
    label: "Map",
    description: "Mapped facilities with precision-aware markers and a full text list.",
  },
];

export default async function HomePage() {
  const { stats, quality, sources, taxonomy, error } = await loadHomeData();
  const asOf = stats?.as_of ?? quality?.as_of;
  const categories = (taxonomy?.categories ?? [])
    .map((category) => ({
      ...category,
      count: stats?.by_category?.[category.code] ?? 0,
    }))
    .filter((category) => category.count > 0)
    .sort((a, b) => b.count - a.count);
  const publishedCategories = categories.length;
  const categoryLink = (category: (typeof categories)[number]) => (
    <Link
      key={category.code}
      href={`/directory?type=${category.code}`}
      className="flex items-baseline justify-between gap-4 bg-white p-4 no-underline hover:bg-[#eef4ff]"
    >
      <span className="font-ui text-sm font-bold text-[#0a0a0a]">{category.label}</span>
      <span className="font-display text-lg font-bold text-[#0038a8]">
        {formatNumber(category.count)}
      </span>
    </Link>
  );

  return (
    <>
      <section className="border-b border-[#d1d8e6] bg-[#f4f7fc]">
        <div className="container-page grid gap-10 py-14 lg:grid-cols-[1.15fr_0.85fr] lg:py-20">
          <div>
            <p className="eyebrow rule-label text-[#0038a8]">Open facility data</p>
            <h1 className="mt-5 max-w-3xl font-display text-4xl font-extrabold leading-[0.95] tracking-tight sm:text-5xl lg:text-6xl">
              Find a Philippine public facility.
              <span className="text-[#0038a8]"> See the source behind every record.</span>
            </h1>
            <p className="mt-6 max-w-2xl font-sans text-lg leading-relaxed text-[#3f434a]">
              PhilFacilities links published records to the agency release they came from. Search
              schools, health facilities, government offices, libraries, and more. Each record keeps
              its source ID, reference period, and location precision.
            </p>
            <div className="mt-8 max-w-2xl">
              <SearchForm categories={taxonomy?.categories ?? []} />
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/directory" className={cn(buttonVariants({ variant: "blue" }))}>
                Browse the directory
              </Link>
              <Link href="/data" className={cn(buttonVariants({ variant: "outline" }))}>
                View data sources
              </Link>
            </div>
          </div>

          <aside className="border border-[#c3ccdd] bg-white p-6 lg:self-start">
            <div className="flex items-center justify-between gap-3 border-b border-[#d1d8e6] pb-4">
              <div>
                <p className="eyebrow text-[#5a5a58]">Measured coverage</p>
                <p className="mt-1 font-display text-2xl font-bold">
                  {stats ? formatNumber(stats.published_facilities) : "Unavailable"} published records
                </p>
              </div>
              <Database aria-hidden="true" className="size-8 text-[#0038a8]" />
            </div>
            {error ? (
              <Alert tone="warning" className="mt-4">
                <AlertTitle>Live coverage is unavailable</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : (
              <dl className="mt-4 grid grid-cols-2 gap-px bg-[#d1d8e6]">
                {[
                  ["Education", stats?.schools],
                  ["Healthcare", stats?.health_facilities],
                  ["Published categories", publishedCategories],
                  ["With coordinates", stats?.with_coordinates],
                  ["Source releases", stats?.source_releases],
                ].map(([label, value], index, items) => (
                  <div
                    key={String(label)}
                    className={cn("bg-white p-4", index === items.length - 1 && "col-span-2")}
                  >
                    <dt className="font-ui text-[11px] font-bold uppercase tracking-wide text-[#5a5a58]">
                      {label}
                    </dt>
                    <dd className="mt-1 font-display text-2xl font-bold">
                      {typeof value === "number" ? formatNumber(value) : "—"}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            <p className="mt-4 border-t border-[#d1d8e6] pt-4 font-ui text-xs leading-relaxed text-[#5a5a58]">
              As of {asOf ? formatDateTime(asOf) : "an unknown time"}. Counts cover published
              records only, not every facility in the country.
            </p>
          </aside>
        </div>
      </section>

      <div className="container-page">
        {stats && stats.synthetic > 0 ? (
        <Alert tone="warning" className="mt-8">
          <AlertTitle>This environment includes labelled synthetic records</AlertTitle>
          <AlertDescription>
            {formatNumber(stats.synthetic)} generated records remain for testing, each marked{" "}
            <code className="font-bold">is_synthetic=true</code>. Do not cite them as official data.
          </AlertDescription>
        </Alert>
      ) : (
        <Alert tone="success" className="mt-8">
          <AlertTitle>Only rights-cleared records are published</AlertTitle>
          <AlertDescription>
            The directory and API show facilities whose source permits publication. Coverage varies
            by source.
          </AlertDescription>
        </Alert>
      )}
      </div>

      <section className="container-page py-14">
        <div className="grid gap-6 md:grid-cols-3">
          {entryPoints.map((entry) => (
            <Link key={entry.href} href={entry.href} className="group no-underline">
              <Card className="flex h-full flex-col transition-colors group-hover:border-[#0038a8]">
                <CardHeader className="flex flex-row items-start justify-between gap-4">
                  <CardTitle className="text-2xl">{entry.label}</CardTitle>
                  <entry.icon aria-hidden="true" className="size-6 text-[#0038a8]" />
                </CardHeader>
                <CardContent className="flex flex-1 flex-col">
                  <p className="font-sans text-sm leading-relaxed text-[#5a5a58]">
                    {entry.description}
                  </p>
                  <span className="mt-auto inline-flex items-center gap-1 pt-4 font-ui text-sm font-bold text-[#0038a8]">
                    View {entry.label.toLowerCase()}
                    <ArrowRight aria-hidden="true" className="size-4" />
                  </span>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      <section className="border-t border-[#d1d8e6] bg-[#f4f7fc]" aria-labelledby="coverage-heading">
        <div className="container-page py-12">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="eyebrow rule-label text-[#0038a8]">Measured coverage by category</p>
              <h2
                id="coverage-heading"
                className="mt-3 font-display text-3xl font-extrabold leading-tight"
              >
                Categories with published records
              </h2>
            </div>
            <p className="max-w-md font-sans text-sm leading-relaxed text-[#5a5a58]">
              Counts cover published records only. Categories without a release are omitted.
            </p>
          </div>
          <div className="mt-6 grid gap-px border border-[#d1d8e6] bg-[#d1d8e6] sm:grid-cols-2">
            {categories.map(categoryLink)}
            {categories.length === 0 ? (
              <p className="bg-white p-4 font-sans text-sm text-[#5a5a58]">
                Category counts are unavailable.
              </p>
            ) : null}
          </div>
        </div>
      </section>

      <section className="border-y border-[#d1d8e6] bg-white">
        <div className="container-page grid gap-10 py-14 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <p className="eyebrow rule-label text-[#0038a8]">Data semantics</p>
            <h2 className="mt-4 font-display text-3xl font-extrabold leading-tight sm:text-4xl">
              What every API record keeps.
            </h2>
            <p className="mt-4 font-sans text-base leading-relaxed text-[#5a5a58]">
              Published records carry their source identifiers, reference period, and location
              precision. Missing values stay null.
            </p>
            <ul className="mt-6 space-y-3 font-sans text-sm">
              {[
                ["Source values are preserved", "Original identifiers and values are never overwritten."],
                ["Null means unknown", "Missing capacity or status is never zero, false, or closed."],
                ["No auto-merges", "Ambiguous matches keep their evidence and review state."],
              ].map(([title, description]) => (
                <li key={title} className="flex gap-3">
                  <ShieldCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[#1f6b3a]" />
                  <span>
                    <strong className="font-ui text-sm">{title}.</strong>{" "}
                    <span className="text-[#5a5a58]">{description}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="eyebrow text-[#5a5a58]">Source register</p>
                <h2 className="mt-2 font-display text-2xl font-bold">Latest source releases</h2>
              </div>
              <Link href="/data" className="font-ui text-sm font-bold text-[#0038a8]">
                All datasets
              </Link>
            </div>
            <div className="mt-5 border border-[#d1d8e6]">
              {sources.slice(0, 4).map((source) => (
                <Link
                  key={source.id}
                  href={`/data/${source.slug}`}
                  className="flex flex-col gap-2 border-b border-[#d1d8e6] p-4 no-underline last:border-b-0 hover:bg-[#f4f7fc] sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <p className="font-ui text-sm font-bold text-[#0a0a0a]">{source.name}</p>
                    <p className="mt-1 font-sans text-xs text-[#5a5a58]">
                      {source.agency} ·{" "}
                      {source.latest_release?.label ??
                        source.latest_geography_release?.release_label ??
                        "No release"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge tone={source.is_synthetic ? "sun" : "muted"}>
                      {source.is_synthetic ? "Synthetic" : titleCase(source.redistribution_status)}
                    </Badge>
                    <span className="font-ui text-xs text-[#5a5a58]">
                      {source.latest_release?.row_count_parsed
                        ? `${formatNumber(source.latest_release.row_count_parsed)} rows`
                        : "—"}
                    </span>
                  </div>
                </Link>
              ))}
              {sources.length === 0 ? (
                <p className="p-4 font-sans text-sm text-[#5a5a58]">No source releases are available.</p>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="bg-[#0a0a0a] text-white">
        <div className="container-page grid gap-8 py-14 lg:grid-cols-[1fr_auto] lg:items-center">
          <div className="min-w-0">
            <p className="eyebrow rule-label text-[#fcd116]">For developers and researchers</p>
            <h2 className="mt-4 max-w-2xl font-display text-3xl font-extrabold leading-tight sm:text-4xl">
              Query the same records the directory uses.
            </h2>
            <p className="mt-3 max-w-2xl font-sans text-sm leading-relaxed text-white/70">
              The OpenAPI contract is the boundary for clients. It includes cursor pagination,
              source evidence, quality warnings, and dated releases.
            </p>
            <pre
              className="mt-5 overflow-x-auto border border-white/20 bg-white/5 p-4 font-mono text-xs leading-relaxed text-white/85 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
              role="region"
              aria-label="API endpoint examples"
              tabIndex={0}
            >
              <code>{`GET /v1/facilities?type=school&has_coordinates=true
GET /v1/facilities/{id}
GET /v1/facilities/{id}/history
GET /v1/quality/summary`}</code>
            </pre>
          </div>
          <div className="flex min-w-0 flex-col gap-3">
            <Link href="/api" className={cn(buttonVariants({ variant: "primary", size: "lg" }))}>
              API overview
            </Link>
            <Link
              href="/api#openapi"
              className={cn(buttonVariants({ variant: "headerGhost", size: "lg" }))}
            >
              OpenAPI document
            </Link>
            <Link
              href="/data"
              className="inline-flex items-center gap-1 font-ui text-sm font-bold text-[#fcd116] no-underline"
            >
              <BookOpenCheck aria-hidden="true" className="size-4" />
              Data dictionary and caveats
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
