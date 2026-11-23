"""
toolbox.py - the CLIENT side: connect an agent to one or more MCP servers

An agent app that speaks MCP does three things:
  1. START a server and connect to it (here: as a child process, over stdio)
  2. ASK it "what tools do you have?"  (list_tools)  and show them to the model
  3. When the model picks a tool, FORWARD the call to the right server (call_tool) and hand back the result

The app does NOT contain a single tool description. It discovers them. Add a tool to the server, and the agent has it.

Use it like this (everything inside ONE 'async with', because connections are tied to the task that opened them):

    async with Toolbox() as box:
        await box.add_server("shop", "shop_server.py")
        tools_for_the_model = box.openai_tools()
        result = await box.call("lookup_order", {"order_id": "A1001"})
"""

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import Client, StdioServerParameters, stdio_client

HERE = Path(__file__).parent


def run_sync(function, *arguments):
    """Run an async function from ordinary code and return its result. The notebooks use this.

    Starting a server means starting a child process. On Windows, Jupyter's own event loop cannot do that, so we run the
    function in a fresh thread with a loop that can. In a normal script you would simply write asyncio.run(function())."""
    def worker():
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()     # the Windows loop that can start child processes
        else:
            loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(function(*arguments))
        finally:
            loop.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(worker).result()


def server_params(script, extra_env=None):
    """How to start a server: run 'python <script>' as a child process."""
    return StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / script)],
        env=extra_env,    # extra environment variables for the server (they are added to a safe default set)
    )


def open_client(script, extra_env=None):
    """Connect to a server that we start ourselves as a child process (the stdio transport).

    The server's own error messages (its stderr) go to the real terminal. We pass that explicitly, because inside a
    notebook the usual stderr is not a real file and cannot be handed to a child process."""
    errlog = sys.__stderr__
    if errlog is None:
        errlog = open(os.devnull, "w")
    return Client(stdio_client(server_params(script, extra_env), errlog=errlog))


def text_of(result):
    """The text parts of a tool result, joined."""
    parts = []
    for item in result.content:
        if item.type == "text":
            parts.append(item.text)
    return "\n".join(parts)


# --- toolbox start ---
class Toolbox:
    def __init__(self, gate=None):
        self.stack = AsyncExitStack()   # closes every connection when we leave the 'async with'
        self.gate = gate                # an optional security check (see mcp_security.py)
        self.clients = {}               # server name -> its connected client
        self.owner = {}                 # tool name -> the name of the server that offers it
        self.tools = []                 # the tools we show to the model
        self.rejected = []              # tools we refused to show, with the reason
        self.calls = []                 # every call that was made: (server, tool, arguments)

    async def __aenter__(self):
        return self

    async def __aexit__(self, error_type, error, traceback):
        await self.stack.aclose()

    async def add_server(self, name, script, extra_env=None, trusted=False):
        """Start a server, ask what tools it offers, and keep the ones that pass the gate.
        A TRUSTED server is one we wrote and control (like our own shop server): its tools skip the gate."""
        client = await self.stack.enter_async_context(open_client(script, extra_env))
        self.clients[name] = client

        listed = await client.list_tools()
        offered = listed.tools
        if self.gate is not None and not trusted:
            offered, problems = self.gate.filter(name, listed.tools)
            for problem in problems:
                self.rejected.append(problem)

        for tool in offered:
            if tool.name in self.owner:
                self.rejected.append(name + "/" + tool.name + ": REJECTED, another server already offers a tool with this name")
                continue
            self.owner[tool.name] = name
            self.tools.append(tool)
            if trusted and self.gate is not None:
                # remember the names of OUR tools: a third-party description that mentions them is trying to steer them
                self.gate.known_tool_names = list(self.gate.known_tool_names) + [tool.name]
        return offered

    def openai_tools(self):
        """The tools in the format the OpenAI chat API wants. The MCP input schema is already JSON Schema, so we reuse it."""
        converted = []
        for tool in self.tools:
            converted.append({
                "type": "function",
                "function": {"name": tool.name, "description": tool.description, "parameters": tool.input_schema},
            })
        return converted

    async def call(self, tool_name, arguments):
        """Forward a tool call to the server that owns the tool. Returns the result as text."""
        if tool_name not in self.owner:
            return "Unknown tool: " + tool_name

        server = self.owner[tool_name]
        if self.gate is not None:
            allowed, reason = self.gate.allow_call(server, tool_name, arguments)
            if not allowed:
                self.calls.append((server, tool_name, arguments, "BLOCKED"))
                return "Blocked: " + reason

        result = await self.clients[server].call_tool(tool_name, arguments)
        text = text_of(result)
        outcome = "ok"
        if result.is_error:
            outcome = "error"
        self.calls.append((server, tool_name, arguments, outcome))
        return text
# --- toolbox end ---
