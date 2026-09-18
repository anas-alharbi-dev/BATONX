"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { MagnifyingGlassIcon } from "@radix-ui/react-icons";

import { ProjectCard } from "@/components/projects/project-card";
import { ErrorState } from "@/components/feedback/states";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiRequestError } from "@/lib/api/client";
import { interpolate, useLanguage } from "@/lib/i18n";
import type { ProjectType } from "@/lib/api/types";

type Filter = "all" | ProjectType;

/**
 * Projects Home (Phase P-3) — see, resume, create. Deliberately not a
 * dashboard: no sort menus, tags, folders, or teams (explicitly out of
 * scope this phase).
 */
export default function ProjectsPage() {
  const { dict } = useLanguage();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const query = useQuery({ queryKey: ["projects"], queryFn: api.listProjects, retry: false });

  const FILTERS: { id: Filter; label: string }[] = [
    { id: "all", label: dict.projectsHome.filterAll },
    { id: "software", label: dict.projectsHome.filterSoftware },
    { id: "data", label: dict.projectsHome.filterData },
  ];

  const projects = useMemo(() => {
    const all = query.data?.projects ?? [];
    const byType = filter === "all" ? all : all.filter((p) => p.project_type === filter);
    const term = search.trim().toLowerCase();
    return term ? byType.filter((p) => p.name.toLowerCase().includes(term)) : byType;
  }, [query.data, filter, search]);

  const hasAnyProjects = (query.data?.projects.length ?? 0) > 0;

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 safe-px lg:px-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-fg">{dict.projectsHome.title}</h1>
          <p className="mt-1 text-sm text-fg-muted">{dict.projectsHome.subtitle}</p>
        </div>
        <Link href="/projects/new" className={buttonClasses("solid", "md")}>
          {dict.projectsHome.newProject}
        </Link>
      </div>

      {query.isPending && (
        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      )}

      {query.isError && (
        <div className="mt-8">
          <ErrorState
            title={dict.projectsHome.couldntLoad}
            description={(query.error as ApiRequestError).message}
            retryable={(query.error as ApiRequestError).retryable}
            onRetry={() => query.refetch()}
          />
        </div>
      )}

      {query.data && !hasAnyProjects && (
        <div className="mt-14 flex flex-col items-center px-4 text-center">
          <h2 className="text-lg font-medium text-fg">{dict.projectsHome.emptyTitle}</h2>
          <p className="mt-2 max-w-sm text-sm text-fg-muted">{dict.projectsHome.emptyBody}</p>
          <Link href="/projects/new" className={`${buttonClasses("solid", "lg")} mt-6`}>
            {dict.createProject.create}
          </Link>
        </div>
      )}

      {query.data && hasAnyProjects && (
        <>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <div role="tablist" aria-label="Filter by project type" className="inline-flex items-center gap-0.5 rounded-md border border-line bg-surface p-0.5">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  role="tab"
                  aria-selected={filter === f.id}
                  onClick={() => setFilter(f.id)}
                  className={
                    "rounded-[5px] px-3 py-1.5 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
                    (filter === f.id ? "bg-surface-raised text-fg" : "text-fg-subtle hover:text-fg-muted")
                  }
                >
                  {f.label}
                </button>
              ))}
            </div>

            <label className="relative flex-1 sm:max-w-xs">
              <span className="sr-only">{dict.projectsHome.searchByName}</span>
              <MagnifyingGlassIcon className="pointer-events-none absolute start-2.5 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" aria-hidden />
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={dict.projectsHome.searchPlaceholder}
                className="w-full rounded-md border border-line bg-bg-subtle py-1.5 ps-8 pe-3 text-[13px] text-fg placeholder:text-fg-subtle focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
              />
            </label>
          </div>

          {projects.length === 0 ? (
            <p className="mt-10 text-center text-sm text-fg-subtle">
              {search
                ? interpolate(dict.projectsHome.noMatchSearch, { search })
                : dict.projectsHome.noMatchFilter}
            </p>
          ) : (
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {projects.map((p) => (
                <ProjectCard key={p.slug} project={p} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
