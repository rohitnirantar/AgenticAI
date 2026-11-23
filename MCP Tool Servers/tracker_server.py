"""
tracker_server.py - a THIRD-PARTY MCP server: a carrier's parcel tracker (the honest version)

Imagine the shop's courier publishes this server, and we want to plug it into our desk so customers can ask
"where is my parcel?". We did not write it, and we do not control it. Notebook 04 compares it with evil_server.py,
which offers the same tool with a poisoned description.
"""

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

mcp = MCPServer("parcel-tracker")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def track_parcel(order_id: str) -> str:
    """Get the courier's tracking status of a parcel, by order id."""
    return "Parcel for order " + order_id.upper() + " is with the courier and should arrive within 2 days."


if __name__ == "__main__":
    mcp.run(transport="stdio")
