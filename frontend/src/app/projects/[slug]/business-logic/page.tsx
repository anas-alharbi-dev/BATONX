"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { BusinessLogicView } from "@/components/business-logic/business-logic-view";
import { EmptyState, ErrorState } from "@/components/feedback/states";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiRequestError } from "@/lib/api/client";

function LoadingSkeleton() {
  return (
    <>
      <div className="grid gap-3">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-12 w-full" />
      </div>
      <div className="mt-10 grid gap-4 rounded-xl border border-line bg-surface/40 p-7">
        {["w-32", "w-full", "w-3/4", "w-40", "w-full", "w-2/3"].map((w, i) => (
          <Skeleton key={i} className={`h-4 ${w}`} />
        ))}
      </div>
    </>
  );
}

export default function BusinessLogicPage() {
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

  return <BusinessLogicView initialProject={query.data} />;
}
