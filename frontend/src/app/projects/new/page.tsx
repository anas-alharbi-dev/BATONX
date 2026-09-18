"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeftIcon, ArrowRightIcon } from "@radix-ui/react-icons";

import { AiUnconfiguredNotice } from "@/components/feedback/ai-unconfigured-notice";
import { Button } from "@/components/ui/button";
import { inputClass } from "@/components/ui/editor-primitives";
import { api, ApiRequestError } from "@/lib/api/client";
import { useLanguage, type Dictionary } from "@/lib/i18n";
import type { DataGoal } from "@/lib/api/types";

type Step = "choose" | "software" | "data";

/**
 * The real Create Project experience (Phase P-3) — inside the authenticated
 * product, not the public Landing. Two decisions in sequence: project type,
 * then the one thing BATONX actually needs to start (an idea, or an
 * analysis goal) — never a dataset upload here (Data starts at the Data
 * Brief; uploading a source is a later, real workflow step).
 */
export default function NewProjectPage() {
  const [step, setStep] = useState<Step>("choose");
  return (
    <div className="mx-auto max-w-2xl px-4 py-10 safe-px lg:px-8">
      {step === "choose" && <ChooseType onChoose={setStep} />}
      {step === "software" && <SoftwareForm onBack={() => setStep("choose")} />}
      {step === "data" && <DataForm onBack={() => setStep("choose")} />}
    </div>
  );
}

function ChooseType({ onChoose }: { onChoose: (step: Step) => void }) {
  const { dict } = useLanguage();
  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight text-fg">{dict.createProject.chooseTitle}</h1>
      <p className="mt-1.5 text-sm text-fg-muted">{dict.createProject.chooseSubtitle}</p>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <TypeCard
          title={dict.createProject.softwareCardTitle}
          description={dict.createProject.softwareCardDesc}
          choose={dict.createProject.choose}
          onClick={() => onChoose("software")}
        />
        <TypeCard
          title={dict.createProject.dataCardTitle}
          description={dict.createProject.dataCardDesc}
          choose={dict.createProject.choose}
          onClick={() => onChoose("data")}
        />
      </div>
    </div>
  );
}

function TypeCard({
  title,
  description,
  choose,
  onClick,
}: {
  title: string;
  description: string;
  choose: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-col items-start gap-2 rounded-lg border border-line bg-surface p-5 text-start transition-colors hover:border-accent/50 hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <span className="text-[15px] font-medium text-fg">{title}</span>
      <span className="text-sm leading-relaxed text-fg-muted">{description}</span>
      <span className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-accent">
        {choose}
        <ArrowRightIcon aria-hidden className="size-3.5 transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5" />
      </span>
    </button>
  );
}

function BackButton({ onBack, label }: { onBack: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onBack}
      className="inline-flex items-center gap-1.5 text-sm text-fg-subtle transition-colors hover:text-fg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <ArrowLeftIcon aria-hidden className="size-3.5 rtl:-scale-x-100" />
      {label}
    </button>
  );
}

function SoftwareForm({ onBack }: { onBack: () => void }) {
  const { dict } = useLanguage();
  const router = useRouter();
  const [idea, setIdea] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.createProject(idea.trim()),
    onSuccess: (data) => router.push(`/projects/${data.project.slug}/discovery`),
  });

  const apiError = mutation.error as ApiRequestError | null;
  const missingKey = apiError?.code === "missing_api_key";

  function submit() {
    if (!idea.trim()) {
      setValidationError(dict.createProject.softwareValidation);
      return;
    }
    setValidationError(null);
    mutation.mutate();
  }

  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <BackButton onBack={onBack} label={dict.createProject.changeType} />
      <h1 className="text-xl font-semibold tracking-tight text-fg">{dict.createProject.softwareQuestion}</h1>

      <div className="grid gap-1.5">
        <textarea
          rows={4}
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder={dict.createProject.softwarePlaceholder}
          className={`${inputClass} resize-y`}
        />
        <p className="text-[13px] text-fg-subtle">{dict.createProject.softwareHint}</p>
      </div>

      <div aria-live="polite" className="min-h-5 text-sm text-danger">
        {validationError}
        {!validationError && apiError && !missingKey && apiError.message}
      </div>

      {missingKey && <AiUnconfiguredNotice />}

      <Button type="submit" size="lg" loading={mutation.isPending} className="w-full sm:w-auto">
        {mutation.isPending ? dict.createProject.analyzing : dict.createProject.startSoftware}
      </Button>
    </form>
  );
}

function dataGoals(dict: Dictionary): { value: DataGoal; label: string; description: string }[] {
  return (Object.keys(dict.createProject.goals) as DataGoal[]).map((value) => ({
    value,
    label: dict.createProject.goals[value].label,
    description: dict.createProject.goals[value].description,
  }));
}

function DataForm({ onBack }: { onBack: () => void }) {
  const { dict } = useLanguage();
  const router = useRouter();
  const [goal, setGoal] = useState<DataGoal>("analytics");
  const [idea, setIdea] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.createProject(idea.trim(), { project_type: "data", data_goal: goal }),
    onSuccess: (data) => router.push(`/projects/${data.project.slug}/data-overview`),
  });

  const apiError = mutation.error as ApiRequestError | null;
  const missingKey = apiError?.code === "missing_api_key";

  function submit() {
    if (!idea.trim()) {
      setValidationError(dict.createProject.dataValidation);
      return;
    }
    setValidationError(null);
    mutation.mutate();
  }

  return (
    <form
      className="grid gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <BackButton onBack={onBack} label={dict.createProject.changeType} />
      <h1 className="text-xl font-semibold tracking-tight text-fg">{dict.createProject.dataQuestion}</h1>

      <fieldset className="grid gap-2">
        <legend className="text-sm font-medium text-fg">{dict.createProject.goalLabel}</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {dataGoals(dict).map((g) => (
            <label
              key={g.value}
              className={
                "flex cursor-pointer flex-col gap-0.5 rounded-md border p-3 transition-colors " +
                (goal === g.value
                  ? "border-accent bg-accent-soft"
                  : "border-line bg-surface hover:border-line-strong")
              }
            >
              <span className="flex items-center gap-2 text-sm font-medium text-fg">
                <input
                  type="radio"
                  name="data-goal"
                  value={g.value}
                  checked={goal === g.value}
                  onChange={() => setGoal(g.value)}
                  className="size-3.5 accent-accent"
                />
                {g.label}
              </span>
              <span className="ps-6 text-[12px] text-fg-subtle">{g.description}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-1.5">
        <label htmlFor="data-idea" className="text-sm font-medium text-fg">
          {dict.createProject.dataIdeaLabel}
        </label>
        <textarea
          id="data-idea"
          rows={4}
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder={dict.createProject.dataPlaceholder}
          className={`${inputClass} resize-y`}
        />
        <p className="text-[13px] text-fg-subtle">{dict.createProject.dataHint}</p>
      </div>

      <div aria-live="polite" className="min-h-5 text-sm text-danger">
        {validationError}
        {!validationError && apiError && !missingKey && apiError.message}
      </div>

      {missingKey && <AiUnconfiguredNotice />}

      <Button type="submit" size="lg" loading={mutation.isPending} className="w-full sm:w-auto">
        {mutation.isPending ? dict.createProject.analyzing : dict.createProject.startData}
      </Button>
    </form>
  );
}
