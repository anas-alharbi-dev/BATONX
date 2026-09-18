"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { DataSourcesView } from "@/components/data/data-sources-view";
import { EmptyState, ErrorState } from "@/components/feedback/states";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiRequestError } from "@/lib/api/client";

export default function DataSourcesPage() {
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
          <Skeleton className="h-24 w-full" />
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

  const project = query.data;

  if (project.project_type !== "data") {
    return (
      <EmptyState
        title="Not a Data Project"
        description="This project follows the Software workflow."
      >
        <Link href="/" className={buttonClasses("solid", "md")}>
          Home
        </Link>
      </EmptyState>
    );
  }

  if (!project.data_brief_approved_at) {
    return (
      <>
        <EmptyState
          title="Approve the Data Brief First"
          description="Data sources are added after the brief is approved."
        >
          <Link
            href={`/projects/${slug}/data-overview`}
            className={buttonClasses("solid", "md")}
          >
            Go to the Data Brief
          </Link>
        </EmptyState>
      </>
    );
  }

  return <DataSourcesView initialProject={project} />;
}
