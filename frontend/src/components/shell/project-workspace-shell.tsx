"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Cross2Icon, ListBulletIcon } from "@radix-ui/react-icons";

import { ConversationLauncher } from "@/components/conversation/conversation-launcher";
import { Skeleton } from "@/components/ui/skeleton";
import type { Project } from "@/lib/api/types";

import { AppTopBar } from "./app-top-bar";
import { IntelligencePanel } from "./intelligence-panel";
import { NextAction } from "./next-action";
import { ProjectJourney } from "./project-journey";

/**
 * The signature three-column BATONX Workspace — the one permanent frame
 * every stage page renders inside. Desktop: Journey | Workspace |
 * Intelligence, side by side. Below `lg` (1024px), Journey and Intelligence
 * both become drawers so the single Workspace column stays legible on a
 * phone or tablet — the process stays reachable (a compact strip always
 * shows the current stage and a button to open the full Journey), it just
 * never fights the content for space. See journey-model.ts and
 * project-journey.tsx for how each column's content is computed; this
 * component only owns layout and drawer state.
 */
export function ProjectWorkspaceShell({
  project,
  children,
}: {
  /** null while the layout's own project fetch is still pending/failed —
   *  each stage page independently fetches and renders its own loading/error
   *  state too, so the shell never blocks `children`; it just shows a
   *  neutral placeholder in the Journey/Intelligence columns until the
   *  shared project data (same query key, same cache) resolves. */
  project: Project | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [journeyOpen, setJourneyOpen] = useState(false);

  // Close the mobile Journey drawer on navigation so it never lingers open
  // over the next page.
  useEffect(() => {
    setJourneyOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!journeyOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setJourneyOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [journeyOpen]);

  return (
    <div className="flex h-[100dvh] flex-col">
      <AppTopBar project={project ?? undefined} />
      {project && <NextAction project={project} />}

      {/* Compact mobile/tablet process strip — Journey collapses to this
          below lg; the process stays one tap away instead of disappearing. */}
      <div className="flex items-center gap-2 border-b border-line bg-bg px-4 py-2 lg:hidden">
        <button
          type="button"
          onClick={() => setJourneyOpen(true)}
          disabled={!project}
          className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
          aria-haspopup="dialog"
        >
          <ListBulletIcon className="size-3.5" aria-hidden />
          Journey
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-[264px] shrink-0 overflow-y-auto border-e border-line bg-bg lg:block">
          {project ? (
            <ProjectJourney project={project} pathname={pathname ?? ""} />
          ) : (
            <div className="grid gap-3 p-4">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          )}
        </aside>

        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-4 py-10 safe-px lg:px-8">{children}</div>
        </main>

        <aside className="hidden w-[340px] shrink-0 overflow-hidden lg:block">
          {project ? (
            <IntelligencePanel project={project} />
          ) : (
            <div className="grid h-full gap-3 border-s border-line p-4">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-24 w-full" />
            </div>
          )}
        </aside>
      </div>

      {/* Tablet/mobile Intelligence entry point — the exact overlay
          mechanism used before this phase, unchanged, reused verbatim. */}
      {project && (
        <div className="lg:hidden">
          <ConversationLauncher project={project} />
        </div>
      )}

      {/* Mobile/tablet Journey drawer */}
      {journeyOpen && project && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <button
            type="button"
            aria-label="Close Journey"
            onClick={() => setJourneyOpen(false)}
            className="flex-1 bg-black/50 backdrop-blur-[1px]"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Project journey"
            className="animate-rise-in relative flex h-full w-full max-w-xs flex-col border-e border-line bg-bg shadow-2xl"
          >
            <button
              type="button"
              onClick={() => setJourneyOpen(false)}
              aria-label="Close Journey"
              className="absolute end-2 top-2.5 z-10 rounded-md p-1.5 text-fg-muted transition-colors hover:bg-surface hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <Cross2Icon className="size-4" aria-hidden />
            </button>
            <ProjectJourney project={project} pathname={pathname ?? ""} />
          </aside>
        </div>
      )}
    </div>
  );
}
