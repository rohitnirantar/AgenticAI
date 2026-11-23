"""
crash_test.py - pull the plug in the middle of a refund, and check that the database stays correct

Two small experiments, each one in its own child process that is killed on purpose with os._exit(1)
(no cleanup, no "finally": like a power cut):

  1. The process dies BEFORE the transaction is committed.  -> the refund must NOT exist (all or nothing).
  2. The process dies just AFTER the commit.                -> the refund MUST exist (a saved refund is not lost).

    python "Persistent State and Databases/crash_test.py"

It uses its own throwaway database file, so your real desk.db is not touched.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import db

# A throwaway database in the temp folder. Set before we use db in this process or in the children.
TEST_DB = str(Path(tempfile.gettempdir()) / "crash_test_desk.db")
os.environ["DESK_DB"] = TEST_DB
db.use_database(TEST_DB)


def child(mode):
    """This runs inside the child process. It starts a refund and then dies."""
    conn = db.connect()
    # Two writes that belong together: the refund and its audit line.
    conn.execute("INSERT INTO refunds (order_id, amount, approved_by, created_at) VALUES ('A1001', 79.00, 'agent', ?)", (db.now(),))
    db.log_event(conn, "refund_issued", order_id="A1001", amount=79.00)

    if mode == "before-commit":
        os._exit(1)       # the power goes out here: nothing was committed

    conn.commit()         # the writes are now saved
    os._exit(1)           # the power goes out here: after the save


def run_child(mode):
    """Start this same file as a separate process, in 'child' mode, and wait for it to die."""
    result = subprocess.run([sys.executable, __file__, "child", mode])
    return result.returncode


def main():
    print("Throwaway database file: " + Path(TEST_DB).name + " (in your temp folder)\n")

    # Experiment 1: crash BEFORE the commit
    db.reset_db()
    code = run_child("before-commit")
    print("Experiment 1: the process died before the commit (exit code " + str(code) + ")")
    print("   refunds in the database : " + str(db.count_rows("refunds")))
    print("   audit lines             : " + str(db.count_rows("audit")))
    if db.count_rows("refunds") == 0 and db.count_rows("audit") == 0:
        print("   OK: nothing was half-written. It is as if the refund never started.\n")
    else:
        print("   PROBLEM: half a refund was saved.\n")

    # Experiment 2: crash AFTER the commit
    db.reset_db()
    code = run_child("after-commit")
    print("Experiment 2: the process died right after the commit (exit code " + str(code) + ")")
    print("   refunds in the database : " + str(db.count_rows("refunds")))
    print("   audit lines             : " + str(db.count_rows("audit")))
    if db.count_rows("refunds") == 1 and db.count_rows("audit") == 1:
        print("   OK: the saved refund and its audit line are both there.")
    else:
        print("   PROBLEM: a committed refund was lost.")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "child":
        child(sys.argv[2])
    else:
        main()
