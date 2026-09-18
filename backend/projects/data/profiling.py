"""
Deterministic dataset profiling (Phase I-1).

Pure Python — stdlib ``csv`` / ``json`` / ``statistics`` only. NO pandas, NO
numpy, NO DuckDB, NO AI. Every number here is computed from the actual bytes.

Bounded and configurable via ``settings.DATA_PROFILE_*``. For a file with more
than ``DATA_PROFILE_SAMPLE_ROWS`` rows, only the first N rows are read and the
run is flagged ``sampled`` (deterministic — always the head).
"""
from __future__ import annotations

import csv
import io
import json
import re
import statistics
from collections import Counter

from django.conf import settings

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?")
_BOOL_TRUE = {"true", "t", "yes", "y", "1"}
_BOOL_FALSE = {"false", "f", "no", "n", "0"}

_PII_NAME_PATTERNS = [
    (re.compile(r"e[-_]?mail", re.I), "email"),
    (re.compile(r"\bphone\b|\bmobile\b|\btelephone\b|\bmsisdn\b", re.I), "phone"),
    (re.compile(r"\bssn\b|national[-_ ]?id|passport|nid\b", re.I), "national_id"),
    (re.compile(r"first[-_ ]?name|last[-_ ]?name|full[-_ ]?name|\bname\b", re.I), "name"),
    (re.compile(r"\biban\b|account[-_ ]?number|card[-_ ]?number|\bcvv\b", re.I), "financial"),
    (re.compile(r"\baddress\b|street|postcode|zip[-_ ]?code", re.I), "address"),
]


class ProfilingError(Exception):
    pass


def _decode(raw: bytes) -> tuple[str, str]:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc), ("utf-8" if enc == "utf-8-sig" else enc)
        except UnicodeDecodeError:
            continue
    raise ProfilingError("could not decode file as text")


def _pii_kind(column_name: str) -> str | None:
    for pattern, kind in _PII_NAME_PATTERNS:
        if pattern.search(column_name or ""):
            return kind
    return None


def _read_csv(text: str, max_rows: int) -> tuple[list[str], list[list[str]], str, bool]:
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        raise ProfilingError("empty CSV")
    header = [h.strip() for h in header]
    if not header or all(h == "" for h in header):
        raise ProfilingError("CSV has no header row")
    rows: list[list[str]] = []
    truncated = False
    for i, row in enumerate(reader):
        if i >= max_rows:
            truncated = True
            break
        # pad/trim to header width
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        elif len(row) > len(header):
            row = row[: len(header)]
        rows.append(row)
    return header, rows, delimiter, truncated


def _read_json(text: str, max_rows: int) -> tuple[list[str], list[list], bool]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProfilingError(f"invalid JSON: {exc}")
    if isinstance(parsed, dict):
        # tolerate {"data": [...]} / {"rows": [...]} / {"records": [...]}
        for key in ("data", "rows", "records", "items", "results"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list) or not parsed:
        raise ProfilingError("JSON must be a non-empty array of objects")
    if not all(isinstance(item, dict) for item in parsed[:50]):
        raise ProfilingError("JSON array items must be objects")
    columns: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        for k in item.keys():
            if k not in seen:
                seen.add(k)
                columns.append(str(k))
    truncated = False
    rows: list[list] = []
    for i, item in enumerate(parsed):
        if i >= max_rows:
            truncated = True
            break
        rows.append([item.get(c, None) for c in columns])
    return columns, rows, truncated


