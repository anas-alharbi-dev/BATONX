import { ExclamationTriangleIcon } from "@radix-ui/react-icons";

/**
 * The real Software artifact chain (``projects/dependencies.py``'s
 * ``ARTIFACT_CHAIN``, staleable subset): editing an approved artifact here
 * is exactly what the backend's own stale-propagation watches for. This
 * mapping is display-only — copy, not enforcement; the backend computes and
 * owns the actual propagation.
 */
const DOWNSTREAM: Record<string, string[]> = {
  blueprint: ["Business Logic", "Architecture", "Roadmap"],
  business_logic: ["Architecture", "Roadmap"],
  architecture: ["Roadmap"],
};

function formatList(items: string[]): string {
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

/**
 * Shown once, right when a user starts editing an already-approved artifact
 * that has real downstream dependents — a concise heads-up, not a modal wall
 * of text. Artifacts with nothing downstream (Roadmap) render nothing.
 */
export function ImpactNotice({ artifact }: { artifact: keyof typeof DOWNSTREAM }) {
  const downstream = DOWNSTREAM[artifact];
  if (!downstream || downstream.length === 0) return null;
  return (
    <p className="mt-2 flex items-start gap-2 rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-relaxed text-warning">
      <ExclamationTriangleIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>
        Changing this may require {formatList(downstream)} to be reviewed again once saved.
      </span>
    </p>
  );
}
