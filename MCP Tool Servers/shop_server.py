"""
shop_server.py - the shop's tools, as an MCP server

MCP (Model Context Protocol) is a standard plug for AI tools, like USB-C. You write the tools ONCE, as a server.
Any AI app that speaks MCP can then discover and use them: our own agent loop, the OpenAI Agents SDK, Claude Desktop...
without anyone rewriting tool descriptions.

An MCP server can offer three kinds of things:
  TOOLS     : actions the model can ask for (lookup_order, issue_refund)
  RESOURCES : data the app can read (the shop's policies, one order)
  PROMPTS   : ready-made prompt templates (a refund reply)

The server never talks to a model. It only answers requests. It runs as its own program, and the AI app starts it
and talks to it over its standard input and output (the "stdio" transport).

IMPORTANT: on stdio, standard OUTPUT is the protocol. Never print() for debugging in a server: write to stderr.

You normally do not run this file by hand: the clients in this module start it. To try it yourself:
    python "MCP Tool Servers/shop_server.py"        (it waits for requests on stdin; press Ctrl+C to stop)

Set SHOP_EXTRA_TOOLS=1 before starting it, and the server offers one more tool (see the bottom of the file).
"""

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

mcp = MCPServer(
    "shop-support",
    instructions="Tools for the support desk of an online shop: look up orders, check and issue refunds, search the policies.",
)

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge_base"
REFUND_WINDOW_DAYS = 30
AUTO_REFUND_LIMIT = 100.00   # refunds above this wait for a person. The limit lives HERE, in the server, in code.


def days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


ORDERS = {
    "A1001": {"item": "Wireless headphones", "price": 79.00, "status": "delivered", "delivered_on": days_ago(18)},
    "A1002": {"item": "Running shoes", "price": 120.00, "status": "in_transit", "expected_delivery": days_ago(-4)},
    "A1003": {"item": "Coffee grinder", "price": 45.00, "status": "delivered", "delivered_on": days_ago(80)},
    "A1004": {"item": "4K television", "price": 250.00, "status": "delivered", "delivered_on": days_ago(5)},
}
REFUNDS = []   # refunds that were issued
PENDING = []   # refunds waiting for a person


def refund_rules(order_id):
    """The refund policy. Returns (is_allowed, explanation)."""
    order = ORDERS.get(order_id.strip().upper())
    if order is None:
        return False, "No order found with id " + order_id + "."
    if order["status"] != "delivered":
        return False, "Not eligible: the order has not been delivered yet."

    days = (date.today() - date.fromisoformat(order["delivered_on"])).days
    if days > REFUND_WINDOW_DAYS:
        return False, "Not eligible: delivered " + str(days) + " days ago, the refund window is " + str(REFUND_WINDOW_DAYS) + " days."
    return True, "Eligible: delivered " + str(days) + " days ago, within the " + str(REFUND_WINDOW_DAYS) + " day window."


# ---------------------------------------------------------------------------
# TOOLS. A tool is a plain Python function with type hints and a docstring.
#   - the function NAME becomes the tool's name
#   - the DOCSTRING becomes the tool's description (this is what the model reads, so write it for the model)
#   - the TYPE HINTS become the input schema. You write no JSON by hand.
# ToolAnnotations are HINTS about what a tool does (read-only or not). A client may use them, but a client must never
# TRUST them from a server it does not control.
# ---------------------------------------------------------------------------
# --- tools start ---
@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def lookup_order(order_id: str) -> str:
    """Get the details of one order: item, price, status and delivery date. The order id looks like A1001."""
    order = ORDERS.get(order_id.strip().upper())
    if order is None:
        return "No order found with id " + order_id + "."

    details = dict(order)
    if order["status"] == "delivered":
        details["days_since_delivery"] = (date.today() - date.fromisoformat(order["delivered_on"])).days
    return json.dumps(details)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def check_refund_eligibility(order_id: str) -> str:
    """Check whether an order can be refunded under the shop's policy (30 days after delivery)."""
    allowed, explanation = refund_rules(order_id)
    return explanation


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
def issue_refund(order_id: str) -> str:
    """Issue a refund for an order. Only use this after the order is confirmed eligible.
    Refunds above $100 are not issued: they wait for a person to approve them."""
    order_id = order_id.strip().upper()
    allowed, explanation = refund_rules(order_id)
    if not allowed:
        return "Refund refused. " + explanation

    for refund in REFUNDS:
        if refund["order_id"] == order_id:
            return "A refund for order " + order_id + " was already issued."

    amount = ORDERS[order_id]["price"]
    if amount > AUTO_REFUND_LIMIT:          # the rule is in code, so no prompt can talk the server out of it
        if order_id not in PENDING:
            PENDING.append(order_id)
        return "The refund of $" + format(amount, ".2f") + " is above the automatic limit and now waits for a person. It has NOT been issued."

    REFUNDS.append({"order_id": order_id, "amount": amount})
    return "Refund of $" + format(amount, ".2f") + " issued for order " + order_id + "."


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def search_policies(question: str) -> str:
    """Search the shop's policies (shipping, returns, warranty, payments). Ask about one topic at a time."""
    words = re.findall(r"[a-z0-9$]+", question.lower())
    scored = []
    for file in sorted(KNOWLEDGE_DIR.glob("*.txt")):
        for paragraph in re.split(r"\n\s*\n", file.read_text(encoding="utf-8")):
            text = paragraph.strip().lower()
            score = 0
            for word in words:
                if len(word) > 3 and word in text:
                    score = score + 1
            if score > 0:
                scored.append((score, paragraph.strip()))
    scored.sort(reverse=True)

    lines = []
    for score, paragraph in scored[:3]:
        lines.append(paragraph)
    if len(lines) == 0:
        return "No policy found for that question."
    return "\n".join(lines)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_refunds() -> str:
    """For staff and tests: the refunds that were issued, and the ones waiting for a person."""
    return json.dumps({"issued": REFUNDS, "waiting_for_a_person": PENDING})
# --- tools end ---


# ---------------------------------------------------------------------------
# RESOURCES: data the app can read. The app decides when to read them (the model does not call them).
# PROMPTS: templates a user can pick, for example from a menu.
# ---------------------------------------------------------------------------
# --- resources start ---
@mcp.resource("shop://policies")
def all_policies() -> str:
    """The full text of the shop's policies."""
    text = ""
    for file in sorted(KNOWLEDGE_DIR.glob("*.txt")):
        text = text + file.read_text(encoding="utf-8").strip() + "\n\n"
    return text.strip()


@mcp.resource("order://{order_id}")
def order_details(order_id: str) -> str:
    """One order, as data. The {order_id} in the address makes this a resource TEMPLATE."""
    return lookup_order(order_id)


@mcp.prompt()
def refund_reply(order_id: str, customer_name: str) -> str:
    """A ready-made prompt that asks for a short, kind reply about a refund."""
    return ("Write a reply of at most 3 short sentences to " + customer_name + " about the refund request for order "
            + order_id + ". Use the tools to check the order and the refund rules first.")
# --- resources end ---


# ---------------------------------------------------------------------------
# One more tool, only when SHOP_EXTRA_TOOLS=1. It shows that a server can GROW and clients that ask "what tools do
# you have?" simply find the new one, with no change in their own code.
# ---------------------------------------------------------------------------
if os.getenv("SHOP_EXTRA_TOOLS") == "1":

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    def get_store_hours() -> str:
        """The opening hours of the shop's phone support line."""
        return "Phone support is open Monday to Friday, 9:00 to 17:00."


if __name__ == "__main__":
    mcp.run(transport="stdio")
