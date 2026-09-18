"""
Stored Source Interpretation schema + normalization (Phase I-1).

A per-Dataset, AI-proposed, human-approved reading of what a dataset *means*.
It never contains or alters deterministic profiling facts — it references them.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_STRING_LIST_FIELDS = ("key_columns", "caveats")


class ColumnMeaning(BaseModel):
    column: str = Field(min_length=1)
    meaning: str = Field(min_length=1)


class SensitivityFlag(BaseModel):
    column: str = Field(min_length=1)
    # e.g. "email", "phone", "name", "national_id", "financial", "other"
    kind: str = Field(min_length=1)
    note: str = ""


class SourceInterpretationContent(BaseModel):
    business_entity: str = Field(min_length=1)
    grain: str = Field(min_length=1)  # "one row represents ..."
    key_columns: list[str] = Field(default_factory=list)
    column_meanings: list[ColumnMeaning] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    sensitivity_flags: list[SensitivityFlag] = Field(default_factory=list)

    @field_validator(*_STRING_LIST_FIELDS, mode="after")
    @classmethod
    def _clean_string_list(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


def normalize_source_interpretation_content(content: dict) -> dict:
    """Idempotent cleanup applied before validation."""
    result = dict(content)
    for field in _STRING_LIST_FIELDS:
        if field in result and isinstance(result[field], list):
            result[field] = [
                str(item).strip() for item in result[field] if str(item).strip()
            ]
    for list_field in ("column_meanings", "sensitivity_flags"):
        if list_field in result and isinstance(result[list_field], list):
            result[list_field] = [
                row for row in result[list_field] if isinstance(row, dict)
            ]
    return result


SECTION_FIELDS = tuple(SourceInterpretationContent.model_fields.keys())
