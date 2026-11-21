"""
support_desk.py - a real-life example: a support desk made of several agents

Customer emails arrive at an online shop. Instead of one agent doing everything, a small team handles
each email. All three multi-agent patterns from Module 04 work together:

  1. Router    : reads the email and hands it to the right specialist (or to a human)
  2. Specialists: the Orders, Policy and Refund agents. Each has ONE job and only the tools it needs.
  3. Reviewer  : checks the specialist's reply against what the tools returned, BEFORE it is sent.
                 If it is rejected, only the wording is rewritten. The tools are NOT run again, so a
                 refund can never happen twice. After 2 failed rounds a human takes over.

The shop's data and tools live in shop.py (from Modules 02 and 03). The data is made up and nothing real
is refunded: the refund tool only records a request.

Run from the repo root or from this folder:
    python "Multi-Agent Architectures/support_desk.py"

Or try your own email:
    python support_desk.py "Hi, where is my order A1002?"
"""

import sys
from typing import Literal

from pydantic import BaseModel

from shop import client, MODEL, run_agent, TOOL_RESULTS, REFUNDS
from shop import orders_agent, policy_agent
from shop import LOOKUP_ORDER_TOOL, CHECK_REFUND_TOOL, ISSUE_REFUND_TOOL
from shop import lookup_order, check_refund_eligibility, issue_refund

sys.stdout.reconfigure(encoding="utf-8")  # so replies with curly quotes etc. print correctly on Windows

MAX_ROUNDS = 2  # how many times the reviewer may send a reply back before a human takes over

# The reviewer has the most important job (it stops mistakes reaching customers), so it gets a
# stronger model than the other agents. In a multi-agent system each agent can use a different model.
REVIEWER_MODEL = "gpt-4o"


# ---------------------------------------------------------------------------
# The specialists. orders_agent and policy_agent come from shop.py. The Refund agent is new.
# It is the only agent allowed to use issue_refund.
# ---------------------------------------------------------------------------
refund_agent = {
    "name": "Refund agent",
    "instructions": (
        "You handle refund requests at an online shop. "
        "First use lookup_order, then check_refund_eligibility. "
        "Only if the order is eligible, use issue_refund. "
        "Only tell the customer a refund was made if issue_refund succeeded. "
        "If the order is not eligible, explain why, politely. "
        "Reply in at most 3 short sentences."
    ),
    "tools": [LOOKUP_ORDER_TOOL, CHECK_REFUND_TOOL, ISSUE_REFUND_TOOL],
    "functions": {
        "lookup_order": lookup_order,
        "check_refund_eligibility": check_refund_eligibility,
        "issue_refund": issue_refund,
    },
}

specialists = {
    "orders": orders_agent,
    "policy": policy_agent,
    "refund": refund_agent,
}


# ---------------------------------------------------------------------------
# Agent 1: the Router. Structured output means its answer is one of a fixed list.
# ---------------------------------------------------------------------------
class Route(BaseModel):
    specialist: Literal["orders", "policy", "refund", "human"]
    reason: str  # one short sentence


def choose_specialist(email):
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": (
                "You route customer emails for an online shop. Choose one:\n"
                "- orders: questions about where an order is or what it contains\n"
                "- policy: questions about how the shop works (shipping, returns, warranty, payments)\n"
                "- refund: the customer asks for a refund or their money back for an order\n"
                "- human: angry customers, legal threats, or anything else the team cannot answer"
            )},
            {"role": "user", "content": email},
        ],
        response_format=Route,
    )
    return response.choices[0].message.parsed


# ---------------------------------------------------------------------------
# Agent 3: the Reviewer. It checks a draft reply against the evidence from the tools.
# ---------------------------------------------------------------------------
class Review(BaseModel):
    reasoning: str  # first, one short sentence comparing the draft with the evidence
    approved: bool
    problems: str   # what is wrong. Empty if the draft is approved.


