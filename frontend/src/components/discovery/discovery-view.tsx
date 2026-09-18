"use client";

import { useState } from "react";

import type { Project } from "@/lib/api/types";
import { useLanguage } from "@/lib/i18n";

import { DiscoveryComplete } from "./discovery-complete";
import { DiscoveryForm } from "./discovery-form";

interface Props {
  initialProject: Project;
}

export function DiscoveryView({ initialProject }: Props) {
  const { dict } = useLanguage();
  const [project, setProject] = useState(initialProject);
  const [editing, setEditing] = useState(false);

  const showComplete = !!project.discovery.answered_at && !editing;
  const ideaPreview = project.original_idea;

  return (
    <>
      <div className="mb-8 grid gap-3">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-fg-subtle">
          {dict.softwareShared.stepPrefix} 1 &middot; {dict.journeySoftware.discovery.label}
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          {showComplete ? dict.journeySoftware.discovery.label : dict.discovery.titleQuestions}
        </h1>
        <p className="text-sm text-fg-muted">
          {dict.journeySoftware.discovery.purpose}
        </p>
        <p className="rounded-md border border-line bg-surface/60 px-3.5 py-2.5 text-sm leading-relaxed text-fg-muted">
          {ideaPreview}
        </p>
        {!showComplete && (
          <p className="text-sm leading-relaxed text-fg-muted">
            {dict.discovery.answerAllHint}
          </p>
        )}
      </div>

      {showComplete ? (
        <DiscoveryComplete project={project} onEdit={() => setEditing(true)} />
      ) : (
        <DiscoveryForm
          project={project}
          onCompleted={(updated) => {
            setProject(updated);
            setEditing(false);
          }}
        />
      )}
    </>
  );
}
