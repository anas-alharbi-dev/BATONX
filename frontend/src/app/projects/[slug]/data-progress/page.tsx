"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { DataProgressView } from "@/components/data/data-progress-view";
import { EmptyState, ErrorState } from "@/components/feedback/states";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiRequestError } from "@/lib/api/client";

export default function DataProgressPage() {
  const { slug } = useParams<{ slug: string }>();
  const query = useQuery({
    queryKey: ["project", slug],
    queryFn: () => api.getProject(slug),
    retry: false,
  });

  if (query.isPending)
    return (
      <>
        <Skeleton className="h-8 w-52" />
      </>
    );

  if (query.isError) {
    const error = query.error as ApiRequestError;
    return error.code === "project_not_found" ? (
      <EmptyState title="Project Not Found" description="This project link is invalid.">
        <Link href="/projects/new" className={buttonClasses("solid", "md")}>
          Start a New Project
        </Link>
      </EmptyState>
    ) : (
      <ErrorState
        title="Couldn’t Load This Project"
        description={error.message}
        retryable={error.retryable}
        onRetry={() => query.refetch()}
      />
    );
  }

  const project = query.data;
  if (project.project_type !== "data") {
    return (
      <EmptyState title="Not a Data Project" description="This project follows the Software workflow.">
        <Link href="/" className={buttonClasses("solid", "md")}>
          Home
        </Link>
      </EmptyState>
    );
  }

  return <DataProgressView initialProject={project} />;
}
