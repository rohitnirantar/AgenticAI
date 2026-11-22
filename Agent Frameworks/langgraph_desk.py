"""
langgraph_desk.py - the support desk built with LangGraph (a complete, runnable example)

LangGraph asks you to draw the flow yourself as a graph: boxes (nodes) that do work, and arrows (edges)
that say what comes next. You get full control over the flow. In return you write the routing yourself.

This one file is the whole story: it builds the desk, then runs a morning inbox of five customer emails
through it and checks every outcome in the shop's data (was a refund really created?).

Run it from the repo root or from this folder, using the module's own environment (see requirements.txt):
    python "Agent Frameworks/langgraph_desk.py"
"""

import sys
import time
from typing import Literal, TypedDict

from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.callbacks import get_usage_metadata_callback
from langgraph.graph import StateGraph, START, END

import shop_tools as shop
import compare  # only for the inbox of test emails and the check of each result

llm = ChatOpenAI(model=shop.MODEL, temperature=0)

# --- specialists start ---
# create_agent builds a complete tool-using agent: the loop AND the tool descriptions.
# Our plain functions work as tools as they are (the docstring and type hints describe them).
orders_agent = create_agent(llm, tools=[shop.lookup_order], system_prompt=shop.ORDERS_INSTRUCTIONS)
policy_agent = create_agent(llm, tools=[shop.search_policies], system_prompt=shop.POLICY_INSTRUCTIONS)
refunds_agent = create_agent(llm, tools=[shop.check_refund_eligibility, shop.issue_refund], system_prompt=shop.REFUNDS_INSTRUCTIONS)
# --- specialists end ---


# --- graph start ---
# The STATE is a shared notebook that every node can read and add to.
class DeskState(TypedDict):
    email: str
    specialist: str
    reply: str


class Route(BaseModel):
    specialist: Literal["orders", "policy", "refunds"]  # the model can only pick one of these three


def route_node(state):
    """Node 1: decide which specialist should handle the email."""
    router = llm.with_structured_output(Route)
    route = router.invoke(
        "Pick the specialist for this customer email. "
        "orders = where an order is or what is in it. "
        "policy = shop rules such as shipping, warranty or payments. "
        "refunds = the customer wants their money back.\n\nEmail: " + state["email"])
    return {"specialist": route.specialist}  # a node returns only the parts of the state it changes


def make_specialist_node(agent):
    """Wrap a specialist agent so it can sit in the graph as a node."""
    def node(state):
        result = agent.invoke({"messages": [{"role": "user", "content": state["email"]}]})
        return {"reply": result["messages"][-1].content}
    return node


def pick_specialist(state):
    """The conditional edge: read the state and return the name of the next node."""
    return state["specialist"]


builder = StateGraph(DeskState)
builder.add_node("route", route_node)
builder.add_node("orders", make_specialist_node(orders_agent))
builder.add_node("policy", make_specialist_node(policy_agent))
builder.add_node("refunds", make_specialist_node(refunds_agent))

builder.add_edge(START, "route")
builder.add_conditional_edges("route", pick_specialist, {"orders": "orders", "policy": "policy", "refunds": "refunds"})
builder.add_edge("orders", END)
builder.add_edge("policy", END)
builder.add_edge("refunds", END)

desk_graph = builder.compile()  # turn the drawing into something we can run
# --- graph end ---


def handle_email(email):
    """Handle one customer email from start to finish."""
    shop.reset_shop()
    started = time.time()

    with get_usage_metadata_callback() as usage:  # counts the tokens of every model call inside
        final_state = desk_graph.invoke({"email": email})

    tokens = 0
    for model_name in usage.usage_metadata:
        tokens = tokens + usage.usage_metadata[model_name]["total_tokens"]

    return {
        "specialist": final_state["specialist"],
        "reply": final_state["reply"],
        "refunds": list(shop.REFUNDS),
        "tool_calls": list(shop.TOOL_CALLS),
        "tokens": tokens,
        "seconds": time.time() - started,
    }


def main():
    """The real-life flow: a morning inbox goes through the desk, and every outcome is checked."""
    sys.stdout.reconfigure(encoding="utf-8")  # so output with special characters prints correctly on Windows
    print("=== LangGraph desk: " + str(len(compare.INBOX)) + " emails ===")

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
