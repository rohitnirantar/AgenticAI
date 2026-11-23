"""
db.py - the shop's memory, kept in a real database (SQLite)

Until now the shop lived in Python variables (ORDERS, REFUNDS, PENDING_APPROVALS). Stop the program and
everything is forgotten: the refunds, the approvals that were waiting, what each customer said yesterday.

SQLite is a database that is just ONE FILE (desk.db). It comes with Python, so there is nothing to install.
This file holds every function that touches the database. The agent never writes SQL: it calls these functions.

Four ideas to look for while you read:
  1. A TRANSACTION   : several writes that succeed together, or not at all (see transaction()).
  2. A UNIQUE rule   : the database itself refuses a second refund for the same order.
  3. PERSISTENCE     : refunds, approvals and tickets are still there after a restart.
  4. AN AUDIT TRAIL  : every money event is written in the SAME transaction as the money itself.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

# Where the database file lives. Set the DESK_DB environment variable to use another file (handy for tests).
DB_PATH = os.getenv("DESK_DB")
if DB_PATH is None:
    DB_PATH = str(Path(__file__).parent / "desk.db")

REFUND_WINDOW_DAYS = 30     # shop policy: refunds only within 30 days of delivery
AUTO_REFUND_LIMIT = 100.00  # refunds above this wait for a person


def use_database(path):
    """Point this module at another database file (the notebooks use a throwaway file)."""
    global DB_PATH
    DB_PATH = str(path)


# ---------------------------------------------------------------------------
# The tables. This text is SQL, the language databases understand.
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id          TEXT PRIMARY KEY,
    customer_id       TEXT NOT NULL,
    item              TEXT NOT NULL,
    price             REAL NOT NULL,
    status            TEXT NOT NULL,
    delivered_on      TEXT,
    expected_delivery TEXT
);

-- UNIQUE on order_id: the database itself refuses a second refund for the same order.
CREATE TABLE IF NOT EXISTS refunds (
    refund_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT NOT NULL UNIQUE REFERENCES orders(order_id),
    amount      REAL NOT NULL CHECK (amount > 0),
    approved_by TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Refunds above the automatic limit wait here until a person decides.
CREATE TABLE IF NOT EXISTS approvals (
    approval_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     TEXT NOT NULL REFERENCES orders(order_id),
    amount       REAL NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at TEXT NOT NULL,
    decided_by   TEXT,
    decided_at   TEXT
);
-- At most ONE pending approval per order, even if the customer writes ten times.
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_per_order ON approvals(order_id) WHERE status = 'pending';

-- Every email and reply, so the desk remembers each customer.
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    email       TEXT NOT NULL,
    reply       TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Who did what, and when. Written in the same transaction as the thing it describes.
CREATE TABLE IF NOT EXISTS audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    at       TEXT NOT NULL,
    event    TEXT NOT NULL,
    details  TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Connecting, and the transaction helper
# ---------------------------------------------------------------------------
def connect():
    """Open the database file."""
    conn = sqlite3.connect(DB_PATH, timeout=10)  # if another program is writing, wait up to 10 seconds
    conn.row_factory = sqlite3.Row               # rows behave like dictionaries: row["price"]
    conn.execute("PRAGMA foreign_keys = ON")     # SQLite only checks links between tables if you ask
    return conn


# --- transaction start ---
@contextmanager
def transaction():
    """Open the database and run the block of code as ONE transaction, then close it.

        with db.transaction() as conn:
            conn.execute("INSERT ...")
            conn.execute("INSERT ...")

    If the block finishes, everything is saved (commit). If anything raises an error, NOTHING is saved (rollback)."""
    conn = connect()
    try:
        with conn:      # sqlite3's own "commit if it worked, roll back if it failed"
            yield conn
    finally:
        conn.close()
# --- transaction end ---


def now():
    """The current time as text."""
    return datetime.now().isoformat(timespec="seconds")


def days_ago(n):
    """A date n days before today, so the sample data is valid whenever you run this."""
    return (date.today() - timedelta(days=n)).isoformat()


def log_event(conn, event, **details):
    """Write one line in the audit trail, using the connection (and so the transaction) we were given."""
    conn.execute("INSERT INTO audit (at, event, details) VALUES (?, ?, ?)", (now(), event, json.dumps(details)))


# ---------------------------------------------------------------------------
# Setting up
# ---------------------------------------------------------------------------
def init_db():
    """Create the tables if they are missing, and add the sample orders the first time."""
    conn = connect()
    conn.executescript(SCHEMA)
    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO orders (order_id, customer_id, item, price, status, delivered_on, expected_delivery) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("A1001", "c-101", "Wireless headphones", 79.00, "delivered", days_ago(18), None),
                ("A1002", "c-102", "Running shoes", 120.00, "in_transit", None, days_ago(-4)),
                ("A1003", "c-101", "Coffee grinder", 45.00, "delivered", days_ago(80), None),
                ("A1004", "c-103", "4K television", 250.00, "delivered", days_ago(5), None),
            ])
        conn.commit()
    conn.close()


def reset_db():
    """Start from zero: drop every table and create it again with the sample orders."""
    conn = connect()
    conn.executescript(
        "DROP TABLE IF EXISTS audit; DROP TABLE IF EXISTS tickets; DROP TABLE IF EXISTS approvals; "
        "DROP TABLE IF EXISTS refunds; DROP TABLE IF EXISTS orders;")
    conn.close()
    init_db()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def get_order(order_id):
    """One order as a dictionary, with its refund status. None if there is no such order."""
    conn = connect()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id.strip().upper(),)).fetchone()
    if row is None:
        conn.close()
        return None

    order = dict(row)
    if order["status"] == "delivered":
        order["days_since_delivery"] = (date.today() - date.fromisoformat(order["delivered_on"])).days

    refund = conn.execute("SELECT amount, created_at FROM refunds WHERE order_id = ?", (order["order_id"],)).fetchone()
    pending = conn.execute("SELECT amount FROM approvals WHERE order_id = ? AND status = 'pending'", (order["order_id"],)).fetchone()
    conn.close()

    order["refund"] = "none"
    if refund is not None:
        order["refund"] = "issued: $" + format(refund["amount"], ".2f") + " on " + refund["created_at"]
    if pending is not None:
        order["refund"] = "waiting for a person to approve"
    return order


def refund_rules(order):
    """The refund policy, applied to one order (a dictionary). Returns (is_allowed, explanation)."""
    if order["status"] != "delivered":
        return False, "Not eligible: the order has not been delivered yet."

    days = (date.today() - date.fromisoformat(order["delivered_on"])).days
    if days > REFUND_WINDOW_DAYS:
        return False, "Not eligible: delivered " + str(days) + " days ago, the refund window is " + str(REFUND_WINDOW_DAYS) + " days."
    return True, "Eligible: delivered " + str(days) + " days ago, within the " + str(REFUND_WINDOW_DAYS) + " day window."


def list_refunds():
    """Every refund issued so far."""
    conn = connect()
    rows = conn.execute("SELECT order_id, amount, approved_by, created_at FROM refunds ORDER BY refund_id").fetchall()
    conn.close()
    refunds = []
    for row in rows:
        refunds.append(dict(row))
    return refunds


def list_pending():
    """Every refund that is waiting for a person."""
    conn = connect()
    rows = conn.execute("SELECT order_id, amount, requested_at FROM approvals WHERE status = 'pending' ORDER BY approval_id").fetchall()
    conn.close()
    pending = []
    for row in rows:
        pending.append(dict(row))
    return pending


def audit_trail(limit=20):
    """The latest lines of the audit trail, oldest first."""
    conn = connect()
    rows = conn.execute("SELECT at, event, details FROM audit ORDER BY audit_id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    lines = []
    for row in rows:
        lines.append(dict(row))
    lines.reverse()
    return lines


def count_rows(table):
    """How many rows a table has. (The table name comes from our own code, never from a customer.)"""
    conn = connect()
    count = conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
    conn.close()
    return count


# ---------------------------------------------------------------------------
# Refunds: the part where mistakes cost money
# ---------------------------------------------------------------------------
# --- refunds start ---
def refund_order(order_id, approved_by):
    """Issue a refund. Returns (ok, message). The checks and the writes happen in ONE transaction."""
    order_id = order_id.strip().upper()
    try:
        with transaction() as conn:
            row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if row is None:
                return False, "No order found with id " + order_id + "."

            allowed, explanation = refund_rules(dict(row))
            if not allowed:
                return False, "Refund refused. " + explanation

            # Two writes. Either both are saved or neither is.
            conn.execute("INSERT INTO refunds (order_id, amount, approved_by, created_at) VALUES (?, ?, ?, ?)",
                         (order_id, row["price"], approved_by, now()))
            log_event(conn, "refund_issued", order_id=order_id, amount=row["price"], approved_by=approved_by)
            return True, "Refund of $" + format(row["price"], ".2f") + " issued for order " + order_id + "."

    except sqlite3.IntegrityError:
        # The UNIQUE rule on refunds.order_id fired: this order already has a refund.
        # The database says no, even if two requests arrived at the same moment.
        return False, "A refund for order " + order_id + " was already issued."


def request_refund(order_id):
    """What the agent's refund tool calls. Small refunds are issued; large ones wait for a person.
    The $100 limit is in this plain function, NOT in a prompt, so the model cannot talk its way around it."""
    order = get_order(order_id)
    if order is None:
        return "No order found with id " + order_id + "."

    allowed, explanation = refund_rules(order)
    if not allowed:
        return "Refund refused. " + explanation

    if order["refund"] != "none":
        return "Nothing to do: the refund for order " + order["order_id"] + " is already " + order["refund"] + "."

    if order["price"] > AUTO_REFUND_LIMIT:
        return hold_for_approval(order["order_id"], order["price"])

    ok, message = refund_order(order["order_id"], "agent (under the automatic limit)")
    return message


def hold_for_approval(order_id, amount):
    """Put a large refund in the waiting line for a person."""
    try:
        with transaction() as conn:
            conn.execute("INSERT INTO approvals (order_id, amount, status, requested_at) VALUES (?, ?, 'pending', ?)",
                         (order_id, amount, now()))
            log_event(conn, "refund_held", order_id=order_id, amount=amount)
            return "The refund of $" + format(amount, ".2f") + " for order " + order_id + " is above the automatic limit of $" \
                + format(AUTO_REFUND_LIMIT, ".0f") + ". It now waits for a person to approve it."
    except sqlite3.IntegrityError:
        return "The refund for order " + order_id + " is already waiting for a person to approve it."


def approve(order_id, approver):
    """A person approves a waiting refund. Returns (ok, message).
    Three things happen in ONE transaction: the approval is closed, the refund is written, the audit line is written."""
    order_id = order_id.strip().upper()
    try:
        with transaction() as conn:
            waiting = conn.execute("SELECT approval_id, amount FROM approvals WHERE order_id = ? AND status = 'pending'",
                                   (order_id,)).fetchone()
            if waiting is None:
                return False, "No refund is waiting for approval on order " + order_id + "."

            conn.execute("UPDATE approvals SET status = 'approved', decided_by = ?, decided_at = ? WHERE approval_id = ?",
                         (approver, now(), waiting["approval_id"]))
            conn.execute("INSERT INTO refunds (order_id, amount, approved_by, created_at) VALUES (?, ?, ?, ?)",
                         (order_id, waiting["amount"], approver, now()))
            log_event(conn, "refund_approved", order_id=order_id, amount=waiting["amount"], approved_by=approver)
            return True, "Refund of $" + format(waiting["amount"], ".2f") + " approved by " + approver + " for order " + order_id + "."
    except sqlite3.IntegrityError:
        return False, "A refund for order " + order_id + " was already issued."


def reject(order_id, approver):
    """A person says no to a waiting refund. Returns (ok, message)."""
    order_id = order_id.strip().upper()
    with transaction() as conn:
        waiting = conn.execute("SELECT approval_id FROM approvals WHERE order_id = ? AND status = 'pending'",
                               (order_id,)).fetchone()
        if waiting is None:
            return False, "No refund is waiting for approval on order " + order_id + "."

        conn.execute("UPDATE approvals SET status = 'rejected', decided_by = ?, decided_at = ? WHERE approval_id = ?",
                     (approver, now(), waiting["approval_id"]))
        log_event(conn, "refund_rejected", order_id=order_id, rejected_by=approver)
        return True, "Refund for order " + order_id + " rejected by " + approver + "."
# --- refunds end ---


# ---------------------------------------------------------------------------
# Tickets: the desk remembers each customer
# ---------------------------------------------------------------------------
# --- tickets start ---
def save_ticket(customer_id, email, reply):
    """Remember one email and the reply it got."""
    with transaction() as conn:
        conn.execute("INSERT INTO tickets (customer_id, email, reply, created_at) VALUES (?, ?, ?, ?)",
                     (customer_id, email, reply, now()))


def customer_history(customer_id, limit=3):
    """The customer's latest tickets, newest first."""
    conn = connect()
    rows = conn.execute(
        "SELECT email, reply, created_at FROM tickets WHERE customer_id = ? ORDER BY ticket_id DESC LIMIT ?",
        (customer_id, limit)).fetchall()
    conn.close()
    history = []
    for row in rows:
        history.append(dict(row))
    return history
# --- tickets end ---


if __name__ == "__main__":
    init_db()
    print("Database ready at " + DB_PATH)
    print("Orders:", count_rows("orders"), " Refunds:", count_rows("refunds"), " Tickets:", count_rows("tickets"))
