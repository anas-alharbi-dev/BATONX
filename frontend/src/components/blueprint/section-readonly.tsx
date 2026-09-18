import { Badge } from "@/components/ui/badge";
import type {
  FunctionalRequirement,
  UserFlow,
  UserRole,
} from "@/lib/api/types";
import { useLanguage } from "@/lib/i18n";

import type { SectionKind } from "./blueprint-shared";

const priorityTone = {
  must: "danger",
  should: "accent",
  could: "neutral",
} as const;

export function SectionReadonly({
  kind,
  value,
}: {
  kind: SectionKind;
  value: unknown;
}) {
  const { dict } = useLanguage();
  if (kind === "prose") {
    return (
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg-muted">
        {(value as string) || "—"}
      </p>
    );
  }

  if (kind === "list") {
    const items = (value as string[]) ?? [];
    if (items.length === 0) return <p className="text-sm text-fg-subtle">—</p>;
    return (
      <ul className="grid list-disc gap-1.5 ps-5 text-sm leading-relaxed text-fg-muted">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    );
  }

  if (kind === "roles") {
    const roles = (value as UserRole[]) ?? [];
    return (
      <dl className="grid gap-3">
        {roles.map((role, i) => (
          <div key={i} className="grid gap-0.5">
            <dt className="text-sm font-medium text-fg">{role.name}</dt>
            <dd className="text-sm leading-relaxed text-fg-muted">
              {role.description}
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  if (kind === "requirements") {
    const reqs = (value as FunctionalRequirement[]) ?? [];
    return (
      <ul className="grid gap-2.5">
        {reqs.map((req) => (
          <li key={req.id} className="flex items-start gap-3 text-sm">
            <span className="mt-0.5 shrink-0 font-mono text-xs text-fg-subtle">
              {req.id}
            </span>
            <Badge tone={priorityTone[req.priority]} className="mt-px shrink-0">
              {dict.blueprint.priority[req.priority]}
            </Badge>
            <span className="leading-relaxed text-fg-muted">{req.text}</span>
          </li>
        ))}
      </ul>
    );
  }

  // flows
  const flows = (value as UserFlow[]) ?? [];
  return (
    <div className="grid gap-4">
      {flows.map((flow, i) => (
        <div key={i} className="grid gap-1.5">
          <h4 className="text-sm font-medium text-fg">{flow.name}</h4>
          <ol className="grid list-decimal gap-1 ps-5 text-sm leading-relaxed text-fg-muted">
            {flow.steps.map((step, j) => (
              <li key={j}>{step}</li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}
