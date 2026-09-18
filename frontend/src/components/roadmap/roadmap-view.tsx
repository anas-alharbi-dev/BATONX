"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type { Project, RoadmapPhase, TaskStatus } from "@/lib/api/types";
import { fieldMessage } from "@/components/review/review-helpers";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { interpolate, useLanguage } from "@/lib/i18n";

import { RoadmapEditor } from "./roadmap-editor";
import { RoadmapEmpty } from "./roadmap-empty";
import { RoadmapGenerating } from "./roadmap-generating";
import { RoadmapNext } from "./roadmap-next";
import { RoadmapPhases } from "./roadmap-phases";
import { RoadmapStatusBar } from "./roadmap-status-bar";
import { allTasks } from "./roadmap-shared";

export function RoadmapView({ initialProject }: { initialProject: Project }) {
  const { dict } = useLanguage();
  const [project, setProject] = useState(initialProject);
  const [editing, setEditing] = useState(false);
  const [editTree, setEditTree] = useState<RoadmapPhase[] | null>(null);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [taskErrors, setTaskErrors] = useState<Record<string, string>>({});

  const slug = project.slug;
  const content = project.roadmap?.content;
  const approved = !!project.roadmap_approved_at;
  const archApproved = !!project.architecture_approved_at;
  const meta = project.roadmap_meta;

  const generate = useMutation({
    mutationFn: () => api.generateRoadmap(slug),
    onSuccess: (updated) => {
      setProject(updated);
      setEditing(false);
      setEditTree(null);
      setConfirmRegenerate(false);
    },
  });

  const save = useMutation({
    mutationFn: () => api.updateRoadmap(slug, editTree ?? []),
    onSuccess: (updated) => {
      setProject(updated);
      setEditing(false);
      setEditTree(null);
    },
  });

  const approve = useMutation({
    mutationFn: () => api.approveRoadmap(slug),
    onSuccess: (updated) => setProject(updated),
  });

  const taskStatus = useMutation({
    mutationFn: (vars: { taskId: string; status: TaskStatus }) =>
      api.setTaskStatus(slug, vars.taskId, vars.status),
    onSuccess: (updated) => setProject(updated),
    onError: (error, vars) =>
      setTaskErrors((prev) => ({
        ...prev,
        [vars.taskId]: (error as ApiRequestError).message,
      })),
    onSettled: () => setPendingTaskId(null),
  });

  const generateError = generate.error as ApiRequestError | null;
  const saveError = save.error as ApiRequestError | null;
  const approveError = approve.error as ApiRequestError | null;

  const editError = saveError
    ? saveError.code === "invalid_roadmap"
      ? fieldMessage(saveError)
      : saveError.message
    : null;

  function toggleEdit() {
    if (editing) {
      setEditing(false);
      setEditTree(null);
      save.reset();
    } else if (content) {
      setEditTree(structuredClone(content.phases));
      setEditing(true);
    }
  }

  function setStatus(taskId: string, status: TaskStatus) {
    setTaskErrors((prev) => {
      const next = { ...prev };
      delete next[taskId];
      return next;
    });
    setPendingTaskId(taskId);
    taskStatus.mutate({ taskId, status });
  }

  const nextTitle = content
    ? allTasks(content).find((t) => t.id === meta?.next_recommended_task_id)?.title
    : undefined;

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.softwareShared.stepPrefix} 5 &middot; {dict.journeySoftware.roadmap.label}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {dict.roadmap.title}
        </h1>
        <p className="text-sm text-fg-muted">
          {dict.journeySoftware.roadmap.purpose}
        </p>
        <p className="rounded-md border border-line bg-surface/60 px-3.5 py-2.5 text-sm leading-relaxed text-fg-muted">
          {project.original_idea}
        </p>
      </div>

      {!content ? (
        generate.isPending ? (
          <RoadmapGenerating />
        ) : (
          <RoadmapEmpty
            variant={archApproved ? "ready" : "needs-architecture"}
            slug={slug}
            onGenerate={() => generate.mutate()}
            loading={generate.isPending}
            error={generateError}
          />
        )
      ) : generate.isPending ? (
        <RoadmapGenerating regenerate />
      ) : (
        <>
          <RoadmapStatusBar
            slug={slug}
            approved={approved}
            approvedAt={project.roadmap_approved_at}
            updatedAt={project.roadmap?.updated_at}
            editing={editing}
            approving={approve.isPending}
            approveError={approveError?.message ?? null}
            stale={!!project.downstream_stale?.roadmap}
            meta={meta}
            nextTaskTitle={nextTitle}
            onApprove={() => approve.mutate()}
            onRegenerate={() => setConfirmRegenerate(true)}
            onToggleEdit={toggleEdit}
          />

          {generateError && (
            <p role="alert" className="mb-4 text-sm text-danger">
              {interpolate(dict.softwareShared.couldntRegenerate, { msg: generateError.message })}
            </p>
          )}

          {editing && editTree ? (
            <RoadmapEditor
              phases={editTree}
              onChange={setEditTree}
              onSave={() => save.mutate()}
              onCancel={toggleEdit}
              saving={save.isPending}
              error={editError}
            />
          ) : (
            <RoadmapPhases
              slug={slug}
              content={content}
              meta={meta}
              approved={approved}
              pendingTaskId={pendingTaskId}
              taskErrors={taskErrors}
              onSetStatus={setStatus}
            />
          )}

          {approved && !editing && (
            <RoadmapNext
              slug={slug}
              nextTaskId={meta?.next_recommended_task_id ?? null}
            />
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmRegenerate}
        title={dict.roadmap.regenerateTitle}
        description={approved ? dict.roadmap.regenerateApprovedDesc : dict.roadmap.regenerateDraftDesc}
        confirmLabel={dict.softwareShared.regenerate}
        tone="danger"
        busy={generate.isPending}
        onConfirm={() => generate.mutate()}
        onCancel={() => setConfirmRegenerate(false)}
      />
    </>
  );
}