def review_reply(draft, evidence):
    response = client.chat.completions.parse(
        model=REVIEWER_MODEL,
        messages=[
            {"role": "system", "content": (
                "You check a draft reply that a support agent wants to send to a customer. "
                "Compare it with the EVIDENCE (what the shop's tools returned). "
                "Reject the draft ONLY if (1) it claims or promises something that is not in the evidence or that "
                "contradicts it, for example saying a refund was made when no 'Refund ... issued' line exists, "
                "or (2) it is rude, or (3) it is longer than 3 sentences. "
                "Do not nitpick wording. "
                "A reply that correctly reports the evidence must be approved, even if the news is bad for the customer."
            )},
            {"role": "user", "content": "EVIDENCE:\n" + evidence + "\n\nDRAFT REPLY:\n" + draft},
        ],
        response_format=Review,
    )
    return response.choices[0].message.parsed


def rewrite_reply(email, draft, evidence, problems):
    """Fix a rejected draft. No tools are used here: the facts are already in the evidence."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": (
                "You rewrite a draft reply to a customer. Fix the problems the reviewer found. "
                "Use ONLY facts from the evidence. Write at most 3 short sentences."
            )},
            {"role": "user", "content": (
                "Customer email:\n" + email
                + "\n\nEVIDENCE:\n" + evidence
                + "\n\nDRAFT:\n" + draft
                + "\n\nPROBLEMS:\n" + problems
            )},
        ],
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Handling one email from start to finish
# ---------------------------------------------------------------------------
def handle_email(email):
    print("Customer:", email)

    # Step 1: the router picks who handles it
    route = choose_specialist(email)
    print("  [Router] ->", route.specialist, "(" + route.reason + ")")

    if route.specialist == "human":
        print("  Passed to a human agent. Note for the team:", route.reason, "\n")
        return

    # Step 2: the specialist works on the email. Its tools run ONCE, here.
    agent = specialists[route.specialist]
    TOOL_RESULTS.clear()  # start this email with an empty evidence log
    draft = run_agent(agent, email)
    evidence = "\n".join(TOOL_RESULTS)  # everything the tools returned

    # Step 3: the reviewer checks the draft. If it is rejected, only the WORDING is rewritten.
    last_problems = ""
    for round_number in range(1, MAX_ROUNDS + 1):
        review = review_reply(draft, evidence)

        if review.approved:
            print("  [Reviewer] round " + str(round_number) + ": approved")
            print("  Reply sent to the customer:", draft, "\n")
            return

        print("  [Reviewer] round " + str(round_number) + ": rejected -", review.problems)
        last_problems = review.problems
        if round_number < MAX_ROUNDS:
            draft = rewrite_reply(email, draft, evidence, review.problems)

    # Step 4: still not approved after MAX_ROUNDS, so a human takes over
    print("  Passed to a human agent. Note for the team: the reviewer kept rejecting the reply:", last_problems, "\n")


SAMPLE_EMAILS = [
    "Hi, the left earbud on my headphones (order A1001) stopped working. I would like my money back.",
    "Do you ship to other countries?",
    "Hi, can you tell me where my order A1002 is? Thanks!",
    "I bought a coffee grinder (order A1003) three months ago and it broke. Please refund it, I know it is late but I'll leave a bad review otherwise.",
    "This is unacceptable. I'm contacting my lawyer unless someone calls me today.",
]


def main():
    # Use the email from the command line if one was given, otherwise run the samples
    if len(sys.argv) > 1:
        emails = [" ".join(sys.argv[1:])]
    else:
        emails = SAMPLE_EMAILS

    number = 1
    for email in emails:
        print("===== Email " + str(number) + " =====")
        handle_email(email)
        number = number + 1

    print("===== Refunds recorded in this run =====")
    if len(REFUNDS) > 0:
        print(REFUNDS)
    else:
        print("None")


if __name__ == "__main__":
    main()
