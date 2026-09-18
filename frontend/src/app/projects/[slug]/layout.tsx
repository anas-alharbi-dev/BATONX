"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { ProjectWorkspaceShell } from "@/components/shell/project-workspace-shell";
import { api } from "@/lib/api/client";

/**
 * Every /projects/[slug]/* route renders inside the signature BATONX
 * Workspace shell (Phase P-1) — Journey | Workspace | Intelligence. This
 * query shares its cache key with each stage page's own `["project", slug]`
 * fetch, so there is no duplicate network call; whichever resolves first
 * feeds both. The shell itself tolerates `project` being null (still
 * loading, or the slug doesn't exist) — it shows neutral placeholders in
 * Journey/Intelligence while `{children}` renders its own existing
 * loading/error UI unchanged.
 */
export default function ProjectLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { slug } = useParams<{ slug: string }>();
  const query = useQuery({
    queryKey: ["project", slug],
    queryFn: () => api.getProject(slug),
    enabled: !!slug,
    retry: false,
  });

  return (
    <ProjectWorkspaceShell project={query.data ?? null}>
      {children}
    </ProjectWorkspaceShell>
  );
}
