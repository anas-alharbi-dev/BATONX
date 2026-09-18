"use client";

import type { ProfilingRun } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { interpolate, useLanguage } from "@/lib/i18n";

export function ProfilingTable({ run }: { run: ProfilingRun }) {
  const { dict } = useLanguage();
  const t = run.table_stats;
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-muted">
        <span>
          <span className="text-fg-subtle">{dict.profilingTable.rows}</span> {t.row_count.toLocaleString()}
        </span>
        <span>
          <span className="text-fg-subtle">{dict.profilingTable.columns}</span> {t.column_count}
        </span>
        <span>
          <span className="text-fg-subtle">{dict.profilingTable.duplicateRows}</span>{" "}
          {t.duplicate_row_count}
        </span>
        {t.sampled && <Badge tone="warning">{dict.profilingTable.sampledBadge}</Badge>}
      </div>

      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full border-collapse text-start text-xs">
          <thead className="bg-surface/60 text-fg-subtle">
            <tr>
              <th className="px-3 py-2 font-medium">{dict.profilingTable.column}</th>
              <th className="px-3 py-2 font-medium">{dict.profilingTable.type}</th>
              <th className="px-3 py-2 font-medium tabular">{dict.profilingTable.nullPct}</th>
              <th className="px-3 py-2 font-medium tabular">{dict.profilingTable.distinctPct}</th>
              <th className="px-3 py-2 font-medium">{dict.profilingTable.notes}</th>
            </tr>
          </thead>
          <tbody>
            {run.columns.map((c) => (
              <tr key={c.name} className="border-t border-line align-top">
                <td className="px-3 py-2 font-mono text-fg" dir="ltr">{c.name}</td>
                <td className="px-3 py-2 text-fg-muted" dir="ltr">{c.dtype}</td>
                <td className="px-3 py-2 tabular text-fg-muted" dir="ltr">{c.null_pct}</td>
                <td className="px-3 py-2 tabular text-fg-muted" dir="ltr">
                  {c.distinct_pct}
                </td>
                <td className="px-3 py-2 text-fg-muted">
                  <div className="flex flex-wrap gap-1.5">
                    {c.probable_key && <Badge tone="accent">{dict.profilingTable.probableKey}</Badge>}
                    {c.sensitivity === "pii_likely" && (
                      <Badge tone="warning">
                        {c.sensitivity_kind ?? dict.profilingTable.sensitive}
                      </Badge>
                    )}
                    {c.numeric_range && (
                      <span className="text-fg-subtle" dir="ltr">
                        {interpolate(dict.profilingTable.range, { range: c.numeric_range })}
                      </span>
                    )}
                    {c.date_range && (
                      <span className="text-fg-subtle" dir="ltr">
                        {interpolate(dict.profilingTable.range, { range: c.date_range })}
                      </span>
                    )}
                    {c.sensitivity !== "pii_likely" &&
                      c.top_values &&
                      c.top_values.length > 0 && (
                        <span className="text-fg-subtle" dir="ltr">
                          {interpolate(dict.profilingTable.topValues, {
                            values: c.top_values
                              .slice(0, 3)
                              .map((v) => `${v.value} (${v.count})`)
                              .join(", "),
                          })}
                        </span>
                      )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-fg-subtle">
        {dict.profilingTable.footer}
      </p>
    </div>
  );
}
