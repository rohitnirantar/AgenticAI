"""
mcp_desk.py - the support desk, with its tools served over MCP

The real-life scenario: the same online shop and the same kinds of emails, but the desk contains NO tool code and NO tool
descriptions. At start-up it launches two MCP servers and asks each one what tools it has:
  shop_server.py     : our own server (orders, refunds, policies). We wrote it, so we trust it.
  tracker_server.py  : the courier's parcel tracker. We did NOT write it, so it goes through a security gate first
                       (an allowlist, a review of its description, and a pinned fingerprint). See mcp_security.py.

Run it, in the main environment, from the repo root or from this folder:
    python "MCP Tool Servers/vet_server.py" tracker_server.py --pin parcel    once: approve the third-party server
    python "MCP Tool Servers/mcp_desk.py"                                     the morning's emails
    python "MCP Tool Servers/mcp_desk.py" --extra                             the server offers one more tool: the desk finds it
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

import mcp_security
from toolbox import Toolbox

load_dotenv()  # read OPENAI_API_KEY from the .env file
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Add OPENAI_API_KEY to your .env file (see .env.example)")

client = OpenAI(timeout=30.0, max_retries=2)
MODEL = "gpt-4o-mini"
PINS_FILE = Path(__file__).parent / "approved_tools.json"

INSTRUCTIONS = (
    "You are a customer support agent at an online shop. Use the tools you have to look up orders, check and issue refunds, "
    "search the shop's policies and track parcels. Never say a refund is issued unless a tool says so. "
    "If a tool says a refund waits for a person, say so plainly. Answer in at most 3 short sentences."
)

INBOX = [
    "Hi, where is my order A1002?",
    "How much does express shipping cost?",
    "The left earbud on my headphones (order A1001) stopped working. Please refund it.",
    "Please refund my 4K television, order A1004. I changed my mind.",
    "I bought a coffee grinder (order A1003) a while ago and it broke. Please refund it.",
]


# --- answer start ---
async def answer(email, box, max_steps=6, verbose=False):
    """The agent loop from Module 02, with ONE change: the tools come from the toolbox, not from our own code."""
    messages = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": email},
    ]
    tools = box.openai_tools()      # discovered from the servers a moment ago

    for step in range(max_steps):
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=tools, temperature=0)
        reply = response.choices[0].message
        messages.append(reply)

        if not reply.tool_calls:
            return reply.content

        for tool_call in reply.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            if verbose:
                print("    tool: " + name + "(" + str(args) + ")")
            result = await box.call(name, args)      # forwarded to whichever server offers this tool
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    return "Stopped: too many steps."
# --- answer end ---


async def run_desk(extra):
    extra_env = None
    if extra:
        extra_env = {"SHOP_EXTRA_TOOLS": "1"}

    # The gate protects us from third-party servers. We only allow the tool we expect, and only if its fingerprint is approved.
    gate = mcp_security.Gate(
        allowed_tools={"parcel": ["track_parcel"]},
        pins=mcp_security.load_pins(PINS_FILE),
    )

    async with Toolbox(gate) as box:
        await box.add_server("shop", "shop_server.py", extra_env, trusted=True)
        await box.add_server("parcel", "tracker_server.py")

        print("Tools the desk discovered (the desk has no tool code of its own):")
        for tool in box.tools:
            print("   " + tool.name.ljust(26) + "from the '" + box.owner[tool.name] + "' server")
        for problem in box.rejected:
            print("   " + problem)
        print()

        emails = list(INBOX)
        if extra:
            emails.append("What are your phone support hours?")

        for email in emails:
            print("Customer: " + email)
            reply = await answer(email, box, verbose=True)
            print("Desk    : " + reply.replace("\n", " ") + "\n")

        print("What the shop server recorded:", await box.call("list_refunds", {}))
        print("Calls made through the toolbox:", len(box.calls))


def main():
    if hasattr(sys.stdout, "reconfigure"):      # (a notebook's output has no reconfigure)
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run_desk("--extra" in sys.argv))


if __name__ == "__main__":
    main()
