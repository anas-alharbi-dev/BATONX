"use client";

import type { ApiArea, ArchComponent, ArchDecision, DataEntity } from "@/lib/api/types";
import { useLanguage } from "@/lib/i18n";

import type { SectionDescriptor } from "./architecture-shared";
import { fieldLabel } from "./section-editors";

function Why({ text, whyThis }: { text: string; whyThis: string }) {
  if (!text) return null;
  return (
    <details className="group mt-2 rounded-md border border-line bg-bg-subtle px-3 py-2">
      <summary className="cursor-pointer list-none text-xs font-medium text-fg-muted transition-colors marker:content-none hover:text-fg group-open:text-fg">
        {whyThis}
      </summary>
      <p className="mt-2 text-sm leading-relaxed text-fg-muted">{text}</p>
    </details>
  );
}

function LabelledValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">{label}</dt>
      <dd className="whitespace-pre-wrap text-sm leading-relaxed text-fg-muted">
        {value || "—"}
      </dd>
    </div>
  );
}

export function SectionReadonly({
  section,
  value,
}: {
  section: SectionDescriptor;
  value: unknown;
}) {
  const { dict } = useLanguage();
  const t = dict.architecture;

  if (section.kind === "fields") {
    const obj = (value ?? {}) as Record<string, string>;
    const headline = section.headlineKey ? obj[section.headlineKey] : undefined;
    return (
      <div className="grid gap-3">
        {headline !== undefined && (
          <p className="text-sm font-medium text-fg">{headline || "—"}</p>
        )}
        <dl className="grid gap-3">
          {section.fields
            ?.filter((f) => f.key !== section.headlineKey && !f.isWhy)
            .map((f) => (
              <LabelledValue key={f.key} label={fieldLabel(f.key, dict)} value={obj[f.key] ?? ""} />
            ))}
        </dl>
        {section.fields?.find((f) => f.isWhy) && (
          <Why text={obj[section.fields.find((f) => f.isWhy)!.key] ?? ""} whyThis={t.fieldLabelWhy} />
        )}
      </div>
    );
  }

  if (section.kind === "list") {
    const items = (value as string[]) ?? [];
    if (items.length === 0) return <p className="text-sm text-fg-subtle">—</p>;
    return (
      <ul className="grid list-disc gap-1.5 ps-5 text-sm leading-relaxed text-fg-muted">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    );
  }

  if (section.kind === "entities") {
    const entities = (value as DataEntity[]) ?? [];
    return (
      <div className="grid gap-4">
        {entities.map((entity, i) => (
          <div key={i} className="rounded-md border border-line p-3">
            <h4 className="font-mono text-sm font-medium text-fg">{entity.entity}</h4>
            {entity.fields.length > 0 && (
              <p className="mt-2 text-sm text-fg-muted">
                <span className="text-fg-subtle">{t.fieldsPrefix}</span>
                {entity.fields.join(", ")}
              </p>
            )}
            {entity.relationships.length > 0 && (
              <ul className="mt-1.5 grid list-disc gap-1 ps-5 text-sm text-fg-muted">
                {entity.relationships.map((rel, j) => (
                  <li key={j}>{rel}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    );
  }

  // objects
  const items = (value as (ArchComponent | ApiArea | ArchDecision | Record<string, string>)[]) ?? [];
  const primary = section.fields?.[0].key ?? "name";
  return (
    <div className="grid gap-3">
      {items.map((item, i) => {
        const obj = item as Record<string, string>;
        return (
          <div key={i} className="rounded-md border border-line p-3">
            <p className="text-sm font-medium text-fg">{obj[primary] || "—"}</p>
            <dl className="mt-2 grid gap-2">
              {section.fields
                ?.filter((f) => f.key !== primary && !f.isWhy)
                .map((f) => (
                  <LabelledValue key={f.key} label={fieldLabel(f.key, dict)} value={obj[f.key] ?? ""} />
                ))}
            </dl>
            {section.fields?.find((f) => f.isWhy) && (
              <Why text={obj[section.fields.find((f) => f.isWhy)!.key] ?? ""} whyThis={t.fieldLabelWhy} />
            )}
          </div>
        );
      })}
    </div>
  );
}
