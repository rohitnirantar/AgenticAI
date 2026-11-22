"""
compare.py - run the same customer emails through any desk and check the results

Every desk in this module (plain_desk, agents_sdk_desk, langgraph_desk, crewai_desk) has the same
function: handle_email(email). Because they match, one test can score all of them.
As in Module 05, we check OUTCOMES in the shop's data (was a refund created?), not just the wording.
"""

import importlib
from pathlib import Path

# The desks we can compare: a short name and the file that holds it
DESKS = {
    "plain": "plain_desk",
    "sdk": "agents_sdk_desk",
    "langgraph": "langgraph_desk",
    "crewai": "crewai_desk",
}

# ---------------------------------------------------------------------------
# The inbox. For each email we know what SHOULD happen.
#   specialist : who should handle it
#   refunds    : the orders that must be refunded afterwards (checked in the shop's data)
#   text       : a word the reply must contain ("" means no check)
# ---------------------------------------------------------------------------
# --- inbox start ---
INBOX = [
    {
        "name": "Order status",
        "email": "Hi, can you tell me where my order A1002 is? Thanks!",
        "specialist": "orders", "refunds": [], "text": "transit",
    },
    {
        "name": "Shipping policy",
        "email": "How much does express shipping cost?",
        "specialist": "policy", "refunds": [], "text": "12",
    },
    {
        "name": "Refund inside 30 days",
        "email": "The left earbud on my headphones (order A1001) stopped working. I would like my money back.",
        "specialist": "refunds", "refunds": ["A1001"], "text": "79",
    },
    {
        "name": "Refund after 30 days",
        "email": "I bought a coffee grinder (order A1003) three months ago and it broke. Please refund it.",
        "specialist": "refunds", "refunds": [], "text": "",
    },
    {
        "name": "Unknown order",
        "email": "Please refund my order A9999, I never received it.",
        "specialist": "refunds", "refunds": [], "text": "",
    },
]
# --- inbox end ---


# --- check start ---
def check_result(case, result):
    """Compare what happened with what we expected. Returns a list of problems (empty = passed)."""
    problems = []

    if result["specialist"] != case["specialist"]:
        problems.append("went to '" + result["specialist"] + "', expected '" + case["specialist"] + "'")

    refunded = []
    for refund in result["refunds"]:
        refunded.append(refund["order_id"])
    if sorted(refunded) != sorted(case["refunds"]):
        problems.append("refunded " + str(refunded) + ", expected " + str(case["refunds"]))

    if case["text"] != "":
        if case["text"].lower() not in result["reply"].lower():
            problems.append("the reply does not contain '" + case["text"] + "'")

    return problems
# --- check end ---


# --- count_lines start ---
def count_code_lines(file_name):
    """Count the lines of real code in a file: no blank lines, no comments, no docstrings.
    It stops at 'def main():' because the code after that only runs the demo. It is not part of the desk."""
    count = 0
    inside_docstring = False

    with open(file_name, encoding="utf-8") as file:
        for line in file:
            text = line.strip()

            # Lines between triple quotes are documentation, not code
            if inside_docstring:
                if '"""' in text:  # this line closes the docstring
                    inside_docstring = False
                continue
            if text.startswith('"""'):
                if text.count('"""') == 1:  # opens a docstring that continues on the next lines
                    inside_docstring = True
                continue

            if text.startswith("def main():"):
                break
            if text == "":
                continue
            if text.startswith("#"):
                continue
            count = count + 1

    return count
# --- count_lines end ---


# --- run_inbox start ---
def run_inbox(desk_name, cases=INBOX, show=False):
    """Run every email in the inbox through one desk. Returns one result per email."""
    desk = importlib.import_module(DESKS[desk_name])

    results = []
    for case in cases:
        result = desk.handle_email(case["email"])
        result["problems"] = check_result(case, result)
        result["name"] = case["name"]
        results.append(result)

        if show:
            mark = "ok    "
            if len(result["problems"]) > 0:
                mark = "FAILED"
            print(mark + " " + case["name"].ljust(22) + " -> " + result["specialist"].ljust(8)
                  + str(result["tokens"]).rjust(5) + " tokens " + format(result["seconds"], ".1f").rjust(5) + " s")
            for problem in result["problems"]:
                print("         " + problem)

    return results


def summarise(desk_name, results):
    """Turn the results of one desk into a few totals."""
    passed = 0
    tokens = 0
    seconds = 0
    for result in results:
        if len(result["problems"]) == 0:
            passed = passed + 1
        tokens = tokens + result["tokens"]
        seconds = seconds + result["seconds"]

    return {
        "desk": desk_name,
        "passed": passed,
        "total": len(results),
        "avg_tokens": round(tokens / len(results)),
        "avg_seconds": seconds / len(results),
        "code_lines": count_code_lines(Path(__file__).parent / (DESKS[desk_name] + ".py")),  # works from any folder
    }
# --- run_inbox end ---
