"""
DuckDB execution boundary (Phase I-2).

The single place `duckdb` is used. Everything that runs SQL — quality checks and
transformation previews — goes through ``DuckDBExecution.run_select``.

Security model (see the phase report for the DuckDB-1.5.5 verification):

BATONX-enforced (independent of DuckDB config):
  * ``validate_select_only`` — a real parse via ``duckdb.extract_statements``:
    exactly one statement, type SELECT, text must begin ``select``/``with``
    (bare ``PRAGMA`` parses as SELECT, so this catches it), plus a whole-word
    denylist over comment-stripped / string-masked SQL for DDL/DML/ATTACH/COPY/
    PRAGMA/CALL/SET/INSTALL/LOAD/... and for file-reader functions, URLs and
    filesystem-path literals.
  * a forked subprocess with ``join(timeout)`` → ``terminate()`` → ``kill()`` so
    a runaway native query is stopped by the OS, not just a Python thread.
  * BATONX registers the allowed datasets as in-memory tables from
    BATONX-controlled paths; the untrusted query only ever sees those names.
  * result rows capped at ``DATA_QUERY_MAX_RESULT_ROWS``.

DuckDB-enforced (verified against 1.5.5, applied at connection setup):
  * ``enable_external_access=false``  → blocks read_csv/read_json/read_parquet/
    glob/ATTACH/COPY-to-file/URLs/INSTALL/LOAD at runtime.
  * ``autoinstall_known_extensions=false`` / ``autoload_known_extensions=false``
  * ``allow_community_extensions=false`` / ``allow_unsigned_extensions=false``
  * ``memory_limit`` / ``threads`` / ``max_temp_directory_size`` limits.
  * ``lock_configuration=true`` after setup → SQL cannot re-enable any of the
    above (verified: ``SET`` after lock raises).

Generated SQL — including SQL produced by BATONX's own renderer or AI — is
treated as untrusted and goes through the identical path.
"""
from __future__ import annotations

import multiprocessing
import re
import threading

from django.conf import settings

# --- errors ----------------------------------------------------------------


class SqlValidationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class QueryExecutionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --- SQL validation (BATONX-enforced) -----------------------------------

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b("
    r"insert|update|delete|merge|upsert|"
    r"create|drop|alter|truncate|"
    r"attach|detach|copy|export|import|"
    r"pragma|call|set|reset|vacuum|checkpoint|analyze|"
    r"install|load|"
    r"prepare|execute|deallocate|"
    r"begin|commit|rollback|transaction"
    r")\b",
    re.IGNORECASE,
)

_FORBIDDEN_FUNCTIONS = re.compile(
    r"\b("
    r"read_csv|read_csv_auto|read_json|read_json_auto|read_json_objects|read_ndjson|"
    r"read_parquet|read_text|read_blob|read_xlsx|"
    r"parquet_scan|csv_scan|json_scan|iceberg_scan|delta_scan|"
    r"parquet_metadata|parquet_schema|parquet_file_metadata|"
    r"sniff_csv|glob|"
    r"install|load"
    r")\s*\(",
    re.IGNORECASE,
)

