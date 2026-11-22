"""
agents_sdk_desk.py - the support desk built with the OpenAI Agents SDK (a complete, runnable example)

The SDK gives us the agent loop (Runner), the tool descriptions (function_tool) and
the routing (handoffs). Compare the size of this file with plain_desk.py.

This one file is the whole story: it builds the desk, then runs a morning inbox of five customer emails
through it and checks every outcome in the shop's data (was a refund really created?).

Run it from the repo root or from this folder, using the module's own environment (see requirements.txt):
    python "Agent Frameworks/agents_sdk_desk.py"
"""

import sys
import time

from agents import Agent, Runner, function_tool, set_tracing_disabled

import shop_tools as shop
import compare  # only for the inbox of test emails and the check of each result

# The SDK can send traces of every run to your OpenAI dashboard. We switch that off here to keep
# the module simple. To see traces at https://platform.openai.com/traces, remove this line.
set_tracing_disabled(True)

# --- desk start ---
# A tool is just our plain function wrapped with function_tool. The SDK reads the name, the docstring
# and the type hints and builds the tool description for us.
orders_agent = Agent(
    name="Orders agent",
    instructions=shop.ORDERS_INSTRUCTIONS,
    tools=[function_tool(shop.lookup_order)],
    model=shop.MODEL,
    handoff_description="Questions about where an order is or what is in it",  # what the triage agent reads
)

policy_agent = Agent(
    name="Policy agent",
    instructions=shop.POLICY_INSTRUCTIONS,
    tools=[function_tool(shop.search_policies)],
    model=shop.MODEL,
    handoff_description="Questions about shop rules: shipping, warranty, payments",
)

refunds_agent = Agent(
    name="Refunds agent",
    instructions=shop.REFUNDS_INSTRUCTIONS,
    tools=[function_tool(shop.check_refund_eligibility), function_tool(shop.issue_refund)],
    model=shop.MODEL,
    handoff_description="Customers who want their money back",
)

# The triage agent does not answer. It hands the customer over to the right specialist.
triage_agent = Agent(
    name="Triage agent",
    instructions="Send the customer's email to the right specialist. Do not answer it yourself.",
    handoffs=[orders_agent, policy_agent, refunds_agent],
    model=shop.MODEL,
)
# --- desk end ---


def handle_email(email):
    """Handle one customer email from start to finish."""
    shop.reset_shop()
    started = time.time()

    result = Runner.run_sync(triage_agent, email)  # runs the whole loop, including the handoff

    # The agent that gave the final answer tells us which specialist handled the email
    specialist = result.last_agent.name.replace(" agent", "").lower()

    return {
        "specialist": specialist,
        "reply": result.final_output,
        "refunds": list(shop.REFUNDS),
        "tool_calls": list(shop.TOOL_CALLS),
        "tokens": result.context_wrapper.usage.total_tokens,
        "seconds": time.time() - started,
    }


def main():
    """The real-life flow: a morning inbox goes through the desk, and every outcome is checked."""
    sys.stdout.reconfigure(encoding="utf-8")  # so output with special characters prints correctly on Windows
    print("=== OpenAI Agents SDK desk: " + str(len(compare.INBOX)) + " emails ===")

    passed = 0
    total_tokens = 0

    for case in compare.INBOX:
        result = handle_email(case["email"])
        problems = compare.check_result(case, result)  # compare the outcome with what we expected

        status = "ok"
        if len(problems) > 0:
            status = "FAILED"
        else:
            passed = passed + 1
        total_tokens = total_tokens + result["tokens"]

        print("\n[" + status + "] " + case["name"])
        print("  Email:      " + case["email"])
        print("  Handled by: " + result["specialist"] + " (tools: " + ", ".join(result["tool_calls"]) + ")")
        print("  Reply:      " + result["reply"].replace("\n", " "))
        print("  Cost:       " + str(result["tokens"]) + " tokens, " + format(result["seconds"], ".1f") + " seconds")
        for problem in problems:
            print("  PROBLEM:    " + problem)

    print("\nCorrect: " + str(passed) + "/" + str(len(compare.INBOX))
          + ", average tokens per email: " + str(round(total_tokens / len(compare.INBOX))))


if __name__ == "__main__":
    main()
