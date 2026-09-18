"""
Data Quality — observations (deterministic), rules (approved), check results
(observed facts). Phase I-2.

Observations are derived from a ``ProfilingRun``; the AI never produces them.
Rules are decisions and require human approval. Any BATONX threshold used to
assign an observation's severity is labelled ``heuristic: true``.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Dimension = Literal[
    "completeness",
    "uniqueness",
    "validity",
    "consistency",
    "duplicates",
    "schema",
    "freshness",
]
Severity = Literal["info", "warn", "critical"]
Assertion = Literal["not_null", "unique", "in_set", "range", "regex", "row_count_gt"]

DIMENSIONS = tuple(Dimension.__args__)  # type: ignore[attr-defined]
SEVERITIES = tuple(Severity.__args__)  # type: ignore[attr-defined]
ASSERTIONS = tuple(Assertion.__args__)  # type: ignore[attr-defined]

# BATONX severity heuristics for completeness (documented, not silent).
_NULL_WARN_PCT = 5.0
_NULL_CRITICAL_PCT = 20.0

_ID_NAME_RE = re.compile(r"(^id$|_id$|(^|_)key$|uuid|guid)", re.IGNORECASE)
_NONNEG_NAME_RE = re.compile(
    r"(amount|price|total|qty|quantity|count|age|rate|balance|revenue)", re.IGNORECASE
)


# --- models --------------------------------------------------------------


class QualityObservation(BaseModel):
    id: str = Field(pattern=r"^DQ-\d{2,}$")
    dataset_ref: str = Field(min_length=1)
    column: str = ""
    dimension: Dimension
    severity: Severity
    statement: str = Field(min_length=1)
    evidence: dict = Field(default_factory=dict)
    heuristic: bool = False


class QualityRule(BaseModel):
    id: str = Field(pattern=r"^QR-\d{2,}$")
    dataset_ref: str = Field(min_length=1)
    column: str = ""
    dimension: Dimension
    assertion: Assertion
    params: dict = Field(default_factory=dict)
    rationale: str = ""
    related_observations: list[str] = Field(default_factory=list)
    accepted_risk: bool = False
    status: Literal["draft", "approved"] = "draft"

    @model_validator(mode="after")
    def _check_params(self) -> "QualityRule":
        a, p = self.assertion, self.params or {}
        if a in ("not_null", "unique") and not self.column:
            raise ValueError(f"{a} needs a column")
        if a == "in_set":
            vals = p.get("values")
            if not isinstance(vals, list) or not vals:
                raise ValueError("in_set needs params.values (non-empty list)")
        if a == "range":
            if "min" not in p and "max" not in p:
                raise ValueError("range needs params.min and/or params.max")
        if a == "regex":
            pat = p.get("pattern")
            if not isinstance(pat, str) or not pat:
                raise ValueError("regex needs params.pattern (string)")
            try:
                re.compile(pat)
            except re.error as exc:
                raise ValueError(f"invalid regex: {exc}")
        if a == "row_count_gt":
            if not isinstance(p.get("threshold"), int) or p["threshold"] < 0:
                raise ValueError("row_count_gt needs params.threshold (non-negative int)")
        return self


class DataQualityContent(BaseModel):
    observations: list[QualityObservation] = Field(default_factory=list)
    rules: list[QualityRule] = Field(default_factory=list)


SECTION_FIELDS = ("rules",)  # only rules are user-editable


def _assign_ids(items: list[dict], prefix: str) -> list[dict]:
    used: set[str] = set()
    out: list[dict] = []
    counter = 1
    pat = re.compile(rf"^{prefix}-\d{{2,}}$")
    for raw in items:
        item = dict(raw)
        rid = str(item.get("id") or "").strip()
        if not rid or not pat.match(rid) or rid in used:
            while f"{prefix}-{counter:02d}" in used:
                counter += 1
            rid = f"{prefix}-{counter:02d}"
            counter += 1
        used.add(rid)
        item["id"] = rid
        out.append(item)
    return out


def normalize_data_quality_content(content: dict) -> dict:
    result = dict(content)
    result["observations"] = _assign_ids(list(result.get("observations") or []), "DQ")
    rules = _assign_ids(list(result.get("rules") or []), "QR")
    for r in rules:
        r.setdefault("status", "draft")
        r["related_observations"] = [
            str(x).strip()
            for x in (r.get("related_observations") or [])
            if str(x).strip()
        ]
        if not r.get("column"):
            r["column"] = ""
    result["rules"] = rules
    return result


# --- deterministic observation derivation -----------------------------


def derive_observations(dataset_ref: str, run: dict) -> list[dict]:
    """From a ProfilingRun's ``{table_stats, columns}`` — no AI, no invented data."""
    table = run.get("table_stats") or {}
    cols = run.get("columns") or []
    obs: list[dict] = []

    def add(**kw):
        obs.append({"dataset_ref": dataset_ref, "column": "", "heuristic": False, **kw})

    row_count = table.get("row_count", 0)

    if table.get("sampled"):
        add(
            dimension="consistency",
            severity="info",
            statement=(
                f"Profiled on a sample of {table.get('sample_size', 0)} rows; "
                "observations may not reflect the full dataset."
            ),
            evidence={"sampled": True, "sample_size": table.get("sample_size")},
        )

    dup = table.get("duplicate_row_count", 0)
    if dup and dup > 0:
        add(
            dimension="duplicates",
            severity="warn",
            statement=f"{dup} fully-duplicate row(s) out of {row_count}.",
            evidence={"duplicate_row_count": dup, "row_count": row_count},
            heuristic=True,
        )

    for c in cols:
        name = c.get("name", "")
        null_count = c.get("null_count", 0)
        null_pct = c.get("null_pct", 0.0)
        count = c.get("count", 0)

        if count and null_count == count:
            add(
                column=name,
                dimension="schema",
                severity="critical",
                statement=f"Column '{name}' is entirely null.",
                evidence={"null_count": null_count, "count": count},
            )
        elif null_count and null_count > 0:
            sev = (
                "critical"
                if null_pct >= _NULL_CRITICAL_PCT
                else "warn"
                if null_pct >= _NULL_WARN_PCT
                else "info"
            )
            add(
                column=name,
                dimension="completeness",
                severity=sev,
                statement=(
                    f"Column '{name}' has {null_count} null value(s) "
                    f"({null_pct}% of rows)."
                ),
                evidence={
                    "null_count": null_count,
                    "null_pct": null_pct,
                    "row_count": row_count,
                },
                heuristic=True,
            )

        if (
            _ID_NAME_RE.search(name)
            and not c.get("probable_key")
            and null_count == 0
            and count > 1
        ):
            add(
                column=name,
                dimension="uniqueness",
                severity="warn",
                statement=(
                    f"Column '{name}' looks like an identifier but is not unique "
                    f"({c.get('distinct_count')} distinct of {count})."
                ),
                evidence={
                    "distinct_count": c.get("distinct_count"),
                    "distinct_pct": c.get("distinct_pct"),
                    "non_null_count": count - null_count,
                },
                heuristic=True,
            )

        if (
            c.get("dtype") in ("integer", "float")
            and (c.get("negative_count") or 0) > 0
            and _NONNEG_NAME_RE.search(name)
        ):
            add(
                column=name,
                dimension="validity",
                severity="info",
                statement=(
                    f"Column '{name}' has {c['negative_count']} negative value(s); "
                    "this field usually should be non-negative."
                ),
                evidence={"negative_count": c["negative_count"]},
                heuristic=True,
            )

    return _assign_ids(obs, "DQ")


def critical_unresolved_count(content: dict) -> int:
    """Critical observations with no approved rule referencing them (and not
    explicitly accepted). Deterministic."""
    obs = content.get("observations") or []
    rules = content.get("rules") or []
    covered: set[str] = set()
    for r in rules:
        if r.get("status") == "approved" or r.get("accepted_risk"):
            covered.update(r.get("related_observations") or [])
    return sum(
        1
        for o in obs
        if o.get("severity") == "critical" and o.get("id") not in covered
    )
