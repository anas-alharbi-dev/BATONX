"""
Data Quality domain services (Phase I-2): observe -> propose rules -> approve ->
run deterministic checks. Observations and check results are facts; only rules
are approved. Checks run through the DuckDB execution boundary.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from django.db import transaction
from django.utils import timezone as dj_timezone
from pydantic import ValidationError

from ai.base import run_operation
from ai.exceptions import AIOperationError
from ai.operations.quality_rule_proposal import QUALITY_RULE_PROPOSAL
from common.storage import local_path
from projects.context import build_context_digest
from projects.data.execution import (
    DuckDBExecution,
    QueryExecutionError,
    SqlValidationError,
)
from projects.data.quality import (
    SECTION_FIELDS,
    DataQualityContent,
    critical_unresolved_count,
    derive_observations,
    normalize_data_quality_content,
)
from projects.data.services import _require_data_project, serialize_job
from projects.data.stale import (
    clear_data_stale,
    project_level_changed,
    propagate_quality_change,
)
from projects.exceptions import ProjectWorkflowError
from projects.models import Dataset, Job, Project, QualityCheckRun

_IDENT_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pydantic_details(error: ValidationError) -> list[dict]:
    return [
        {"loc": ".".join(str(p) for p in i["loc"]), "msg": i["msg"]}
        for i in error.errors()
    ]


def _content(project: Project) -> dict:
    return dict((project.data_quality or {}).get("content") or {})


def _profiled_datasets(project: Project) -> list[Dataset]:
    return [
        d for d in project.datasets.all() if d.status == Dataset.Status.PROFILED
    ]


# --- observations (deterministic, no approval, no AI) -----------------


def observe_data_quality(project: Project) -> dict:
    _require_data_project(project)
    datasets = _profiled_datasets(project)
    if not datasets:
        raise ProjectWorkflowError(
            "no_profiled_datasets",
            "Profile at least one dataset before deriving quality observations.",
            status=409,
        )

    observations: list[dict] = []
    for ds in datasets:
        run = ds.profiling_runs.first()
        if not run:
            continue
        observations.extend(
            derive_observations(
                str(ds.id), {"table_stats": run.table_stats, "columns": run.columns}
            )
        )
    # re-number DQ ids across all datasets, keep existing rules
    current = _content(project)
    merged = normalize_data_quality_content(
        {"observations": observations, "rules": current.get("rules", [])}
    )
    now = _now_iso()
    with transaction.atomic():
        project.data_quality = {
            "content": merged,
            "generated_at": (project.data_quality or {}).get("generated_at") or now,
            "updated_at": now,
            "approved_at": (project.data_quality or {}).get("approved_at"),
        }
        project.save(update_fields=["data_quality", "updated_at"])
    return serialize_data_quality(project)


# --- rules (AI-proposed, human-approved) ------------------------------


def propose_quality_rules(project: Project) -> dict:
    _require_data_project(project)
    current = _content(project)
    observations = current.get("observations") or []
    if not observations:
        raise ProjectWorkflowError(
            "no_observations",
            "Derive quality observations before proposing rules.",
            status=409,
        )

    dataset_ids = {str(d.id) for d in project.datasets.all()}

    def _ds_ctx(d: Dataset) -> dict:
        run = d.profiling_runs.first()
        cols = (run.columns if run else None) or []
        return {
            "id": str(d.id),
            "name": d.name,
            "source_type": d.source_type,
            "row_count": d.row_count,
            "columns": [
                {
                    "name": c["name"],
                    "dtype": c["dtype"],
                    "null_pct": c.get("null_pct", 0),
                    "distinct_pct": c.get("distinct_pct", 0),
                }
                for c in cols
            ],
            "interpretation": (
                (d.interpretation or {}).get("content")
                if d.interpretation_approved_at
                else None
            ),
        }

    ai_ctx = {
        "data_brief": (project.data_brief or {}).get("content") or {},
        "datasets": [_ds_ctx(d) for d in project.datasets.all()],
        "observations": observations,
    }
    draft = run_operation(QUALITY_RULE_PROPOSAL, ai_ctx, project=project)

    proposed = draft.model_dump(mode="json").get("rules", [])
    for r in proposed:
        r["status"] = "draft"
        if r.get("dataset_ref") not in dataset_ids:
            raise ProjectWorkflowError(
                "invalid_quality_rule",
                "A proposed rule targets a dataset that is not part of this project.",
                details={"dataset_ref": r.get("dataset_ref")},
            )

    merged = normalize_data_quality_content(
        {"observations": observations, "rules": proposed}
    )
    try:
        DataQualityContent.model_validate(merged)
    except ValidationError as error:
        raise AIOperationError(
            code="ai_invalid_output",
            message="The proposed quality rules did not match the expected structure.",
            retryable=True,
            details=_pydantic_details(error),
        )

    was_approved = project.data_quality_approved_at is not None
    now = _now_iso()
    with transaction.atomic():
        project.data_quality = {
            "content": merged,
            "generated_at": (project.data_quality or {}).get("generated_at") or now,
            "updated_at": now,
            "approved_at": None,
        }
        project.data_quality_approved_at = None
        fields = ["data_quality", "data_quality_approved_at", "updated_at"]
        if was_approved:
            impact = propagate_quality_change(project)
            if project_level_changed(impact):
                fields.append("downstream_stale")
        project.save(update_fields=fields)
    return serialize_data_quality(project)


def update_data_quality(project: Project, patch) -> dict:
    _require_data_project(project)
    current = _content(project)
    if not current:
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Derive quality observations first.", status=409
        )
    if not isinstance(patch, dict) or not patch:
        raise ProjectWorkflowError(
            "invalid_data_quality", "Provide 'rules' to update."
        )
    unknown = sorted(set(patch) - set(SECTION_FIELDS))
    if unknown:
        raise ProjectWorkflowError(
            "invalid_data_quality",
            f"Only these are editable: {', '.join(SECTION_FIELDS)}.",
            details={"unknown": unknown},
        )

    dataset_ids = {str(d.id) for d in project.datasets.all()}
    rules = patch.get("rules", current.get("rules", []))
    for r in rules:
        if isinstance(r, dict) and r.get("dataset_ref") not in dataset_ids:
            raise ProjectWorkflowError(
                "invalid_quality_rule",
                "A rule targets a dataset that is not part of this project.",
                details={"dataset_ref": r.get("dataset_ref")},
            )

    merged = normalize_data_quality_content(
        {"observations": current.get("observations", []), "rules": rules}
    )
    try:
        DataQualityContent.model_validate(merged)
    except ValidationError as error:
        raise ProjectWorkflowError(
            "invalid_data_quality",
            "One or more rules are not valid. Check the highlighted fields.",
            details={"errors": _pydantic_details(error)},
        )

    was_approved = project.data_quality_approved_at is not None
    with transaction.atomic():
        project.data_quality["content"] = merged
        project.data_quality["updated_at"] = _now_iso()
        project.data_quality["approved_at"] = None
        project.data_quality_approved_at = None
        fields = ["data_quality", "data_quality_approved_at", "updated_at"]
        if was_approved:
            project.context_digest = build_context_digest(project)
            fields.append("context_digest")
            impact = propagate_quality_change(project)
            if project_level_changed(impact):
                fields.append("downstream_stale")
        project.save(update_fields=fields)
    return serialize_data_quality(project)


def approve_data_quality(project: Project) -> dict:
    _require_data_project(project)
    current = _content(project)
    if not current:
        raise ProjectWorkflowError(
            "invalid_workflow_state", "Nothing to approve.", status=409
        )
    approved_at = dj_timezone.now()
    with transaction.atomic():
        rules = current.get("rules", [])
        for r in rules:
            r["status"] = "approved"
        current["rules"] = rules
        project.data_quality["content"] = current
        project.data_quality["approved_at"] = approved_at.isoformat()
        project.data_quality_approved_at = approved_at
        # the human re-confirming the rules is this artifact's own
        # reconciliation — clear its own stale flag (never anything else's)
        clear_data_stale(project, "data_quality")
        project.context_digest = build_context_digest(project)
        project.save(
            update_fields=[
                "data_quality",
                "data_quality_approved_at",
                "downstream_stale",
                "context_digest",
                "updated_at",
            ]
        )
    return serialize_data_quality(project)


# --- deterministic check execution -----------------------------------


def _view_name(dataset: Dataset) -> str:
    return "src_" + _IDENT_SAFE.sub("", str(dataset.id))[:28]


def _quote_ident(name: str) -> str:
    if '"' in name or not name:
        raise SqlValidationError("bad_column", f"unsafe column {name!r}")
    return '"' + name + '"'


def _sql_literal(value) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _rule_predicate(rule: dict, view: str) -> tuple[str, str, bool]:
    """(count_sql, sample_sql, is_row_count_gt). count_sql -> violating rows."""
    a = rule["assertion"]
    col = rule.get("column") or ""
    p = rule.get("params") or {}
    qc = _quote_ident(col) if col else ""

    if a == "not_null":
        where = f"{qc} IS NULL"
    elif a == "unique":
        where = (
            f"{qc} IS NOT NULL AND {qc} IN "
            f"(SELECT {qc} FROM \"{view}\" WHERE {qc} IS NOT NULL "
            f"GROUP BY {qc} HAVING count(*) > 1)"
        )
    elif a == "in_set":
        vals = ", ".join(_sql_literal(v) for v in p["values"])
        where = f"{qc} IS NOT NULL AND {qc} NOT IN ({vals})"
    elif a == "range":
        clauses = []
        if "min" in p:
            clauses.append(f"{qc} < {_sql_literal(p['min'])}")
        if "max" in p:
            clauses.append(f"{qc} > {_sql_literal(p['max'])}")
        where = f"{qc} IS NOT NULL AND (" + " OR ".join(clauses) + ")"
    elif a == "regex":
        pat = _sql_literal(p["pattern"])
        where = f"{qc} IS NOT NULL AND NOT regexp_matches(CAST({qc} AS VARCHAR), {pat})"
    elif a == "row_count_gt":
        count_sql = f'SELECT count(*) AS n FROM "{view}"'
        return count_sql, "", True
    else:  # pragma: no cover - schema-guarded
        raise SqlValidationError("unsupported_assertion", a)

    count_sql = f'SELECT count(*) AS n FROM "{view}" WHERE {where}'
    sample_sql = f'SELECT * FROM "{view}" WHERE {where}'
    return count_sql, sample_sql, False


def run_quality_checks(project: Project) -> dict:
    _require_data_project(project)
    if not project.data_quality_approved_at:
        raise ProjectWorkflowError(
            "quality_rules_not_approved",
            "Approve the quality rules before running checks.",
            status=409,
        )
    current = _content(project)
    rules = current.get("rules") or []
    if not rules:
        raise ProjectWorkflowError(
            "no_quality_rules", "There are no rules to check.", status=409
        )

    from django.conf import settings

    max_samples = settings.DATA_QUERY_MAX_FAILURE_SAMPLES
    obs_by_id = {o["id"]: o for o in current.get("observations", [])}
    datasets_by_id = {str(d.id): d for d in project.datasets.all()}

    job = Job.objects.create(
        project=project,
        kind=Job.Kind.RUN_QUALITY_CHECKS,
        status=Job.Status.RUNNING,
        started_at=dj_timezone.now(),
    )

    # group rules by dataset -> one forked run per dataset
    by_ds: dict[str, list[dict]] = {}
    for r in rules:
        by_ds.setdefault(r["dataset_ref"], []).append(r)

    results: list[dict] = []
    try:
        ex = DuckDBExecution()
        for ds_id, ds_rules in by_ds.items():
            ds = datasets_by_id.get(ds_id)
            if ds is None or ds.status != Dataset.Status.PROFILED:
                for r in ds_rules:
                    results.append(
                        _result(r, passed=False, failing=None, error="dataset not profiled")
                    )
                continue
            view = _view_name(ds)
            path = local_path(ds.storage_ref)
            sensitive = {
                c["name"]
                for c in (ds.inferred_schema or [])
                if c.get("sensitivity")
            }

            queries: list[tuple[str, str]] = []
            plan: dict[str, dict] = {}
            for r in ds_rules:
                count_sql, sample_sql, is_rcg = _rule_predicate(r, view)
                queries.append((f"c_{r['id']}", count_sql))
                if sample_sql:
                    queries.append((f"s_{r['id']}", f"{sample_sql} LIMIT {max_samples}"))
                plan[r["id"]] = {"rule": r, "is_rcg": is_rcg, "has_sample": bool(sample_sql)}

            out = ex.run_many(
                queries,
                datasets=[(view, path, ds.source_type)],
                max_rows=max_samples,
            )

            for rid, meta in plan.items():
                r = meta["rule"]
                count_res = out.get(f"c_{rid}", {})
                n = (count_res.get("rows") or [[0]])[0][0] or 0
                if meta["is_rcg"]:
                    threshold = r["params"]["threshold"]
                    passed = n > threshold
                    failing = 0 if passed else 1
                    samples = []
                else:
                    passed = n == 0
                    failing = n
                    samples = _redact(
                        out.get(f"s_{rid}", {}), sensitive
                    ) if meta["has_sample"] else []
                results.append(
                    _result(r, passed=passed, failing=failing, samples=samples)
                )
    except (SqlValidationError, QueryExecutionError) as exc:
        job.status = Job.Status.FAILED
        job.error = exc.message[:2000]
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise ProjectWorkflowError(
            "quality_check_failed",
            f"Quality checks failed: {exc.message}",
            status=422,
            details={"job_id": str(job.id), "code": exc.code},
        )

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "critical_failed": sum(
            1
            for r in results
            if not r["passed"]
            and any(
                obs_by_id.get(o, {}).get("severity") == "critical"
                for o in r.get("related_observations", [])
            )
        ),
    }
    with transaction.atomic():
        run = QualityCheckRun.objects.create(
            project=project, job=job, results=results, summary=summary
        )
        job.status = Job.Status.SUCCEEDED
        job.progress = 100
        job.result_ref = {"quality_check_run": str(run.id)}
        job.finished_at = dj_timezone.now()
        job.save(update_fields=["status", "progress", "result_ref", "finished_at"])
    return serialize_data_quality(project)


def _result(rule: dict, *, passed: bool, failing, error: str = "", samples=None) -> dict:
    return {
        "rule_id": rule["id"],
        "dataset_ref": rule["dataset_ref"],
        "assertion": rule["assertion"],
        "column": rule.get("column", ""),
        "accepted_risk": bool(rule.get("accepted_risk")),
        "related_observations": rule.get("related_observations", []),
        "passed": passed,
        "failing_row_count": failing,
        "sample_failures": samples or [],
        "error": error,
        "checked_at": _now_iso(),
    }


def _redact(result: dict, sensitive: set[str]) -> list[dict]:
    cols = result.get("columns") or []
    out = []
    for row in (result.get("rows") or []):
        rec = {}
        for i, c in enumerate(cols):
            rec[c] = "***" if c in sensitive else row[i]
        out.append(rec)
    return out


# --- serialization ---------------------------------------------------


def serialize_data_quality(project: Project) -> dict:
    content = _content(project)
    latest = project.quality_check_runs.first()
    return {
        "content": content or {"observations": [], "rules": []},
        "approved": project.data_quality_approved_at is not None,
        "approved_at": (
            project.data_quality_approved_at.isoformat()
            if project.data_quality_approved_at
            else None
        ),
        "unresolved_critical": critical_unresolved_count(content) if content else 0,
        "latest_check_run": serialize_quality_check_run(latest) if latest else None,
    }


def serialize_quality_check_run(run: QualityCheckRun) -> dict:
    return {
        "id": str(run.id),
        "results": run.results,
        "summary": run.summary,
        "job": serialize_job(run.job) if run.job else None,
        "created_at": run.created_at.isoformat(),
    }
