"""
simple_agent.py - Module 02 in one file

Puts everything from the five notebooks together:
  1. Structured output  : turn a customer message into data
  2. Tools              : weather (real API), today's date, percentage calculator
  3. Agent loop         : the model asks for tools, we run them, repeat until it answers
"""

import os
import json
from datetime import date

import requests
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 1. Setup
# ---------------------------------------------------------------------------
load_dotenv()  # read OPENAI_API_KEY from the .env file
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Add OPENAI_API_KEY to your .env file (see .env.example)")

client = OpenAI()      # finds OPENAI_API_KEY on its own
MODEL = "gpt-4o-mini"  # a small, cheap model is plenty here


# ---------------------------------------------------------------------------
# 2. Structured output: get data back instead of a paragraph
# ---------------------------------------------------------------------------
class Order(BaseModel):
    item: str        # what was ordered
    quantity: int    # how many
    is_urgent: bool  # does the customer sound urgent?


def extract_order(message):
    """Ask the model to fill in the Order fields from a customer message."""
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Extract the order details from the customer's message."},
            {"role": "user", "content": message},
        ],
        response_format=Order,  # the shape we want back
    )
    return response.choices[0].message.parsed  # an Order object, not text


# ---------------------------------------------------------------------------
# 3. Tools: normal Python functions the model can ask us to run
# ---------------------------------------------------------------------------
def get_weather(city):
    """Current weather for a city, from the free Open-Meteo API (no key needed)."""
    # Step 1: turn the city name into latitude and longitude
    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1},
        timeout=10,
    ).json()
    if "results" not in geo:
        return f"Sorry, I could not find a city called {city}."
    place = geo["results"][0]

    # Step 2: ask for the weather at that location
    data = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,precipitation",
        },
        timeout=10,
    ).json()
    now = data["current"]
    return f"{place['name']}: {now['temperature_2m']} degrees C, rain right now: {now['precipitation']} mm"


def get_today():
    """Today's date. A model does not know what day it is."""
    return date.today().isoformat()


def percentage_of(percent, amount):
    """For example, 18% of 2400."""
    return percent / 100 * amount


# The model cannot see our code, so we describe each tool: name, what it does, inputs.
# The model reads the descriptions to decide WHICH tool to use, so write them clearly.
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather (temperature and rain) for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name, for example Pune"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today",
            "description": "Get today's date.",
            "parameters": {"type": "object", "properties": {}},  # no inputs needed
        },
    },
    {
        "type": "function",
        "function": {
            "name": "percentage_of",
            "description": "Calculate a percentage of an amount, for example 18 percent of 2400.",
            "parameters": {
                "type": "object",
                "properties": {
                    "percent": {"type": "number", "description": "The percentage, for example 18"},
                    "amount": {"type": "number", "description": "The amount to take the percentage of"},
                },
                "required": ["percent", "amount"],
            },
        },
    },
]

# A lookup table: tool name -> the real Python function
available_tools = {
    "get_weather": get_weather,
    "get_today": get_today,
    "percentage_of": percentage_of,
}


def run_tool(name, args):
    """Run the tool the model asked for and return the result as text."""
    if name not in available_tools:
        return f"Unknown tool: {name}"
    try:
        return str(available_tools[name](**args))
    except Exception as error:  # if a tool breaks, tell the model instead of crashing
        return f"The tool failed: {error}"


# ---------------------------------------------------------------------------
# 4. The agent: a loop of "ask the model -> run the tools it asks for"
# ---------------------------------------------------------------------------
def run_agent(question, max_steps=5):
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Use the tools when you need them."},
        {"role": "user", "content": question},
    ]

    # max_steps is a safety limit: every lap costs money, so never loop forever
    for step in range(1, max_steps + 1):
        # THINK: ask the model what to do next
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
        message = response.choices[0].message
        messages.append(message)

        # No tool requested? The model has its answer, so we are done.
        if not message.tool_calls:
            return message.content

        # ACT + OBSERVE: run each requested tool and add the result to the conversation
        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)  # JSON text -> Python dict
            result = run_tool(tool_call.function.name, args)
            print(f"  [step {step}] {tool_call.function.name}({args}) -> {result}")

            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    return "Stopped: too many steps."


def main():
    # Part 1: structured output
    print("=== 1. Structured output ===")
    order = extract_order("Hi, I ordered 3 blue t-shirts last week and they still haven't arrived. Please hurry!")
    print(f"  item={order.item}, quantity={order.quantity}, urgent={order.is_urgent}\n")

    # Part 2: the agent with tools
    print("=== 2. Agent with tools ===")
    for question in [
        "Should I carry an umbrella in Pune today? Also, what is 18% of 2400?",
        "What is 10% of the current temperature in Pune?",  # needs two steps: weather, then maths
    ]:
        print(f"\nQuestion: {question}")
        print("Answer:", run_agent(question))

    # Part 3: your turn
    print("\n=== 3. Ask your own question ===")
    while True:
        try:
            question = input("\nYour question (press Enter to quit): ").strip()
        except EOFError:  # no keyboard input available
            break
        if not question:
            break
        print("Answer:", run_agent(question))


if __name__ == "__main__":
    main()
