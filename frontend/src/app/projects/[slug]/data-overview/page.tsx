"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { DataBriefView } from "@/components/data/data-brief-view";
import { EmptyState, ErrorState } from "@/components/feedback/states";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiRequestError } from "@/lib/api/client";

export default function DataOverviewPage() {
  const { slug } = useParams<{ slug: string }>();
  const query = useQuery({
    queryKey: ["project", slug],
    queryFn: () => api.getProject(slug),
    retry: false,
  });

  if (query.isPending) {
    return (
      <>
        <div className="grid gap-3">
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-8 w-52" />
          <Skeleton className="h-12 w-full" />
        </div>
      </>
    );
  }

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

  if (query.data.project_type !== "data") {
    return (
      <EmptyState
        title="Not a Data Project"
        description="This project follows the Software workflow."
      >
        <Link
          href={`/projects/${slug}/discovery`}
          className={buttonClasses("solid", "md")}
        >
          Open Software Workspace
        </Link>
      </EmptyState>
    );
  }

  return <DataBriefView initialProject={query.data} />;
}
