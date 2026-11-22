"""
shop_tools.py - the shop's data and tools, shared by every framework in this module

This is the same shop as Modules 02 to 05: the orders, the refund rules and the policy search.
The tools are PLAIN Python functions. Notice what is missing compared with Module 05:
there are no hand-written tool descriptions (the JSON "make_tool" blocks) and no agent loop.
Each framework builds those for us from the function name, its docstring and its type hints.
That is one of the main things a framework gives you.
"""

import os
import re
import json
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
load_dotenv()  # read OPENAI_API_KEY from the .env file (the frameworks read it from there too)
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Add OPENAI_API_KEY to your .env file (see .env.example)")

client = OpenAI()
MODEL = "gpt-4o-mini"                       # every framework in this module uses the same model
EMBEDDING_MODEL = "text-embedding-3-small"

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge_base"  # the shop's policy files


# ---------------------------------------------------------------------------
# The shop's order data (made up). In a real company this would be a database.
# ---------------------------------------------------------------------------
def days_ago(n):
    """A date n days before today, so the sample data stays valid whenever you run this."""
    return (date.today() - timedelta(days=n)).isoformat()


ORDERS = {
    "A1001": {"item": "Wireless headphones", "price": 79.00, "status": "delivered", "delivered_on": days_ago(18)},
    "A1002": {"item": "Running shoes", "price": 120.00, "status": "in_transit", "expected_delivery": days_ago(-4)},
    "A1003": {"item": "Coffee grinder", "price": 45.00, "status": "delivered", "delivered_on": days_ago(80)},
    "A1004": {"item": "4K television", "price": 250.00, "status": "delivered", "delivered_on": days_ago(5)},
}

REFUND_WINDOW_DAYS = 30  # shop policy: refunds only within 30 days of delivery
REFUNDS = []             # refund requests recorded by the agents
TOOL_CALLS = []          # a log of every tool that ran, so we can compare the frameworks


def reset_shop():
    """Clear the refunds and the tool log, so every test starts fresh."""
    REFUNDS.clear()
    TOOL_CALLS.clear()


# ---------------------------------------------------------------------------
# Tool 1: look up an order
# The docstring is what the model reads to decide when to use the tool.
# ---------------------------------------------------------------------------
def lookup_order(order_id: str) -> str:
    """Get the details of one order: item, price, status and delivery date."""
    TOOL_CALLS.append("lookup_order")
    order = ORDERS.get(order_id.strip().upper())
    if order is None:
        return "No order found with id " + order_id + "."

    details = dict(order)  # a copy, so we do not change the shop's data
    if order["status"] == "delivered":
        delivered = date.fromisoformat(order["delivered_on"])
        details["days_since_delivery"] = (date.today() - delivered).days
    return json.dumps(details)


# ---------------------------------------------------------------------------
# Tools 2 and 3: the refund rules
# ---------------------------------------------------------------------------
def refund_check(order_id):
    """Apply the refund policy. Returns (is_allowed, explanation)."""
    order = ORDERS.get(order_id.strip().upper())
    if order is None:
        return False, "No order found with id " + order_id + "."
    if order["status"] != "delivered":
        return False, "Not eligible: the order has not been delivered yet."

    days = (date.today() - date.fromisoformat(order["delivered_on"])).days
    if days > REFUND_WINDOW_DAYS:
        return False, "Not eligible: delivered " + str(days) + " days ago, the refund window is " + str(REFUND_WINDOW_DAYS) + " days."
    return True, "Eligible: delivered " + str(days) + " days ago, within the " + str(REFUND_WINDOW_DAYS) + " day window."


def check_refund_eligibility(order_id: str) -> str:
    """Check whether an order can be refunded under the shop's policy."""
    TOOL_CALLS.append("check_refund_eligibility")
    allowed, explanation = refund_check(order_id)
    return explanation


def issue_refund(order_id: str) -> str:
    """Issue a refund for an order. Only use this after the order is confirmed eligible."""
    TOOL_CALLS.append("issue_refund")
    # The model can make mistakes, so this tool checks the rules AGAIN before acting.
    allowed, explanation = refund_check(order_id)
    if not allowed:
        return "Refund refused. " + explanation

    # Never refund the same order twice.
    for refund in REFUNDS:
        if refund["order_id"] == order_id.strip().upper():
            return "A refund for order " + order_id + " was already issued."

    order = ORDERS[order_id.strip().upper()]
    REFUNDS.append({"order_id": order_id.strip().upper(), "amount": order["price"]})
    return "Refund of $" + format(order["price"], ".2f") + " issued for order " + order_id + "."


# ---------------------------------------------------------------------------
# Tool 4: search the shop's policies (Module 03). The first search prepares the index.
# ---------------------------------------------------------------------------
chunks = []         # the policy paragraphs
chunk_vectors = []  # one embedding vector per paragraph


def embed(texts):
    """Turn a list of texts into a list of vectors."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    vectors = []
    for item in response.data:
        vectors.append(item.embedding)
    return vectors


def similarity(vector_a, vector_b):
    """Higher = closer in meaning. (OpenAI vectors have length 1, so multiplying and adding is enough.)"""
    total = 0
    for index in range(len(vector_a)):
        total = total + vector_a[index] * vector_b[index]
    return total


def build_index():
    """Read the policy files and embed every paragraph. Only runs the first time."""
    if len(chunks) > 0:
        return

    for file in sorted(KNOWLEDGE_DIR.glob("*.txt")):
        text = file.read_text(encoding="utf-8")
        for paragraph in re.split(r"\n\s*\n", text):  # a blank line separates paragraphs
            if paragraph.strip() != "":
                chunks.append({"source": file.name, "text": paragraph.strip()})

    texts = []
    for chunk in chunks:
        texts.append(chunk["text"])
    for vector in embed(texts):
        chunk_vectors.append(vector)


def search_policies(question: str) -> str:
    """Search the shop's policies (refunds, shipping, warranty, payments). Ask about one topic at a time."""
    TOOL_CALLS.append("search_policies")
    build_index()
    question_vector = embed([question])[0]

    # Score every paragraph against the question
    scored = []
    for index in range(len(chunks)):
        score = similarity(question_vector, chunk_vectors[index])
        scored.append((score, index))
    scored.sort(reverse=True)  # best match first

    # Return the best 5 as text
    lines = []
    for score, index in scored[:5]:
        chunk = chunks[index]
        lines.append("[" + chunk["source"] + "] " + chunk["text"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# What every specialist is told. Each framework version uses these same words,
# so any difference in the results comes from the framework and not from the prompt.
# ---------------------------------------------------------------------------
ORDERS_INSTRUCTIONS = (
    "You are the Orders specialist at an online shop. "
    "Answer questions about a customer's order using the lookup_order tool. "
    "Keep the reply to 2 short sentences."
)

POLICY_INSTRUCTIONS = (
    "You are the Policy specialist at an online shop. "
    "Answer questions about shop rules ONLY from the results of the search_policies tool. "
    "If the answer is not there, say you don't know. "
    "Keep the reply to 2 short sentences."
)

REFUNDS_INSTRUCTIONS = (
    "You are the Refunds specialist at an online shop. "
    "First use check_refund_eligibility. Only if the order is eligible, use issue_refund. "
    "Then tell the customer what happened. Never promise a refund that was not issued. "
    "Keep the reply to 2 short sentences."
)
