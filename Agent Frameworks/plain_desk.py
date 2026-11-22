"""
plain_desk.py - the support desk built BY HAND (no framework)

This is the baseline for the module. It is the same pattern you built in Modules 02 to 04:
  1. describe every tool to the model by hand (the JSON blocks)
  2. write the agent loop
  3. write a router that picks the specialist
Every framework in this module does these three jobs for you. Compare the size of this file with the others.
"""

import json
import time

from openai import OpenAI
from pydantic import BaseModel

import shop_tools as shop

client = OpenAI()


# ---------------------------------------------------------------------------
# Job 1: describe every tool to the model by hand. Each tool needs its own description,
# even though the function already says the same thing.
# ---------------------------------------------------------------------------
# --- tools start ---
def make_tool(name, description, input_name, input_description):
    """Build the description of a tool that takes a single text input."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {input_name: {"type": "string", "description": input_description}},
                "required": [input_name],
            },
        },
    }


LOOKUP_ORDER_TOOL = make_tool("lookup_order", "Get the details of one order: item, price, status and delivery date.",
                              "order_id", "The order id, for example A1001")
SEARCH_POLICIES_TOOL = make_tool("search_policies", "Search the shop's policies (refunds, shipping, warranty, payments).",
                                 "question", "What to look up, in plain words")
CHECK_REFUND_TOOL = make_tool("check_refund_eligibility", "Check whether an order can be refunded under the shop's policy.",
                              "order_id", "The order id, for example A1001")
ISSUE_REFUND_TOOL = make_tool("issue_refund", "Issue a refund for an order. Only use this after the order is confirmed eligible.",
                              "order_id", "The order id, for example A1001")
# --- tools end ---


# An agent is just a name, instructions, tools, and the functions behind the tools.
orders_agent = {"name": "Orders agent", "instructions": shop.ORDERS_INSTRUCTIONS,
                "tools": [LOOKUP_ORDER_TOOL], "functions": {"lookup_order": shop.lookup_order}}
policy_agent = {"name": "Policy agent", "instructions": shop.POLICY_INSTRUCTIONS,
                "tools": [SEARCH_POLICIES_TOOL], "functions": {"search_policies": shop.search_policies}}
refunds_agent = {"name": "Refunds agent", "instructions": shop.REFUNDS_INSTRUCTIONS,
                 "tools": [CHECK_REFUND_TOOL, ISSUE_REFUND_TOOL],
                 "functions": {"check_refund_eligibility": shop.check_refund_eligibility, "issue_refund": shop.issue_refund}}

SPECIALISTS = {"orders": orders_agent, "policy": policy_agent, "refunds": refunds_agent}


# ---------------------------------------------------------------------------
# Job 2: the agent loop. Ask the model, run the tools it requests, repeat until it answers.
# ---------------------------------------------------------------------------
# --- loop start ---
def run_agent(agent, message, max_steps=6):
    """Give one message to an agent. It may use its tools several times, then it replies.
    Returns the reply and the tokens used."""
    messages = [
        {"role": "system", "content": agent["instructions"]},
        {"role": "user", "content": message},
    ]
    tokens = 0

    for step in range(max_steps):
        response = client.chat.completions.create(model=shop.MODEL, messages=messages, tools=agent["tools"])
        reply = response.choices[0].message
        messages.append(reply)
        tokens = tokens + response.usage.total_tokens

        # No tool requested? The agent has its answer.
        if not reply.tool_calls:
            return reply.content, tokens

        # Otherwise run each requested tool and give the result back to the agent
        for tool_call in reply.tool_calls:
            args = json.loads(tool_call.function.arguments)
            result = agent["functions"][tool_call.function.name](**args)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    return "Stopped: too many steps.", tokens
# --- loop end ---


# ---------------------------------------------------------------------------
# Job 3: the router. A small model call that picks the specialist.
# ---------------------------------------------------------------------------
# --- router start ---
class Route(BaseModel):
    specialist: str  # "orders", "policy" or "refunds"


def choose_specialist(email):
    """Ask the model which specialist should handle this email. Returns the name and the tokens used."""
    response = client.chat.completions.parse(
        model=shop.MODEL,
        messages=[
            {"role": "system", "content": "Pick the specialist for this customer email. "
                                          "orders = where an order is or what is in it. "
                                          "policy = shop rules such as shipping, warranty or payments. "
                                          "refunds = the customer wants their money back."},
            {"role": "user", "content": email},
        ],
        response_format=Route,
    )
    return response.choices[0].message.parsed.specialist, response.usage.total_tokens
# --- router end ---


def handle_email(email):
    """Handle one customer email from start to finish."""
    shop.reset_shop()
    started = time.time()

    specialist, router_tokens = choose_specialist(email)
    reply, agent_tokens = run_agent(SPECIALISTS[specialist], email)

    return {
        "specialist": specialist,
        "reply": reply,
        "refunds": list(shop.REFUNDS),
        "tool_calls": list(shop.TOOL_CALLS),
        "tokens": router_tokens + agent_tokens,
        "seconds": time.time() - started,
    }
