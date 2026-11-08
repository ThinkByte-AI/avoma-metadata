"use client";

import { IngestionPanel } from "@/components/admin/ingestion";
import { ErrorState, PageHeader } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/hooks/use-me";
import { ApiError } from "@/lib/api";

export default function IngestionPage() {
  const { data: me, isPending, error, refetch } = useMe();
  return (
    <div>
      <PageHeader title="Data Ingestion" description="Load and index meetings from the S3 archive." />
      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : me.role !== "admin" ? (
        <ErrorState error={new ApiError(403, "forbidden", "Administrator access is required.")} />
      ) : (
        <IngestionPanel />
      )}
    </div>
  );
}
