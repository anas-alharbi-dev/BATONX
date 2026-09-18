import type { ArchitectureContent } from "@/lib/api/types";

export type SectionKey = keyof ArchitectureContent;
export type SectionKind = "fields" | "list" | "objects" | "entities";

export interface FieldSpec {
  key: string;
  label: string;
  multiline?: boolean;
  /** render as a "Why this?" disclosure in read-only mode */
  isWhy?: boolean;
}

export interface SectionDescriptor {
  key: SectionKey;
  label: string;
  kind: SectionKind;
  /** for "fields" and "objects" */
  fields?: FieldSpec[];
  /** for "list" and "objects" */
  itemNoun?: string;
  /** for "fields": the field shown as the headline value in read-only mode */
  headlineKey?: string;
}

const CHOICE_WHY = (headline = "choice"): FieldSpec[] => [
  { key: headline, label: headline === "approach" ? "Approach" : "Choice" },
  { key: "why", label: "Why this?", multiline: true, isWhy: true },
];

/** Order matches the Phase 3 brief. */
export const SECTIONS: SectionDescriptor[] = [
  {
    key: "overview",
    label: "Overview",
    kind: "fields",
    headlineKey: "style",
    fields: [
      { key: "style", label: "Style" },
      { key: "summary", label: "Summary", multiline: true },
    ],
  },
  { key: "frontend", label: "Frontend", kind: "fields", headlineKey: "choice", fields: CHOICE_WHY() },
  { key: "backend", label: "Backend", kind: "fields", headlineKey: "choice", fields: CHOICE_WHY() },
  { key: "database", label: "Database", kind: "fields", headlineKey: "choice", fields: CHOICE_WHY() },
  {
    key: "auth",
    label: "Authentication & Authorization",
    kind: "fields",
    headlineKey: "approach",
    fields: CHOICE_WHY("approach"),
  },
  {
    key: "components",
    label: "Core Components",
    kind: "objects",
    itemNoun: "component",
    fields: [
      { key: "name", label: "Name" },
      { key: "responsibility", label: "Responsibility", multiline: true },
    ],
  },
  {
    key: "api_areas",
    label: "API Areas",
    kind: "objects",
    itemNoun: "API area",
    fields: [
      { key: "name", label: "Name" },
      { key: "purpose", label: "Purpose", multiline: true },
    ],
  },
  { key: "data_model", label: "Conceptual Data Model", kind: "entities" },
  {
    key: "integrations",
    label: "External Integrations",
    kind: "objects",
    itemNoun: "integration",
    fields: [
      { key: "name", label: "Name" },
      { key: "purpose", label: "Purpose", multiline: true },
      { key: "why", label: "Why this?", multiline: true, isWhy: true },
    ],
  },
  { key: "security", label: "Security Considerations", kind: "list", itemNoun: "consideration" },
  {
    key: "deployment",
    label: "Deployment & Infrastructure",
    kind: "fields",
    headlineKey: "approach",
    fields: CHOICE_WHY("approach"),
  },
  {
    key: "key_decisions",
    label: "Key Technical Decisions",
    kind: "objects",
    itemNoun: "decision",
    fields: [
      { key: "decision", label: "Decision" },
      { key: "rationale", label: "Rationale", multiline: true },
    ],
  },
  { key: "constraints", label: "Constraints", kind: "list", itemNoun: "constraint" },
];
