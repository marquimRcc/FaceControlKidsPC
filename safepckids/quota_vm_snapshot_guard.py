"""Full-content consistency guard for OFFLINE synthetic SQLite VM cutovers.

A table count alone is insufficient: a concurrent legacy writer can replace a
balance/receipt/embedding without adding rows after the rollback snapshot.
Caller MUST hold BEGIN IMMEDIATE on the live database while comparing.
This helper does not open files, acquire a writer lease or modify the ledger.
"""
from __future__ import annotations

from itertools import zip_longest
import sqlite3

_SCHEMA_QUERY = (
    "SELECT type, name, tbl_name, sql FROM sqlite_master "
    "WHERE name NOT LIKE 'sqlite_stat%' ORDER BY type, name"
)
_MISSING = object()


def assert_snapshot_matches(live: sqlite3.Connection, snapshot: sqlite3.Connection) -> None:
    """Reject changes to ANY schema object or data row, including receipts.

    Compare under the caller's live write transaction. SQLite's backup API
    gives a consistent snapshot; this check detects subsequent modifications
    even when table counts are unchanged. Streaming bounds memory use.
    """
    live_schema = live.execute(_SCHEMA_QUERY).fetchall()
    if live_schema != snapshot.execute(_SCHEMA_QUERY).fetchall():
        raise RuntimeError("VM fixture schema changed since snapshot")
    for kind, name, _table, _sql in live_schema:
        if kind != "table":
            continue
        identifier = '"' + name.replace('"', '""') + '"'
        columns = len(live.execute(f"PRAGMA table_info({identifier})").fetchall())
        if not columns:
            raise RuntimeError("VM snapshot has an unsupported table layout")
        query = (f"SELECT * FROM {identifier} ORDER BY " +
                 ", ".join(str(i) for i in range(1, columns + 1)))
        old_rows = snapshot.execute(query)
        new_rows = live.execute(query)
        for current, original in zip_longest(new_rows, old_rows, fillvalue=_MISSING):
            if current != original:
                raise RuntimeError("VM fixture content changed since snapshot")
