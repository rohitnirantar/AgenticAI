"""
prompts.py - the words every engine is given

All four desks (plain Python, OpenAI Agents SDK, LangGraph, CrewAI) get EXACTLY the same instructions.
That way, any difference in the results comes from the framework and not from the prompt.
They are taken from the agents we already built in Modules 04 and 05, so nothing here is new.
"""

import shop
import desk

ORDERS = shop.ORDERS_INSTRUCTIONS   # answers questions about an order (tool: lookup_order)
POLICY = shop.POLICY_INSTRUCTIONS   # answers questions about shop rules (tool: search_policies)
REFUND = desk.REFUND_INSTRUCTIONS   # handles refund requests (tools: lookup_order, check_refund_eligibility, issue_refund)

# How an email is routed. "human" is the way out for anything the desk should not answer itself.
ROUTING = desk.ROUTING_RULES
