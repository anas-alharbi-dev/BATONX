"""
Stored Business Logic schema + normalization.

Business Logic sits between the Blueprint ("what are we building?") and the
Architecture ("how do we build it?") and makes explicit *how the product must
behave* - the rules an AI coding agent must not invent later.

Storage contract (this module) vs. AI-output contract
(``ai.operations.business_logic_generation.BusinessLogicDraft``): the difference
is that stored business rules / validations / edge cases carry a stable,
server-assigned id (``BR-01``, ``VAL-01``, ``EC-01``).
``normalize_business_logic_content`` is the single place that assigns ids,
canonicalises requirement references (``FR-08`` -> ``FR8`` to match the
Blueprint's ids), and trims blanks. It is idempotent.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_ID_RE = {
    "business_rules": re.compile(r"^BR-\d{2,}$"),
    "validations": re.compile(r"^VAL-\d{2,}$"),
    "edge_cases": re.compile(r"^EC-\d{2,}$"),
}
_ID_PREFIX = {"business_rules": "BR", "validations": "VAL", "edge_cases": "EC"}
_REQ_RE = re.compile(r"^\s*fr[-\s_]?0*(\d+)\s*$", re.IGNORECASE)


def _clean(items) -> list[str]:
    return [str(x).strip() for x in (items or []) if str(x).strip()]


def canonical_requirement(ref: str) -> str:
    """``FR-08`` / ``fr 8`` / ``FR8`` -> ``FR8`` (Blueprint id form); else unchanged."""
    match = _REQ_RE.match(str(ref or ""))
    return f"FR{match.group(1)}" if match else str(ref or "").strip()


def _canon_reqs(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ref in _clean(items):
        canon = canonical_requirement(ref)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


# --- sub-models -----------------------------------------------------------


class Actor(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class Permission(BaseModel):
    actor: str = Field(min_length=1)
    can: list[str] = Field(min_length=1)
    conditions: list[str] = Field(default_factory=list)

    @field_validator("can", "conditions", mode="after")
    @classmethod
    def _c(cls, v):
        return _clean(v)


class BusinessRule(BaseModel):
    id: str = Field(pattern=r"^BR-\d{2,}$")
    statement: str = Field(min_length=1)
    actor: str = ""
    conditions: list[str] = Field(default_factory=list)
    outcome: str = ""
    exceptions: list[str] = Field(default_factory=list)
    validations: list[str] = Field(default_factory=list)
    related_requirements: list[str] = Field(default_factory=list)
    derived: bool = False

    @field_validator("conditions", "exceptions", "validations", mode="after")
    @classmethod
    def _c(cls, v):
        return _clean(v)


class Validation(BaseModel):
    id: str = Field(pattern=r"^VAL-\d{2,}$")
    rule: str = Field(min_length=1)
    applies_to: str = ""
    related_requirements: list[str] = Field(default_factory=list)


class ApprovalFlow(BaseModel):
    name: str = Field(min_length=1)
    approver: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    conditions: list[str] = Field(default_factory=list)
    related_requirements: list[str] = Field(default_factory=list)

    @field_validator("steps", "conditions", mode="after")
    @classmethod
    def _c(cls, v):
        return _clean(v)


class StateTransition(BaseModel):
    entity: str = Field(min_length=1)
    from_state: str = Field(min_length=1)
    to_state: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    actor: str = ""
    guards: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    related_requirements: list[str] = Field(default_factory=list)

    @field_validator("guards", "effects", mode="after")
    @classmethod
    def _c(cls, v):
        return _clean(v)


class EdgeCase(BaseModel):
    id: str = Field(pattern=r"^EC-\d{2,}$")
    scenario: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    related_requirements: list[str] = Field(default_factory=list)


class BusinessLogicContent(BaseModel):
    summary: str = Field(min_length=1)
    actors: list[Actor] = Field(min_length=1)
    permissions: list[Permission] = Field(default_factory=list)
    business_rules: list[BusinessRule] = Field(min_length=1)
    validations: list[Validation] = Field(default_factory=list)
    approval_flows: list[ApprovalFlow] = Field(default_factory=list)
    state_transitions: list[StateTransition] = Field(default_factory=list)
    edge_cases: list[EdgeCase] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    @field_validator("open_questions", mode="after")
    @classmethod
    def _c(cls, v):
        return _clean(v)


SECTION_FIELDS = tuple(BusinessLogicContent.model_fields.keys())


# --- normalization ------------------------------------------------------


def _assign_ids(items: list[dict], kind: str) -> list[dict]:
    pattern = _ID_RE[kind]
    prefix = _ID_PREFIX[kind]
    used: set[str] = set()
    result: list[dict] = []
    counter = 1
    for item in items or []:
        item = dict(item)
        rid = str(item.get("id") or "").strip()
        if not (rid and pattern.match(rid)) or rid in used:
            while f"{prefix}-{counter:02d}" in used:
                counter += 1
            rid = f"{prefix}-{counter:02d}"
            counter += 1
        used.add(rid)
        item["id"] = rid
        result.append(item)
    return result


_REQ_FIELDS_BY_SECTION = {
    "permissions": (),  # no requirement refs
    "business_rules": ("related_requirements",),
    "validations": ("related_requirements",),
    "approval_flows": ("related_requirements",),
    "state_transitions": ("related_requirements",),
    "edge_cases": ("related_requirements",),
}


def normalize_business_logic_content(content: dict) -> dict:
    result = dict(content)

    for kind in ("business_rules", "validations", "edge_cases"):
        if isinstance(result.get(kind), list):
            result[kind] = _assign_ids(result[kind], kind)

    for section, req_fields in _REQ_FIELDS_BY_SECTION.items():
        rows = result.get(section)
        if not isinstance(rows, list):
            continue
        cleaned = []
        for row in rows:
            row = dict(row)
            for field in req_fields:
                if field in row:
                    row[field] = _canon_reqs(row[field])
            cleaned.append(row)
        result[section] = cleaned

    if isinstance(result.get("open_questions"), list):
        result["open_questions"] = _clean(result["open_questions"])

    return result
