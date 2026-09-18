"use client";

import type { DiscoveryAnswer, DiscoveryQuestion } from "@/lib/api/types";
import { Fieldset } from "@/components/ui/field";
import { useLanguage } from "@/lib/i18n";

interface BaseProps {
  question: DiscoveryQuestion;
  value: DiscoveryAnswer | undefined;
  error?: string | null;
  onChange: (value: DiscoveryAnswer) => void;
}

const optionRow =
  "flex items-start gap-3 rounded-md border border-line bg-bg-subtle px-3.5 py-3 " +
  "cursor-pointer transition-colors duration-150 hover:border-line-strong " +
  "has-[:checked]:border-accent has-[:checked]:bg-accent/[0.06] " +
  "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent";

export function TextQuestion({ question, value, error, onChange }: BaseProps) {
  const fieldId = `field-${question.id}`;
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;
  return (
    <div className="grid gap-2">
      <label htmlFor={fieldId} className="text-sm font-medium text-fg">
        {question.question}
      </label>
      <p id={hintId} className="-mt-1 text-sm text-fg-muted">
        {question.why_it_matters}
      </p>
      <textarea
        id={fieldId}
        name={fieldId}
        rows={3}
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={error ? `${hintId} ${errorId}` : hintId}
        aria-invalid={error ? true : undefined}
        className="w-full resize-y rounded-md border border-line bg-bg-subtle px-3.5 py-2.5 text-sm text-fg placeholder:text-fg-subtle transition-colors duration-150 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
      />
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function SingleSelectQuestion({
  question,
  value,
  error,
  onChange,
}: BaseProps) {
  const groupName = `field-${question.id}`;
  return (
    <Fieldset
      legend={question.question}
      hint={question.why_it_matters}
      error={error}
      errorId={`${groupName}-error`}
    >
      {question.options.map((option, index) => (
        <label key={option} className={optionRow}>
          <input
            type="radio"
            name={groupName}
            id={index === 0 ? groupName : undefined}
            value={option}
            checked={value === option}
            onChange={() => onChange(option)}
            className="mt-0.5 size-4 accent-accent"
          />
          <span className="text-sm text-fg">{option}</span>
        </label>
      ))}
    </Fieldset>
  );
}

export function MultiSelectQuestion({
  question,
  value,
  error,
  onChange,
}: BaseProps) {
  const { dict } = useLanguage();
  const groupName = `field-${question.id}`;
  const selected = Array.isArray(value) ? value : [];

  function toggle(option: string) {
    onChange(
      selected.includes(option)
        ? selected.filter((item) => item !== option)
        : [...selected, option],
    );
  }

  return (
    <Fieldset
      legend={
        <>
          {question.question}{" "}
          <span className="font-normal text-fg-subtle">{dict.discovery.selectAllThatApply}</span>
        </>
      }
      hint={question.why_it_matters}
      error={error}
      errorId={`${groupName}-error`}
    >
      {question.options.map((option, index) => (
        <label key={option} className={optionRow}>
          <input
            type="checkbox"
            id={index === 0 ? groupName : undefined}
            value={option}
            checked={selected.includes(option)}
            onChange={() => toggle(option)}
            className="mt-0.5 size-4 rounded accent-accent"
          />
          <span className="text-sm text-fg">{option}</span>
        </label>
      ))}
    </Fieldset>
  );
}
