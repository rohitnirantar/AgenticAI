"""
openai_traces_demo.py - see a run in OpenAI's own tracing dashboard (optional)

In this module we built tracing ourselves, in plain Python, so you can see how it works. OpenAI also offers
a tracing dashboard for your account. The OpenAI Agents SDK (Module 06) sends traces there automatically:
every model call, tool call and handoff, with timings. You look at them at https://platform.openai.com/traces

This script runs one small agent inside a trace and prints the link to open.

IMPORTANT: this is the one place in the module where data LEAVES your computer. The prompts and the tool results
are uploaded to your OpenAI account's trace dashboard. Our shop data is made up, so that is fine here. With real
customer data, think first: see the last section of notebook 03 and the 'trace_include_sensitive_data' option below.

It needs the Module 06 environment, because the Agents SDK is installed there:
    .\\venv-frameworks\\Scripts\\Activate.ps1
    python "Production and Observability/openai_traces_demo.py"
"""

import sys

from dotenv import load_dotenv

load_dotenv()  # the SDK reads OPENAI_API_KEY from the environment, and uses it to upload the traces too

from agents import Agent, RunConfig, Runner, function_tool, gen_trace_id, trace
from agents.tracing import get_trace_provider

import shop  # the shop's data and tools, from this folder

sys.stdout.reconfigure(encoding="utf-8")


# A tool for the agent. The type hints and the docstring tell the SDK how to describe it to the model.
@function_tool
def lookup_order(order_id: str) -> str:
    """Get the details of one order: item, price, status and delivery date."""
    return shop.lookup_order(order_id)


orders_agent = Agent(
    name="Orders agent",
    instructions="You are the Orders specialist at an online shop. Answer using the lookup_order tool, in 2 short sentences.",
    tools=[lookup_order],
    model="gpt-4o-mini",
)

# Set this to False to keep the PROMPTS and TOOL RESULTS out of the trace. You still see the timings and the steps.
# That is the safe choice for real customer data.
SEND_CONTENT = True


def main():
    trace_id = gen_trace_id()

    # Everything inside this block becomes ONE trace in the dashboard, with the name and the metadata below.
    with trace("Support desk: order question", trace_id=trace_id, metadata={"app": "support-desk", "module": "07"}):
        for email in ["Where is my order A1002?", "What did I pay for order A1001?"]:
            result = Runner.run_sync(orders_agent, email, run_config=RunConfig(trace_include_sensitive_data=SEND_CONTENT))
            print("Email: " + email)
            print("Reply: " + result.final_output + "\n")

    get_trace_provider().force_flush()  # a short script may end before the traces are uploaded, so upload them now
    print("Open this link (sign in to the OpenAI account whose API key you used):")
    print("https://platform.openai.com/traces/trace?trace_id=" + trace_id)


if __name__ == "__main__":
    main()
