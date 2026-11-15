"use client";

import Link from "next/link";
import { useEffect } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="container-page py-16">
      <div className="max-w-2xl">
        <p className="eyebrow rule-label text-[#b42318]">Page error</p>
        <h1 className="mt-4 font-display text-4xl font-extrabold tracking-tight">
          This page could not be completed.
        </h1>
        <p className="mt-3 font-sans text-base leading-relaxed text-[#5a5a58]">
          The failure was recorded without exposing internal details. You can retry this request or
          return to the text directory, which remains the primary fallback.
        </p>
        {error.digest ? (
          <p className="mt-2 font-mono text-xs text-[#5a5a58]">Reference: {error.digest}</p>
        ) : null}
        <div className="mt-6 flex flex-wrap gap-3">
          <button type="button" onClick={reset} className={cn(buttonVariants({ variant: "blue" }))}>
            Try again
          </button>
          <Link href="/directory" className={cn(buttonVariants({ variant: "outline" }))}>
            Go to directory
          </Link>
        </div>
        <Alert tone="info" className="mt-8">
          <AlertTitle>No data was changed</AlertTitle>
          <AlertDescription>
            This is a read-only interface. A page failure does not modify source records or
            canonical data.
          </AlertDescription>
        </Alert>
      </div>
    </div>
  );
}
