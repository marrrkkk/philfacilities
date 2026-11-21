import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import type { TaxonomyTermOut } from "@/lib/api";

export function SearchForm({
  defaultQuery = "",
  defaultType = "",
  compact = false,
  categories = [],
  preserve = {},
}: {
  defaultQuery?: string;
  defaultType?: string;
  compact?: boolean;
  categories?: TaxonomyTermOut[];
  preserve?: Record<string, string | undefined>;
}) {
  return (
    <form
      action="/directory"
      method="get"
      role="search"
      className="border border-[#d1d8e6] bg-white p-3 shadow-[6px_6px_0_0_#fcd116]"
    >
      {compact && defaultType ? <input type="hidden" name="type" value={defaultType} /> : null}
      {Object.entries(preserve).map(([name, value]) =>
        value ? <input key={name} type="hidden" name={name} value={value} /> : null,
      )}
      <div className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor="site-search" className="sr-only">
          Search facilities by name, address, or source identifier
        </label>
        <Input
          id="site-search"
          name="q"
          type="search"
          defaultValue={defaultQuery}
          placeholder="Search facility, municipality, or source ID"
          className={compact ? "h-10" : "h-12 text-base"}
          autoComplete="off"
        />
        {!compact ? (
          <>
            <label htmlFor="site-search-type" className="sr-only">
              Facility category
            </label>
            <Select
              id="site-search-type"
              name="type"
              defaultValue={defaultType}
              className="h-12 sm:max-w-[14rem]"
            >
              <option value="">All categories</option>
              {categories.map((category) => (
                <option key={category.code} value={category.code}>
                  {category.label}
                </option>
              ))}
            </Select>
          </>
        ) : null}
        <Button type="submit" variant="blue" className="h-12 shrink-0 px-5">
          <Search aria-hidden="true" />
          Search
        </Button>
      </div>
      {!compact ? (
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-ui text-xs text-[#5a5a58]">
          <span>Try a facility name, barangay, or agency identifier.</span>
          <Link href="/directory" className="inline-flex items-center gap-1 text-[#0038a8]">
            Browse all records <ArrowRight aria-hidden="true" className="size-3" />
          </Link>
        </p>
      ) : null}
    </form>
  );
}
