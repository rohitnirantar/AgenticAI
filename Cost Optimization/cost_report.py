"""
cost_report.py - "The desk costs too much. Make it cheaper, without making it worse."

The real-life scenario: a day of support traffic (the 28 emails, plus 8 questions that are repeated), and five ways to run
the desk. We measure every one with the SAME emails and the SAME scoring, then project the monthly bill.

    A  the starting point : the strongest model (gpt-4o) answers everything
    B  the cheap model    : gpt-4o-mini answers everything
    C  routed             : a cheap router sends easy emails to mini and hard ones to gpt-4o
    D  routed + cache     : C, plus remembered answers for general questions (exact and semantic)
    E  routed + cache + trimmed prompt : D, plus only the relevant handbook lines in the prompt

Run it (takes a few minutes, costs about 20 cents):
    python "Cost Optimization/cost_report.py"

Note: OpenAI's automatic PROMPT caching is on for every setup below, because the handbook always comes first in the
prompt. So the "starting point" is already better than a careless one. See notebook 03.
"""

import sys

import cache
import inbox
import strategies
import trim

EMAILS_PER_MONTH = 30000   # the volume we project to. Change it to your own.


def print_table(rows, baseline_cost):
    """One line per setup."""
    print("Setup".ljust(36) + "$ / 1,000".rjust(10) + "Perfect".rjust(10) + "Avg s".rjust(8) + "  Saved".rjust(9) + "   $ / month".rjust(13))
    print("-" * 86)
    for name, result in rows:
        saved = (1 - result["cost_per_1000"] / baseline_cost) * 100
        monthly = result["cost_per_1000"] * EMAILS_PER_MONTH / 1000
        print(name.ljust(36)
              + format(result["cost_per_1000"], ".2f").rjust(10)
              + (str(result["perfect"]) + "/" + str(result["emails"])).rjust(10)
              + format(result["avg_seconds"], ".1f").rjust(8)
              + (format(saved, ".0f") + "%").rjust(9)
              + ("$" + format(monthly, ",.0f")).rjust(13))


def main():
    if hasattr(sys.stdout, "reconfigure"):      # (a notebook's output has no reconfigure)
        sys.stdout.reconfigure(encoding="utf-8")
    items = inbox.traffic()
    print("A day of traffic: " + str(len(items)) + " emails (" + str(len(inbox.EMAILS)) + " different ones + "
          + str(len(inbox.REPEATS)) + " repeats)\n")

    rows = []

    print("A  strongest model for everything...")
    rows.append(("A  gpt-4o for everything", strategies.evaluate(strategies.always_big, items)))

    print("B  cheap model for everything...")
    rows.append(("B  gpt-4o-mini for everything", strategies.evaluate(strategies.always_small, items)))

    print("C  routed...")
    rows.append(("C  routed (easy: mini, hard: 4o)", strategies.evaluate(strategies.routed, items)))

    print("D  routed + cache...")
    answer_cache = cache.AnswerCache()
    rows.append(("D  C + answer cache", strategies.evaluate(strategies.WithCache(strategies.routed, answer_cache), items)))
    cache_stats = dict(answer_cache.stats)

    print("E  routed + cache + trimmed prompt...")
    index = trim.HandbookIndex()
    answer_cache_2 = cache.AnswerCache()
    rows.append(("E  D + trimmed prompt", strategies.evaluate(strategies.WithCache(strategies.Trimmed(index), answer_cache_2), items)))

    print()
    baseline_cost = rows[0][1]["cost_per_1000"]
    print_table(rows, baseline_cost)
    print("\n($ / month is projected for " + format(EMAILS_PER_MONTH, ",") + " emails a month.)")
    print("Cache in D: " + str(cache_stats))

    print("\nReplies that missed a required fact:")
    found_any = False
    for name, result in rows:
        for miss in result["misses"]:
            found_any = True
            print("  [" + name[:1] + "] " + miss["email"][:70] + "  ->  " + miss["source"])
    if not found_any:
        print("  (none)")


if __name__ == "__main__":
    main()
