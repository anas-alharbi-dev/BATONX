import type { ReactNode } from "react";

interface FieldProps {
  /** id of the control this labels */
  htmlFor: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  /** pass through to wire aria-describedby on the control */
  hintId?: string;
  errorId?: string;
}

/** Labelled single control (text / textarea). Label above, hint under label, error below. */
export function Field({
  htmlFor,
  label,
  hint,
  error,
  children,
  hintId,
  errorId,
}: FieldProps) {
  return (
    <div className="grid gap-2">
      <label htmlFor={htmlFor} className="text-sm font-medium text-fg">
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="-mt-1 text-sm text-fg-muted">
          {hint}
        </p>
      ) : null}
      {children}
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

interface FieldsetProps {
  legend: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  errorId?: string;
  children: ReactNode;
}

/** Grouped choice control (radios / checkboxes). Uses fieldset + legend. */
export function Fieldset({ legend, hint, error, errorId, children }: FieldsetProps) {
  return (
    <fieldset className="grid gap-3">
      <legend className="text-sm font-medium text-fg">{legend}</legend>
      {hint ? <p className="-mt-1 text-sm text-fg-muted">{hint}</p> : null}
      <div className="grid gap-2">{children}</div>
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
