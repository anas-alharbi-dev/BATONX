"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { DiscoveryView } from "@/components/discovery/discovery-view";
import { EmptyState, ErrorState } from "@/components/feedback/states";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiRequestError } from "@/lib/api/client";

function LoadingSkeleton() {
  return (
    <>
      <div className="grid gap-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-12 w-full" />
      </div>
      <div className="mt-10 grid gap-8">
        {[0, 1, 2].map((i) => (
          <div key={i} className="grid gap-3">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
          </div>
        ))}
      </div>
    </>
  );
}

export default function DiscoveryPage() {
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
          description="This project link is invalid or the project no longer exists. Start a new one from the home page."
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

  return <DiscoveryView initialProject={query.data} />;
}
