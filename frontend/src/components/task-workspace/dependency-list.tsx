"use client";

import Link from "next/link";
import { CheckCircledIcon, CircleIcon } from "@radix-ui/react-icons";

import type { DependencyState, TaskStatus } from "@/lib/api/types";
import { useLanguage, type Dictionary } from "@/lib/i18n";

function statusText(status: DependencyState["status"], dict: Dictionary): string {
  return status in dict.taskStatus
    ? dict.taskStatus[status as TaskStatus]
    : dict.taskWorkspace.unknownStatus;
}

export function DependencyList({
  slug,
  dependencies,
}: {
  slug: string;
  dependencies: DependencyState[];
}) {
  const { dict } = useLanguage();

  if (dependencies.length === 0) {
    return (
      <p className="text-sm text-fg-subtle">
        {dict.taskWorkspace.noDependencies}
      </p>
    );
  }

  return (
    <ul className="grid gap-2">
      {dependencies.map((dep) => {
        const done = dep.status === "completed";
        return (
          <li
            key={dep.id}
            className="flex items-start gap-2.5 rounded-md border border-line bg-bg p-3 text-sm"
          >
            {done ? (
              <CheckCircledIcon
                className="mt-0.5 size-4 shrink-0 text-accent"
                aria-hidden
              />
            ) : (
              <CircleIcon
                className="mt-0.5 size-4 shrink-0 text-fg-subtle"
                aria-hidden
              />
            )}
            <div className="min-w-0">
              <Link
                href={`/projects/${slug}/roadmap/tasks/${dep.id}`}
                className="font-medium text-fg underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <span className="font-mono text-xs text-fg-subtle">{dep.id}</span>{" "}
                {dep.title}
              </Link>
              <p className="text-fg-subtle">
                {done ? dict.taskStatus.completed : statusText(dep.status, dict)}
                {dep.expected_output ? ` — ${dep.expected_output}` : ""}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
