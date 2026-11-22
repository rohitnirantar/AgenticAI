"""
crewai_desk.py - the support desk built with CrewAI (a complete, runnable example)

CrewAI thinks in teams: an AGENT has a role, a goal and a backstory, a TASK is a job to do,
and a CREW is a team that works through tasks. It reads almost like a job description.

This one file is the whole story: it builds the desk, then runs a morning inbox of five customer emails
through it and checks every outcome in the shop's data (was a refund really created?).

Run it from the repo root or from this folder, using the module's own environment (see requirements.txt):
    python "Agent Frameworks/crewai_desk.py"
"""

import os
import sys

# CrewAI sends anonymous usage data by default. We switch that off for this course.
# (These must be set before CrewAI is imported.)
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["OTEL_SDK_DISABLED"] = "true"

import time
from typing import Literal

from pydantic import BaseModel
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

import shop_tools as shop
import compare  # only for the inbox of test emails and the check of each result

# --- specialists start ---
# Wrap our plain functions as CrewAI tools. The docstring tells the agent what each tool does.
lookup_order = tool("lookup_order")(shop.lookup_order)
search_policies = tool("search_policies")(shop.search_policies)
check_refund_eligibility = tool("check_refund_eligibility")(shop.check_refund_eligibility)
issue_refund = tool("issue_refund")(shop.issue_refund)


def make_specialists():
    """Build the team. Each agent has a role, a goal, and a backstory (our instructions)."""
    llm = LLM(model=shop.MODEL, temperature=0)
    return {
        "orders": Agent(
            role="Orders specialist",
            goal="Answer questions about where an order is and what is in it",
            backstory=shop.ORDERS_INSTRUCTIONS, tools=[lookup_order], llm=llm),
        "policy": Agent(
            role="Policy specialist",
            goal="Answer questions about shop rules: shipping costs, returns, warranty and payments",
            backstory=shop.POLICY_INSTRUCTIONS, tools=[search_policies], llm=llm),
        "refunds": Agent(
            role="Refunds specialist",
            goal="Handle requests from customers who want their money back",
            backstory=shop.REFUNDS_INSTRUCTIONS, tools=[check_refund_eligibility, issue_refund], llm=llm),
    }
# --- specialists end ---


# --- desk start ---
class Route(BaseModel):
    specialist: Literal["orders", "policy", "refunds"]


def choose_specialist(email):
    """A one-agent crew whose only job is to pick the specialist. Returns the name and the tokens used."""
    triage_agent = Agent(
        role="Triage agent",
        goal="Decide which specialist should handle a customer email",
        backstory="orders = where an order is or what is in it. "
                  "policy = shop rules such as shipping, warranty or payments. "
                  "refunds = the customer wants their money back.",
        llm=LLM(model=shop.MODEL, temperature=0))
    triage_task = Task(
        description="Pick the specialist for this customer email:\n" + email,
        expected_output="The name of one specialist",
        agent=triage_agent,
        output_pydantic=Route)  # CrewAI turns the answer into a Route for us

    result = Crew(agents=[triage_agent], tasks=[triage_task], process=Process.sequential).kickoff()
    return result.pydantic.specialist, result.token_usage.total_tokens


def answer_email(specialist_name, email):
    """A one-agent crew: the chosen specialist writes the reply. Returns the reply and the tokens used."""
    specialist = make_specialists()[specialist_name]
    reply_task = Task(
        description="Reply to this customer email:\n" + email,
        expected_output="Only the reply text for the customer: 2 short sentences, no subject line, no greeting, no signature.",
        agent=specialist)

    result = Crew(agents=[specialist], tasks=[reply_task], process=Process.sequential).kickoff()
    return result.raw, result.token_usage.total_tokens
# --- desk end ---


def handle_email(email):
    """Handle one customer email from start to finish."""
    shop.reset_shop()
    started = time.time()

    specialist, router_tokens = choose_specialist(email)
    reply, agent_tokens = answer_email(specialist, email)

    return {
        "specialist": specialist,
        "reply": reply,
        "refunds": list(shop.REFUNDS),
        "tool_calls": list(shop.TOOL_CALLS),
        "tokens": router_tokens + agent_tokens,
        "seconds": time.time() - started,
    }


def main():
    """The real-life flow: a morning inbox goes through the desk, and every outcome is checked."""
    sys.stdout.reconfigure(encoding="utf-8")  # so output with special characters prints correctly on Windows
    print("=== CrewAI desk: " + str(len(compare.INBOX)) + " emails ===")

    passed = 0
    total_tokens = 0

    for case in compare.INBOX:
        result = handle_email(case["email"])
        problems = compare.check_result(case, result)  # compare the outcome with what we expected

        status = "ok"
        if len(problems) > 0:
            status = "FAILED"
        else:
            passed = passed + 1
        total_tokens = total_tokens + result["tokens"]

        print("\n[" + status + "] " + case["name"])
        print("  Email:      " + case["email"])
        print("  Handled by: " + result["specialist"] + " (tools: " + ", ".join(result["tool_calls"]) + ")")
        print("  Reply:      " + result["reply"].replace("\n", " "))
        print("  Cost:       " + str(result["tokens"]) + " tokens, " + format(result["seconds"], ".1f") + " seconds")
        for problem in problems:
            print("  PROBLEM:    " + problem)

    print("\nCorrect: " + str(passed) + "/" + str(len(compare.INBOX))
          + ", average tokens per email: " + str(round(total_tokens / len(compare.INBOX))))


if __name__ == "__main__":
    main()
