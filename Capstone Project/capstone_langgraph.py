"""
capstone_langgraph.py - the guarded, observable support desk with LangGraph (one complete, runnable file)

The framework-specific part is only here: a graph that routes an email to one of four nodes (three specialists and
a "human" exit), plus a callback class that reports every model call into our traces. Everything around it is
shared by all engines: the guardrails (pipeline.py), the tools with the refund limit (tools.py), and the scenario
that is run (scenario.py).

Run it end to end, in the Module 06 environment (venv-frameworks), from the repo root or from this folder:
    python "Capstone Project/capstone_langgraph.py"            (the morning scenario, all guardrails on)
    python "Capstone Project/capstone_langgraph.py" --evals    (and then the 9-case eval suite)
"""

import sys
import time
from typing import Literal, TypedDict

from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.graph import StateGraph, START, END

import observe
import prompts
import scenario
import shop
import tools

NAME = "langgraph"

llm = ChatOpenAI(model=shop.MODEL, temperature=0)


# --- observe start ---
class ObserveCallback(BaseCallbackHandler):
    """LangChain calls these methods around EVERY model call, including the ones made by agents nested inside
    graph nodes. We turn each call into a span in our trace."""

    def __init__(self):
        self.started = {}  # run_id -> when that model call began

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self.started[run_id] = time.time()

    def on_llm_end(self, response, *, run_id, **kwargs):
        usage = response.generations[0][0].message.usage_metadata
        seconds = time.time() - self.started.pop(run_id, time.time())
        observe.record_model_call("langgraph:" + shop.MODEL, shop.MODEL, usage["input_tokens"],
                                  usage["output_tokens"], seconds)
# --- observe end ---


# --- desk start ---
# create_agent builds a complete tool-using agent (the loop AND the tool descriptions) from our plain functions.
# The refund limit and the evidence log are inside the functions.
orders_agent = create_agent(llm, tools=[tools.lookup_order], system_prompt=prompts.ORDERS)
policy_agent = create_agent(llm, tools=[tools.search_policies], system_prompt=prompts.POLICY)
refund_agent = create_agent(
    llm, tools=[tools.lookup_order, tools.check_refund_eligibility, tools.issue_refund], system_prompt=prompts.REFUND)


class DeskState(TypedDict):
    email: str
    route: str
    reply: str


class Route(BaseModel):
    route: Literal["orders", "policy", "refund", "human"]  # the router can only answer one of these four


def route_node(state):
    """Node 1: decide who handles the email."""
    router = llm.with_structured_output(Route)
    decision = router.invoke(prompts.ROUTING + "\n\nEmail: " + state["email"])
    return {"route": decision.route}


def make_specialist_node(agent):
    """Wrap a specialist agent so it can sit in the graph as a node."""
    def node(state):
        result = agent.invoke({"messages": [{"role": "user", "content": state["email"]}]})
        return {"reply": result["messages"][-1].content}
    return node


def human_node(state):
    """The 'human' exit: no agent runs, and nothing is answered."""
    return {"reply": ""}


def pick_next(state):
    """The conditional edge: read the state and name the next node."""
    return state["route"]


builder = StateGraph(DeskState)
builder.add_node("route", route_node)
builder.add_node("orders", make_specialist_node(orders_agent))
builder.add_node("policy", make_specialist_node(policy_agent))
builder.add_node("refund", make_specialist_node(refund_agent))
builder.add_node("human", human_node)

builder.add_edge(START, "route")
builder.add_conditional_edges("route", pick_next,
                              {"orders": "orders", "policy": "policy", "refund": "refund", "human": "human"})
for node_name in ["orders", "policy", "refund", "human"]:
    builder.add_edge(node_name, END)

desk_graph = builder.compile()


def run(email):
    """The engine: run the graph. recursion_limit is LangGraph's own step limit (our budget against loops)."""
    final_state = desk_graph.invoke(
        {"email": email},
        config={"callbacks": [ObserveCallback()], "recursion_limit": 15},
    )
    return {"route": final_state["route"], "reply": final_state["reply"]}
# --- desk end ---


if __name__ == "__main__":
    scenario.main(sys.modules[__name__])
