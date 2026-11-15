import Link from "next/link";
import { ArrowUpRight, MapPin } from "lucide-react";

import type { FacilitySummary } from "@/lib/api";
import {
  ACCESS_LABELS,
  formatDateTime,
  INCLUSION_CLASS_LABELS,
  PRECISION_LABELS,
  titleCase,
} from "@/lib/format";
import { Badge } from "@/components/ui/badge";

export function FacilityCard({ facility }: { facility: FacilitySummary }) {
  const place =
    facility.geography.barangay_name ??
    facility.geography.municipality_name ??
    facility.geography.province_name ??
    facility.geography.region_name;

  const latitude = facility.location.latitude;
  const longitude = facility.location.longitude;
  const categoryLabel =
    facility.facility_type === "school"
      ? "School"
      : facility.facility_type === "health_facility"
        ? "Health facility"
        : titleCase(facility.facility_type);
  const inclusionLabel =
    INCLUSION_CLASS_LABELS[facility.inclusion_class] ?? titleCase(facility.inclusion_class);
  const accessLabel = ACCESS_LABELS[facility.public_access_class];

  return (
    <article className="group border-b border-[#d1d8e6] bg-white">
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap gap-1.5">
            <Badge tone={facility.facility_type === "school" ? "default" : "outline"}>
              {categoryLabel}
            </Badge>
            {facility.facility_subtype ? (
              <Badge tone="muted">{facility.facility_subtype}</Badge>
            ) : null}
            <Badge tone={facility.inclusion_class === "GOVERNMENT_FACILITY" ? "default" : "outline"}>
              {inclusionLabel}
            </Badge>
            <Badge tone="muted">{titleCase(facility.ownership_type)}</Badge>
            {accessLabel ? <Badge tone="outline">{accessLabel}</Badge> : null}
            {facility.is_synthetic ? <Badge tone="sun">Synthetic demo</Badge> : null}
          </div>
          {(facility.functions ?? []).length > 0 ? (
            <p className="mb-2 font-ui text-xs font-semibold uppercase tracking-wide text-[#5a5a58]">
              {(facility.functions ?? []).map((value) => titleCase(value)).join(" · ")}
            </p>
          ) : null}
          <h3 className="font-display text-2xl font-bold leading-tight">
            <Link
              href={`/facilities/${facility.slug ?? facility.id}`}
              className="no-underline hover:underline hover:decoration-2 hover:underline-offset-4"
            >
              {facility.display_name}
            </Link>
          </h3>
          <div className="mt-3 grid gap-2 font-sans text-sm text-[#5a5a58]">
            <p className="flex items-start gap-2">
              <MapPin aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[#0038a8]" />
              <span>
                {place ? `${place} · ` : "Geography not linked · "}
                {latitude != null && longitude != null
                  ? `${PRECISION_LABELS[facility.location.precision] ?? facility.location.precision} (${latitude.toFixed(4)}, ${longitude.toFixed(4)})`
                  : "Coordinates unknown"}
              </span>
            </p>
            <p>
              Source records: {facility.source_count} · Canonical record updated{" "}
              {formatDateTime(facility.updated_at)}
            </p>
          </div>
        </div>
        <Link
          href={`/facilities/${facility.slug ?? facility.id}`}
          className="inline-flex shrink-0 items-center gap-1 font-ui text-sm font-bold text-[#0038a8] no-underline hover:underline"
          aria-label={`View profile for ${facility.display_name}`}
        >
          View profile
          <ArrowUpRight aria-hidden="true" className="size-4" />
        </Link>
      </div>
    </article>
  );
}
