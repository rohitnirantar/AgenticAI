"""
capstone_crewai.py - the guarded, observable support desk with CrewAI (one complete, runnable file)

The framework-specific part is only here: a one-agent triage crew that picks the route, a one-agent crew for the
chosen specialist, plus two event handlers that report every model call into our traces. Everything around it is
shared by all engines: the guardrails (pipeline.py), the tools with the refund limit (tools.py), and the scenario
that is run (scenario.py).

Run it end to end, in the Module 06 environment (venv-frameworks), from the repo root or from this folder:
    python "Capstone Project/capstone_crewai.py"            (the morning scenario, all guardrails on)
    python "Capstone Project/capstone_crewai.py" --evals    (and then the 9-case eval suite)
"""

import os

# CrewAI sends anonymous usage data by default. We switch that off for this course.
# (These must be set before CrewAI is imported.)
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["OTEL_SDK_DISABLED"] = "true"

import sys
from typing import Literal

from pydantic import BaseModel
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
from crewai.events import crewai_event_bus, LLMCallStartedEvent, LLMCallCompletedEvent

import observe
import prompts
import scenario
import shop
import tools

NAME = "crewai"


# --- observe start ---
call_started = {}  # call id -> when that model call began


@crewai_event_bus.on(LLMCallStartedEvent)
def on_llm_start(source, event):
    """CrewAI announces every model call on an event bus. We listen, and note when each one began."""
    call_started[event.call_id] = event.timestamp


@crewai_event_bus.on(LLMCallCompletedEvent)
def on_llm_end(source, event):
    """...and when each one ends, we turn it into a span in our trace."""
    started = call_started.pop(event.call_id, event.timestamp)
    model = event.model
    if model is None:
        model = shop.MODEL

    if event.usage is not None:
        observe.record_model_call("crewai:" + model, model, event.usage["prompt_tokens"],
                                  event.usage["completion_tokens"], (event.timestamp - started).total_seconds())
# --- observe end ---


# --- desk start ---
# Our shared plain functions become CrewAI tools. The refund limit and the evidence log are inside the functions.
lookup_order = tool("lookup_order")(tools.lookup_order)
check_refund_eligibility = tool("check_refund_eligibility")(tools.check_refund_eligibility)
issue_refund = tool("issue_refund")(tools.issue_refund)
search_policies = tool("search_policies")(tools.search_policies)


def make_specialists():
    """Build the team. Each agent has a role, a goal and a backstory (our shared instructions).
    max_iter is CrewAI's own step limit for an agent (our budget against loops)."""
    llm = LLM(model=shop.MODEL, temperature=0)
    return {
        "orders": Agent(
            role="Orders specialist", goal="Answer questions about where an order is and what is in it",
            backstory=prompts.ORDERS, tools=[lookup_order], llm=llm, max_iter=6),
        "policy": Agent(
            role="Policy specialist", goal="Answer questions about shop rules: shipping costs, returns, warranty and payments",
            backstory=prompts.POLICY, tools=[search_policies], llm=llm, max_iter=6),
        "refund": Agent(
            role="Refund specialist", goal="Handle requests from customers who want their money back",
            backstory=prompts.REFUND, tools=[lookup_order, check_refund_eligibility, issue_refund], llm=llm, max_iter=6),
    }


class Route(BaseModel):
    route: Literal["orders", "policy", "refund", "human"]


def choose_route(email):
    """A one-agent crew whose only job is to pick the route. CrewAI turns its answer into a typed Route."""
    triage_agent = Agent(
        role="Triage agent", goal="Decide who should handle a customer email",
        backstory=prompts.ROUTING, llm=LLM(model=shop.MODEL, temperature=0), max_iter=3)
    triage_task = Task(
        description="Pick the route for this customer email:\n" + email,
        expected_output="One route: orders, policy, refund or human",
        agent=triage_agent, output_pydantic=Route)

    result = Crew(agents=[triage_agent], tasks=[triage_task], process=Process.sequential).kickoff()
    return result.pydantic.route


def write_reply(route, email):
    """A one-agent crew: the chosen specialist writes the reply."""
    specialist = make_specialists()[route]
    reply_task = Task(
        description="Reply to this customer email:\n" + email,
        expected_output="Only the reply text for the customer: at most 3 short sentences, no subject line, no greeting, no signature.",
        agent=specialist)

    result = Crew(agents=[specialist], tasks=[reply_task], process=Process.sequential).kickoff()
    return result.raw


def run(email):
    """The engine: pick the route, then (unless it is 'human') let the specialist's crew answer."""
    route = choose_route(email)
    reply = ""
    if route != "human":
        reply = write_reply(route, email)

    # CrewAI handles its events on other threads. In our tests every call had already reached the trace by the
    # time the crews returned, but nothing guarantees it. So we wait until all events are handled (cheap insurance):
    # a call that arrived after the trace was closed would be missing, and the cost would be too low.
    crewai_event_bus.flush()
    return {"route": route, "reply": reply}
# --- desk end ---


if __name__ == "__main__":
    scenario.main(sys.modules[__name__])
