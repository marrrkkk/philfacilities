import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Breadcrumbs({ items }: { items: { href?: string; label: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-6">
      <ol className="flex flex-wrap items-center gap-1 font-ui text-xs text-[#5a5a58]">
        <li>
          <Link href="/" className="text-[#5a5a58] hover:text-[#0038a8]">
            Home
          </Link>
        </li>
        {items.map((item) => (
          <li key={`${item.href ?? "current"}-${item.label}`} className="flex items-center gap-1">
            <ChevronRight aria-hidden="true" className="size-3 text-[#8a919e]" />
            {item.href ? (
              <Link href={item.href} className="text-[#5a5a58] hover:text-[#0038a8]">
                {item.label}
              </Link>
            ) : (
              <span aria-current="page" className="text-[#0a0a0a]">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function Pagination({
  nextCursor,
  basePath,
  params,
}: {
  nextCursor: string | null | undefined;
  basePath: string;
  params: Record<string, string | undefined>;
}) {
  if (!nextCursor) return null;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  query.set("cursor", nextCursor);
  return (
    <div className="mt-6 flex justify-center">
      <Link href={`${basePath}?${query.toString()}`} className={cn(buttonVariants({ variant: "outline" }))}>
        Load next page
      </Link>
    </div>
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="border border-dashed border-[#b8c2d4] bg-[#f4f7fc] p-8 text-center">
      <p className="font-display text-xl font-bold">{title}</p>
      <div className="mx-auto mt-2 max-w-xl font-sans text-sm leading-relaxed text-[#5a5a58]">
        {children}
      </div>
    </div>
  );
}
