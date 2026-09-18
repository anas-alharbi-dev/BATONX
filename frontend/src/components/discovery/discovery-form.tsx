"use client";

import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { useMutation } from "@tanstack/react-query";

import { api, ApiRequestError } from "@/lib/api/client";
import type {
  DiscoveryAnswer,
  DiscoveryQuestion,
  Project,
} from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { interpolate, useLanguage } from "@/lib/i18n";

import {
  MultiSelectQuestion,
  SingleSelectQuestion,
  TextQuestion,
} from "./question-fields";

function isAnswered(question: DiscoveryQuestion, value: DiscoveryAnswer | undefined) {
  if (question.type === "multi_select") {
    return (
      Array.isArray(value) &&
      value.length > 0 &&
      value.every((item) => question.options.includes(item))
    );
  }
  if (question.type === "single_select") {
    return typeof value === "string" && question.options.includes(value);
  }
  return typeof value === "string" && value.trim().length > 0;
}

interface Props {
  project: Project;
  onCompleted: (project: Project) => void;
}

export function DiscoveryForm({ project, onCompleted }: Props) {
  const { dict } = useLanguage();
  const questions = project.discovery.questions;

  const [answers, setAnswers] = useState<Record<string, DiscoveryAnswer>>(
    () => ({ ...project.discovery.answers }),
  );
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [topError, setTopError] = useState<string | null>(null);

  const answeredCount = useMemo(
    () => questions.filter((q) => isAnswered(q, answers[q.id])).length,
    [questions, answers],
  );
  const remaining = questions.length - answeredCount;

  const mutation = useMutation({
    mutationFn: () => api.submitDiscoveryAnswers(project.slug, answers),
    onSuccess: (updated) => onCompleted(updated),
    onError: (error) => {
      const err = error as ApiRequestError;
      if (err.code === "incomplete_answers") {
        const missing = (err.details as { missing?: string[] })?.missing ?? [];
        setFieldErrors(
          Object.fromEntries(
            missing.map((id) => [id, dict.discovery.answerToContinue]),
          ),
        );
        focusFirst(missing[0]);
      } else if (err.code === "invalid_answer") {
        const id = (err.details as { question_id?: string })?.question_id;
        if (id) {
          setFieldErrors({ [id]: dict.discovery.invalidAnswer });
          focusFirst(id);
        } else {
          setTopError(err.message);
        }
      } else {
        setTopError(err.message);
      }
    },
  });

  function focusFirst(id?: string) {
    if (!id) return;
    const el = document.getElementById(`field-${id}`);
    document.getElementById(`q-${id}`)?.scrollIntoView({ block: "center" });
    (el as HTMLElement | null)?.focus?.();
  }

  function setAnswer(id: string, value: DiscoveryAnswer) {
    setAnswers((prev) => ({ ...prev, [id]: value }));
    setFieldErrors((prev) => {
      if (!prev[id]) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }

  function handleSubmit() {
    setTopError(null);
    const missing = questions
      .filter((q) => !isAnswered(q, answers[q.id]))
      .map((q) => q.id);

    if (missing.length > 0) {
      setFieldErrors(
        Object.fromEntries(
          missing.map((id) => [id, dict.discovery.answerToContinue]),
        ),
      );
      focusFirst(missing[0]);
      return;
    }

    mutation.mutate();
  }

  const pct = Math.round((answeredCount / questions.length) * 100);

  return (
    <form
      className="grid gap-8"
      onSubmit={(event) => {
        event.preventDefault();
        handleSubmit();
      }}
    >
      <div className="grid gap-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-fg-muted">{dict.discovery.progress}</span>
          <span className="tabular text-fg-muted" aria-live="polite">
            {interpolate(dict.discovery.answeredCount, {
              a: String(answeredCount),
              b: String(questions.length),
            })}
          </span>
        </div>
        <div
          className="h-1.5 overflow-hidden rounded-full bg-surface-hover"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={questions.length}
          aria-valuenow={answeredCount}
        >
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-300 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {topError ? (
        <p
          role="alert"
          className="rounded-md border border-danger/25 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {topError}
        </p>
      ) : null}

      <ol className="grid gap-8 stagger">
        {questions.map((question, index) => (
          <li
            key={question.id}
            id={`q-${question.id}`}
            style={{ "--i": index } as CSSProperties}
            className="scroll-mt-24"
          >
            <div className="mb-2 font-mono text-xs text-fg-subtle">
              {interpolate(dict.discovery.questionOf, {
                a: String(index + 1),
                b: String(questions.length),
              })}
            </div>
            {question.type === "text" && (
              <TextQuestion
                question={question}
                value={answers[question.id]}
                error={fieldErrors[question.id]}
                onChange={(value) => setAnswer(question.id, value)}
              />
            )}
            {question.type === "single_select" && (
              <SingleSelectQuestion
                question={question}
                value={answers[question.id]}
                error={fieldErrors[question.id]}
                onChange={(value) => setAnswer(question.id, value)}
              />
            )}
            {question.type === "multi_select" && (
              <MultiSelectQuestion
                question={question}
                value={answers[question.id]}
                error={fieldErrors[question.id]}
                onChange={(value) => setAnswer(question.id, value)}
              />
            )}
          </li>
        ))}
      </ol>

      <div className="sticky bottom-0 -mx-4 flex flex-col gap-3 border-t border-line bg-bg/90 px-4 py-4 backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-fg-muted" aria-live="polite">
          {remaining === 0
            ? dict.discovery.allAnswered
            : interpolate(dict.discovery.questionsLeft, { n: String(remaining) })}
        </p>
        <Button type="submit" size="lg" loading={mutation.isPending}>
          {mutation.isPending ? dict.discovery.savingAnswers : dict.discovery.saveAndContinue}
        </Button>
      </div>
    </form>
  );
}
