"use client";

import type { ArchitectureContent } from "@/lib/api/types";

import { SECTIONS, type SectionKey } from "./architecture-shared";
import { ArchitectureSection } from "./architecture-section";

interface Props {
  content: ArchitectureContent;
  editable: boolean;
  editingKey: SectionKey | null;
  saving: boolean;
  editError?: string | null;
  onStartEdit: (key: SectionKey) => void;
  onCancel: () => void;
  onSave: (key: SectionKey, value: unknown) => void;
}

export function ArchitectureSections({
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
        <ArchitectureSection
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
