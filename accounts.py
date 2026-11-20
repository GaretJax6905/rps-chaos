"""Accounts and saved Boss Ladder runs, stored server-side in SQLite.

Only a Werkzeug password hash is stored. A finished run is saved by the
server from its own session state, never from a score the browser sends,
and a UNIQUE (user_id, run_id) constraint means it is saved exactly once.
"""

import sqlite3
import time

from werkzeug.security import check_password_hash, generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    run_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    outcome TEXT NOT NULL,
    bosses_beaten INTEGER NOT NULL,
    rounds_won INTEGER NOT NULL,
    score INTEGER NOT NULL,
    finished REAL NOT NULL,
    UNIQUE (user_id, run_id)
);
"""

MIN_PASSWORD = 8


class AccountError(ValueError):
    """A problem the player can fix (shown on the form)."""


def connect(path: str) -> sqlite3.Connection:
    """Open the database and make sure the tables exist."""
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def register(db, email: str, password: str, display_name: str = "") -> int:
    """Create an account and return its id."""
    email = (email or "").strip().lower()
    if "@" not in email or len(email) > 254:
        raise AccountError("Enter a valid email address.")
    if len(password or "") < MIN_PASSWORD:
        raise AccountError(f"Password must be at least {MIN_PASSWORD} characters.")
    name = (display_name or "").strip()[:40] or email.split("@")[0]
    try:
        with db:
            cur = db.execute(
                "INSERT INTO users (email, display_name, password_hash, created)"
                " VALUES (?, ?, ?, ?)",
                (email, name, generate_password_hash(password), time.time()),
            )
    except sqlite3.IntegrityError as problem:
        raise AccountError("An account with that email already exists.") from problem
    return cur.lastrowid


def authenticate(db, email: str, password: str):
    """Return the user row for a correct email and password, else None."""
    row = db.execute(
        "SELECT * FROM users WHERE email = ?", ((email or "").strip().lower(),)
    ).fetchone()
    if row and check_password_hash(row["password_hash"], password or ""):
        return row
    return None


def get_user(db, user_id):
    """The user row for an id, or None."""
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def save_run(db, user_id: int, state: dict, score: int) -> bool:
    """Save one finished ladder run. Returns False if it was already saved."""
    stats = state["stats"]
    try:
        with db:
            db.execute(
                "INSERT INTO runs (user_id, run_id, mode, outcome, bosses_beaten,"
                " rounds_won, score, finished) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    state["run_id"],
                    state["mode"],
                    state["status"],
                    stats["bosses"],
                    stats["wins"],
                    score,
                    time.time(),
                ),
            )
    except sqlite3.IntegrityError:
        return False
    return True


def runs_for(db, user_id: int, limit: int = 10) -> list:
    """This player's most recent saved runs (only theirs)."""
    rows = db.execute(
        "SELECT mode, outcome, bosses_beaten, rounds_won, score, finished"
        " FROM runs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def summary(db, user_id: int) -> dict:
    """Best score, furthest boss and run count for the dashboard."""
    row = db.execute(
        "SELECT COUNT(*) AS played, COALESCE(MAX(score), 0) AS best,"
        " COALESCE(MAX(bosses_beaten), 0) AS furthest FROM runs WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return dict(row)
