"""
support_desk_db.py - a morning at the support desk, with a desk that REMEMBERS

The real-life scenario: customers write in, the agent answers, and some refunds need a person.
The twist: everything is kept in the database file (desk.db), so the desk survives a restart.

Try this (from the repo root, in the main virtual environment):

    python "Persistent State and Databases/support_desk_db.py" --fresh     # start from an empty shop
    python "Persistent State and Databases/support_desk_db.py"             # run AGAIN: nothing is forgotten
    python "Persistent State and Databases/approve_pending.py"             # a person approves the big refund
    python "Persistent State and Databases/support_desk_db.py"             # the desk now knows it was approved

--fresh wipes the database first. Without it, the database keeps everything from the earlier runs.
"""

import sys

import db
import desk_agent

# A morning's emails: (customer id, email text)
INBOX = [
    ("c-102", "Hi, where is my order A1002?"),
    ("c-101", "The left earbud on my headphones (order A1001) stopped working. Please refund it."),
    ("c-103", "Please refund my 4K television, order A1004. I changed my mind."),
    ("c-101", "Did you refund my headphones? What happened with my request?"),
    ("c-101", "Please refund order A1003 too, the grinder broke."),
    ("c-103", "Any news on my TV refund?"),
    ("c-101", "Sorry, please refund order A1001 again, I think the first one did not go through."),
]


def print_database_state():
    """Show what the database holds now. This is what survives a restart."""
    print("\n--- What the database holds now ---")
    print("Refunds issued:")
    for refund in db.list_refunds():
        print("   " + refund["order_id"] + "  $" + format(refund["amount"], ".2f") + "  approved by: " + refund["approved_by"])
    if len(db.list_refunds()) == 0:
        print("   (none)")

    print("Waiting for a person:")
    for waiting in db.list_pending():
        print("   " + waiting["order_id"] + "  $" + format(waiting["amount"], ".2f") + "  since " + waiting["requested_at"])
    if len(db.list_pending()) == 0:
        print("   (none)")

    print("Tickets saved: " + str(db.count_rows("tickets")) + "     Audit lines: " + str(db.count_rows("audit")))


def main():
    if "--fresh" in sys.argv:
        db.reset_db()
        print("Started from an empty shop (--fresh).")
    else:
        db.init_db()

    print("Database file: " + db.DB_PATH)
    print("Tickets already in it: " + str(db.count_rows("tickets")) + "\n")

    for customer_id, email in INBOX:
        print("[" + customer_id + "] " + email)
        reply = desk_agent.handle_email(email, customer_id)
        print("  -> " + reply.replace("\n", " ") + "\n")

    print_database_state()
    print("\nNow run this file again, WITHOUT --fresh, and see what the desk remembers.")


if __name__ == "__main__":
    main()
