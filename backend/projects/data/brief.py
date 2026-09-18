"""
Stored Data Brief schema + normalization (Phase I-1).

The Data Brief is the first approved artifact of a Data project — the analogue
of the Software Blueprint. Domain/storage contract, distinct from the AI output
contract in ``ai.operations.data_brief_generation``.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_STRING_LIST_FIELDS = (
    "audience",
    "success_criteria",
    "constraints",
    "candidate_sources",
    "out_of_scope",
)


class DataBriefContent(BaseModel):
    business_goal: str = Field(min_length=1)
    decision_context: str = Field(min_length=1)
    audience: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    candidate_sources: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    # Echoed from ``Project.data_goal`` for context; informational only.
    data_goal: str = ""

    @field_validator(*_STRING_LIST_FIELDS, mode="after")
    @classmethod
    def _clean_string_list(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


def normalize_data_brief_content(content: dict) -> dict:
    """Idempotent cleanup applied before validation: trim blank list entries."""
    result = dict(content)
    for field in _STRING_LIST_FIELDS:
        if field in result and isinstance(result[field], list):
            result[field] = [
                str(item).strip() for item in result[field] if str(item).strip()
            ]
    if "data_goal" in result and result["data_goal"] is not None:
        result["data_goal"] = str(result["data_goal"]).strip()
    return result


SECTION_FIELDS = tuple(DataBriefContent.model_fields.keys())
