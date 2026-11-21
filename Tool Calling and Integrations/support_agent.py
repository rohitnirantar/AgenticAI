"""
support_agent.py - a real-life example: a customer support assistant

An online shop receives customer emails. This script handles each email end to end,
using everything from Module 02:

  Step 1  Structured output : read the email and turn it into a "ticket" (data, not text)
  Step 2  Routing           : plain Python decides what to do with the ticket
  Step 3  Tools + agent loop: the assistant looks up the order, checks the refund rules,
                              issues a refund if allowed, and writes a reply

The shop's data is made up and lives in this file, so the only thing you need is your
OpenAI key. Nothing real is refunded: the refund tool only records a request.

Run from the repo root or from this folder:
    python "Tool Calling and Integrations/support_agent.py"

Or try your own email:
    python support_agent.py "Hi, order A1001 arrived broken, I want a refund"
"""

import os
import sys
import json
from datetime import date, timedelta
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
sys.stdout.reconfigure(encoding="utf-8")  # so replies with curly quotes etc. print correctly on Windows

load_dotenv()  # read OPENAI_API_KEY from the .env file
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Add OPENAI_API_KEY to your .env file (see .env.example)")

client = OpenAI()
MODEL = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# The shop's data (made up). In a real company this would be a database.
# ---------------------------------------------------------------------------
def days_ago(n):
    """A date n days before today, so the sample data stays valid whenever you run this."""
    return (date.today() - timedelta(days=n)).isoformat()


ORDERS = {
    "A1001": {"customer": "Priya", "item": "Wireless headphones", "price": 79.00,
              "status": "delivered", "delivered_on": days_ago(18)},
    "A1002": {"customer": "Rahul", "item": "Running shoes", "price": 120.00,
              "status": "in_transit", "expected_delivery": days_ago(-4)},   # 4 days from now
    "A1003": {"customer": "Meera", "item": "Coffee grinder", "price": 45.00,
              "status": "delivered", "delivered_on": days_ago(80)},
}

REFUND_WINDOW_DAYS = 30   # shop policy: refunds only within 30 days of delivery
REFUNDS = []              # refund requests recorded by the assistant


# ---------------------------------------------------------------------------
# Step 1: Structured output. Describe the shape of a ticket and let the model fill it in.
# ---------------------------------------------------------------------------
class Ticket(BaseModel):
    issue_type: Literal["refund_request", "delivery_question", "other"]  # only these 3 values allowed
    order_id: str      # for example "A1001", or "" if the customer gave no order number
    is_urgent: bool    # does the customer sound upset or in a hurry?


def create_ticket(email):
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Read the customer email and fill in the support ticket."},
            {"role": "user", "content": email},
        ],
        response_format=Ticket,  # the shape we want back
    )
    return response.choices[0].message.parsed  # a Ticket object, not text


# ---------------------------------------------------------------------------
# Step 3 (part 1): The tools. Small, safe functions the assistant can ask us to run.
# ---------------------------------------------------------------------------
def find_order(order_id):
    return ORDERS.get(order_id.strip().upper())


def lookup_order(order_id):
    """Return the details of an order."""
    order = find_order(order_id)
    if order is None:
        return f"No order found with id {order_id}."
    return json.dumps(order)


def refund_check(order_id):
    """Apply the refund policy. Returns (is_allowed, explanation)."""
    order = find_order(order_id)
    if order is None:
        return False, f"No order found with id {order_id}."
    if order["status"] != "delivered":
        return False, "Not eligible: the order has not been delivered yet."

    days = (date.today() - date.fromisoformat(order["delivered_on"])).days
    if days > REFUND_WINDOW_DAYS:
        return False, f"Not eligible: delivered {days} days ago, the refund window is {REFUND_WINDOW_DAYS} days."
    return True, f"Eligible: delivered {days} days ago, within the {REFUND_WINDOW_DAYS} day window."


def check_refund_eligibility(order_id):
    """Tell the assistant whether an order can be refunded."""
    return refund_check(order_id)[1]


