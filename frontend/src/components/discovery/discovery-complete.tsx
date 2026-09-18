"use client";

import { CheckIcon } from "@radix-ui/react-icons";

import type { Project } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { ArtifactApprovedNotice } from "@/components/workspace/artifact-approved-notice";
import { useLanguage } from "@/lib/i18n";

interface Props {
  project: Project;
  onEdit: () => void;
}

export function DiscoveryComplete({ project, onEdit }: Props) {
  const { dict } = useLanguage();
  const { questions, answers } = project.discovery;

  return (
    <div className="grid gap-8">
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full border border-accent/30 bg-accent/10 text-accent"
        >
          <CheckIcon className="size-4" />
        </span>
        <div className="grid gap-1">
          <h2 className="text-lg font-semibold text-fg">{dict.discovery.completeTitle}</h2>
          <p className="text-sm leading-relaxed text-fg-muted">
            {dict.discovery.completeBody}
          </p>
        </div>
      </div>

      <dl className="divide-y divide-line overflow-hidden rounded-xl border border-line">
        {questions.map((question) => {
          const answer = answers[question.id];
          const display = Array.isArray(answer)
            ? answer.join(", ")
            : (answer ?? "—");
          return (
            <div key={question.id} className="grid gap-1 bg-bg px-4 py-4">
              <dt className="text-sm font-medium text-fg">{question.question}</dt>
              <dd className="text-sm text-fg-muted">{display}</dd>
            </div>
          );
        })}
      </dl>

      <ArtifactApprovedNotice
        summary={dict.discovery.nextSummary}
        nextLabel={project.stage === "discovery" ? dict.discovery.continueToBlueprint : dict.discovery.openBlueprint}
        nextHref={`/projects/${project.slug}/blueprint`}
      />

      {project.stage === "discovery" ? (
        <Button variant="outline" size="sm" className="w-fit" onClick={onEdit}>
          {dict.discovery.editAnswers}
        </Button>
      ) : (
        <p className="text-sm text-fg-subtle">
          {dict.discovery.locked}
        </p>
      )}
    </div>
  );
}
