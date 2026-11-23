"""
tools.py - the shop's tools, written ONCE and used by every framework

These are plain Python functions. Each framework turns them into tools in its own way
(function_tool, a LangChain tool, a CrewAI tool). Three things happen inside every tool, whatever the framework:

  1. The REFUND LIMIT applies. issue_refund is the guarded version from Module 05: a refund above $100 is not
     issued, it waits for a human. A framework cannot get around it, because the rule lives in the tool.
  2. The result goes into the EVIDENCE log, so the output guard can later check the reply against what the tools said.
  3. The call is recorded as a SPAN in the request's trace, so every framework shows its tool calls in the same way.

This is the lesson of the capstone in one file: keep your business rules in plain functions, outside the framework.
"""

import observe
import shop
import guards

ESCALATION = {"reason": ""}  # filled in when an agent decides that a person must handle the email


# --- tools start ---


def lookup_order(order_id: str) -> str:
    """Get the details of one order: item, price, status and delivery date."""
    with observe.span("tool:lookup_order", kind="tool", order_id=order_id):
        result = shop.lookup_order(order_id)
    shop.TOOL_RESULTS.append(result)
    return result


def check_refund_eligibility(order_id: str) -> str:
    """Check whether an order can be refunded under the shop's policy."""
    with observe.span("tool:check_refund_eligibility", kind="tool", order_id=order_id):
        result = shop.check_refund_eligibility(order_id)
    shop.TOOL_RESULTS.append(result)
    return result


def issue_refund(order_id: str) -> str:
    """Issue a refund for an order. Only use this after the order is confirmed eligible.
    A refund above the automatic limit is not issued: it is sent to a human for approval."""
    with observe.span("tool:issue_refund", kind="tool", order_id=order_id):
        result = guards.issue_refund_guarded(order_id)  # the Module 05 refund limit
    shop.TOOL_RESULTS.append(result)
    return result


def search_policies(question: str) -> str:
    """Search the shop's policies (refunds, shipping, warranty, payments). Ask about one topic at a time."""
    with observe.span("tool:search_policies", kind="tool", question=question):
        result = shop.search_policies(question)
    shop.TOOL_RESULTS.append(result)
    return result


def escalate_to_human(reason: str) -> str:
    """Hand the email to a person. Use it for angry customers, legal threats, or anything the shop's team must answer."""
    with observe.span("tool:escalate_to_human", kind="tool", reason=reason):
        ESCALATION["reason"] = reason
    return "A person has been notified and will answer this email."
# --- tools end ---
