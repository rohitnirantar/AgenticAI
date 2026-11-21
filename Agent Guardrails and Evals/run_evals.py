"""
run_evals.py - run the test suite for the support desk and print a scorecard

Run it after every change to a prompt, a model or a guardrail. If the pass rate drops, the change made
something worse. It exits with an error code when the pass rate is below THRESHOLD, so it could also run
automatically before every release.

Run from the repo root or from this folder:
    python "Agent Guardrails and Evals/run_evals.py"

Each case runs 2 times because models are not deterministic. It makes roughly 100 small model calls.
"""

import sys

import evals

sys.stdout.reconfigure(encoding="utf-8")  # so output with special characters prints correctly on Windows

THRESHOLD = 0.8  # the lowest pass rate we accept
RUNS_PER_CASE = 2


def main():
    print("Running " + str(len(evals.EVAL_CASES)) + " cases, " + str(RUNS_PER_CASE) + " runs each...\n")
    report = evals.run_evals(runs=RUNS_PER_CASE)
    pass_rate = evals.print_scorecard(report)

    if pass_rate < THRESHOLD:
        print("\nBELOW THE THRESHOLD of " + str(round(THRESHOLD * 100)) + "%. Do not release this version.")
        sys.exit(1)

    print("\nAbove the threshold of " + str(round(THRESHOLD * 100)) + "%.")


if __name__ == "__main__":
    main()
