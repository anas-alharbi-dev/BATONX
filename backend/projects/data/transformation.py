"""
Transformation Plan — a Project-level structured artifact (Phase I-2).

Structured steps are the Source of Truth. SQL is a derived render
(``projects.data.sql_render``). Only the fixed I-2 op set is accepted; join /
aggregate / pivot / union are intentionally NOT valid ops yet.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Op = Literal[
    "drop_columns",
    "rename",
    "cast",
    "fill_na",
    "dedupe",
    "standardize_values",
    "parse_date",
    "derive_column",
    "filter_rows",
]
OPS = tuple(Op.__args__)  # type: ignore[attr-defined]

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .\-]*$")


class TransformStep(BaseModel):
    id: str = Field(pattern=r"^TX-\d{2,}$")
    op: Op
    params: dict = Field(default_factory=dict)
    input_refs: list[str] = Field(default_factory=list)
    output_name: str = Field(min_length=1)
    rationale: str = ""
    related_quality_rules: list[str] = Field(default_factory=list)

    @field_validator("output_name")
    @classmethod
    def _safe_output(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("output_name must be a plain identifier")
        return v


class TransformOutput(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    grain: str = ""
    columns: list[dict] = Field(default_factory=list)  # derived schema, best-effort


class TransformationPlanContent(BaseModel):
    source_dataset_id: str = Field(min_length=1)
    steps: list[TransformStep] = Field(min_length=1)
    outputs: list[TransformOutput] = Field(default_factory=list)


SECTION_FIELDS = tuple(TransformationPlanContent.model_fields.keys())


def normalize_transformation_plan_content(content: dict) -> dict:
    result = dict(content)
    steps_in = list(result.get("steps") or [])
    used: set[str] = set()
    out_steps: list[dict] = []
    counter = 1
    pat = re.compile(r"^TX-\d{2,}$")
    for raw in steps_in:
        step = dict(raw)
        sid = str(step.get("id") or "").strip()
        if not sid or not pat.match(sid) or sid in used:
            while f"TX-{counter:02d}" in used:
                counter += 1
            sid = f"TX-{counter:02d}"
            counter += 1
        used.add(sid)
        step["id"] = sid
        step["related_quality_rules"] = [
            str(x).strip()
            for x in (step.get("related_quality_rules") or [])
            if str(x).strip()
        ]
        step["input_refs"] = [
            str(x).strip() for x in (step.get("input_refs") or []) if str(x).strip()
        ]
        if not step.get("output_name"):
            step["output_name"] = f"step_{sid.lower().replace('-', '_')}"
        out_steps.append(step)
    result["steps"] = out_steps

    result["outputs"] = [o for o in (result.get("outputs") or []) if isinstance(o, dict)]
    return result
