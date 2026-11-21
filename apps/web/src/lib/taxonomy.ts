import type { TaxonomyResponse, TaxonomyTermOut } from "@/lib/api";
import { titleCase } from "@/lib/format";

export type TermLabels = Record<string, string>;

export function termLabels(terms: TaxonomyTermOut[] | undefined): TermLabels {
  return Object.fromEntries((terms ?? []).map((term) => [term.code, term.label]));
}

export function labelFor(labels: TermLabels, code: string | null | undefined, fallback?: string) {
  if (!code) return fallback ?? "Unknown";
  return labels[code] ?? fallback ?? titleCase(code);
}

export function categoryLabels(taxonomy: TaxonomyResponse | null | undefined): TermLabels {
  return termLabels(taxonomy?.categories);
}

export type SubtypeOption = TaxonomyTermOut & {
  categoryCode: string;
  categoryLabel: string;
};

export function subtypeOptions(
  taxonomy: TaxonomyResponse | null | undefined,
): SubtypeOption[] {
  return (taxonomy?.categories ?? []).flatMap((category) =>
    (category.subtypes ?? []).map((subtype) => ({
      ...subtype,
      categoryCode: category.code,
      categoryLabel: category.label,
    })),
  );
}
