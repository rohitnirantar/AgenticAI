"""
capstone_sdk.py - the guarded, observable support desk with the OpenAI Agents SDK (one complete, runnable file)

The framework-specific part is only here: a triage agent that hands emails to three specialists, plus a small
class that reports every model call into our traces. Everything around it is shared by all engines:
the guardrails (pipeline.py), the tools with the refund limit (tools.py), and the scenario that is run (scenario.py).

Run it end to end, in the Module 06 environment (venv-frameworks), from the repo root or from this folder:
    python "Capstone Project/capstone_sdk.py"            (the morning scenario, all guardrails on)
    python "Capstone Project/capstone_sdk.py" --evals    (and then the 9-case eval suite)
"""

import sys
import time

from agents import Agent, Runner, RunHooks, function_tool, set_tracing_disabled

import observe
import prompts
import scenario
import shop
import tools

NAME = "sdk"

# The SDK can also send its traces to your OpenAI dashboard (see Module 07). We keep our own traces instead.
set_tracing_disabled(True)


# --- observe start ---
class ObserveHooks(RunHooks):
    """The SDK calls these methods around EVERY model call it makes. We turn each call into a span in our trace.
    This is how you make an Agents SDK run show up in the same traces, with the same costs, as everything else."""

    def __init__(self):
        self.started = time.time()

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        self.started = time.time()

    async def on_llm_end(self, context, agent, response):
        usage = response.usage
        observe.record_model_call("sdk:" + shop.MODEL, shop.MODEL, usage.input_tokens, usage.output_tokens,
                                  time.time() - self.started, agent=agent.name)
# --- observe end ---


# --- desk start ---
# Our shared plain functions become tools with function_tool: the SDK builds the description from the
# function's name, docstring and type hints. The refund limit and the evidence log are inside the functions.
orders_agent = Agent(
    name="Orders agent",
    instructions=prompts.ORDERS,
    tools=[function_tool(tools.lookup_order)],
    model=shop.MODEL,
    handoff_description="Questions about where an order is or what it contains",
)

policy_agent = Agent(
    name="Policy agent",
    instructions=prompts.POLICY,
    tools=[function_tool(tools.search_policies)],
    model=shop.MODEL,
    handoff_description="Questions about how the shop works: shipping, returns, warranty, payments",
)

refund_agent = Agent(
    name="Refund agent",
    instructions=prompts.REFUND,
    tools=[function_tool(tools.lookup_order), function_tool(tools.check_refund_eligibility),
           function_tool(tools.issue_refund)],
    model=shop.MODEL,
    handoff_description="Customers who ask for a refund or their money back",
)

# The triage agent routes. It does not answer. For anything a person should handle it uses the escalate tool.
triage_agent = Agent(
    name="Triage agent",
    instructions=prompts.ROUTING + "\nHand the email to the right specialist and do not answer it yourself. "
                                   "For the 'human' case, use the escalate_to_human tool instead.",
    tools=[function_tool(tools.escalate_to_human)],
    handoffs=[orders_agent, policy_agent, refund_agent],
    model=shop.MODEL,
)


def run(email):
    """The engine: run the triage agent. max_turns is the SDK's own step limit (our budget against loops)."""
    result = Runner.run_sync(triage_agent, email, hooks=ObserveHooks(), max_turns=8)

    if tools.ESCALATION["reason"] != "":
        return {"route": "human", "reply": ""}

    route = result.last_agent.name.replace(" agent", "").lower()   # orders, policy or refund
    return {"route": route, "reply": result.final_output}
# --- desk end ---


if __name__ == "__main__":
    scenario.main(sys.modules[__name__])
