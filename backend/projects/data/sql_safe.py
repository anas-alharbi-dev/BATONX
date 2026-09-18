"""
Small shared SQL-safety helpers reused by every deterministic query builder in
`projects/data/` (quality checks, metric validation, query execution). Not
Software-shared code — safe to change freely within Data services.
"""
from __future__ import annotations

import re

from projects.data.execution import SqlValidationError

_IDENT_SAFE = re.compile(r"[^A-Za-z0-9_]")
_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .\-]*$")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")


def view_name(prefix: str, obj_id) -> str:
    """A safe, deterministic DuckDB view/table identifier for a UUID-keyed row."""
    return prefix + "_" + _IDENT_SAFE.sub("", str(obj_id))[:28]


def quote_ident(name: str) -> str:
    name = str(name)
    if not name or '"' in name or not _COLUMN_RE.match(name):
        raise SqlValidationError("bad_identifier", f"unsafe identifier: {name!r}")
    return '"' + name + '"'


def sql_literal(value) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return repr(value)
    s = str(value)
    if _NUMERIC_RE.match(s):
        return s
    return "'" + s.replace("'", "''") + "'"
