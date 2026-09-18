"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeftIcon, CheckIcon } from "@radix-ui/react-icons";

import { api, ApiRequestError } from "@/lib/api/client";
import type { TaskStatus, TaskWorkspace } from "@/lib/api/types";
import { useMutation } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { STATUS_TONE } from "@/components/roadmap/roadmap-shared";
import { useLanguage } from "@/lib/i18n";

import { DependencyList } from "./dependency-list";
import { PromptPanel } from "./prompt-panel";
import { RelevantContextPanel } from "./relevant-context-panel";
import { TaskStatusControl } from "./task-status-control";

function SectionHeading({ n, title }: { n: number; title: string }) {
  return (
    <h2 className="mb-3 flex items-center gap-2.5 text-sm font-semibold tracking-tight text-fg">
      <span className="grid size-5 shrink-0 place-items-center rounded-full border border-line-strong bg-surface font-mono text-[11px] text-fg-subtle">
        {n}
      </span>
      {title}
    </h2>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-t border-line py-3 first:border-t-0 first:pt-0">
      <p className="text-xs uppercase tracking-[0.06em] text-fg-subtle">{label}</p>
      {children}
    </div>
  );
}

export function TaskWorkspaceView({
  slug,
  initial,
}: {
  slug: string;
  initial: TaskWorkspace;
}) {
  const { dict } = useLanguage();
  const [workspace, setWorkspace] = useState(initial);
  const { task, phase } = workspace;

  const buildPrompts = workspace.prompts.filter((p) => p.kind === "build");
  const reviewPrompts = workspace.prompts.filter((p) => p.kind === "review");

  const generate = useMutation({
    mutationFn: () => api.generateBuildPrompt(slug, task.id),
    onSuccess: (updated) => setWorkspace(updated),
  });

  const generateReview = useMutation({
    mutationFn: () => api.generateReviewPrompt(slug, task.id),
    onSuccess: (updated) => setWorkspace(updated),
  });

  const status = useMutation({
    mutationFn: (next: TaskStatus) =>
      api
        .setTaskStatus(slug, task.id, next)
        .then(() => api.getTaskWorkspace(slug, task.id)),
    onSuccess: (updated) => setWorkspace(updated),
  });
  const statusError = status.error as ApiRequestError | null;

  const hasRequirements =
    workspace.requirements.length > 0 || workspace.requirement_notes.length > 0;

  return (
    <>
      <div className="mb-6 flex items-center justify-between gap-3 text-sm">
        <Link
          href={`/projects/${slug}/roadmap`}
          className="inline-flex items-center gap-1.5 text-fg-muted underline-offset-4 hover:text-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <ArrowLeftIcon className="size-3.5 rtl:-scale-x-100" aria-hidden />
          {dict.taskWorkspace.backToRoadmap}
        </Link>
        <Link
          href={`/projects/${slug}/progress`}
          className="text-fg-muted underline-offset-4 hover:text-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {dict.taskWorkspace.backToProgress}
        </Link>
      </div>

      <header className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-fg-subtle">
            {phase.title} &middot; {task.id}
          </span>
          <Badge tone={STATUS_TONE[task.status]}>{dict.taskStatus[task.status]}</Badge>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {task.title}
        </h1>
        <p className="text-sm leading-relaxed text-fg-muted">{task.objective}</p>
      </header>

      <div className="mt-10 grid gap-10">
        {/* 1 — Understand the task */}
        <section>
          <SectionHeading n={1} title={dict.taskWorkspace.understandTask} />
          <div className="rounded-xl border border-line bg-surface/40 px-5 py-2">
            <Row label={dict.softwareShared.fieldWhy}>
              <p className="text-sm leading-relaxed text-fg-muted">{task.why}</p>
            </Row>
            <Row label={dict.softwareShared.fieldRequirements}>
              {hasRequirements ? (
                <ul className="grid gap-2 text-sm text-fg-muted">
                  {workspace.requirements.map((r) => (
                    <li key={r.id} className="flex flex-wrap items-start gap-2">
                      <span className="mt-0.5 shrink-0 rounded-sm border border-line bg-surface px-1.5 font-mono text-[11px] text-fg-subtle">
                        {r.id}
                      </span>
                      <Badge tone="neutral" className="shrink-0">
                        {dict.blueprint.priority[r.priority]}
                      </Badge>
                      <span className="min-w-0 flex-1 leading-relaxed">
                        {r.text}
                      </span>
                    </li>
                  ))}
                  {workspace.requirement_notes.map((n, i) => (
                    <li key={`note-${i}`}>{n}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-fg-subtle">
                  {dict.taskWorkspace.noRequirements}
                </p>
              )}
            </Row>
            <Row label={dict.roadmap.dependsOn}>
              <DependencyList slug={slug} dependencies={workspace.dependencies} />
            </Row>
            <Row label={dict.roadmap.expectedOutput}>
              <p className="text-sm leading-relaxed text-fg-muted">
                {task.expected_output}
              </p>
            </Row>
          </div>

          <div className="mt-3 rounded-xl border border-accent/25 bg-accent/[0.05] p-5">
            <p className="text-xs uppercase tracking-[0.06em] text-accent">
              {dict.roadmap.acceptanceCriteria}
            </p>
            <ul className="mt-2 grid gap-2 text-sm leading-relaxed text-fg-muted">
              {task.acceptance_criteria.map((c, i) => (
                <li key={i} className="flex items-start gap-2">
                  <CheckIcon
                    className="mt-0.5 size-4 shrink-0 text-accent"
                    aria-hidden
                  />
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-3">
            <RelevantContextPanel context={workspace.relevant_context} />
          </div>
        </section>

        {/* 2 — Build Prompt */}
        <section>
          <SectionHeading n={2} title={dict.taskWorkspace.generateBuildHeading} />
          <PromptPanel
            kind="build"
            step={2}
            slug={slug}
            prompts={buildPrompts}
            blocked={workspace.blocked}
            unfinished={workspace.unfinished_dependencies}
            dependencies={workspace.dependencies}
            generating={generate.isPending}
            error={generate.error as ApiRequestError | null}
            onGenerate={() => generate.mutate()}
          />
        </section>

        {/* 3 — Review Prompt */}
        <section>
          <SectionHeading n={3} title={dict.taskWorkspace.generateReviewHeading} />
          <PromptPanel
            kind="review"
            step={3}
            slug={slug}
            prompts={reviewPrompts}
            blocked={workspace.blocked}
            unfinished={workspace.unfinished_dependencies}
            dependencies={workspace.dependencies}
            hasBuildPrompt={buildPrompts.length > 0}
            generating={generateReview.isPending}
            error={generateReview.error as ApiRequestError | null}
            onGenerate={() => generateReview.mutate()}
          />
        </section>

        {/* 4 — Task status */}
        <section>
          <SectionHeading n={4} title={dict.taskWorkspace.updateStatusHeading} />
          <div className="rounded-xl border border-line bg-surface/40 p-5">
            <TaskStatusControl
              status={task.status}
              blocked={workspace.blocked}
              unfinishedDependencies={workspace.unfinished_dependencies}
              pending={status.isPending}
              error={statusError?.message ?? null}
              onSetStatus={(next) => status.mutate(next)}
            />
          </div>
        </section>
      </div>
    </>
  );
}
