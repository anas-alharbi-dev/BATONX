"""
Deterministic Analysis execution (Phase I-4).

Compiles an APPROVED ``AnalysisPlan`` into one or more DuckDB SELECT queries
over the exact same execution boundary Phase I-2/I-3 already hardened
(``projects.data.execution``) — no second execution engine. AI is never asked
to compute or alter a number: every value in a Finding comes straight out of
a DuckDB result cell; every fact ``statement`` is built by plain Python string
formatting from those values.

Each Analysis method has exactly one known, deterministic compilation
strategy. Anything a method cannot faithfully compile (e.g. a ``trend``
analysis over a KPI with no ``time_field``) raises ``UnsupportedAnalysisError``
rather than guessing.

``compile_analysis`` takes the *validated* ``AnalysisPlanContent`` (typed
attribute access to comparisons/filters/time ranges), not the raw Django row —
the plan's ``business_id`` (needed only for evidence refs, not part of the
content schema) is passed alongside it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from common.storage import local_path
from projects.data.analysis import AnalysisPlanContent, ComparisonSpec
from projects.data.metrics import MetricFilter, MetricStructured
from projects.data.sql_safe import quote_ident, sql_literal, view_name


class UnsupportedAnalysisError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _pct_change(baseline, comparison) -> float | None:
    if baseline in (None, 0) or comparison is None:
        return None
    return (comparison - baseline) / abs(baseline) * 100.0


def _pct_conv(start, count) -> float | None:
    if not start:
        return None
    return (count / start) * 100.0


def _metric_expr(structured: MetricStructured) -> str:
    """Identical aggregation-expression logic to
    ``metrics_services._build_validation_sql`` (deliberately duplicated, not
    imported/refactored — consistent with ``sql_safe.py``'s precedent of not
    touching already-tested I-3 code for a new I-4 caller)."""
    if structured.aggregation == "ratio":
        num = quote_ident(structured.numerator.field)
        den = quote_ident(structured.denominator.field)
        return (
            f"CASE WHEN sum({den}) = 0 OR sum({den}) IS NULL THEN NULL "
            f"ELSE sum({num}) / sum({den}) END"
        )
    if structured.aggregation == "count":
        return "count(*)" if not structured.measure else f"count({quote_ident(structured.measure.field)})"
    if structured.aggregation == "count_distinct":
        return f"count(DISTINCT {quote_ident(structured.measure.field)})"
    return f"{structured.aggregation}({quote_ident(structured.measure.field)})"


def _filter_clauses(filters: list[MetricFilter]) -> list[str]:
    clauses = []
    for f in filters:
        col = quote_ident(f.field)
        if f.operator == "eq":
            clauses.append(f"{col} = {sql_literal(f.value)}")
        elif f.operator == "ne":
            clauses.append(f"{col} != {sql_literal(f.value)}")
        elif f.operator == "lt":
            clauses.append(f"{col} < {sql_literal(f.value)}")
        elif f.operator == "lte":
            clauses.append(f"{col} <= {sql_literal(f.value)}")
        elif f.operator == "gt":
            clauses.append(f"{col} > {sql_literal(f.value)}")
        elif f.operator == "gte":
            clauses.append(f"{col} >= {sql_literal(f.value)}")
        elif f.operator in ("in", "not_in"):
            vals = ", ".join(sql_literal(v) for v in f.value)
            clauses.append(f"{col} {'NOT IN' if f.operator == 'not_in' else 'IN'} ({vals})")
    return clauses


def _time_range_clause(time_field: str, time_range: dict | None) -> list[str]:
    if not time_range or not time_field:
        return []
    return [
        f"{quote_ident(time_field)} BETWEEN {sql_literal(time_range['start'])} "
        f"AND {sql_literal(time_range['end'])}"
    ]


def _where(clauses: list[str]) -> str:
    return f" WHERE {' AND '.join(clauses)}" if clauses else ""


def _next_finding_id(n: int) -> str:
    return f"F-{n:02d}"


class _Ctx:
    """Compile-time bookkeeping threaded through to each method's ``finalize``."""

    def __init__(self, plan_business_id: str):
        self.plan_business_id = plan_business_id
        self.queries: list[tuple[str, str]] = []
        self.datasets: dict[str, tuple[str, str, str]] = {}  # dataset_id -> (view, path, type)
        self._n = 0

    def add_dataset(self, dataset) -> str:
        view = view_name("src", dataset.id)
        self.datasets[str(dataset.id)] = (view, local_path(dataset.storage_ref), dataset.source_type)
        return view

    def add_query(self, sql: str) -> str:
        self._n += 1
        label = f"q{self._n}"
        self.queries.append((label, sql))
        return label


