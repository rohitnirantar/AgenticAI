"""
run_desk.py - the support desk, running on the framework of your choice

A real-life flow: a morning inbox of customer emails goes through the desk. Every desk in this module has
the same handle_email(email) function, so the framework behind it can be swapped with one word.
Each outcome is checked against the shop's data (was a refund really created?), and the script ends with a
summary of correctness, tokens, time and lines of code.

Run it from the repo root or from this folder:
    python "Agent Frameworks/run_desk.py"              (the OpenAI Agents SDK desk)
    python "Agent Frameworks/run_desk.py" langgraph    (plain, sdk, langgraph or crewai)
    python "Agent Frameworks/run_desk.py" all          (all four, side by side)

Use the module's own environment (see requirements.txt). Each desk makes about 10 small model calls.
"""

import sys

import compare

sys.stdout.reconfigure(encoding="utf-8")  # so output with special characters prints correctly on Windows


def main():
    choice = "sdk"
    if len(sys.argv) > 1:
        choice = sys.argv[1].lower()

    names = [choice]
    if choice == "all":
        names = ["plain", "sdk", "langgraph", "crewai"]

    for name in names:
        if name not in compare.DESKS:
            raise SystemExit("Unknown desk '" + name + "'. Choose plain, sdk, langgraph, crewai or all.")

    summaries = []
    for name in names:
        print("=== " + name + " desk: " + str(len(compare.INBOX)) + " emails ===")
        results = compare.run_inbox(name, show=True)
        summaries.append(compare.summarise(name, results))

        # Show the actual replies for a single desk. (With 'all' the table below is enough.)
        if len(names) == 1:
            print("\nReplies:")
            for result in results:
                print("- " + result["name"] + ": " + result["reply"].replace("\n", " "))
        print()

    print("Desk".ljust(11) + "Correct".ljust(10) + "Avg tokens".ljust(12) + "Avg seconds".ljust(13) + "Lines of code")
    print("-" * 56)
    for item in summaries:
        print(item["desk"].ljust(11)
              + (str(item["passed"]) + "/" + str(item["total"])).ljust(10)
              + str(item["avg_tokens"]).ljust(12)
              + format(item["avg_seconds"], ".1f").ljust(13)
              + str(item["code_lines"]))


if __name__ == "__main__":
    main()
