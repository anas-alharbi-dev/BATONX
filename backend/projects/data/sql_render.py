"""
Deterministic SQL renderer for the fixed Transformation Plan op set (Phase I-2).

Structured steps are the Source of Truth. This compiles them to a single
DuckDB ``WITH ... SELECT`` over one BATONX-registered source view. The output is
still passed through ``validate_select_only`` before execution.

If any step / param cannot be compiled safely -> ``UnsupportedOperationError``
(the service turns this into ``422 unsupported_operation``). We never guess.
"""
from __future__ import annotations

import re

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .\-]*$")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")
_CAST_TYPES = {
    "bigint": "BIGINT",
    "integer": "BIGINT",
    "int": "BIGINT",
    "double": "DOUBLE",
    "float": "DOUBLE",
    "decimal": "DOUBLE",
    "varchar": "VARCHAR",
    "string": "VARCHAR",
    "text": "VARCHAR",
    "boolean": "BOOLEAN",
    "bool": "BOOLEAN",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
    "datetime": "TIMESTAMP",
}
_FILTER_OPS = {"=", "!=", "<", "<=", ">", ">=", "in", "not_in", "is_null", "is_not_null"}
# derive_column: a tiny allow-listed expression grammar
_EXPR_TOKEN = re.compile(
    r"""\s*(
        "(?:[^"]|"")*"        |   # quoted identifier
        '(?:[^']|'')*'        |   # string literal
        \d+(?:\.\d+)?         |   # number
        [A-Za-z_][A-Za-z0-9_]* |  # bare identifier / function name
        <=|>=|<>|!=|[-+*/(),<>=] |
        \|\|
    )""",
    re.VERBOSE,
)
_EXPR_FUNCS = {
    "upper", "lower", "trim", "length", "coalesce", "abs", "round", "floor",
    "ceil", "nullif", "concat", "cast", "try_cast",
}
_EXPR_BARE_KEYWORDS = {"as", "and", "or", "not", "null", "true", "false", "is"}


class UnsupportedOperationError(Exception):
    def __init__(self, message: str, *, op: str = ""):
        super().__init__(message)
        self.message = message
        self.op = op


def _ident(name: str) -> str:
    name = str(name)
    if not _IDENT_RE.match(name) or '"' in name:
        raise UnsupportedOperationError(f"unsafe column identifier: {name!r}")
    return '"' + name + '"'


def _lit(value) -> str:
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


def _check_expression(expr: str) -> str:
    """Allow only identifiers / literals / a few functions / arithmetic."""
    pos = 0
    out: list[str] = []
    depth = 0
    while pos < len(expr):
        m = _EXPR_TOKEN.match(expr, pos)
        if not m:
            if expr[pos:].strip() == "":
                break
            raise UnsupportedOperationError(
                f"unsupported token in derive expression near: {expr[pos:pos+16]!r}",
                op="derive_column",
            )
        tok = m.group(1)
        low = tok.lower()
        if tok in ("(", ")"):
            depth += 1 if tok == "(" else -1
            if depth < 0:
                raise UnsupportedOperationError("unbalanced parentheses", op="derive_column")
        elif tok.startswith('"') or tok.startswith("'"):
            pass
        elif _NUMERIC_RE.match(tok):
            pass
        elif tok in ("+", "-", "*", "/", ",", "<", ">", "=", "<=", ">=", "<>", "!=", "||"):
            pass
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", tok):
            nxt = expr[m.end():].lstrip()
            is_call = nxt.startswith("(")
            if is_call and low not in _EXPR_FUNCS:
                raise UnsupportedOperationError(
                    f"function '{tok}' is not allowed in a derive expression",
                    op="derive_column",
                )
            if not is_call and low not in _EXPR_BARE_KEYWORDS:
                # treat as a column reference -> must be a safe identifier
                _ident(tok)
        else:
            raise UnsupportedOperationError(
                f"unsupported token {tok!r} in derive expression", op="derive_column"
            )
        out.append(tok)
        pos = m.end()
    if depth != 0:
        raise UnsupportedOperationError("unbalanced parentheses", op="derive_column")
    return expr.strip()


