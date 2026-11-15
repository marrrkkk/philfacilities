import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div
      className="container-page py-10"
      role="status"
      aria-busy="true"
      aria-label="Loading page"
    >
      <Skeleton className="h-4 w-40" />
      <Skeleton className="mt-6 h-10 w-2/3" />
      <Skeleton className="mt-3 h-5 w-1/2" />
      <div className="mt-10 grid gap-8 lg:grid-cols-[18rem_1fr]">
        <Skeleton className="h-96 w-full" />
        <div className="space-y-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      </div>
    </div>
  );
}
