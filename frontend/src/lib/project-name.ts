import type { Project } from "@/lib/api/types";

/**
 * ``Project.name`` is never actually set by the current backend (inspected:
 * `create_project()` only ever writes `original_idea`, never `name` — it
 * stays `""` for every real project). Rather than adding a name field or an
 * AI-derived title (out of scope, no backend change needed), every surface
 * that shows a project's name derives one from the idea consistently
 * through this one function — never a bare "Untitled project" when a real
 * idea exists to summarize.
 */
export function displayProjectName(project: Pick<Project, "name" | "original_idea">): string {
  if (project.name) return project.name;
  const idea = project.original_idea?.trim();
  if (!idea) return "Untitled project";
  return idea.length > 48 ? `${idea.slice(0, 48).trimEnd()}…` : idea;
}
