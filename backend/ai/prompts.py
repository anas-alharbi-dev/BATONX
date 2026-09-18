"""Shared prompt fragments used across AI operations."""


def render_business_logic(bl: dict) -> list[str]:
    """
    Render an approved-Business-Logic dict (full ``content`` or a
    context-selection slice) as prompt lines. Empty list when Business Logic is
    absent (e.g. a grandfathered project). Tolerant of both key spellings
    (``from_state``/``from``).
    """
    if not bl:
        return []
    lines = [
        "APPROVED BUSINESS LOGIC (authoritative - implement exactly, do not invent):",
        f"Summary: {bl.get('summary', '')}",
    ]
    for rule in bl.get("business_rules") or []:
        refs = ", ".join(rule.get("related_requirements", []))
        lines.append(
            f"- {rule.get('id', 'BR')}: {rule.get('statement', '')}"
            + (f" (actor: {rule['actor']})" if rule.get("actor") else "")
            + (f" [reqs: {refs}]" if refs else "")
        )
    perms = bl.get("permissions") or []
    if perms:
        lines.append("Permissions:")
        for p in perms:
            lines.append(f"- {p.get('actor', '')}: " + "; ".join(p.get("can", [])))
    vals = bl.get("validations") or []
    if vals:
        lines.append("Business validations:")
        for v in vals:
            lines.append(f"- {v.get('id', 'VAL')}: {v.get('rule', '')}")
    trans = bl.get("state_transitions") or []
    if trans:
        lines.append("State transitions:")
        for t in trans:
            src = t.get("from_state") or t.get("from") or "?"
            dst = t.get("to_state") or t.get("to") or "?"
            lines.append(
                f"- {t.get('entity', '?')}: {src} -> {dst} on '{t.get('trigger', '')}'"
                + (f" (actor: {t['actor']})" if t.get("actor") else "")
            )
    flows = bl.get("approval_flows") or []
    if flows:
        lines.append("Approval flows:")
        for f in flows:
            lines.append(
                f"- {f.get('name', '')} (approver: {f.get('approver', '')}): "
                + " -> ".join(f.get("steps", []))
            )
    edges = bl.get("edge_cases") or []
    if edges:
        lines.append("Edge cases:")
        for e in edges:
            lines.append(
                f"- {e.get('id', 'EC')}: {e.get('scenario', '')} => "
                f"{e.get('expected_behavior', '')}"
            )
    oq = bl.get("open_questions") or []
    if oq:
        lines.append("Open questions (unresolved - do NOT assume a policy):")
        lines.extend(f"- {q}" for q in oq)
    return lines


# Injected into every generation system prompt. Encodes VYRA's AI quality rules
# (product spec section 29).
QUALITY_RULES = """\
Quality rules you must follow:
- Use the user's actual idea and the analysis provided. Do not invent features,
  user types, or integrations the user did not state or clearly imply.
- Separate confirmed facts from assumptions.
- Only surface decisions that materially change scope, user roles, business rules,
  target platform, architecture, external integrations, payments or transactions,
  security, or the core workflow.
- Prefer specific, decision-forcing questions over broad or generic ones.
- One decision per question. No compound questions.
- Keep the set small: 3 to 6 items. Fewer is better when the idea is already clear.
- Never contradict the user's stated intent.
"""
