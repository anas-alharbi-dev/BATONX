"use client";

import type { BusinessRule, BLStateTransition } from "@/lib/api/types";
import {
  AddButton,
  inputClass,
  RemoveButton,
  StringListEditor,
} from "@/components/ui/editor-primitives";
import { interpolate, useLanguage, type Dictionary } from "@/lib/i18n";

import type { FieldSpec, SectionDescriptor } from "./business-logic-shared";

const labelClass = "text-xs uppercase tracking-[0.06em] text-fg-subtle";

/** Maps the shared (English) FieldSpec/itemNoun words used across
 *  business-logic-shared.ts to their dictionary translation — the same
 *  presentation-layer-overlay pattern already used for section labels
 *  (see business-logic-section.tsx), so business-logic-shared.ts itself
 *  stays untouched. Falls back to the raw English word for anything not
 *  in the map, so an unrecognized field never disappears. */
export function fieldLabel(key: string, dict: Dictionary): string {
  const map: Record<string, string> = {
    name: dict.businessLogic.fieldLabelName,
    description: dict.businessLogic.fieldLabelDescription,
    actor: dict.businessLogic.fieldLabelActor,
    can: dict.businessLogic.fieldLabelCan,
    conditions: dict.businessLogic.fieldLabelConditions,
    rule: dict.businessLogic.fieldLabelRule,
    applies_to: dict.businessLogic.fieldLabelAppliesTo,
    approver: dict.businessLogic.fieldLabelApprover,
    steps: dict.businessLogic.fieldLabelSteps,
    scenario: dict.businessLogic.fieldLabelScenario,
    expected_behavior: dict.businessLogic.fieldLabelExpectedBehavior,
    related_requirements: dict.businessLogic.relatedRequirementsLabel,
  };
  return map[key] ?? key;
}

function itemNounLabel(noun: string, dict: Dictionary): string {
  const map: Record<string, string> = {
    actor: dict.businessLogic.itemNounActor,
    permission: dict.businessLogic.itemNounPermission,
    validation: dict.businessLogic.itemNounValidation,
    flow: dict.businessLogic.itemNounFlow,
    "edge case": dict.businessLogic.itemNounEdgeCase,
    condition: dict.businessLogic.itemNounCondition,
    action: dict.businessLogic.itemNounAction,
    step: dict.businessLogic.itemNounStep,
    "requirement id": dict.businessLogic.itemNounRequirementId,
  };
  return map[noun] ?? noun;
}

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

