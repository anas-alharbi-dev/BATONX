"""
Metric / KPI structured grammar (Phase I-3).

A deliberately constrained grammar — not an unrestricted expression engine.
Every reference (``base_table_ref`` + every field) must resolve against the
project's real dataset schemas; a definition that can't be deterministically
translated or validated is rejected.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Aggregation = Literal["sum", "count", "count_distinct", "avg", "min", "max", "ratio"]
FilterOp = Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"]


class MetricMeasure(BaseModel):
    field: str = Field(min_length=1)


class MetricFilter(BaseModel):
    field: str = Field(min_length=1)
    operator: FilterOp
    value: object = None

    @model_validator(mode="after")
    def _check_value(self) -> "MetricFilter":
        if self.operator in ("in", "not_in") and not isinstance(self.value, list):
            raise ValueError(f"'{self.operator}' needs a list value")
        return self


class MetricStructured(BaseModel):
    aggregation: Aggregation
    base_table_ref: str = Field(min_length=1)
    measure: Optional[MetricMeasure] = None
    numerator: Optional[MetricMeasure] = None
    denominator: Optional[MetricMeasure] = None
    default_filters: list[MetricFilter] = Field(default_factory=list)
    time_field: str = ""
    dimensions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_shape(self) -> "MetricStructured":
        if self.aggregation == "ratio":
            if not self.numerator or not self.denominator:
                raise ValueError("ratio needs both numerator and denominator")
        elif self.aggregation != "count":
            if not self.measure:
                raise ValueError(f"{self.aggregation} needs a measure field")
        return self

    def referenced_fields(self) -> set[str]:
        fields: set[str] = set()
        for m in (self.measure, self.numerator, self.denominator):
            if m:
                fields.add(m.field)
        for f in self.default_filters:
            fields.add(f.field)
        if self.time_field:
            fields.add(self.time_field)
        fields.update(self.dimensions)
        return fields


class MetricFields(BaseModel):
    """Validated shape of one metric — used for both AI drafts and edits."""

    name: str = Field(min_length=1)
    business_meaning: str = ""
    formula_text: str = ""
    structured: MetricStructured
    time_grain: str = ""
    allowed_dimensions: list[str] = Field(default_factory=list)
    source_fields: list[str] = Field(default_factory=list)
    owner: str = ""
    related_goal_ref: str = ""
    caveats: list[str] = Field(default_factory=list)
    validation_checks: list[str] = Field(default_factory=list)

    @field_validator(
        "allowed_dimensions", "source_fields", "caveats", "validation_checks",
        mode="after",
    )
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return [str(x).strip() for x in v if str(x).strip()]


EDITABLE_FIELDS = tuple(
    f for f in MetricFields.model_fields.keys()
)


def validate_references(structured: MetricStructured, schema: dict[str, set[str]]) -> None:
    """
    ``schema`` maps ``base_table_ref -> {available field names}``. Raises
    ``ValueError`` naming the first bad reference. No AI-invented fields survive.
    """
    ref = structured.base_table_ref
    if ref not in schema:
        raise ValueError(f"unknown base_table_ref: {ref!r}")
    available = schema[ref]
    for field in sorted(structured.referenced_fields()):
        if field not in available:
            raise ValueError(f"field {field!r} does not exist on {ref!r}")
