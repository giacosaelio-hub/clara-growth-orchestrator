"""Estado en SQLite: cuentas, contactos, eventos procesados, acciones y la auditoría."""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    name TEXT,
    tax_id TEXT,
    entity_countries TEXT,          -- JSON list, e.g. ["BR", "MX"]
    employees INTEGER,
    industry TEXT,
    legal_type TEXT,                -- company | sole_proprietor
    stage TEXT NOT NULL DEFAULT 'target',
    is_customer INTEGER NOT NULL DEFAULT 0,
    has_open_opportunity INTEGER NOT NULL DEFAULT 0,
    assigned_ae TEXT,
    do_not_contact INTEGER NOT NULL DEFAULT 0,
    last_outreach_at TEXT,
    last_event_at TEXT,
    next_follow_up_at TEXT
);
CREATE TABLE IF NOT EXISTS contacts (
    email TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    name TEXT,
    title TEXT,
    language TEXT,
    linkedin_url TEXT,
    personal_email INTEGER NOT NULL DEFAULT 0,
    opted_out INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY,
    type TEXT,
    account_id TEXT,
    received_at TEXT,
    outcome TEXT
);
CREATE TABLE IF NOT EXISTS actions (
    idempotency_key TEXT PRIMARY KEY,
    account_id TEXT,
    action TEXT,
    payload TEXT,
    status TEXT,                    -- pending | done | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS action_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT,
    attempt INTEGER,
    outcome TEXT,                   -- sent | error | timeout | confirmed_sent | skipped_already_done | wait
    detail TEXT,
    at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT,
    account_id TEXT,
    decision TEXT,
    rule TEXT,
    reason TEXT,
    ai_output TEXT,
    action_status TEXT,
    created_at TEXT
);
"""


def connect(path: str = "data/state.db") -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def get_account(conn, account_id):
    row = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
    if row is None:
        return None
    acc = dict(row)
    acc["entity_countries"] = json.loads(acc["entity_countries"] or "[]")
    return acc


def get_contact(conn, email):
    row = conn.execute("SELECT * FROM contacts WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


ACCOUNT_COLUMNS = {"account_id", "name", "tax_id", "entity_countries", "employees", "industry", "legal_type",
                   "stage", "is_customer", "has_open_opportunity", "assigned_ae", "do_not_contact",
                   "last_outreach_at", "last_event_at", "next_follow_up_at"}
CONTACT_COLUMNS = {"email", "account_id", "name", "title", "language", "linkedin_url", "personal_email", "opted_out"}


def _only(fields: dict, allowed: set) -> dict:
    """Los nombres de columna vienen de datos externos: nunca meter una clave desconocida en el SQL."""
    return {k: v for k, v in fields.items() if k in allowed}


def upsert_account(conn, acc: dict):
    fields = _only(acc, ACCOUNT_COLUMNS)
    if isinstance(fields.get("entity_countries"), list):
        fields["entity_countries"] = json.dumps(fields["entity_countries"])
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{c} = excluded.{c}" for c in fields if c != "account_id")
    conn.execute(
        f"INSERT INTO accounts ({cols}) VALUES ({marks}) ON CONFLICT(account_id) DO UPDATE SET {updates}",
        list(fields.values()),
    )


def upsert_contact(conn, contact: dict):
    contact = _only(contact, CONTACT_COLUMNS)
    cols = ", ".join(contact)
    marks = ", ".join("?" for _ in contact)
    updates = ", ".join(f"{c} = excluded.{c}" for c in contact if c != "email")
    conn.execute(
        f"INSERT INTO contacts ({cols}) VALUES ({marks}) ON CONFLICT(email) DO UPDATE SET {updates}",
        list(contact.values()),
    )


def update_account(conn, account_id, **fields):
    fields = _only(fields, ACCOUNT_COLUMNS - {"account_id"})
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE accounts SET {sets} WHERE account_id = ?", [*fields.values(), account_id])


def audit(conn, event_id, account_id, decision, rule, reason, ai_output, action_status, now):
    conn.execute(
        "INSERT INTO audit_log (event_id, account_id, decision, rule, reason, ai_output, action_status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (event_id, account_id, decision, rule, reason,
         json.dumps(ai_output, ensure_ascii=False) if ai_output else None, action_status, now),
    )