# =====================================================================
# Per-method compilation — each takes (project, content, metrics,
# datasets_by_metric, ctx) and returns a ``finalize(results) -> findings``
# closure. ``metrics`` is the ordered list of resolved MetricDefinition rows
# for ``content.required_metrics``; ``datasets_by_metric`` maps
# ``business_id -> Dataset``.
# =====================================================================


def _compile_descriptive(project, content: AnalysisPlanContent, metrics, datasets_by_metric, ctx: _Ctx):
    segment = content.segments[0] if content.segments else None
    plan_range = content.time_range or None
    steps = []  # (metric, value_label, breakdown_label|None)

    for m in metrics:
        structured = MetricStructured.model_validate(m.structured)
        ds = datasets_by_metric[m.business_id]
        view = ctx.add_dataset(ds)
        expr = _metric_expr(structured)
        clauses = _filter_clauses(structured.default_filters)
        clauses += _time_range_clause(structured.time_field, plan_range)
        sql = f'SELECT {expr} AS value, count(*) AS row_count FROM "{view}"{_where(clauses)}'
        value_label = ctx.add_query(sql)

        breakdown_label = None
        if segment:
            b_sql = (
                f'SELECT {quote_ident(segment)} AS segment, {expr} AS value '
                f'FROM "{view}"{_where(clauses)} GROUP BY 1 ORDER BY 2 DESC LIMIT 50'
            )
            breakdown_label = ctx.add_query(b_sql)
        steps.append((m, value_label, breakdown_label))

    def finalize(results: dict) -> list[dict]:
        findings = []
        n = 0
        for m, value_label, breakdown_label in steps:
            n += 1
            value_rows = results[value_label]["rows"]
            value = value_rows[0][0] if value_rows else None
            row_count = value_rows[0][1] if value_rows else 0
            breakdown = []
            if breakdown_label:
                breakdown = [
                    {"segment": r[0], "value": r[1]} for r in results[breakdown_label]["rows"]
                ]
            statement = f"{m.name} is {_fmt(value)}."
            findings.append({
                "id": _next_finding_id(n),
                "statement": statement,
                "metric_values": {"value": value, "row_count": row_count},
                "breakdown": breakdown,
                "evidence": {
                    "analysis_plan_ref": ctx.plan_business_id,
                    "kpi_refs": [m.business_id],
                    "dataset_refs": [str(datasets_by_metric[m.business_id].id)],
                    "query_refs": [],
                },
                "computed_at": _now_iso(),
            })
        return findings

    return finalize


def _compile_trend(project, content: AnalysisPlanContent, metrics, datasets_by_metric, ctx: _Ctx):
    baseline: ComparisonSpec = content.comparisons[0]
    comparison: ComparisonSpec = content.comparisons[1]
    steps = []
    for m in metrics:
        structured = MetricStructured.model_validate(m.structured)
        if not structured.time_field:
            raise UnsupportedAnalysisError(
                f"KPI {m.business_id} has no time_field — a trend analysis needs one.",
                details={"kpi": m.business_id},
            )
        ds = datasets_by_metric[m.business_id]
        view = ctx.add_dataset(ds)
        expr = _metric_expr(structured)
        base_clauses = _filter_clauses(structured.default_filters)
        b_sql = f'SELECT {expr} FROM "{view}"{_where(base_clauses + _time_range_clause(structured.time_field, baseline.time_range))}'
        c_sql = f'SELECT {expr} FROM "{view}"{_where(base_clauses + _time_range_clause(structured.time_field, comparison.time_range))}'
        b_label = ctx.add_query(b_sql)
        c_label = ctx.add_query(c_sql)
        steps.append((m, b_label, c_label))

    def finalize(results: dict) -> list[dict]:
        findings = []
        n = 0
        for m, b_label, c_label in steps:
            n += 1
            b_rows = results[b_label]["rows"]
            c_rows = results[c_label]["rows"]
            b_val = b_rows[0][0] if b_rows else None
            c_val = c_rows[0][0] if c_rows else None
            pct = _pct_change(b_val, c_val)
            if pct is not None:
                direction = "increased" if pct >= 0 else "decreased"
                statement = (
                    f"{m.name} {direction} by {abs(pct):.1f}% from "
                    f"{baseline.label} to {comparison.label}."
                )
            elif b_val is not None and c_val is not None:
                delta = c_val - b_val
                direction = "increased" if delta >= 0 else "decreased"
                statement = (
                    f"{m.name} {direction} from {_fmt(b_val)} ({baseline.label}) to "
                    f"{_fmt(c_val)} ({comparison.label})."
                )
            else:
                statement = (
                    f"{m.name} could not be compared between {baseline.label} and "
                    f"{comparison.label} — insufficient data."
                )
            findings.append({
                "id": _next_finding_id(n),
                "statement": statement,
                "metric_values": {
                    "baseline": b_val, "comparison": c_val,
                    "delta": (c_val - b_val) if (b_val is not None and c_val is not None) else None,
                    "pct_change": pct,
                },
                "breakdown": [],
                "evidence": {
                    "analysis_plan_ref": ctx.plan_business_id,
                    "kpi_refs": [m.business_id],
                    "dataset_refs": [str(datasets_by_metric[m.business_id].id)],
                    "query_refs": [],
                },
                "computed_at": _now_iso(),
            })
        return findings

    return finalize


