"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { TaskWorkspaceView } from "@/components/task-workspace/task-workspace-view";
import { EmptyState, ErrorState } from "@/components/feedback/states";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiRequestError } from "@/lib/api/client";

function LoadingSkeleton() {
  return (
    <>
      <Skeleton className="h-4 w-20" />
      <div className="mt-6 grid gap-3">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-8 w-2/3" />
      </div>
      <div className="mt-8 grid gap-6">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="grid gap-2">
            <Skeleton className="h-3 w-28" />
            <Skeleton className="h-12 w-full" />
          </div>
        ))}
      </div>
    </>
  );
}

export default function TaskWorkspacePage() {
  const params = useParams<{ slug: string; taskId: string }>();
  const { slug, taskId } = params;

  const query = useQuery({
    queryKey: ["task", slug, taskId],
    queryFn: () => api.getTaskWorkspace(slug, taskId),
    retry: false,
  });

  if (query.isPending) return <LoadingSkeleton />;

  if (query.isError) {
    const error = query.error as ApiRequestError;

    if (error.code === "task_not_found" || error.code === "project_not_found") {
      return (
        <EmptyState
          title="Task Not Found"
          description="This task isn’t in the project’s Roadmap. It may have been removed or renumbered by an edit."
        >
          <Link
            href={`/projects/${slug}/roadmap`}
            className={buttonClasses("solid", "md")}
          >
            Back to Roadmap
          </Link>
        </EmptyState>
      );
    }

    if (error.code === "roadmap_not_approved") {
      return (
        <EmptyState
          title="Approve the Roadmap First"
          description="Task Workspaces open once the Development Roadmap is approved."
        >
          <Link
            href={`/projects/${slug}/roadmap`}
            className={buttonClasses("solid", "md")}
          >
            Go to Roadmap
          </Link>
        </EmptyState>
      );
    }

    return (
      <ErrorState
        title="Couldn’t Load This Task"
        description={error.message}
        retryable={error.retryable}
        retrying={query.isRefetching}
        onRetry={() => query.refetch()}
      />
    );
  }

  return <TaskWorkspaceView slug={slug} initial={query.data} />;
}
