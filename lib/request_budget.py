"""Cross-process upper bound on provider request attempts for one invocation.

The caller supplies an estimated cost per attempt. This ledger limits the
number of attempts; it cannot certify the provider's final invoice.
"""

import sqlite3


class BudgetExhausted(RuntimeError):
    """No provider request may be sent because the attempt cap was reached."""


def create_budget(path, max_attempts):
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    with sqlite3.connect(path, timeout=30) as db:
        db.execute(
            "CREATE TABLE request_budget (id INTEGER PRIMARY KEY CHECK (id = 1), "
            "max_attempts INTEGER NOT NULL, used_attempts INTEGER NOT NULL)"
        )
        db.execute(
            "INSERT INTO request_budget (id, max_attempts, used_attempts) VALUES (1, ?, 0)",
            (max_attempts,),
        )


def read_budget(path):
    with sqlite3.connect(path, timeout=30) as db:
        row = db.execute(
            "SELECT max_attempts, used_attempts FROM request_budget WHERE id = 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("request budget ledger is missing or invalid")
    return {"max_attempts": row[0], "used_attempts": row[1]}


def reserve_attempt(path):
    """Reserve before network I/O, atomically across threads and processes."""
    with sqlite3.connect(path, timeout=30, isolation_level=None) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT max_attempts, used_attempts FROM request_budget WHERE id = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("request budget ledger is missing or invalid")
        max_attempts, used_attempts = row
        if used_attempts >= max_attempts:
            raise BudgetExhausted(
                f"provider request cap reached ({used_attempts}/{max_attempts})"
            )
        db.execute(
            "UPDATE request_budget SET used_attempts = used_attempts + 1 WHERE id = 1"
        )
        db.commit()
        return used_attempts + 1
