"""
agents_sdk_mcp.py - the SAME MCP server, used by a DIFFERENT framework (the OpenAI Agents SDK)

In mcp_desk.py we wrote the agent loop ourselves and used the tools through our own small client (toolbox.py).
Here the OpenAI Agents SDK does everything: it starts the server, discovers the tools, shows them to the model and
forwards the calls. We write NO tool code and NO client code. The server is exactly the same file.

That is the whole promise of MCP: write the tools once, and every MCP-speaking app can use them.

    python "MCP Tool Servers/agents_sdk_mcp.py"
"""

import asyncio
import os
import sys
from pathlib import Path

from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv

load_dotenv()  # read OPENAI_API_KEY from the .env file
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Add OPENAI_API_KEY to your .env file (see .env.example)")

SERVER = str(Path(__file__).parent / "shop_server.py")

EMAILS = [
    "Hi, where is my order A1002?",
    "The left earbud on my headphones (order A1001) stopped working. Please refund it.",
    "Please refund my 4K television, order A1004. I changed my mind.",
]


async def main():
    if hasattr(sys.stdout, "reconfigure"):      # (a notebook's output has no reconfigure)
        sys.stdout.reconfigure(encoding="utf-8")

    # One line starts the server and connects to it. The SDK discovers its tools by itself.
    async with MCPServerStdio(params={"command": sys.executable, "args": [SERVER]}, cache_tools_list=True) as server:
        agent = Agent(
            name="Support agent",
            instructions=("You are a customer support agent at an online shop. Use your tools. "
                          "Never say a refund is issued unless a tool says so. Answer in at most 3 short sentences."),
            mcp_servers=[server],
            model="gpt-4o-mini",
        )

        tools = await server.list_tools()
        names = []
        for tool in tools:
            names.append(tool.name)
        print("Tools the Agents SDK discovered: " + ", ".join(names) + "\n")

        for email in EMAILS:
            result = await Runner.run(agent, email)
            print("Customer: " + email)
            print("Desk    : " + result.final_output.replace("\n", " ") + "\n")


if __name__ == "__main__":
    asyncio.run(main())