_URL_LITERAL = re.compile(r"[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
_FS_PATH_LITERAL = re.compile(r"'\s*(?:[/~]|\.{1,2}/|[a-zA-Z]:\\)")


def _strip_comments(sql: str) -> str:
    return _LINE_COMMENT.sub(" ", _BLOCK_COMMENT.sub(" ", sql))


def _mask_strings(sql: str) -> str:
    return _STRING_LITERAL.sub("''", sql)


def validate_select_only(sql: str) -> None:
    """Raise ``SqlValidationError`` unless ``sql`` is a single read-only SELECT."""
    if not sql or not sql.strip():
        raise SqlValidationError("empty_sql", "No SQL to run.")

    # 1) real parse — one statement, SELECT type
    import duckdb

    try:
        con = duckdb.connect(":memory:")
        try:
            statements = con.extract_statements(sql)
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        raise SqlValidationError("invalid_sql", f"Could not parse SQL: {exc}")

    if len(statements) != 1:
        raise SqlValidationError(
            "multiple_statements", "Only a single SQL statement is allowed."
        )
    stmt_type = str(getattr(statements[0], "type", "")).upper()
    if not stmt_type.endswith("SELECT"):
        raise SqlValidationError(
            "non_select_statement", f"Only SELECT queries are allowed (got {stmt_type})."
        )

    # 2) text-level checks over comment-stripped SQL
    no_comments = _strip_comments(sql).strip()
    lowered = no_comments.lstrip("( \t\r\n").lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise SqlValidationError(
            "non_select_statement",
            "The query must begin with SELECT or WITH.",
        )

    masked = _mask_strings(no_comments)
    kw = _FORBIDDEN_KEYWORDS.search(masked)
    if kw:
        raise SqlValidationError(
            "forbidden_keyword", f"'{kw.group(1).upper()}' is not allowed in a query."
        )
    fn = _FORBIDDEN_FUNCTIONS.search(masked)
    if fn:
        raise SqlValidationError(
            "forbidden_function",
            f"'{fn.group(1)}(...)' is not allowed — datasets are registered by BATONX.",
        )

    # 3) no URLs / filesystem paths anywhere in the raw SQL (incl. strings)
    if _URL_LITERAL.search(sql):
        raise SqlValidationError("forbidden_reference", "URLs are not allowed in a query.")
    if _FS_PATH_LITERAL.search(sql):
        raise SqlValidationError(
            "forbidden_reference", "Filesystem paths are not allowed in a query."
        )


# --- forked worker (runs the actual query) ----------------------------

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _jsonable(value):  # pragma: no cover - subprocess helper
    """Coerce a DuckDB cell to something a Postgres JSONField accepts."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()[:64]
    try:  # date / datetime / time
        return value.isoformat()
    except AttributeError:
        pass
    try:  # Decimal
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _duckdb_worker(datasets, queries, max_rows, limits, out_q):  # pragma: no cover - subprocess
    """
    Executed in a forked child. Imports only duckdb + stdlib (no Django). Builds
    a fresh in-memory database, materialises the allowed datasets from
    BATONX-controlled paths, hardens + LOCKS the config, then runs each of
    ``queries`` (``[(label, sql), ...]``) in order.
    """
    interrupted = threading.Event()
    try:
        import duckdb

        con = duckdb.connect(":memory:")

        # resource limits (must be set before lock_configuration)
        con.execute(f"SET memory_limit='{limits['memory_limit']}'")
        con.execute(f"SET threads={int(limits['threads'])}")
        try:
            con.execute(f"SET max_temp_directory_size='{limits['max_temp_size']}'")
        except Exception:
            pass
        # extension hardening (before tables so the reader below still works)
        for stmt in (
            "SET autoinstall_known_extensions=false",
            "SET autoload_known_extensions=false",
            "SET allow_community_extensions=false",
            "SET allow_unsigned_extensions=false",
            "SET allow_extensions_metadata_mismatch=false",
        ):
            try:
                con.execute(stmt)
            except Exception:
                pass

        for view, path, source_type in datasets:
            if not _IDENT_RE.match(view):
                raise RuntimeError(f"unsafe view identifier {view!r}")
            path_lit = path.replace("'", "''")
            if source_type == "json":
                reader = f"read_json('{path_lit}')"
            else:
                reader = (
                    f"read_csv('{path_lit}', header=true, sample_size=-1, "
                    f"ignore_errors=false, auto_detect=true)"
                )
            con.execute(f'CREATE TABLE "{view}" AS SELECT * FROM {reader}')

        # now cut off the outside world and lock it
        con.execute("SET enable_external_access=false")
        try:
            con.execute("SET disabled_filesystems='LocalFileSystem'")
        except Exception:
            pass
        con.execute("SET lock_configuration=true")

        # watchdog: interrupt a slow query slightly before the parent kills us
        def _watchdog():
            interrupted.set()
            try:
                con.interrupt()
            except Exception:
                pass

        timer = threading.Timer(max(0.2, float(limits["timeout"]) - 0.5), _watchdog)
        timer.daemon = True
        timer.start()
        results: dict = {}
        try:
            for label, sql in queries:
                cur = con.execute(sql)
                rows = cur.fetchmany(max_rows + 1)
                columns = [d[0] for d in (cur.description or [])]
                truncated = len(rows) > max_rows
                results[label] = {
                    "columns": columns,
                    "rows": [[_jsonable(c) for c in r] for r in rows[:max_rows]],
                    "row_count": min(len(rows), max_rows),
                    "truncated": truncated,
                }
        finally:
            timer.cancel()

        out_q.put(("ok", results))
    except Exception as exc:  # noqa: BLE001
        kind = "timeout" if interrupted.is_set() else "err"
        out_q.put((kind, f"{type(exc).__name__}: {exc}"))


# --- public runner -----------------------------------------------------


class DuckDBExecution:
    """Runs a validated SELECT over BATONX-registered datasets, process-isolated."""

    def __init__(self):
        self.timeout = float(settings.DATA_QUERY_TIMEOUT_SECONDS)
        self.limits = {
            "memory_limit": settings.DATA_DUCKDB_MEMORY_LIMIT,
            "threads": settings.DATA_DUCKDB_THREADS,
            "max_temp_size": settings.DATA_DUCKDB_MAX_TEMP_SIZE,
            "timeout": self.timeout,
        }

    def run_select(
        self,
        sql: str,
        *,
        datasets: list[tuple[str, str, str]],
        max_rows: int | None = None,
    ) -> dict:
        return self.run_many([("q", sql)], datasets=datasets, max_rows=max_rows)["q"]

    def run_many(
        self,
        queries: list[tuple[str, str]],
        *,
        datasets: list[tuple[str, str, str]],
        max_rows: int | None = None,
    ) -> dict:
        for _, sql in queries:
            validate_select_only(sql)
        max_rows = int(max_rows or settings.DATA_QUERY_MAX_RESULT_ROWS)

        try:
            ctx = multiprocessing.get_context("fork")
        except ValueError:  # pragma: no cover - non-POSIX fallback
            return self._run_in_thread(queries, datasets, max_rows)

        out_q: multiprocessing.Queue = ctx.Queue()
        proc = ctx.Process(
            target=_duckdb_worker,
            args=(datasets, queries, max_rows, self.limits, out_q),
            daemon=True,
        )
        proc.start()
        proc.join(self.timeout)

        if proc.is_alive():
            proc.terminate()
            proc.join(2)
            if proc.is_alive():
                proc.kill()
                proc.join(2)
            raise QueryExecutionError(
                "query_timeout",
                f"Execution exceeded the {self.timeout:g}s limit and was stopped.",
            )

        try:
            kind, payload = out_q.get_nowait()
        except Exception:
            raise QueryExecutionError(
                "execution_failed", "The query process exited without a result."
            )
        if kind == "timeout":
            raise QueryExecutionError(
                "query_timeout",
                f"Execution exceeded the {self.timeout:g}s limit and was interrupted.",
            )
        if kind == "err":
            raise QueryExecutionError("execution_failed", str(payload))
        return payload

    def _run_in_thread(self, queries, datasets, max_rows) -> dict:  # pragma: no cover
        q: list = []
        t = threading.Thread(
            target=_duckdb_worker,
            args=(datasets, queries, max_rows, self.limits, _ListQueue(q)),
            daemon=True,
        )
        t.start()
        t.join(self.timeout)
        if t.is_alive():
            raise QueryExecutionError(
                "query_timeout", f"Execution exceeded the {self.timeout:g}s limit."
            )
        if not q:
            raise QueryExecutionError("execution_failed", "No result.")
        kind, payload = q[0]
        if kind == "timeout":
            raise QueryExecutionError("query_timeout", "Execution exceeded the limit.")
        if kind == "err":
            raise QueryExecutionError("execution_failed", str(payload))
        return payload


class _ListQueue:  # pragma: no cover - thread fallback helper
    def __init__(self, backing):
        self._backing = backing

    def put(self, item):
        self._backing.append(item)