def issue_refund(order_id):
    """Record a refund request."""
    # The model can make mistakes, so this tool checks the rules AGAIN before acting.
    allowed, explanation = refund_check(order_id)
    if not allowed:
        return "Refund refused. " + explanation

    order = find_order(order_id)
    REFUNDS.append({"order_id": order_id.strip().upper(), "amount": order["price"]})
    return f"Refund of ${order['price']:.2f} recorded for order {order_id}."


def make_tool(name, description):
    """Describe a tool to the model. All three of our tools take just an order id."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "The order id, for example A1001"}},
                "required": ["order_id"],
            },
        },
    }


# The model reads these descriptions to decide which tool to use, so write them clearly.
tools = [
    make_tool("lookup_order", "Get the details of an order: item, price, delivery status and dates."),
    make_tool("check_refund_eligibility", "Check whether an order can be refunded under the shop's policy."),
    make_tool("issue_refund", "Issue a refund for an order. Only use this after the order is confirmed eligible."),
]

available_tools = {
    "lookup_order": lookup_order,
    "check_refund_eligibility": check_refund_eligibility,
    "issue_refund": issue_refund,
}


def run_tool(name, args):
    """Run the tool the model asked for and return the result as text."""
    if name not in available_tools:
        return f"Unknown tool: {name}"
    try:
        return str(available_tools[name](**args))
    except Exception as error:  # if a tool breaks, tell the model instead of crashing
        return f"The tool failed: {error}"


# ---------------------------------------------------------------------------
# Step 3 (part 2): The agent loop. Ask the model, run the tools it asks for, repeat.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a friendly customer support assistant for an online shop.
Rules:
- Always look up the order before answering.
- Only issue a refund after check_refund_eligibility says the order is eligible.
- Only tell the customer a refund was made if issue_refund succeeded.
- If the order is not eligible or not delivered yet, explain why, politely.
- Write the reply to the customer in at most 3 short sentences and sign it 'Support Team'."""


def run_agent(email, ticket, max_steps=6):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Customer email:\n{email}\n\nTicket: {ticket.issue_type}, order {ticket.order_id}"},
    ]

    # max_steps is a safety limit: every lap costs money, so never loop forever
    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
        message = response.choices[0].message
        messages.append(message)

        # No tool requested? The assistant has written its reply, so we are done.
        if not message.tool_calls:
            return message.content

        # Run each requested tool and give the result back to the model
        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            result = run_tool(tool_call.function.name, args)
            print(f"    [step {step}] {tool_call.function.name}({args['order_id']}) -> {result}")

            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    return "Stopped: too many steps."


# ---------------------------------------------------------------------------
# Handle one email from start to finish
# ---------------------------------------------------------------------------
def handle_email(email):
    print(f'Email : "{email}"')

    # Step 1: email -> ticket (structured output)
    ticket = create_ticket(email)
    order_text = ticket.order_id
    if order_text == "":
        order_text = "(none)"  # the customer gave no order number
    print(f"Ticket: issue={ticket.issue_type}, order={order_text}, urgent={ticket.is_urgent}")

    # Step 2: routing. Plain Python decides, using the structured data.
    if ticket.issue_type == "other" or not ticket.order_id:
        print("Action: passed to a human agent (not an order question)\n")
        return

    # Step 3: the assistant resolves it with tools
    print("Action: assistant is working on it...")
    reply = run_agent(email, ticket)
    print(f"Reply : {reply}\n")


SAMPLE_EMAILS = [
    "Hi, the left earbud on my headphones (order A1001) stopped working. I would like my money back.",
    "Where is my order A1002? I need those running shoes for a race this weekend!",
    "I bought a coffee grinder (order A1003) a while ago and I want a refund please.",
    "Hello, do you sell gift cards?",
]


def main():
    # Use the email from the command line if one was given, otherwise run the samples
    if len(sys.argv) > 1:
        emails = [" ".join(sys.argv[1:])]
    else:
        emails = SAMPLE_EMAILS

    for number, email in enumerate(emails, start=1):
        print(f"===== Email {number} =====")
        handle_email(email)

    print("===== Refunds recorded in this run =====")
    if REFUNDS:
        print(REFUNDS)
    else:
        print("None")


if __name__ == "__main__":
    main()