def _compile_segmentation(project, content: AnalysisPlanContent, metrics, datasets_by_metric, ctx: _Ctx):
    m = metrics[0]
    segment = content.segments[0]
    structured = MetricStructured.model_validate(m.structured)
    ds = datasets_by_metric[m.business_id]
    view = ctx.add_dataset(ds)
    expr = _metric_expr(structured)
    clauses = _filter_clauses(structured.default_filters)
    clauses += _time_range_clause(structured.time_field, content.time_range or None)
    sql = (
        f'SELECT {quote_ident(segment)} AS segment, {expr} AS value '
        f'FROM "{view}"{_where(clauses)} GROUP BY 1 ORDER BY 2 DESC LIMIT 50'
    )
    label = ctx.add_query(sql)

    def finalize(results: dict) -> list[dict]:
        rows = results[label]["rows"]
        breakdown = [{"segment": r[0], "value": r[1]} for r in rows]
        if breakdown:
            top, bottom = breakdown[0], breakdown[-1]
            statement = (
                f"{segment} '{top['segment']}' has the highest {m.name} at "
                f"{_fmt(top['value'])}; '{bottom['segment']}' has the lowest at "
                f"{_fmt(bottom['value'])}."
            )
        else:
            statement = f"No {segment} groups were found for {m.name}."
        return [{
            "id": _next_finding_id(1),
            "statement": statement,
            "metric_values": {},
            "breakdown": breakdown,
            "evidence": {
                "analysis_plan_ref": ctx.plan_business_id,
                "kpi_refs": [m.business_id],
                "dataset_refs": [str(ds.id)],
                "query_refs": [],
            },
            "computed_at": _now_iso(),
        }]

    return finalize


def _compile_comparison(project, content: AnalysisPlanContent, metrics, datasets_by_metric, ctx: _Ctx):
    m = metrics[0]
    left: ComparisonSpec = content.comparisons[0]
    right: ComparisonSpec = content.comparisons[1]
    structured = MetricStructured.model_validate(m.structured)
    ds = datasets_by_metric[m.business_id]
    view = ctx.add_dataset(ds)
    expr = _metric_expr(structured)
    base_clauses = _filter_clauses(structured.default_filters)
    l_sql = f'SELECT {expr} FROM "{view}"{_where(base_clauses + _filter_clauses(left.filters) + _time_range_clause(structured.time_field, left.time_range))}'
    r_sql = f'SELECT {expr} FROM "{view}"{_where(base_clauses + _filter_clauses(right.filters) + _time_range_clause(structured.time_field, right.time_range))}'
    l_label = ctx.add_query(l_sql)
    r_label = ctx.add_query(r_sql)

    def finalize(results: dict) -> list[dict]:
        l_rows = results[l_label]["rows"]
        r_rows = results[r_label]["rows"]
        l_val = l_rows[0][0] if l_rows else None
        r_val = r_rows[0][0] if r_rows else None
        pct = _pct_change(l_val, r_val)
        statement = f"{m.name} for {left.label} is {_fmt(l_val)}; for {right.label} is {_fmt(r_val)}"
        statement += f" ({'+' if pct >= 0 else ''}{pct:.1f}%)." if pct is not None else "."
        return [{
            "id": _next_finding_id(1),
            "statement": statement,
            "metric_values": {"left": l_val, "right": r_val, "pct_change": pct,
                               "left_label": left.label, "right_label": right.label},
            "breakdown": [],
            "evidence": {
                "analysis_plan_ref": ctx.plan_business_id,
                "kpi_refs": [m.business_id],
                "dataset_refs": [str(ds.id)],
                "query_refs": [],
            },
            "computed_at": _now_iso(),
        }]

    return finalize


