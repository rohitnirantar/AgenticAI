"""
mcp_security.py - a gate between your agent and MCP servers you do not fully control

MCP makes it easy to plug in someone else's tools. That is its strength and its risk. A tool's NAME and DESCRIPTION
are text that the model reads and trusts, and they come from the server. A malicious or hacked server can hide
instructions in them ("TOOL POISONING"). Four defences, all in this file, all plain code:

  1. REVIEW      : scan tool descriptions for text that tries to give the model orders
  2. ALLOWLIST   : a third-party server may only offer the tools we expect from it
  3. PINNING     : remember a fingerprint of every tool we approved, and refuse a tool that changed afterwards
                   (a "rug pull": a server that was fine yesterday and is hostile after an update)
  4. CALL RULES  : decide per call, in code, what may run (for example: no refunds while handling a tracking question)

None of these is perfect. They are layers. The strongest layer is the least obvious one: do not give a model tools it
does not need for the job (least privilege), because then there is nothing to abuse.
"""

import hashlib
import json
import re

# Phrases that a normal tool description has no reason to contain
SUSPICIOUS_PATTERNS = [
    r"ignore (all|any|your|previous|the previous)",
    r"do not (tell|mention|show|reveal|inform)",
    r"don't (tell|mention|show|reveal)",
    r"<important>",
    r"before (using|calling|you use) this tool",
    r"you must (also )?(first )?call",
    r"without (telling|asking|informing)",
    r"secretly",
    r"system prompt",
    r"instead of",
]
MAX_DESCRIPTION_LENGTH = 600   # a long description is a place to hide things


# --- review start ---
def review_tool(tool, known_tool_names=()):
    """Look for signs of tool poisoning in one tool. Returns a list of warnings (empty means nothing suspicious)."""
    warnings = []

    texts = [tool.description]
    for field in tool.input_schema.get("properties", {}).values():   # descriptions inside the inputs are read by the model too
        texts.append(str(field.get("description", "")))

    for text in texts:
        lowered = text.lower()
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, lowered):
                warnings.append("contains the phrase /" + pattern + "/")
        for other in known_tool_names:                       # a description that names ANOTHER tool is trying to steer it
            if other != tool.name and other in lowered:
                warnings.append("mentions another tool: " + other)

    if len(tool.description) > MAX_DESCRIPTION_LENGTH:
        warnings.append("the description is very long (" + str(len(tool.description)) + " characters)")
    return warnings
# --- review end ---


# --- pin start ---
def fingerprint(tool):
    """A short fingerprint of everything the model will read about a tool. If any of it changes, the fingerprint changes."""
    content = json.dumps({"name": tool.name, "description": tool.description, "schema": tool.input_schema}, sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_pins(path):
    """The approved fingerprints: {"server/tool": fingerprint}."""
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


def save_pins(path, pins):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(pins, file, indent=2)
# --- pin end ---


# --- gate start ---
class Gate:
    def __init__(self, allowed_tools=None, pins=None, known_tool_names=(), blocked_calls=(), review=True):
        self.allowed_tools = allowed_tools          # None = no allowlist. Otherwise: {server name: [tool names]}
        self.pins = pins                            # None = no pinning. Otherwise: {"server/tool": fingerprint}
        self.known_tool_names = known_tool_names    # names of our OWN tools, to spot descriptions that try to steer them
        self.blocked_calls = blocked_calls          # tool names that may not run in this session (least privilege)
        self.review = review                        # scan descriptions for poisoning (switch off only to test the other layers)

    def filter(self, server_name, tools):
        """Decide which of a server's tools the model may see. Returns (accepted tools, list of problems)."""
        accepted = []
        problems = []

        for tool in tools:
            label = server_name + "/" + tool.name

            if self.allowed_tools is not None:
                expected = self.allowed_tools.get(server_name, [])
                if tool.name not in expected:
                    problems.append(label + ": REJECTED, not on the allowlist for this server")
                    continue

            if self.pins is not None:
                pinned = self.pins.get(label)
                if pinned is None:
                    problems.append(label + ": REJECTED, this tool was never approved (no pin)")
                    continue
                if pinned != fingerprint(tool):
                    problems.append(label + ": REJECTED, the tool CHANGED since it was approved (possible rug pull)")
                    continue

            warnings = []
            if self.review:
                warnings = review_tool(tool, self.known_tool_names)
            if len(warnings) > 0:
                problems.append(label + ": REJECTED, suspicious description: " + "; ".join(warnings))
                continue

            accepted.append(tool)
        return accepted, problems

    def allow_call(self, server_name, tool_name, arguments):
        """Decide, at the moment of the call, whether it may run. Returns (allowed, reason)."""
        if tool_name in self.blocked_calls:
            return False, tool_name + " is not allowed in this session"
        return True, ""
# --- gate end ---
