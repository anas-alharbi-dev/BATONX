"""
Stored Architecture schema + normalization.

For architecture there is no AI-output-vs-storage transform (no server-assigned
ids), so this single schema is the contract for both. The AI operation module
imports ``ArchitectureContent`` from here; ``ai.base`` treats it as an opaque
Pydantic model, so no domain logic leaks into the AI layer.

``normalize_architecture_content`` trims blank list entries. Idempotent; runs
after generation and after every section edit.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_STRING_LIST_FIELDS = ("security", "constraints")


def _clean(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item and item.strip()]


class Overview(BaseModel):
    style: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class TechChoice(BaseModel):
    choice: str = Field(min_length=1)
    why: str = Field(min_length=1)


class AuthApproach(BaseModel):
    approach: str = Field(min_length=1)
    why: str = Field(min_length=1)


class DeploymentApproach(BaseModel):
    approach: str = Field(min_length=1)
    why: str = Field(min_length=1)


class Component(BaseModel):
    name: str = Field(min_length=1)
    responsibility: str = Field(min_length=1)


class ApiArea(BaseModel):
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)


class Entity(BaseModel):
    entity: str = Field(min_length=1)
    fields: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)

    @field_validator("fields", "relationships", mode="after")
    @classmethod
    def _clean_lists(cls, value: list[str]) -> list[str]:
        return _clean(value)


class Integration(BaseModel):
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    why: str = ""


class Decision(BaseModel):
    decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class ArchitectureContent(BaseModel):
    overview: Overview
    frontend: TechChoice
    backend: TechChoice
    database: TechChoice
    auth: AuthApproach
    components: list[Component] = Field(min_length=1)
    api_areas: list[ApiArea] = Field(min_length=1)
    data_model: list[Entity] = Field(min_length=1)
    integrations: list[Integration] = Field(default_factory=list)
    security: list[str] = Field(min_length=1)
    deployment: DeploymentApproach
    key_decisions: list[Decision] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)

    @field_validator(*_STRING_LIST_FIELDS, mode="after")
    @classmethod
    def _clean_string_lists(cls, value: list[str]) -> list[str]:
        return _clean(value)


def normalize_architecture_content(content: dict) -> dict:
    """Idempotent pre-validation cleanup: trim blank list entries."""
    result = dict(content)

    for field in _STRING_LIST_FIELDS:
        if isinstance(result.get(field), list):
            result[field] = [str(x).strip() for x in result[field] if str(x).strip()]

    if isinstance(result.get("data_model"), list):
        cleaned_entities = []
        for entity in result["data_model"]:
            entity = dict(entity)
            for key in ("fields", "relationships"):
                if isinstance(entity.get(key), list):
                    entity[key] = [
                        str(x).strip() for x in entity[key] if str(x).strip()
                    ]
            cleaned_entities.append(entity)
        result["data_model"] = cleaned_entities

    return result


SECTION_FIELDS = tuple(ArchitectureContent.model_fields.keys())
