"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { RoadmapView } from "@/components/roadmap/roadmap-view";
import { EmptyState, ErrorState } from "@/components/feedback/states";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiRequestError } from "@/lib/api/client";

function LoadingSkeleton() {
  return (
    <>
      <div className="grid gap-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-12 w-full" />
      </div>
      <div className="mt-10 grid gap-5">
        {[0, 1].map((p) => (
          <div key={p} className="grid gap-3 rounded-xl border border-line bg-surface/40 p-5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ))}
      </div>
    </>
  );
}

export default function RoadmapPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;

  const query = useQuery({
    queryKey: ["project", slug],
    queryFn: () => api.getProject(slug),
    retry: false,
  });

  if (query.isPending) return <LoadingSkeleton />;

  if (query.isError) {
    const error = query.error as ApiRequestError;
    if (error.code === "project_not_found") {
      return (
        <EmptyState
          title="Project Not Found"
          description="This project link is invalid or the project no longer exists."
        >
          <Link href="/projects/new" className={buttonClasses("solid", "md")}>
            Start a New Project
          </Link>
        </EmptyState>
      );
    }
    return (
      <ErrorState
        title="Couldn’t Load This Project"
        description={error.message}
        retryable={error.retryable}
        retrying={query.isRefetching}
        onRetry={() => query.refetch()}
      />
    );
  }

  return <RoadmapView initialProject={query.data} />;
}