def _is_null(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _classify(values: list) -> str:
    non_null = [v for v in values if not _is_null(v)]
    if not non_null:
        return "string"
    as_str = [str(v).strip() for v in non_null]
    if all(isinstance(v, bool) for v in non_null) or all(
        s.lower() in _BOOL_TRUE | _BOOL_FALSE for s in as_str
    ):
        return "boolean"
    if all(_INT_RE.match(s) for s in as_str):
        return "integer"
    if all(_FLOAT_RE.match(s) for s in as_str):
        return "float"
    if all(_DATE_RE.match(s) for s in as_str):
        return "date"
    if all(_DATETIME_RE.match(s) for s in as_str):
        return "datetime"
    distinct = len(set(as_str))
    if distinct <= max(1, len(as_str) // 20) and distinct <= 50:
        return "categorical"
    return "string"


def _numeric(values: list[str]) -> dict:
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return {}
    nums.sort()

    def pct(p: float) -> float:
        if len(nums) == 1:
            return round(nums[0], 4)
        idx = p * (len(nums) - 1)
        lo = int(idx)
        frac = idx - lo
        hi = min(lo + 1, len(nums) - 1)
        return round(nums[lo] + (nums[hi] - nums[lo]) * frac, 4)

    return {
        "min": round(nums[0], 4),
        "max": round(nums[-1], 4),
        "mean": round(statistics.fmean(nums), 4),
        "median": round(statistics.median(nums), 4),
        "stddev": round(statistics.pstdev(nums), 4) if len(nums) > 1 else 0.0,
        "p25": pct(0.25),
        "p75": pct(0.75),
        "zero_count": sum(1 for n in nums if n == 0),
        "negative_count": sum(1 for n in nums if n < 0),
        "numeric_range": f"{round(nums[0], 4)} .. {round(nums[-1], 4)}",
    }


def _dates(values: list[str]) -> dict:
    vals = sorted(str(v).strip() for v in values)
    if not vals:
        return {}
    return {"min_date": vals[0], "max_date": vals[-1], "date_range": f"{vals[0]} .. {vals[-1]}"}


def _profile_column(name: str, raw_values: list, total_rows: int) -> dict:
    top_cap = settings.DATA_PROFILE_TOP_VALUES
    sample_cap = settings.DATA_PROFILE_SAMPLE_VALUES

    null_count = sum(1 for v in raw_values if _is_null(v))
    non_null = [v for v in raw_values if not _is_null(v)]
    non_null_str = [str(v).strip() for v in non_null]
    count = len(raw_values)

    distinct = set(non_null_str)
    distinct_count = len(distinct)
    dtype = _classify(raw_values)
    pii = _pii_kind(name)

    col: dict = {
        "name": name,
        "dtype": dtype,
        "count": count,
        "null_count": null_count,
        "null_pct": round(null_count / count * 100, 2) if count else 0.0,
        "distinct_count": distinct_count,
        "distinct_pct": round(distinct_count / len(non_null_str) * 100, 2)
        if non_null_str
        else 0.0,
        "probable_key": (
            null_count == 0 and distinct_count == len(non_null_str) and count > 1
        ),
        "sensitivity": "pii_likely" if pii else None,
        "sensitivity_kind": pii,
    }

    if dtype in ("integer", "float"):
        col.update(_numeric(non_null_str))
    elif dtype in ("date", "datetime"):
        col.update(_dates(non_null_str))
    else:
        lengths = [len(s) for s in non_null_str[: settings.DATA_MAX_ROWS]]
        if lengths:
            col["min_length"] = min(lengths)
            col["max_length"] = max(lengths)
        col["blank_count"] = sum(1 for v in raw_values if isinstance(v, str) and v.strip() == "" )

    counter = Counter(non_null_str)
    redact = pii is not None
    col["top_values"] = [
        {"value": "***" if redact else val, "count": cnt}
        for val, cnt in counter.most_common(top_cap)
    ]
    sample_vals = list(dict.fromkeys(non_null_str))[:sample_cap]
    col["sample"] = ["***" for _ in sample_vals] if redact else sample_vals
    return col


def profile_bytes(raw: bytes, source_type: str) -> dict:
    """Return ``{table_stats, columns, delimiter, encoding}`` — deterministic."""
    max_rows = settings.DATA_PROFILE_SAMPLE_ROWS
    text, encoding = _decode(raw)

    delimiter = None
    if source_type == "csv":
        header, rows, delimiter, truncated = _read_csv(text, max_rows)
    elif source_type == "json":
        header, rows, truncated = _read_json(text, max_rows)
    else:  # pragma: no cover - guarded upstream
        raise ProfilingError(f"unsupported source_type {source_type!r}")

    row_count = len(rows)
    column_count = len(header)

    # duplicate rows among those read
    seen: Counter = Counter(tuple("" if _is_null(c) else str(c) for c in r) for r in rows)
    duplicate_row_count = sum(c - 1 for c in seen.values() if c > 1)

    columns = []
    for idx, name in enumerate(header):
        col_values = [r[idx] if idx < len(r) else None for r in rows]
        columns.append(_profile_column(name or f"column_{idx + 1}", col_values, row_count))

    return {
        "table_stats": {
            "row_count": row_count,
            "column_count": column_count,
            "duplicate_row_count": duplicate_row_count,
            "sampled": bool(truncated),
            "sample_size": row_count if truncated else row_count,
        },
        "columns": columns,
        "delimiter": delimiter,
        "encoding": encoding,
    }


def inferred_schema_from_columns(columns: list[dict]) -> list[dict]:
    """The compact schema cached on ``Dataset.inferred_schema``."""
    return [
        {
            "name": c["name"],
            "dtype": c["dtype"],
            "nullable": c["null_count"] > 0,
            "sensitivity": c.get("sensitivity"),
        }
        for c in columns
    ]