def _render_step(op: str, params: dict, prev_cte: str) -> str:
    p = params or {}

    if op == "drop_columns":
        cols = [_ident(c) for c in (p.get("columns") or [])]
        if not cols:
            raise UnsupportedOperationError("drop_columns needs 'columns'", op=op)
        return f"SELECT * EXCLUDE ({', '.join(cols)}) FROM {prev_cte}"

    if op == "rename":
        mapping = p.get("mapping") or {}
        if not mapping:
            raise UnsupportedOperationError("rename needs 'mapping'", op=op)
        pairs = ", ".join(f"{_ident(k)} AS {_ident(v)}" for k, v in mapping.items())
        return f"SELECT * RENAME ({pairs}) FROM {prev_cte}"

    if op == "cast":
        col = _ident(p.get("column", ""))
        to = _CAST_TYPES.get(str(p.get("to_type", "")).lower())
        if not to:
            raise UnsupportedOperationError(
                f"cast to_type must be one of {sorted(set(_CAST_TYPES.values()))}", op=op
            )
        return f"SELECT * REPLACE (TRY_CAST({col} AS {to}) AS {col}) FROM {prev_cte}"

    if op == "fill_na":
        col = _ident(p.get("column", ""))
        if "value" not in p:
            raise UnsupportedOperationError("fill_na needs 'value'", op=op)
        return f"SELECT * REPLACE (COALESCE({col}, {_lit(p['value'])}) AS {col}) FROM {prev_cte}"

    if op == "dedupe":
        subset = p.get("subset") or []
        if subset:
            keys = ", ".join(_ident(c) for c in subset)
            return (
                f"SELECT * FROM {prev_cte} "
                f"QUALIFY row_number() OVER (PARTITION BY {keys} ORDER BY {keys}) = 1"
            )
        return f"SELECT DISTINCT * FROM {prev_cte}"

    if op == "standardize_values":
        col = _ident(p.get("column", ""))
        mapping = p.get("mapping") or {}
        if not mapping:
            raise UnsupportedOperationError("standardize_values needs 'mapping'", op=op)
        whens = " ".join(
            f"WHEN {_lit(k)} THEN {_lit(v)}" for k, v in mapping.items()
        )
        return f"SELECT * REPLACE (CASE {col} {whens} ELSE {col} END AS {col}) FROM {prev_cte}"

    if op == "parse_date":
        col = _ident(p.get("column", ""))
        fmt = p.get("format")
        if fmt:
            if "'" in str(fmt) or len(str(fmt)) > 40:
                raise UnsupportedOperationError("invalid date format", op=op)
            expr = f"TRY_STRPTIME({col}::VARCHAR, {_lit(fmt)})"
        else:
            expr = f"TRY_CAST({col} AS DATE)"
        return f"SELECT * REPLACE ({expr} AS {col}) FROM {prev_cte}"

    if op == "derive_column":
        name = _ident(p.get("name", ""))
        expr = _check_expression(str(p.get("expression", "")))
        if not expr:
            raise UnsupportedOperationError("derive_column needs 'expression'", op=op)
        return f"SELECT *, ({expr}) AS {name} FROM {prev_cte}"

    if op == "filter_rows":
        col = _ident(p.get("column", ""))
        oper = str(p.get("operator", "")).lower()
        if oper not in _FILTER_OPS:
            raise UnsupportedOperationError(
                f"filter operator must be one of {sorted(_FILTER_OPS)}", op=op
            )
        if oper == "is_null":
            cond = f"{col} IS NULL"
        elif oper == "is_not_null":
            cond = f"{col} IS NOT NULL"
        elif oper in ("in", "not_in"):
            values = p.get("value")
            if not isinstance(values, list) or not values:
                raise UnsupportedOperationError("'in' filter needs a non-empty list", op=op)
            rendered = ", ".join(_lit(v) for v in values)
            cond = f"{col} {'NOT IN' if oper == 'not_in' else 'IN'} ({rendered})"
        else:
            symbol = {"=": "=", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}[oper]
            cond = f"{col} {symbol} {_lit(p.get('value'))}"
        return f"SELECT * FROM {prev_cte} WHERE {cond}"

    raise UnsupportedOperationError(f"unsupported operation: {op}", op=op)


def render_plan_sql(content: dict, *, source_view: str) -> str:
    """Compile the plan's steps into one ``WITH ... SELECT`` over ``source_view``."""
    if not _IDENT_RE.match(source_view):
        raise UnsupportedOperationError("unsafe source view name")
    steps = content.get("steps") or []
    if not steps:
        raise UnsupportedOperationError("the plan has no steps")

    ctes = [f's0 AS (SELECT * FROM "{source_view}")']
    prev = "s0"
    for i, step in enumerate(steps, start=1):
        rendered = _render_step(step.get("op", ""), step.get("params") or {}, prev)
        cte = f"s{i}"
        ctes.append(f"{cte} AS ({rendered})")
        prev = cte

    return "WITH " + ",\n     ".join(ctes) + f"\nSELECT * FROM {prev}"
