"""
approve_pending.py - the support lead's tool: see the refunds that are waiting, and decide

This is a SEPARATE program from the desk. It works because both read the same database file.
That is the point of persistent state: the desk and the person do not need to be running at the same time.

    python "Persistent State and Databases/approve_pending.py"                    list what is waiting
    python "Persistent State and Databases/approve_pending.py" A1004 Priya        approve order A1004, as Priya
    python "Persistent State and Databases/approve_pending.py" A1004 Priya no     reject it instead
"""

import sys

import db


def main():
    db.init_db()

    # With no arguments: just list what is waiting
    if len(sys.argv) < 3:
        waiting = db.list_pending()
        if len(waiting) == 0:
            print("Nothing is waiting for approval.")
        for item in waiting:
            print(item["order_id"] + "  $" + format(item["amount"], ".2f") + "  waiting since " + item["requested_at"])
        if len(waiting) > 0:
            print("\nTo decide: python approve_pending.py <order id> <your name> [no]")
        return

    order_id = sys.argv[1]
    person = sys.argv[2]

    if len(sys.argv) > 3 and sys.argv[3].lower() == "no":
        ok, message = db.reject(order_id, person)
    else:
        ok, message = db.approve(order_id, person)
    print(message)


if __name__ == "__main__":
    main()
