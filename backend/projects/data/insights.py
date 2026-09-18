"""
Insight evidence validator (Phase I-4) — the critical boundary between
deterministic fact (``AnalysisResult.findings``) and AI interpretation
(``Insight``). Every rule here exists to make one guarantee: an Insight can
never assert a number, or a causal claim, that the referenced Findings do not
actually support.
"""
from __future__ import annotations

import json
import re

CONFIDENCE_LEVELS = ("low", "medium", "high")

_CAUSAL_PATTERNS = [
    re.compile(r"\bcaused\b", re.I),
    re.compile(r"\bcauses\b", re.I),
    re.compile(r"\bdue to\b", re.I),
    re.compile(r"\bresulted in\b", re.I),
    re.compile(r"\bled to\b", re.I),
    re.compile(r"\bbecause of\b", re.I),
]

# standalone numbers, incl. "%", "12.4", "1,234" — deliberately simple: this is
# a reconciliation backstop, not an NLP system.
_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*%?")


def _numbers_in(text: str) -> set[str]:
    found = set()
    for raw in _NUMBER_RE.findall(text or ""):
        cleaned = raw.strip(",.")
        if any(ch.isdigit() for ch in cleaned):
            found.add(cleaned)
    return found


def _evidence_blob(findings_by_id: dict, finding_ids: list[str]) -> str:
    parts = []
    for fid in finding_ids:
        f = findings_by_id.get(fid)
        if not f:
            continue
        parts.append(f.get("statement", ""))
        parts.append(json.dumps(f.get("metric_values", {}), default=str))
        parts.append(json.dumps(f.get("breakdown", []), default=str))
    return " ".join(parts)


def validate_insight_evidence(findings: list[dict], fields: dict) -> None:
    """
    Raises ``ValueError`` naming the first violation. ``findings`` is
    ``AnalysisResult.findings`` (the full immutable list); ``fields`` is the
    proposed Insight's fields (fact, interpretation, recommendation,
    supporting_finding_ids, ...).

    Enforces:
      - supporting_finding_ids non-empty, every id resolves to a real finding
      - Insight.fact must EXACTLY match one referenced finding's deterministic
        statement — never a free AI restatement (guarantees no fabricated or
        silently-altered number reaches ``fact``)
      - every number in ``interpretation`` must be reconcilable against the
        referenced findings' statement/metric_values/breakdown
      - ``fact``/``interpretation`` may not assert causal wording as settled
        fact (correlation/association only) — causal *suggestions* belong in
        ``recommendation``, which is advisory and is not scanned for this
    """
    findings_by_id = {f["id"]: f for f in findings}
    supporting = fields.get("supporting_finding_ids") or []
    if not supporting:
        raise ValueError("supporting_finding_ids must be non-empty")
    for fid in supporting:
        if fid not in findings_by_id:
            raise ValueError(f"supporting_finding_ids references an unknown finding: {fid!r}")

    fact = (fields.get("fact") or "").strip()
    allowed_statements = {findings_by_id[fid]["statement"] for fid in supporting}
    if fact not in allowed_statements:
        raise ValueError(
            "Insight.fact must exactly match one of the referenced findings' "
            "deterministic statements — it cannot be freely restated or "
            "contain a number that was not literally computed"
        )

    evidence_numbers = _numbers_in(_evidence_blob(findings_by_id, supporting))
    interpretation = fields.get("interpretation") or ""
    for num in _numbers_in(interpretation):
        if num not in evidence_numbers:
            raise ValueError(
                f"interpretation states a number ({num}) that cannot be "
                "reconciled with the referenced findings"
            )

    for field_name in ("fact", "interpretation"):
        text = fields.get(field_name) or ""
        for pattern in _CAUSAL_PATTERNS:
            if pattern.search(text):
                raise ValueError(
                    f"{field_name} asserts causal wording ({pattern.pattern!r}) "
                    "as fact — this Analysis method only supports correlation/"
                    "association; phrase causal language as an advisory "
                    "suggestion to investigate in 'recommendation', not a fact"
                )
