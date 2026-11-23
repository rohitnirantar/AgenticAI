"""
vet_server.py - look at an MCP server BEFORE you plug it into an agent

The real-life scenario: someone on the team says "let's add this MCP server". Before it goes anywhere near the
desk, you run this. It starts the server, lists every tool exactly as the model would see it, runs the review
from mcp_security.py, and prints a fingerprint for each tool. If you are happy, --pin saves the fingerprints, so
that a later change to any tool is noticed.

    python "MCP Tool Servers/vet_server.py" tracker_server.py                    look, and review
    python "MCP Tool Servers/vet_server.py" tracker_server.py --pin parcel       approve it: save its fingerprints
    python "MCP Tool Servers/vet_server.py" evil_server.py                       see what a poisoned server looks like

The fingerprints are saved in approved_tools.json next to this file.
"""

import asyncio
import sys
from pathlib import Path

from mcp import Client

import mcp_security
import toolbox

PINS_FILE = Path(__file__).parent / "approved_tools.json"


async def vet(script, pin_name):
    async with Client(toolbox.server_params(script)) as client:
        listed = await client.list_tools()

        pins = mcp_security.load_pins(PINS_FILE)
        for tool in listed.tools:
            print("TOOL: " + tool.name)
            print("   description the model will read:")
            for line in tool.description.splitlines():
                print("      | " + line)
            print("   fingerprint: " + mcp_security.fingerprint(tool))

            warnings = mcp_security.review_tool(tool, ["issue_refund", "lookup_order", "check_refund_eligibility"])
            if len(warnings) == 0:
                print("   review: nothing suspicious")
            for warning in warnings:
                print("   REVIEW WARNING: " + warning)

            if pin_name is not None and len(warnings) == 0:
                pins[pin_name + "/" + tool.name] = mcp_security.fingerprint(tool)
                print("   -> pinned as " + pin_name + "/" + tool.name)
            print()

        if pin_name is not None:
            mcp_security.save_pins(PINS_FILE, pins)
            print("Saved to " + PINS_FILE.name)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    pin_name = None
    if "--pin" in sys.argv:
        pin_name = sys.argv[sys.argv.index("--pin") + 1]
    asyncio.run(vet(sys.argv[1], pin_name))


if __name__ == "__main__":
    main()
