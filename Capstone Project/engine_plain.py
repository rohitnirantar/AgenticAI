"""
engine_plain.py - the baseline engine: the hand-built agent loop from Modules 02 to 05 (no framework)

It uses the router, the agents and run_agent() that we wrote ourselves. This is what the frameworks are compared with.
Its model calls need no special hook: the wrapped OpenAI client from Module 07 (observe.instrument_client) already
records them. That is the benefit of owning the loop, and the reason it has no 'observe' block below.

Run it end to end (the whole scenario, with every guardrail on):
    python "Capstone Project/engine_plain.py"
"""

import sys

import shop
import desk
import scenario

NAME = "plain"


# --- desk start ---
def run(email):
    """Route the email, then let the chosen specialist answer it."""
    route = desk.choose_specialist(email)            # a model call that picks: orders, policy, refund or human
    if route.specialist == "human":
        return {"route": "human", "reply": ""}

    agent = desk.specialists[route.specialist]
    if route.specialist == "refund":
        agent = desk.guarded_refund_agent            # the same agent, with the refund limit in its tool

    reply = shop.run_agent(agent, email)             # the loop we wrote in Module 02
    return {"route": route.specialist, "reply": reply}
# --- desk end ---


if __name__ == "__main__":
    scenario.main(sys.modules[__name__])
