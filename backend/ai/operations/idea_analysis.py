"""
idea_analysis — Phase 0 plumbing operation.

Given a raw product idea, return a small structured analysis. Its job in Phase 0
is to exercise the full AI path end to end: prompt -> Anthropic -> structured JSON
-> schema validation -> persistence. The real discovery pipeline is built in
later phases and will follow this same shape (Operation + Pydantic schema).
"""
from pydantic import BaseModel, Field

from ai.base import Operation

SYSTEM_PROMPT = (
    "You are VYRA's product analyst. VYRA turns a software idea into a structured "
    "engineering workflow. Given a raw idea, identify what is already clear and "
    "what still needs to be decided before requirements can be written. Be concise "
    "and specific to the idea. Do not invent features the user did not mention. "
    "Always respond by calling the provided tool."
)


class IdeaAnalysis(BaseModel):
    domain: str = Field(
        description="Short label for the product domain, e.g. 'B2B marketplace'."
    )
    product_type_guess: str = Field(
        description="Best guess at the product type, e.g. 'web application'."
    )
    known: list[str] = Field(
        default_factory=list,
        description="Facts clearly stated or strongly implied by the idea.",
    )
    unknowns: list[str] = Field(
        default_factory=list,
        description="Important decisions still missing from the idea.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions VYRA would make if forced to proceed right now.",
    )


def build_user_prompt(context: dict) -> str:
    return (
        'Software idea:\n\n"""\n'
        f"{context['idea']}\n"
        '"""\n\nAnalyse this idea.'
    )


IDEA_ANALYSIS = Operation(
    name="idea_analysis",
    system_prompt=SYSTEM_PROMPT,
    schema=IdeaAnalysis,
    build_user_prompt=build_user_prompt,
)
