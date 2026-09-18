"use client";

import type {
  FunctionalRequirement,
  Priority,
  UserFlow,
  UserRole,
} from "@/lib/api/types";
import {
  AddButton,
  inputClass,
  RemoveButton,
  StringListEditor as ListEditor,
} from "@/components/ui/editor-primitives";
import { interpolate, useLanguage } from "@/lib/i18n";

import { PRIORITIES, type SectionKind } from "./blueprint-shared";

function ProseEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <textarea
      rows={4}
      autoComplete="off"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`${inputClass} resize-y`}
    />
  );
}

function RolesEditor({
  value,
  onChange,
}: {
  value: UserRole[];
  onChange: (v: UserRole[]) => void;
}) {
  const { dict } = useLanguage();
  const t = dict.blueprint.rolesEditor;
  const set = (i: number, patch: Partial<UserRole>) =>
    onChange(value.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  return (
    <div className="grid gap-3">
      {value.map((role, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-line p-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              autoComplete="off"
              placeholder={t.namePlaceholder}
              value={role.name}
              onChange={(e) => set(i, { name: e.target.value })}
              className={inputClass}
            />
            <RemoveButton
              label={interpolate(t.removeRole, { n: String(i + 1) })}
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
            />
          </div>
          <textarea
            rows={2}
            autoComplete="off"
            placeholder={t.descriptionPlaceholder}
            value={role.description}
            onChange={(e) => set(i, { description: e.target.value })}
            className={`${inputClass} resize-y`}
          />
        </div>
      ))}
      <AddButton
        label={t.addRole}
        onClick={() => onChange([...value, { name: "", description: "" }])}
      />
    </div>
  );
}

function RequirementsEditor({
  value,
  onChange,
}: {
  value: FunctionalRequirement[];
  onChange: (v: FunctionalRequirement[]) => void;
}) {
  const { dict } = useLanguage();
  const t = dict.blueprint.requirementsEditor;
  const set = (i: number, patch: Partial<FunctionalRequirement>) =>
    onChange(value.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  return (
    <div className="grid gap-2">
      {value.map((req, i) => (
        <div key={req.id || `new-${i}`} className="flex items-start gap-2">
          <span className="mt-2.5 w-10 shrink-0 font-mono text-xs text-fg-subtle">
            {req.id || t.newIdFallback}
          </span>
          <input
            type="text"
            autoComplete="off"
            placeholder={t.capabilityPlaceholder}
            value={req.text}
            onChange={(e) => set(i, { text: e.target.value })}
            className={inputClass}
          />
          <select
            aria-label={interpolate(t.priorityFor, { ref: req.id || String(i + 1) })}
            value={req.priority}
            onChange={(e) => set(i, { priority: e.target.value as Priority })}
            className={`${inputClass} w-28 shrink-0 [color-scheme:dark]`}
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {dict.blueprint.priority[p]}
              </option>
            ))}
          </select>
          <RemoveButton
            label={interpolate(t.removeRequirement, { ref: req.id || String(i + 1) })}
            onClick={() => onChange(value.filter((_, idx) => idx !== i))}
          />
        </div>
      ))}
      <AddButton
        label={t.addRequirement}
        onClick={() =>
          onChange([...value, { id: "", text: "", priority: "should" }])
        }
      />
    </div>
  );
}

function FlowsEditor({
  value,
  onChange,
}: {
  value: UserFlow[];
  onChange: (v: UserFlow[]) => void;
}) {
  const { dict } = useLanguage();
  const t = dict.blueprint.flowsEditor;
  const set = (i: number, patch: Partial<UserFlow>) =>
    onChange(value.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));
  return (
    <div className="grid gap-3">
      {value.map((flow, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-line p-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              autoComplete="off"
              placeholder={t.namePlaceholder}
              value={flow.name}
              onChange={(e) => set(i, { name: e.target.value })}
              className={inputClass}
            />
            <RemoveButton
              label={interpolate(t.removeFlow, { n: String(i + 1) })}
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
            />
          </div>
          <div className="ps-3">
            <p className="mb-1.5 text-xs text-fg-subtle">{t.stepsLabel}</p>
            <ListEditor
              value={flow.steps}
              onChange={(steps) => set(i, { steps })}
              itemNoun={t.stepsItemNoun}
            />
          </div>
        </div>
      ))}
      <AddButton
        label={t.addFlow}
        onClick={() => onChange([...value, { name: "", steps: [""] }])}
      />
    </div>
  );
}

export function SectionEditor({
  kind,
  value,
  onChange,
}: {
  kind: SectionKind;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  switch (kind) {
    case "prose":
      return (
        <ProseEditor value={value as string} onChange={onChange as (v: string) => void} />
      );
    case "list":
      return (
        <ListEditor
          value={(value as string[]) ?? []}
          onChange={onChange as (v: string[]) => void}
        />
      );
    case "roles":
      return (
        <RolesEditor
          value={(value as UserRole[]) ?? []}
          onChange={onChange as (v: UserRole[]) => void}
        />
      );
    case "requirements":
      return (
        <RequirementsEditor
          value={(value as FunctionalRequirement[]) ?? []}
          onChange={onChange as (v: FunctionalRequirement[]) => void}
        />
      );
    case "flows":
      return (
        <FlowsEditor
          value={(value as UserFlow[]) ?? []}
          onChange={onChange as (v: UserFlow[]) => void}
        />
      );
  }
}
