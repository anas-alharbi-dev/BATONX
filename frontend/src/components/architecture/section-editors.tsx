"use client";

import type { DataEntity } from "@/lib/api/types";
import {
  AddButton,
  inputClass,
  RemoveButton,
  StringListEditor,
} from "@/components/ui/editor-primitives";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

import type { FieldSpec, SectionDescriptor } from "./architecture-shared";

/** Maps the shared (English) FieldSpec/itemNoun words used across
 *  architecture-shared.ts to their dictionary translation — the same
 *  presentation-layer-overlay pattern already used for section labels
 *  (see architecture-section.tsx), so architecture-shared.ts itself stays
 *  untouched. Falls back to the raw English word for anything unmapped. */
export function fieldLabel(key: string, dict: Dictionary): string {
  const map: Record<string, string> = {
    style: dict.architecture.fieldLabelStyle,
    summary: dict.architecture.fieldLabelSummary,
    choice: dict.architecture.fieldLabelChoice,
    approach: dict.architecture.fieldLabelApproach,
    why: dict.architecture.fieldLabelWhy,
    name: dict.architecture.fieldLabelName,
    responsibility: dict.architecture.fieldLabelResponsibility,
    purpose: dict.architecture.fieldLabelPurpose,
    decision: dict.architecture.fieldLabelDecision,
    rationale: dict.architecture.fieldLabelRationale,
  };
  return map[key] ?? key;
}

function itemNounLabel(noun: string, dict: Dictionary): string {
  const map: Record<string, string> = {
    component: dict.architecture.itemNounComponent,
    "API area": dict.architecture.itemNounApiArea,
    integration: dict.architecture.itemNounIntegration,
    decision: dict.architecture.itemNounDecision,
    field: dict.architecture.itemNounField,
    relationship: dict.architecture.itemNounRelationship,
  };
  return map[noun] ?? noun;
}

function FieldControl({
  spec,
  value,
  onChange,
  dict,
}: {
  spec: FieldSpec;
  value: string;
  onChange: (v: string) => void;
  dict: Dictionary;
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
        {fieldLabel(spec.key, dict)}
      </span>
      {spec.multiline ? (
        <textarea
          rows={3}
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`${inputClass} resize-y`}
        />
      ) : (
        <input
          type="text"
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
        />
      )}
    </label>
  );
}

function FieldsEditor({
  fields,
  value,
  onChange,
}: {
  fields: FieldSpec[];
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
}) {
  const { dict } = useLanguage();
  return (
    <div className="grid gap-3">
      {fields.map((spec) => (
        <FieldControl
          key={spec.key}
          spec={spec}
          value={value?.[spec.key] ?? ""}
          onChange={(v) => onChange({ ...value, [spec.key]: v })}
          dict={dict}
        />
      ))}
    </div>
  );
}

function ObjectsEditor({
  fields,
  itemNoun,
  value,
  onChange,
}: {
  fields: FieldSpec[];
  itemNoun: string;
  value: Record<string, string>[];
  onChange: (v: Record<string, string>[]) => void;
}) {
  const { dict } = useLanguage();
  const noun = itemNounLabel(itemNoun, dict);
  const set = (i: number, patch: Record<string, string>) =>
    onChange(value.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  const empty = Object.fromEntries(fields.map((f) => [f.key, ""]));
  return (
    <div className="grid gap-3">
      {value.map((row, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-line p-3">
          <div className="flex items-start justify-between gap-2">
            <span className="text-xs text-fg-subtle">
              {noun} {i + 1}
            </span>
            <RemoveButton
              label={interpolate(dict.architecture.removeItemTemplate, { noun, n: String(i + 1) })}
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
            />
          </div>
          {fields.map((spec) => (
            <FieldControl
              key={spec.key}
              spec={spec}
              value={row?.[spec.key] ?? ""}
              onChange={(v) => set(i, { [spec.key]: v })}
              dict={dict}
            />
          ))}
        </div>
      ))}
      <AddButton
        label={interpolate(dict.architecture.addItemTemplate, { noun })}
        onClick={() => onChange([...value, empty])}
      />
    </div>
  );
}

function EntitiesEditor({
  value,
  onChange,
}: {
  value: DataEntity[];
  onChange: (v: DataEntity[]) => void;
}) {
  const { dict } = useLanguage();
  const t = dict.architecture;
  const set = (i: number, patch: Partial<DataEntity>) =>
    onChange(value.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));
  return (
    <div className="grid gap-3">
      {value.map((entity, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-line p-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              autoComplete="off"
              placeholder={t.entityNamePlaceholder}
              value={entity.entity}
              onChange={(e) => set(i, { entity: e.target.value })}
              className={inputClass}
            />
            <RemoveButton
              label={interpolate(t.removeEntity, { n: String(i + 1) })}
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
            />
          </div>
          <div className="ps-3">
            <p className="mb-1.5 text-xs text-fg-subtle">{t.fieldsLabel}</p>
            <StringListEditor
              value={entity.fields}
              onChange={(fields) => set(i, { fields })}
              itemNoun={t.itemNounField}
            />
          </div>
          <div className="ps-3">
            <p className="mb-1.5 text-xs text-fg-subtle">{t.relationshipsLabel}</p>
            <StringListEditor
              value={entity.relationships}
              onChange={(relationships) => set(i, { relationships })}
              itemNoun={t.itemNounRelationship}
            />
          </div>
        </div>
      ))}
      <AddButton
        label={t.addEntity}
        onClick={() =>
          onChange([...value, { entity: "", fields: [], relationships: [] }])
        }
      />
    </div>
  );
}

export function SectionEditor({
  section,
  value,
  onChange,
}: {
  section: SectionDescriptor;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  switch (section.kind) {
    case "fields":
      return (
        <FieldsEditor
          fields={section.fields ?? []}
          value={(value as Record<string, string>) ?? {}}
          onChange={onChange as (v: Record<string, string>) => void}
        />
      );
    case "list":
      return (
        <StringListEditor
          value={(value as string[]) ?? []}
          onChange={onChange as (v: string[]) => void}
          itemNoun={section.itemNoun}
        />
      );
    case "objects":
      return (
        <ObjectsEditor
          fields={section.fields ?? []}
          itemNoun={section.itemNoun ?? "item"}
          value={(value as Record<string, string>[]) ?? []}
          onChange={onChange as (v: Record<string, string>[]) => void}
        />
      );
    case "entities":
      return (
        <EntitiesEditor
          value={(value as DataEntity[]) ?? []}
          onChange={onChange as (v: DataEntity[]) => void}
        />
      );
  }
}