function FieldControl({
  spec,
  value,
  onChange,
  dict,
}: {
  spec: FieldSpec;
  value: unknown;
  onChange: (v: unknown) => void;
  dict: Dictionary;
}) {
  return (
    <label className="grid gap-1.5">
      <span className={labelClass}>{fieldLabel(spec.key, dict)}</span>
      {spec.kind === "list" ? (
        <StringListEditor
          value={(value as string[]) ?? []}
          onChange={onChange as (v: string[]) => void}
          itemNoun={itemNounLabel(spec.itemNoun ?? "item", dict)}
        />
      ) : spec.kind === "textarea" ? (
        <textarea
          rows={2}
          autoComplete="off"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className={`${inputClass} resize-y`}
        />
      ) : (
        <input
          type="text"
          autoComplete="off"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
        />
      )}
    </label>
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
  value: Record<string, unknown>[];
  onChange: (v: Record<string, unknown>[]) => void;
}) {
  const { dict } = useLanguage();
  const noun = itemNounLabel(itemNoun, dict);
  const empty = Object.fromEntries(
    fields.map((f) => [f.key, f.kind === "list" ? [] : ""]),
  );
  const set = (i: number, patch: Record<string, unknown>) =>
    onChange(value.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  return (
    <div className="grid gap-3">
      {value.map((row, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-line p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-fg-subtle">
              {noun} {i + 1}
            </span>
            <RemoveButton
              label={interpolate(dict.businessLogic.removeItemTemplate, { noun, n: String(i + 1) })}
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
            />
          </div>
          {fields.map((spec) => (
            <FieldControl
              key={spec.key}
              spec={spec}
              value={row?.[spec.key]}
              onChange={(v) => set(i, { [spec.key]: v })}
              dict={dict}
            />
          ))}
        </div>
      ))}
      <AddButton
        label={interpolate(dict.businessLogic.addItemTemplate, { noun })}
        onClick={() => onChange([...value, empty])}
      />
    </div>
  );
}

function RulesEditor({
  value,
  onChange,
}: {
  value: BusinessRule[];
  onChange: (v: BusinessRule[]) => void;
}) {
  const { dict } = useLanguage();
  const t = dict.businessLogic;
  const set = (i: number, patch: Partial<BusinessRule>) =>
    onChange(value.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const blank: BusinessRule = {
    id: "",
    statement: "",
    actor: "",
    conditions: [],
    outcome: "",
    exceptions: [],
    validations: [],
    related_requirements: [],
    derived: false,
  };
  return (
    <div className="grid gap-3">
      {value.map((rule, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-line p-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs text-fg-subtle">
              {rule.id || t.newRule}
            </span>
            <RemoveButton
              label={interpolate(t.removeRule, { n: String(i + 1) })}
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
            />
          </div>
          <label className="grid gap-1.5">
            <span className={labelClass}>{t.statementLabel}</span>
            <textarea
              rows={2}
              value={rule.statement}
              onChange={(e) => set(i, { statement: e.target.value })}
              className={`${inputClass} resize-y`}
            />
          </label>
          <label className="grid gap-1.5">
            <span className={labelClass}>{t.fieldLabelActor}</span>
            <input
              type="text"
              autoComplete="off"
              value={rule.actor}
              onChange={(e) => set(i, { actor: e.target.value })}
              className={inputClass}
            />
          </label>
          <label className="grid gap-1.5">
            <span className={labelClass}>{t.outcomeLabel}</span>
            <textarea
              rows={2}
              value={rule.outcome}
              onChange={(e) => set(i, { outcome: e.target.value })}
              className={`${inputClass} resize-y`}
            />
          </label>
          <div className="grid gap-1.5">
            <span className={labelClass}>{t.fieldLabelConditions}</span>
            <StringListEditor
              value={rule.conditions}
              onChange={(conditions) => set(i, { conditions })}
              itemNoun={t.itemNounCondition}
            />
          </div>
          <div className="grid gap-1.5">
            <span className={labelClass}>{t.exceptionsLabel}</span>
            <StringListEditor
              value={rule.exceptions}
              onChange={(exceptions) => set(i, { exceptions })}
              itemNoun={t.itemNounException}
            />
          </div>
          <div className="grid gap-1.5">
            <span className={labelClass}>{t.relatedRequirementsLabel}</span>
            <StringListEditor
              value={rule.related_requirements}
              onChange={(related_requirements) => set(i, { related_requirements })}
              itemNoun={t.itemNounRequirementId}
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-fg-muted">
            <input
              type="checkbox"
              className="size-4 accent-accent"
              checked={rule.derived}
              onChange={(e) => set(i, { derived: e.target.checked })}
            />
            {t.derivedLabel}
          </label>
        </div>
      ))}
      <AddButton label={t.addRule} onClick={() => onChange([...value, blank])} />
    </div>
  );
}

function TransitionsEditor({
  value,
  onChange,
}: {
  value: BLStateTransition[];
  onChange: (v: BLStateTransition[]) => void;
}) {
  const { dict } = useLanguage();
  const t = dict.businessLogic;
  const set = (i: number, patch: Partial<BLStateTransition>) =>
    onChange(value.map((tr, idx) => (idx === i ? { ...tr, ...patch } : tr)));
  const blank: BLStateTransition = {
    entity: "",
    from_state: "",
    to_state: "",
    trigger: "",
    actor: "",
    guards: [],
    effects: [],
    related_requirements: [],
  };
  const textField = (
    i: number,
    key: keyof BLStateTransition,
    label: string,
  ) => (
    <label className="grid gap-1.5">
      <span className={labelClass}>{label}</span>
      <input
        type="text"
        autoComplete="off"
        value={value[i][key] as string}
        onChange={(e) => set(i, { [key]: e.target.value })}
        className={inputClass}
      />
    </label>
  );
  return (
    <div className="grid gap-3">
      {value.map((tr, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-line p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-fg-subtle">
              {interpolate(t.newTransition, { n: String(i + 1) })}
            </span>
            <RemoveButton
              label={interpolate(t.removeTransition, { n: String(i + 1) })}
              onClick={() => onChange(value.filter((_, idx) => idx !== i))}
            />
          </div>
          {textField(i, "entity", t.entityLabel)}
          <div className="grid gap-2 sm:grid-cols-2">
            {textField(i, "from_state", t.fromStateLabel)}
            {textField(i, "to_state", t.toStateLabel)}
          </div>
          {textField(i, "trigger", t.triggerLabel)}
          {textField(i, "actor", t.fieldLabelActor)}
          <div className="grid gap-1.5">
            <span className={labelClass}>{t.guardsLabel}</span>
            <StringListEditor
              value={tr.guards}
              onChange={(guards) => set(i, { guards })}
              itemNoun={t.itemNounGuard}
            />
          </div>
          <div className="grid gap-1.5">
            <span className={labelClass}>{t.effectsLabel}</span>
            <StringListEditor
              value={tr.effects}
              onChange={(effects) => set(i, { effects })}
              itemNoun={t.itemNounEffect}
            />
          </div>
          <div className="grid gap-1.5">
            <span className={labelClass}>{t.relatedRequirementsLabel}</span>
            <StringListEditor
              value={tr.related_requirements}
              onChange={(related_requirements) => set(i, { related_requirements })}
              itemNoun={t.itemNounRequirementId}
            />
          </div>
        </div>
      ))}
      <AddButton label={t.addTransition} onClick={() => onChange([...value, blank])} />
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
    case "prose":
      return (
        <ProseEditor
          value={value as string}
          onChange={onChange as (v: string) => void}
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
          value={(value as Record<string, unknown>[]) ?? []}
          onChange={onChange as (v: Record<string, unknown>[]) => void}
        />
      );
    case "rules":
      return (
        <RulesEditor
          value={(value as BusinessRule[]) ?? []}
          onChange={onChange as (v: BusinessRule[]) => void}
        />
      );
    case "transitions":
      return (
        <TransitionsEditor
          value={(value as BLStateTransition[]) ?? []}
          onChange={onChange as (v: BLStateTransition[]) => void}
        />
      );
  }
}
