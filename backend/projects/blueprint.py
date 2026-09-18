"""
Stored Product Blueprint schema + normalization.

This is the domain/storage contract (distinct from the AI output contract in
``ai.operations.blueprint_generation``). The difference: stored functional
requirements carry a stable server-assigned ``id`` (``FR1``, ``FR2``, ...) so the
UI and later phases can reference them. ``normalize_blueprint_content`` is the
single place that assigns ids and trims blank list entries; it runs after
generation and after every section edit.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

_STRING_LIST_FIELDS = (
    "target_users",
    "core_features",
    "mvp_features",
    "future_features",
    "business_rules",
    "out_of_scope",
)


class Priority(str, Enum):
    MUST = "must"
    SHOULD = "should"
    COULD = "could"


class UserRole(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class FunctionalRequirement(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=3)
    priority: Priority = Priority.SHOULD


class UserFlow(BaseModel):
    name: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)

    @field_validator("steps", mode="after")
    @classmethod
    def _clean_steps(cls, value: list[str]) -> list[str]:
        cleaned = [step.strip() for step in value if step and step.strip()]
        if not cleaned:
            raise ValueError("a flow needs at least one step")
        return cleaned


class BlueprintContent(BaseModel):
    product_summary: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    solution: str = Field(min_length=1)
    target_users: list[str] = Field(min_length=1)
    user_roles: list[UserRole] = Field(min_length=1)
    core_features: list[str] = Field(min_length=1)
    mvp_features: list[str] = Field(min_length=1)
    future_features: list[str] = Field(default_factory=list)
    functional_requirements: list[FunctionalRequirement] = Field(min_length=1)
    business_rules: list[str] = Field(default_factory=list)
    user_flows: list[UserFlow] = Field(min_length=1)
    out_of_scope: list[str] = Field(default_factory=list)

    @field_validator(*_STRING_LIST_FIELDS, mode="after")
    @classmethod
    def _clean_string_list(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


def normalize_blueprint_content(content: dict) -> dict:
    """
    Idempotent cleanup applied before validation:
    - assign / preserve functional-requirement ids (``FR1`` ..), keeping any the
      caller already supplied and minting unique ones for the rest
    - trim blank entries from string-list sections
    """
    result = dict(content)

    requirements = list(result.get("functional_requirements") or [])
    used_ids: set[str] = set()
    normalized_reqs: list[dict] = []
    counter = 1
    for req in requirements:
        req = dict(req)
        rid = str(req.get("id") or "").strip()
        if not rid or rid in used_ids:
            while f"FR{counter}" in used_ids:
                counter += 1
            rid = f"FR{counter}"
            counter += 1
        used_ids.add(rid)
        req["id"] = rid
        normalized_reqs.append(req)
    result["functional_requirements"] = normalized_reqs

    for field in _STRING_LIST_FIELDS:
        if field in result and isinstance(result[field], list):
            result[field] = [
                str(item).strip() for item in result[field] if str(item).strip()
            ]

    return result


SECTION_FIELDS = tuple(BlueprintContent.model_fields.keys())
