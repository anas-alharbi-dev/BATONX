"use client";

import type {
  BusinessRule,
  BLStateTransition,
} from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { useLanguage } from "@/lib/i18n";

import type { SectionDescriptor } from "./business-logic-shared";
import { fieldLabel } from "./section-editors";

function ReqRefs({ ids, tracesTo }: { ids: string[]; tracesTo: string }) {
  if (!ids || ids.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] uppercase tracking-[0.06em] text-fg-subtle">
        {tracesTo}
      </span>
      {ids.map((id) => (
        <span
          key={id}
          className="rounded-sm border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-fg-muted"
        >
          {id}
        </span>
      ))}
    </div>
  );
}

function Meta({ label, items }: { label: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <p className="mt-1 text-sm leading-relaxed text-fg-muted">
      <span className="text-fg-subtle">{label}: </span>
      {items.join("; ")}
    </p>
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
  const t = dict.businessLogic;

  if (section.kind === "prose") {
    return (
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg-muted">
        {(value as string) || "—"}
      </p>
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

  if (section.kind === "rules") {
    const rules = (value as BusinessRule[]) ?? [];
    return (
      <ul className="grid gap-3">
        {rules.map((r) => (
          <li key={r.id} className="rounded-md border border-line bg-bg p-3.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-sm border border-line-strong bg-surface px-1.5 py-0.5 font-mono text-[11px] font-medium text-fg">
                {r.id}
              </span>
              {r.actor && <Badge tone="neutral">{r.actor}</Badge>}
              {r.derived && <Badge tone="warning">{t.derivedBadge}</Badge>}
            </div>
            <p className="mt-2 text-sm font-medium leading-relaxed text-fg">
              {r.statement}
            </p>
            <Meta label={t.whenLabel} items={r.conditions} />
            {r.outcome && (
              <p className="mt-1 text-sm leading-relaxed text-fg-muted">
                <span className="text-fg-subtle">{t.thenLabel} </span>
                {r.outcome}
              </p>
            )}
            <Meta label={t.exceptionsLabel} items={r.exceptions} />
            <Meta label={t.validationsLabel} items={r.validations} />
            <ReqRefs ids={r.related_requirements} tracesTo={t.tracesTo} />
          </li>
        ))}
      </ul>
    );
  }

  if (section.kind === "transitions") {
    const items = (value as BLStateTransition[]) ?? [];
    return (
      <ul className="grid gap-2.5">
        {items.map((tr, i) => (
          <li key={i} className="rounded-md border border-line bg-bg p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-fg">{tr.entity}</span>
              <span className="font-mono text-xs text-fg-muted" dir="ltr">
                {tr.from_state} &rarr; {tr.to_state}
              </span>
              {tr.actor && <Badge tone="neutral">{tr.actor}</Badge>}
            </div>
            <p className="mt-1 text-fg-muted">
              <span className="text-fg-subtle">{t.triggerColon} </span>
              {tr.trigger}
            </p>
            <Meta label={t.guardsLabel} items={tr.guards} />
            <Meta label={t.effectsLabel} items={tr.effects} />
            <ReqRefs ids={tr.related_requirements} tracesTo={t.tracesTo} />
          </li>
        ))}
      </ul>
    );
  }

  // objects
  const rows = (value as Record<string, unknown>[]) ?? [];
  return (
    <div className="grid gap-3">
      {rows.map((row, i) => {
        const primary = section.fields?.[0];
        return (
          <div key={i} className="rounded-md border border-line bg-bg p-3">
            {primary && (
              <p className="text-sm font-medium text-fg">
                {String(row[primary.key] ?? "—")}
              </p>
            )}
            <dl className="mt-1.5 grid gap-1.5">
              {section.fields?.slice(1).map((f) => {
                const raw = row[f.key];
                const text =
                  f.kind === "list"
                    ? ((raw as string[]) ?? []).join("; ")
                    : String(raw ?? "");
                if (!text) return null;
                return (
                  <div key={f.key} className="grid gap-0.5">
                    <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">
                      {fieldLabel(f.key, dict)}
                    </dt>
                    <dd className="text-sm leading-relaxed text-fg-muted">
                      {text}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>
        );
      })}
    </div>
  );
}
