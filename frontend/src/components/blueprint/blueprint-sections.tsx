"use client";

import type { BlueprintContent } from "@/lib/api/types";

import { SECTIONS, type SectionKey } from "./blueprint-shared";
import { BlueprintSection } from "./blueprint-section";

interface Props {
  content: BlueprintContent;
  editable: boolean;
  editingKey: SectionKey | null;
  saving: boolean;
  /** validation error for the section currently being edited */
  editError?: string | null;
  onStartEdit: (key: SectionKey) => void;
  onCancel: () => void;
  onSave: (key: SectionKey, value: unknown) => void;
}

export function BlueprintSections({
  content,
  editable,
  editingKey,
  saving,
  editError,
  onStartEdit,
  onCancel,
  onSave,
}: Props) {
  return (
    <div className="rounded-xl border border-line bg-surface/40 p-5 sm:p-7">
      {SECTIONS.map((section) => (
        <BlueprintSection
          key={section.key}
          section={section}
          content={content}
          editable={editable}
          isEditing={editingKey === section.key}
          otherEditing={editingKey !== null && editingKey !== section.key}
          saving={saving && editingKey === section.key}
          error={editingKey === section.key ? editError : null}
          onStartEdit={onStartEdit}
          onCancel={onCancel}
          onSave={onSave}
        />
      ))}
    </div>
  );
}
