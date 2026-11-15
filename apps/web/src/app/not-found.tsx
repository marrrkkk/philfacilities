import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function NotFound() {
  return (
    <div className="container-page py-16">
      <div className="max-w-2xl">
        <p className="eyebrow rule-label text-[#0038a8]">404</p>
        <h1 className="mt-4 font-display text-4xl font-extrabold tracking-tight">
          No published record exists at this address.
        </h1>
        <p className="mt-3 font-sans text-base leading-relaxed text-[#5a5a58]">
          The facility, dataset, or page may not be published, may have moved, or may never have
          existed. A missing record is not evidence that the real-world facility does not exist.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/directory" className={cn(buttonVariants({ variant: "blue" }))}>
            Search the directory
          </Link>
          <Link href="/data" className={cn(buttonVariants({ variant: "outline" }))}>
            Browse datasets
          </Link>
        </div>
      </div>
    </div>
  );
}
