"""
router.py - decide which model should answer an email

The idea: do not hire an expert for a job a beginner can do. Easy emails go to the cheap model, hard ones to the
strong one. Two routers, so you can compare them:

  route_by_rules : a few plain rules. Free and instant, but it only sees the SURFACE of the email.
  route_by_llm   : the cheap model reads the email and decides. It costs a (very small) call, but it understands.

A router is itself a model call, so its cost counts too. And a router can be wrong: an arithmetic email sent to
the cheap model gets a cheap, wrong answer. So we always MEASURE the router against emails whose difficulty we know.
"""

import time
from typing import Literal

from pydantic import BaseModel

import llm


# --- rules start ---
HARD_WORDS = ["lawyer", "exception", "frustrated", "angry", "card number", "how much more", "in total", "after the"]


def route_by_rules(email):
    """Plain rules. Returns 'easy' or 'hard'. Free, and it never makes a model call."""
    text = email.lower()

    if len(text.split()) > 20:          # a long email usually asks for several things
        return "hard"
    if text.count("?") > 1:             # several questions
        return "hard"
    for word in HARD_WORDS:
        if word in text:
            return "hard"
    return "easy"
# --- rules end ---


# --- llm start ---
class Difficulty(BaseModel):
    difficulty: Literal["easy", "hard"]


ROUTER_INSTRUCTIONS = (
    "You sort customer emails for an online shop. "
    "Answer 'easy' if the email asks ONE simple question about shipping, payment, returns or warranty "
    "that a single line of a policy answers. "
    "Answer 'hard' if it asks several things at once, needs a calculation, asks for an exception, "
    "mentions a lawyer, a card number or an angry complaint, or needs two rules to be combined."
)


def route_by_llm(email):
    """The cheap model decides. Returns (difficulty, cost in dollars, seconds)."""
    started = time.time()
    response = llm.client.chat.completions.parse(
        model=llm.SMALL,
        messages=[
            {"role": "system", "content": ROUTER_INSTRUCTIONS},
            {"role": "user", "content": email},
        ],
        response_format=Difficulty,
        max_tokens=20,
        temperature=0,
    )
    seconds = time.time() - started

    usage = response.usage
    cost = llm.cost_of(llm.SMALL, usage.prompt_tokens, 0, usage.completion_tokens)
    return response.choices[0].message.parsed.difficulty, cost, seconds
# --- llm end ---


def model_for(difficulty):
    """The routing table: which model answers which difficulty."""
    if difficulty == "hard":
        return llm.BIG
    return llm.SMALL