def _compile_funnel(project, content: AnalysisPlanContent, metrics, datasets_by_metric, ctx: _Ctx):
    m = metrics[0]
    ds = datasets_by_metric[m.business_id]
    view = ctx.add_dataset(ds)
    steps: list[ComparisonSpec] = content.comparisons
    labels = []
    cumulative: list[MetricFilter] = []
    for step in steps:
        cumulative = cumulative + list(step.filters)
        sql = f'SELECT count(*) FROM "{view}"{_where(_filter_clauses(cumulative))}'
        labels.append(ctx.add_query(sql))

    def finalize(results: dict) -> list[dict]:
        counts = [
            (results[lbl]["rows"][0][0] if results[lbl]["rows"] else 0) for lbl in labels
        ]
        start = counts[0] if counts else 0
        breakdown = []
        for i, (step, count) in enumerate(zip(steps, counts)):
            prev = counts[i - 1] if i > 0 else count
            breakdown.append({
                "step": step.label,
                "count": count,
                "conversion_from_previous_pct": _pct_conv(prev, count),
                "conversion_from_start_pct": _pct_conv(start, count),
            })
        overall = _pct_conv(start, counts[-1]) if counts else None
        if overall is not None:
            statement = (
                f"Funnel {steps[0].label} → {steps[-1].label}: {counts[-1]} of {start} "
                f"({overall:.1f}%) converted through all steps."
            )
        else:
            statement = f"Funnel {steps[0].label} → {steps[-1].label}: no starting rows found."
        return [{
            "id": _next_finding_id(1),
            "statement": statement,
            "metric_values": {"step_counts": counts, "overall_conversion_pct": overall},
            "breakdown": breakdown,
            "evidence": {
                "analysis_plan_ref": ctx.plan_business_id,
                "kpi_refs": [m.business_id],
                "dataset_refs": [str(ds.id)],
                "query_refs": [],
            },
            "computed_at": _now_iso(),
        }]

    return finalize


_COMPILERS = {
    "descriptive": _compile_descriptive,
    "trend": _compile_trend,
    "segmentation": _compile_segmentation,
    "comparison": _compile_comparison,
    "funnel": _compile_funnel,
}


def compile_analysis(project, business_id: str, content: AnalysisPlanContent, metrics, datasets_by_metric):
    """
    Returns ``(queries, datasets, finalize)``:
      - ``queries``: ``[(label, sql), ...]`` for ``DuckDBExecution.run_many``
      - ``datasets``: ``[(view, path, source_type), ...]`` to register
      - ``finalize(results)``: pure function, raw ``run_many`` results ->
        ``list[finding dict]`` (F-01, F-02, ...)

    Raises ``UnsupportedAnalysisError`` if this plan cannot be safely compiled.
    """
    compiler = _COMPILERS.get(content.method)
    if compiler is None:
        raise UnsupportedAnalysisError(f"Unknown analysis method: {content.method!r}")

    ctx = _Ctx(business_id)
    finalize = compiler(project, content, metrics, datasets_by_metric, ctx)
    return ctx.queries, list(ctx.datasets.values()), finalize


def build_data_caveats(project, datasets_used, fields_used: set[str]) -> list[str]:
    """Deterministic caveats — dataset sampling flags + relevant approved
    Quality rules. Never AI-authored."""
    caveats = []
    for ds in datasets_used:
        if ds.sampled:
            caveats.append(
                f"Dataset {ds.name} ({ds.id}) was profiled from a bounded sample — "
                "results are approximate."
            )
    quality = (project.data_quality or {}).get("content") or {}
    ds_ids = {str(d.id) for d in datasets_used}
    for rule in quality.get("rules", []):
        if rule.get("status") != "approved":
            continue
        if rule.get("dataset_ref") not in ds_ids:
            continue
        if rule.get("column") and fields_used and rule["column"] not in fields_used:
            continue
        caveats.append(
            f"{rule['id']}: {rule['assertion']}({rule.get('column') or 'table'}) "
            "applies to this data — see Data Quality."
        )
    return caveats[:10]
