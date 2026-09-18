"use client";

import type { RelevantContext } from "@/lib/api/types";
import { useLanguage } from "@/lib/i18n";

function Row({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="grid gap-0.5">
      <dt className="text-xs uppercase tracking-[0.06em] text-fg-subtle">{label}</dt>
      <dd className="text-sm leading-relaxed text-fg-muted">{value}</dd>
    </div>
  );
}

function List({ label, items }: { label: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="grid gap-1">
      <p className="text-xs uppercase tracking-[0.06em] text-fg-subtle">{label}</p>
      <ul className="grid list-disc gap-1 ps-5 text-sm leading-relaxed text-fg-muted">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function RelevantContextPanel({ context }: { context: RelevantContext }) {
  const { dict } = useLanguage();
  const t = dict.taskWorkspace;
  const a = context.architecture;
  const bl = context.business_logic ?? {};
  const blRules = bl.business_rules ?? [];
  const blValidations = bl.validations ?? [];
  const blTransitions = bl.state_transitions ?? [];
  const blPermissions = bl.permissions ?? [];
  const blEdgeCases = bl.edge_cases ?? [];
  const hasBusinessLogic =
    blRules.length > 0 ||
    blValidations.length > 0 ||
    blTransitions.length > 0 ||
    blPermissions.length > 0 ||
    blEdgeCases.length > 0;
  return (
    <details className="group rounded-xl border border-line bg-surface/40">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-xl p-4 text-sm font-medium text-fg marker:content-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent">
        <span>
          {t.relevantContext}
          {hasBusinessLogic ? t.relevantContextWithRules : ""} {t.relevantContextSuffix}
        </span>
        <span className="shrink-0 text-xs text-fg-subtle group-open:hidden">
          {t.show}
        </span>
        <span className="hidden shrink-0 text-xs text-fg-subtle group-open:inline">
          {t.hide}
        </span>
      </summary>

      <div className="grid gap-5 border-t border-line p-4">
        <dl className="grid gap-3">
          <Row label={t.fieldProblem} value={context.product.problem} />
          <Row label={t.fieldSolution} value={context.product.solution} />
        </dl>

        <dl className="grid gap-3">
          <Row label={t.fieldArchStyle} value={a.style} />
          <Row label={t.fieldFrontend} value={a.frontend} />
          <Row label={t.fieldBackend} value={a.backend} />
          <Row label={t.fieldDatabase} value={a.database} />
          <Row label={t.fieldAuth} value={a.auth} />
        </dl>

        {a.components.length > 0 && (
          <List
            label={t.fieldComponents}
            items={a.components.map((c) => `${c.name} — ${c.responsibility}`)}
          />
        )}
        {a.api_areas.length > 0 && (
          <List
            label={t.fieldApiAreas}
            items={a.api_areas.map((x) => `${x.name} — ${x.purpose}`)}
          />
        )}
        {a.data_model.length > 0 && (
          <List
            label={t.fieldDataEntities}
            items={a.data_model.map(
              (e) =>
                `${e.entity}${e.fields.length ? ` (${e.fields.join(", ")})` : ""}`,
            )}
          />
        )}
        {a.integrations.length > 0 && (
          <List
            label={t.fieldIntegrations}
            items={a.integrations.map((i) => `${i.name} — ${i.purpose}`)}
          />
        )}
        <List label={t.fieldSecurity} items={a.security} />
        <List
          label={t.fieldKeyDecisions}
          items={a.key_decisions.map((d) => `${d.decision} — ${d.rationale}`)}
        />
        <List label={t.fieldConstraints} items={a.constraints} />
        {context.user_roles.length > 0 && (
          <List
            label={t.fieldUserRoles}
            items={context.user_roles.map((r) => `${r.name} — ${r.description}`)}
          />
        )}
        <List label={t.fieldBusinessRules} items={context.business_rules} />

        {hasBusinessLogic && (
          <div className="grid gap-4 rounded-lg border border-line bg-bg/40 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.06em] text-fg-subtle">
              {t.approvedBusinessLogicHeading}
            </p>
            <List
              label={t.fieldBusinessRulesTraced}
              items={blRules.map((r) => {
                const reqs = r.related_requirements.length
                  ? ` [${r.related_requirements.join(", ")}]`
                  : "";
                const when = r.conditions.length
                  ? ` — when ${r.conditions.join("; ")}`
                  : "";
                const then = r.outcome ? ` → ${r.outcome}` : "";
                return `${r.id}: ${r.statement}${when}${then}${reqs}`;
              })}
            />
            <List
              label={t.fieldPermissions}
              items={blPermissions.map(
                (p) =>
                  `${p.actor}: ${p.can.join(", ")}${
                    p.conditions.length ? ` (if ${p.conditions.join("; ")})` : ""
                  }`,
              )}
            />
            <List
              label={t.fieldBusinessValidations}
              items={blValidations.map(
                (v) => `${v.id}: ${v.rule}${v.applies_to ? ` (${v.applies_to})` : ""}`,
              )}
            />
            <List
              label={t.fieldStateTransitions}
              items={blTransitions.map(
                (t2) =>
                  `${t2.entity}: ${t2.from} → ${t2.to} on ${t2.trigger}${
                    t2.actor ? ` by ${t2.actor}` : ""
                  }${t2.guards.length ? ` [guards: ${t2.guards.join("; ")}]` : ""}`,
              )}
            />
            <List
              label={t.fieldEdgeCases}
              items={blEdgeCases.map(
                (e) => `${e.id}: ${e.scenario} → ${e.expected_behavior}`,
              )}
            />
          </div>
        )}
      </div>
    </details>
  );
}
