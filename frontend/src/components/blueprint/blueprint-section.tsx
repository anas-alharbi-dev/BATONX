"use client";

import { useState } from "react";
import { Pencil1Icon } from "@radix-ui/react-icons";

import type { BlueprintContent } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";

import type { SectionDescriptor, SectionKey } from "./blueprint-shared";
import { SectionEditor } from "./section-editors";
import { SectionReadonly } from "./section-readonly";

interface Props {
  section: SectionDescriptor;
  content: BlueprintContent;
  /** section-level editing is offered at all */
  editable: boolean;
  /** this section is the one currently open for editing */
  isEditing: boolean;
  /** another section is open — hide this one's Edit affordance */
  otherEditing: boolean;
  saving: boolean;
  error?: string | null;
  onStartEdit: (key: SectionKey) => void;
  onCancel: () => void;
  onSave: (key: SectionKey, value: unknown) => void;
}

export function BlueprintSection({
  section,
  content,
  editable,
  isEditing,
  otherEditing,
  saving,
  error,
  onStartEdit,
  onCancel,
  onSave,
}: Props) {
  const { dict } = useLanguage();
  const current = content[section.key];
  const [draft, setDraft] = useState<unknown>(current);
  const label = dict.blueprint.sections[section.key as keyof typeof dict.blueprint.sections] ?? section.label;

  function startEdit() {
    setDraft(structuredClone(current));
    onStartEdit(section.key);
  }

  return (
    <section
      id={`section-${section.key}`}
      className="scroll-mt-28 border-t border-line py-6 first:border-t-0 first:pt-0"
    >
      <div className="mb-3 flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-fg-subtle">
          {label}
        </h2>
        {editable && !isEditing && !otherEditing && (
          <Button variant="ghost" size="sm" onClick={startEdit}>
            <Pencil1Icon className="size-3.5" aria-hidden />
            {dict.common.edit}
          </Button>
        )}
      </div>

      {isEditing ? (
        <div className="grid gap-3">
          <SectionEditor kind={section.kind} value={draft} onChange={setDraft} />
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <div className="flex gap-3">
            <Button
              size="sm"
              loading={saving}
              onClick={() => onSave(section.key, draft)}
            >
              {dict.softwareShared.saveSection}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onCancel}
              disabled={saving}
            >
              {dict.common.cancel}
            </Button>
          </div>
        </div>
      ) : (
        <SectionReadonly kind={section.kind} value={current} />
      )}
    </section>
  );
}
