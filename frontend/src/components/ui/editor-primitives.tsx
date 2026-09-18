"use client";

import { PlusIcon, TrashIcon } from "@radix-ui/react-icons";
import { interpolate, useLanguage } from "@/lib/i18n";

/** Shared field styling for the structured section editors (Blueprint, Architecture). */
export const inputClass =
  "w-full rounded-md border border-line bg-bg-subtle px-3 py-2 text-sm text-fg " +
  "placeholder:text-fg-subtle transition-colors duration-150 focus-visible:border-accent " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25";

export function RemoveButton({
  onClick,
  label,
}: {
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="grid size-9 shrink-0 place-items-center rounded-md border border-line text-fg-subtle transition-colors hover:border-line-strong hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent [touch-action:manipulation]"
    >
      <TrashIcon className="size-4" aria-hidden />
    </button>
  );
}

export function AddButton({
  onClick,
  label,
}: {
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-line-strong px-3 py-2 text-sm text-fg-muted transition-colors hover:border-accent hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent [touch-action:manipulation]"
    >
      <PlusIcon className="size-4" aria-hidden />
      {label}
    </button>
  );
}

/**
 * string[] editor — one text input per row + add/remove. Shared across
 * every structured artifact editor (Blueprint, Business Logic, Architecture,
 * Roadmap, Data). The "Add {noun}"/"Remove {noun} {n}" wording comes from
 * the dictionary (Phase P-7) so it combines grammatically with whichever
 * language `itemNoun` itself is authored in at each call site — the noun is
 * still the caller's responsibility, this only localizes the verb.
 */
export function StringListEditor({
  value,
  onChange,
  itemNoun,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  itemNoun?: string;
}) {
  const { dict } = useLanguage();
  const noun = itemNoun ?? dict.common.defaultItemNoun;
  const set = (i: number, v: string) =>
    onChange(value.map((item, idx) => (idx === i ? v : item)));
  return (
    <div className="grid gap-2">
      {value.map((item, i) => (
        <div key={i} className="flex items-center gap-2">
          <input
            type="text"
            autoComplete="off"
            value={item}
            onChange={(e) => set(i, e.target.value)}
            className={inputClass}
          />
          <RemoveButton
            label={interpolate(dict.common.removeNounTemplate, { noun, n: String(i + 1) })}
            onClick={() => onChange(value.filter((_, idx) => idx !== i))}
          />
        </div>
      ))}
      <AddButton
        label={interpolate(dict.common.addNounTemplate, { noun })}
        onClick={() => onChange([...value, ""])}
      />
    </div>
  );
}
