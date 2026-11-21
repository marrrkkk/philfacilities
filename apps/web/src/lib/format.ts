const dateFormatter = new Intl.DateTimeFormat("en-PH", {
  year: "numeric",
  month: "short",
  day: "numeric",
  timeZone: "Asia/Manila",
});

const dateTimeFormatter = new Intl.DateTimeFormat("en-PH", {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Manila",
  timeZoneName: "short",
});

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dateFormatter.format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dateTimeFormatter.format(date);
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Unknown";
  return new Intl.NumberFormat("en-PH").format(value);
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "Unknown";
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export const PRECISION_LABELS: Record<string, string> = {
  gps_verified: "GPS verified",
  field_verified: "Field verified",
  source_gps: "Source GPS",
  map_geocoded: "Map geocoded",
  barangay_centroid: "Barangay centroid",
  unknown: "Unknown precision",
};

export const PRECISION_OPTIONS: Array<[string, string]> = [
  ["source_gps", PRECISION_LABELS.source_gps],
  ["gps_verified", PRECISION_LABELS.gps_verified],
  ["field_verified", PRECISION_LABELS.field_verified],
  ["map_geocoded", PRECISION_LABELS.map_geocoded],
  ["barangay_centroid", PRECISION_LABELS.barangay_centroid],
  ["unknown", PRECISION_LABELS.unknown],
];

export const COVERAGE_SCOPE_LABELS: Record<string, string> = {
  NATIONAL_OFFICIAL_INVENTORY: "National official inventory",
  NATIONAL_PARTIAL: "National, partial",
  REGIONAL: "Regional",
  PARTICIPATING_LGUS: "Participating LGUs",
  SELECTED_LGUS: "Selected LGUs",
  SINGLE_LGU: "Single LGU",
  DIRECTORY_SUBSET: "Directory subset",
  DISCOVERY_LAYER: "Discovery layer",
  UNKNOWN_COVERAGE: "Unknown coverage",
};

export function coverageScopeLabel(value: string | null | undefined): string {
  if (!value) return "Coverage not stated";
  return COVERAGE_SCOPE_LABELS[value] ?? titleCase(value);
}

export function ingestionRunTone(
  status: string | null | undefined,
): "success" | "warning" | "danger" | "muted" {
  if (status === "published" || status === "succeeded") return "success";
  if (status === "failed") return "danger";
  if (status === "skipped_duplicate") return "muted";
  return "warning";
}

export const PRECISION_DESCRIPTIONS: Record<string, string> = {
  gps_verified: "Coordinates were verified in the field by the source agency.",
  field_verified: "Coordinates were checked on the ground during source collection.",
  source_gps: "The source supplied GPS coordinates; independent verification is not implied.",
  map_geocoded: "The source geocoded an address; this is not a building-level survey.",
  barangay_centroid: "The point represents a barangay area, not a specific building.",
  unknown: "No usable coordinate precision is known. Do not treat any point as exact.",
};

export function isPreciseLocation(precision: string | null | undefined): boolean {
  return ["gps_verified", "field_verified", "source_gps", "map_geocoded"].includes(
    precision ?? "",
  );
}

export const INCLUSION_CLASS_LABELS: Record<string, string> = {
  GOVERNMENT_FACILITY: "Government facility",
  PRIVATE_PUBLIC_SERVICE_PROVIDER: "Private public-service provider",
  PUBLIC_ACCESS_VENUE: "Public-access venue",
  DISCOVERY_CANDIDATE: "Unclassified record",
};

export const ACCESS_LABELS: Record<string, string> = {
  PUBLIC_FREE: "Public, free",
  PUBLIC_PAID_OR_CONDITIONAL: "Public, paid or conditional",
  SERVICE_USERS_ONLY: "Service users only",
  APPOINTMENT_ONLY: "Appointment only",
  MEMBERS_STUDENTS_ONLY: "Members or students only",
  STAFF_ONLY: "Staff only",
  RESTRICTED: "Restricted",
  UNKNOWN: "Access unknown",
};
