"""
Analysis Plan structured grammar (Phase I-4).

Deliberately constrained to five methods, each with a known deterministic
execution strategy (``analysis_execution.py``) — not a general-purpose
statistics engine. Structural shape (which fields a method requires) is
validated here, purely from the content itself. Reference validation (does
``required_metrics``/``segments``/comparison filter fields actually exist,
belong to this project, and are approved) is a separate DB-aware step in
``analysis_services.py`` — kept apart so this module has no DB dependency.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from projects.data.metrics import MetricFilter

AnalysisMethodLiteral = Literal[
    "descriptive", "trend", "segmentation", "comparison", "funnel"
]


class ComparisonSpec(BaseModel):
    """One named 'side' of a trend/comparison/funnel — either a time window, a
    set of extra filters, or both. For ``funnel`` each entry is one ordered
    step; its filters accumulate with every prior step's filters."""

    label: str = Field(min_length=1)
    time_range: Optional[dict] = None  # {"start": "...", "end": "..."}
    filters: list[MetricFilter] = Field(default_factory=list)

    @field_validator("time_range")
    @classmethod
    def _check_time_range(cls, v):
        if v is None:
            return v
        if not isinstance(v, dict) or not v.get("start") or not v.get("end"):
            raise ValueError("time_range needs non-empty 'start' and 'end'")
        return v


class AnalysisPlanContent(BaseModel):
    business_question: str = Field(min_length=1)
    method: AnalysisMethodLiteral
    hypotheses: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(default_factory=list)  # KPI business ids
    segments: list[str] = Field(default_factory=list)
    comparisons: list[ComparisonSpec] = Field(default_factory=list)
    time_range: Optional[dict] = None
    expected_outputs: list[str] = Field(default_factory=list)

    @field_validator(
        "hypotheses", "required_metrics", "segments", "expected_outputs",
        mode="after",
    )
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return [str(x).strip() for x in v if str(x).strip()]

    @field_validator("time_range")
    @classmethod
    def _check_overall_time_range(cls, v):
        if v is None:
            return v
        if not isinstance(v, dict) or not v.get("start") or not v.get("end"):
            raise ValueError("time_range needs non-empty 'start' and 'end'")
        return v

    @model_validator(mode="after")
    def _check_method_shape(self) -> "AnalysisPlanContent":
        if not self.required_metrics:
            raise ValueError("required_metrics must be non-empty")

        if self.method == "trend":
            if len(self.comparisons) != 2:
                raise ValueError(
                    "trend needs exactly 2 comparisons (a baseline and a "
                    "comparison period), each with a time_range"
                )
            if not all(c.time_range for c in self.comparisons):
                raise ValueError("every trend comparison needs a time_range")
        elif self.method == "comparison":
            if len(self.comparisons) != 2:
                raise ValueError("comparison needs exactly 2 comparisons to compare")
        elif self.method == "funnel":
            if len(self.comparisons) < 2:
                raise ValueError(
                    "funnel needs at least 2 ordered steps in comparisons"
                )
            if not all(c.filters for c in self.comparisons):
                raise ValueError("every funnel step needs at least one filter")
        elif self.method == "segmentation":
            if not self.segments:
                raise ValueError("segmentation needs at least one segment/dimension")
        # descriptive: no additional structural requirement
        return self


EDITABLE_FIELDS = tuple(AnalysisPlanContent.model_fields.keys())
