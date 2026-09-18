"""
Query Plan schema (Phase I-3). The plan is a human decision — required before
SQL generation. Multi-dataset joins are explicitly out of scope for I-3 (see
``QueryPlanContent.joins`` — must be empty; documented deferral to I-4+).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class QueryPlanContent(BaseModel):
    objective: str = Field(min_length=1)
    required_kpi_refs: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    base_table_ref: str = Field(min_length=1)
    grain: str = ""
    dimensions: list[str] = Field(default_factory=list)
    filters: list[dict] = Field(default_factory=list)
    joins: list[dict] = Field(default_factory=list)
    sort: list[str] = Field(default_factory=list)
    expected_result_shape: str = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("joins")
    @classmethod
    def _no_joins_yet(cls, v: list[dict]) -> list[dict]:
        if v:
            raise ValueError(
                "multi-dataset joins are not supported in this phase "
                "(deferred) — use a single base_table_ref"
            )
        return v

    @field_validator(
        "required_kpi_refs", "required_fields", "dimensions", "sort", "assumptions",
        mode="after",
    )
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return [str(x).strip() for x in v if str(x).strip()]


PLAN_FIELDS = tuple(QueryPlanContent.model_fields.keys())
