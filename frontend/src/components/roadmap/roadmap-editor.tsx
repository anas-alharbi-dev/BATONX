"use client";

import type { RoadmapPhase, RoadmapTask } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  AddButton,
  inputClass,
  RemoveButton,
  StringListEditor,
} from "@/components/ui/editor-primitives";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

const labelClass = "text-xs uppercase tracking-[0.06em] text-fg-subtle";

function newTask(): RoadmapTask {
  return {
    id: "",
    order: 0,
    phase_id: "",
    title: "",
    objective: "",
    why: "",
    requirements: [],
    dependencies: [],
    expected_output: "",
    acceptance_criteria: [""],
    status: "not_started",
  };
}

function newPhase(): RoadmapPhase {
  return { id: "", order: 0, title: "", objective: "", tasks: [newTask()] };
}

function TaskEditor({
  task,
  otherTasks,
  onChange,
  onRemove,
  dict,
}: {
  task: RoadmapTask;
  otherTasks: { id: string; title: string }[];
  onChange: (t: RoadmapTask) => void;
  onRemove: () => void;
  dict: Dictionary;
}) {
  const set = (patch: Partial<RoadmapTask>) => onChange({ ...task, ...patch });

  return (
    <div className="grid gap-3 rounded-md border border-line bg-bg-subtle p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-xs text-fg-subtle">
          {task.id || dict.roadmap.newTask}
        </span>
        <RemoveButton label={dict.roadmap.removeTask} onClick={onRemove} />
      </div>

      <label className="grid gap-1.5">
        <span className={labelClass}>{dict.softwareShared.fieldTitle}</span>
        <input
          type="text"
          autoComplete="off"
          value={task.title}
          onChange={(e) => set({ title: e.target.value })}
          className={inputClass}
        />
      </label>

      <label className="grid gap-1.5">
        <span className={labelClass}>{dict.softwareShared.fieldObjective}</span>
        <textarea
          rows={2}
          value={task.objective}
          onChange={(e) => set({ objective: e.target.value })}
          className={`${inputClass} resize-y`}
        />
      </label>

      <label className="grid gap-1.5">
        <span className={labelClass}>{dict.softwareShared.fieldWhy}</span>
        <textarea
          rows={2}
          value={task.why}
          onChange={(e) => set({ why: e.target.value })}
          className={`${inputClass} resize-y`}
        />
      </label>

      <div className="grid gap-1.5">
        <span className={labelClass}>{dict.softwareShared.fieldRequirements}</span>
        <StringListEditor
          value={task.requirements}
          onChange={(requirements) => set({ requirements })}
          itemNoun={dict.roadmap.itemNounRequirement}
        />
      </div>

      {otherTasks.length > 0 && (
        <div className="grid gap-1.5">
          <span className={labelClass}>{dict.softwareShared.fieldDependsOn}</span>
          <p className="text-xs text-fg-subtle">
            {dict.roadmap.pickEarlierTasks}
          </p>
          <div className="grid gap-1">
            {otherTasks.map((o) => (
              <label
                key={o.id}
                className="flex items-center gap-2 text-sm text-fg-muted"
              >
                <input
                  type="checkbox"
                  className="size-4 accent-accent"
                  checked={task.dependencies.includes(o.id)}
                  onChange={(e) =>
                    set({
                      dependencies: e.target.checked
                        ? [...task.dependencies, o.id]
                        : task.dependencies.filter((d) => d !== o.id),
                    })
                  }
                />
                <span className="font-mono text-xs">{o.id}</span>
                {o.title || dict.roadmap.untitled}
              </label>
            ))}
          </div>
        </div>
      )}

      <label className="grid gap-1.5">
        <span className={labelClass}>{dict.softwareShared.fieldExpectedOutput}</span>
        <textarea
          rows={2}
          value={task.expected_output}
          onChange={(e) => set({ expected_output: e.target.value })}
          className={`${inputClass} resize-y`}
        />
      </label>

      <div className="grid gap-1.5">
        <span className={labelClass}>{dict.softwareShared.fieldAcceptanceCriteria}</span>
        <StringListEditor
          value={task.acceptance_criteria}
          onChange={(acceptance_criteria) => set({ acceptance_criteria })}
          itemNoun={dict.roadmap.itemNounCriterion}
        />
      </div>
    </div>
  );
}

interface Props {
  phases: RoadmapPhase[];
  onChange: (phases: RoadmapPhase[]) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}

export function RoadmapEditor({
  phases,
  onChange,
  onSave,
  onCancel,
  saving,
  error,
}: Props) {
  const { dict } = useLanguage();
  const allTaskRefs = phases
    .flatMap((p) => p.tasks)
    .filter((t) => t.id)
    .map((t) => ({ id: t.id, title: t.title }));

  const setPhase = (pi: number, patch: Partial<RoadmapPhase>) =>
    onChange(phases.map((p, i) => (i === pi ? { ...p, ...patch } : p)));

  return (
    <div className="grid gap-5">
      {phases.map((phase, pi) => (
        <div
          key={pi}
          className="grid gap-3 rounded-xl border border-line bg-surface/40 p-4 sm:p-5"
        >
          <div className="flex items-start justify-between gap-2">
            <span className="font-mono text-xs text-fg-subtle">
              {phase.id || dict.roadmap.newPhase}
            </span>
            <RemoveButton
              label={interpolate(dict.roadmap.removePhase, { n: String(pi + 1) })}
              onClick={() => onChange(phases.filter((_, i) => i !== pi))}
            />
          </div>

          <label className="grid gap-1.5">
            <span className={labelClass}>{dict.softwareShared.fieldPhaseTitle}</span>
            <input
              type="text"
              autoComplete="off"
              value={phase.title}
              onChange={(e) => setPhase(pi, { title: e.target.value })}
              className={inputClass}
            />
          </label>
          <label className="grid gap-1.5">
            <span className={labelClass}>{dict.softwareShared.fieldPhaseObjective}</span>
            <textarea
              rows={2}
              value={phase.objective}
              onChange={(e) => setPhase(pi, { objective: e.target.value })}
              className={`${inputClass} resize-y`}
            />
          </label>

          <div className="grid gap-3">
            {phase.tasks.map((task, ti) => (
              <TaskEditor
                key={ti}
                task={task}
                dict={dict}
                otherTasks={allTaskRefs.filter((r) => r.id !== task.id)}
                onChange={(t) =>
                  setPhase(pi, {
                    tasks: phase.tasks.map((x, i) => (i === ti ? t : x)),
                  })
                }
                onRemove={() =>
                  setPhase(pi, {
                    tasks: phase.tasks.filter((_, i) => i !== ti),
                  })
                }
              />
            ))}
            <AddButton
              label={dict.roadmap.addTask}
              onClick={() => setPhase(pi, { tasks: [...phase.tasks, newTask()] })}
            />
          </div>
        </div>
      ))}

      <AddButton
        label={dict.roadmap.addPhase}
        onClick={() => onChange([...phases, newPhase()])}
      />

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <div className="sticky bottom-0 -mx-4 flex gap-3 border-t border-line bg-bg/90 px-4 py-3 backdrop-blur-md">
        <Button loading={saving} onClick={onSave}>
          {dict.roadmap.saveRoadmap}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={saving}>
          {dict.common.cancel}
        </Button>
      </div>
    </div>
  );
}
