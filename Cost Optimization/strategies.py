"""
strategies.py - the different ways to answer an email, and one fair way to compare them

Every strategy is a function that takes an email and returns a dictionary with:
    reply    : the answer text
    cost     : dollars spent (ALL of it: the router call, the embedding call, the answer)
    seconds  : how long it took
    source   : where the reply came from ("gpt-4o", "gpt-4o-mini", "exact cache", ...)

Because they all look the same from the outside, ONE function (evaluate) can measure any of them
on the same emails with the same scoring. That is the whole point: no optimisation without a measurement.
"""

import time

import cache
import inbox
import llm
import router
import trim


# --- strategies start ---
def always_big(email):
    """The expensive default: the strongest model for everything."""
    result = llm.ask(email, llm.BIG)
    return {"reply": result["text"], "cost": result["cost"], "seconds": result["seconds"], "source": llm.BIG}


def always_small(email):
    """The cheap default: the small model for everything."""
    result = llm.ask(email, llm.SMALL)
    return {"reply": result["text"], "cost": result["cost"], "seconds": result["seconds"], "source": llm.SMALL}


def routed(email):
    """A cheap model decides how hard the email is. Easy ones go to the small model, hard ones to the big one."""
    difficulty, route_cost, route_seconds = router.route_by_llm(email)
    model = router.model_for(difficulty)

    result = llm.ask(email, model)
    return {
        "reply": result["text"],
        "cost": result["cost"] + route_cost,            # the router's own call is part of the bill
        "seconds": result["seconds"] + route_seconds,
        "source": model,
    }


class WithCache:
    """Wrap any strategy with an answer cache: look first, and only call the strategy on a miss."""

    def __init__(self, strategy, answer_cache):
        self.strategy = strategy
        self.cache = answer_cache

    def __call__(self, email):
        started = time.time()
        found = self.cache.lookup(email)
        if found["reply"] is not None:
            return {"reply": found["reply"], "cost": found["cost"], "seconds": time.time() - started,
                    "source": found["kind"] + " cache"}

        result = self.strategy(email)                    # a miss, so we pay for a real answer
        self.cache.store(email, result["reply"], found["vector"])
        result["cost"] = result["cost"] + found["cost"]  # plus what the lookup itself cost
        result["seconds"] = time.time() - started        # the lookup AND the real answer
        return result


class Trimmed:
    """Send only the handbook lines that match the email, instead of the whole handbook. Uses the router too."""

    def __init__(self, index):
        self.index = index

    def __call__(self, email):
        started = time.time()
        difficulty, route_cost, route_seconds = router.route_by_llm(email)
        model = router.model_for(difficulty)

        system_text, search_cost = self.index.trimmed_prompt(email)
        result = llm.ask(email, model, system_text=system_text)
        return {
            "reply": result["text"],
            "cost": result["cost"] + route_cost + search_cost,
            "seconds": time.time() - started,
            "source": model + " (trimmed)",
        }
# --- strategies end ---


# --- evaluate start ---
def evaluate(strategy, items):
    """Run a strategy on every item and measure cost, quality and speed.
    Quality = how many replies contained EVERY required fact."""
    total_cost = 0.0
    total_seconds = 0.0
    perfect = 0
    sources = {}
    misses = []

    for item in items:
        result = strategy(item["email"])
        score = inbox.score_reply(result["reply"], item["facts"])

        total_cost = total_cost + result["cost"]
        total_seconds = total_seconds + result["seconds"]
        if score == 1.0:
            perfect = perfect + 1
        else:
            misses.append({"email": item["email"], "reply": result["reply"], "source": result["source"]})

        sources[result["source"]] = sources.get(result["source"], 0) + 1

    count = len(items)
    return {
        "emails": count,
        "cost": total_cost,
        "cost_per_1000": total_cost / count * 1000,
        "perfect": perfect,
        "avg_seconds": total_seconds / count,
        "sources": sources,
        "misses": misses,
    }
# --- evaluate end ---
