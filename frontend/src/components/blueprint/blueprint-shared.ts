import type { BlueprintContent } from "@/lib/api/types";

export type SectionKey = keyof BlueprintContent;
export type SectionKind = "prose" | "list" | "roles" | "requirements" | "flows";

export interface SectionDescriptor {
  key: SectionKey;
  label: string;
  kind: SectionKind;
  /** noun for the "Add …" control in list-like editors */
  itemNoun?: string;
}

/** Order matches the approved product spec. */
export const SECTIONS: SectionDescriptor[] = [
  { key: "product_summary", label: "Product Summary", kind: "prose" },
  { key: "problem", label: "Problem", kind: "prose" },
  { key: "solution", label: "Solution", kind: "prose" },
  { key: "target_users", label: "Target Users", kind: "list", itemNoun: "user group" },
  { key: "user_roles", label: "User Roles", kind: "roles" },
  { key: "core_features", label: "Core Features", kind: "list", itemNoun: "feature" },
  { key: "mvp_features", label: "MVP Features", kind: "list", itemNoun: "feature" },
  { key: "future_features", label: "Future Features", kind: "list", itemNoun: "feature" },
  {
    key: "functional_requirements",
    label: "Functional Requirements",
    kind: "requirements",
  },
  { key: "business_rules", label: "Business Rules", kind: "list", itemNoun: "rule" },
  { key: "user_flows", label: "User Flows", kind: "flows" },
  { key: "out_of_scope", label: "Out of Scope", kind: "list", itemNoun: "item" },
];

export const PRIORITIES = ["must", "should", "could"] as const;
