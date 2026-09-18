import { CheckIcon } from "@radix-ui/react-icons";

const STEPS: { label: string; state: "done" | "current" | "upcoming" }[] = [
  { label: "Discovery", state: "done" },
  { label: "Blueprint", state: "done" },
  { label: "Roadmap", state: "current" },
  { label: "Tasks / Build", state: "upcoming" },
  { label: "Delivery Readiness", state: "upcoming" },
];

/**
 * A quiet, static preview of the real Project Journey — not illustrative
 * marketing art, the product's own visual language shown at rest. Reuses
 * the same workflow-status tokens the live Journey rail uses.
 */
export function AuthJourneyPreview() {
  return (
    <div className="w-full max-w-xs px-8">
      <p className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-fg-subtle">
        You lead. BATONX orchestrates.
      </p>
      <ol className="mt-6">
        {STEPS.map((step, i) => (
          <li key={step.label} className="relative flex gap-3 pb-6 last:pb-0">
            {i < STEPS.length - 1 && (
              <span
                aria-hidden
                className={
                  "absolute left-[9px] top-5 h-[calc(100%-4px)] w-px " +
                  (step.state === "done" ? "bg-accent/50" : "bg-line-strong")
                }
              />
            )}
            <span
              aria-hidden
              className={
                "relative grid size-5 shrink-0 place-items-center rounded-full border font-mono text-[10px] " +
                (step.state === "done"
                  ? "border-completed/50"
                  : step.state === "current"
                    ? "border-active/60 ring-2 ring-active/20"
                    : "border-line-strong bg-bg")
              }
            >
              {step.state === "done" ? (
                <CheckIcon className="size-2.5 text-fg-inverse" />
              ) : step.state === "current" ? (
                <span className="size-2 rounded-full bg-active" />
              ) : (
                <span className="text-fg-subtle">{i + 1}</span>
              )}
              {step.state === "done" && (
                <span className="absolute inset-0 -z-10 rounded-full bg-completed" />
              )}
            </span>
            <span
              className={
                "text-[13px] font-medium " +
                (step.state === "upcoming" ? "text-fg-subtle" : "text-fg")
              }
            >
              {step.label}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
