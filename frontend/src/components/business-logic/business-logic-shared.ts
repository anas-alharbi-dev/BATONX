import type { BusinessLogicContent } from "@/lib/api/types";

export type SectionKey = keyof BusinessLogicContent;
export type SectionKind = "prose" | "list" | "objects" | "rules" | "transitions";
export type FieldKind = "text" | "textarea" | "list";

export interface FieldSpec {
  key: string;
  label: string;
  kind: FieldKind;
  itemNoun?: string;
}

export interface SectionDescriptor {
  key: SectionKey;
  label: string;
  kind: SectionKind;
  fields?: FieldSpec[];
  itemNoun?: string;
}

const REQ: FieldSpec = {
  key: "related_requirements",
  label: "Related Requirements",
  kind: "list",
  itemNoun: "requirement id",
};

export const SECTIONS: SectionDescriptor[] = [
  { key: "summary", label: "Behavioral Summary", kind: "prose" },
  {
    key: "actors",
    label: "Roles & Actors",
    kind: "objects",
    itemNoun: "actor",
    fields: [
      { key: "name", label: "Name", kind: "text" },
      { key: "description", label: "What they do", kind: "textarea" },
    ],
  },
  {
    key: "permissions",
    label: "Permissions",
    kind: "objects",
    itemNoun: "permission",
    fields: [
      { key: "actor", label: "Actor", kind: "text" },
      { key: "can", label: "Can", kind: "list", itemNoun: "action" },
      { key: "conditions", label: "Conditions", kind: "list", itemNoun: "condition" },
    ],
  },
  { key: "business_rules", label: "Business Rules", kind: "rules" },
  {
    key: "validations",
    label: "Business Validations",
    kind: "objects",
    itemNoun: "validation",
    fields: [
      { key: "rule", label: "Rule", kind: "textarea" },
      { key: "applies_to", label: "Applies to", kind: "text" },
      REQ,
    ],
  },
  {
    key: "approval_flows",
    label: "Approval Flows",
    kind: "objects",
    itemNoun: "flow",
    fields: [
      { key: "name", label: "Name", kind: "text" },
      { key: "approver", label: "Approver", kind: "text" },
      { key: "steps", label: "Steps", kind: "list", itemNoun: "step" },
      { key: "conditions", label: "Conditions", kind: "list", itemNoun: "condition" },
      REQ,
    ],
  },
  { key: "state_transitions", label: "State Transitions", kind: "transitions" },
  {
    key: "edge_cases",
    label: "Edge Cases & Exceptions",
    kind: "objects",
    itemNoun: "edge case",
    fields: [
      { key: "scenario", label: "Scenario", kind: "textarea" },
      { key: "expected_behavior", label: "Expected behavior", kind: "textarea" },
      REQ,
    ],
  },
  {
    key: "open_questions",
    label: "Open Questions",
    kind: "list",
    itemNoun: "question",
  },
];
