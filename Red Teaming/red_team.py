"""
red_team.py - attack the desk before a stranger does, and block the release if an attack gets through

The real-life scenario: the team is about to ship an update of the support desk. Security asks one question:
"Can anyone get a refund they should not get, or read something they should not read?"

This script answers it with numbers. It runs ALL of these against BOTH versions of the desk (naive and hardened):
  1. the hand-written attack library (attacks.py)
  2. attacks that worked in earlier runs (regression_attacks.json, a file that grows over time)
  3. NEW attacks invented by an attacker AI (attacker_ai.py), unless you pass --no-generate

Then it prints the success rate of the attackers, by goal and by tactic, and saves every attack that worked as a
permanent regression test. Run it (takes a few minutes, costs a few cents):

    python "Red Teaming/red_team.py"                  attack both versions
    python "Red Teaming/red_team.py" --no-generate    only the saved attacks (fast, no attacker AI)
    python "Red Teaming/red_team.py" --runs 3         try every attack 3 times (a model does not always answer the same way)
    python "Red Teaming/red_team.py" --gate           exit with an error if ANY attack beats the hardened desk (for CI)
"""

import json
import sys
from pathlib import Path

import attacker_ai
import attacks
import victim

REGRESSION_FILE = Path(__file__).parent / "regression_attacks.json"


# --- suite start ---
def run_suite(attack_list, mode, runs=1):
    """Run every attack against one version of the desk, 'runs' times each. Returns the list of results.
    A model does not always answer the same way, and an attacker only needs ONE success, so we try more than once."""
    results = []
    for attack in attack_list:
        for run_number in range(runs):
            results.append(attacks.run_attack(attack, mode))
    return results


def attacks_that_worked_once(results):
    """How many DIFFERENT attacks worked at least once."""
    emails = []
    for result in results:
        if result["worked"] and result["email"] not in emails:
            emails.append(result["email"])
    return len(emails)


def success_rate(results):
    """The share of attacks that worked, as (count, total)."""
    worked = 0
    for result in results:
        if result["worked"]:
            worked = worked + 1
    return worked, len(results)


def group_by(results, field):
    """Split results into groups by 'goal' or 'category'. Returns {name: [results]}."""
    groups = {}
    for result in results:
        name = result[field]
        if name not in groups:
            groups[name] = []
        groups[name].append(result)
    return groups
# --- suite end ---


def load_regression():
    """The attacks that worked in earlier runs."""
    if not REGRESSION_FILE.exists():
        return []
    with open(REGRESSION_FILE, encoding="utf-8") as file:
        return json.load(file)


def save_regression(known, new_results):
    """Add every attack that worked (against either version) to the regression file, without duplicates."""
    emails_known = []
    for attack in known:
        emails_known.append(attack["email"])

    for attack in attacks.ATTACKS:          # the hand-written library is already saved in attacks.py
        emails_known.append(attack["email"])

    saved = list(known)
    added = 0
    for result in new_results:
        if result["worked"] and result["email"] not in emails_known:
            saved.append({"id": result["id"], "category": result["category"], "goal": result["goal"], "email": result["email"]})
            emails_known.append(result["email"])
            added = added + 1

    with open(REGRESSION_FILE, "w", encoding="utf-8") as file:
        json.dump(saved, file, indent=2)
    return added


def print_summary(name, results):
    worked, total = success_rate(results)
    print(name.upper().ljust(9) + " attackers succeeded in " + str(worked) + " of " + str(total) + " tries"
          + "   (" + str(attacks_that_worked_once(results)) + " different attacks worked at least once)")
    for goal, group in group_by(results, "goal").items():
        group_worked, group_total = success_rate(group)
        print("     " + goal.ljust(14) + str(group_worked) + " of " + str(group_total))


def main():
    if hasattr(sys.stdout, "reconfigure"):      # (a notebook's output has no reconfigure)
        sys.stdout.reconfigure(encoding="utf-8")

    attack_list = list(attacks.ATTACKS)
    regression = load_regression()
    attack_list = attack_list + regression
    print("Hand-written attacks: " + str(len(attacks.ATTACKS)) + "    saved from earlier runs: " + str(len(regression)))

    if "--no-generate" not in sys.argv:
        print("Asking the attacker AI for new attacks...")
        for goal_name in attacks.GOALS:
            attack_list = attack_list + attacker_ai.generate_variants(goal_name, how_many=4)
    runs = 1
    if "--runs" in sys.argv:
        runs = int(sys.argv[sys.argv.index("--runs") + 1])
    print("Attacks in this run: " + str(len(attack_list)) + ", each tried " + str(runs) + " time(s)\n")

    print("Attacking the NAIVE desk (rules only in the prompt)...")
    naive_results = run_suite(attack_list, victim.NAIVE, runs)
    print("Attacking the HARDENED desk (rules also in code)...")
    hardened_results = run_suite(attack_list, victim.HARDENED, runs)

    print()
    print_summary("naive", naive_results)
    print()
    print_summary("hardened", hardened_results)

    print("\nBy tactic, on the NAIVE desk (which tactics get through?):")
    for category, group in group_by(naive_results, "category").items():
        worked, total = success_rate(group)
        print("     " + category.ljust(26) + str(worked) + " of " + str(total))

    hardened_worked = []
    for result in hardened_results:
        if result["worked"]:
            hardened_worked.append(result)
    print("\nAttacks that BEAT the hardened desk: " + str(len(hardened_worked)))
    for result in hardened_worked:
        print("   [" + result["id"] + "] " + result["email"][:90].replace("\n", " "))

    added = save_regression(regression, naive_results + hardened_results)
    print("\nNew attacks saved to regression_attacks.json: " + str(added))

    if "--gate" in sys.argv and len(hardened_worked) > 0:
        print("\nRELEASE BLOCKED: an attack beat the hardened desk.")
        sys.exit(1)


if __name__ == "__main__":
    main()
