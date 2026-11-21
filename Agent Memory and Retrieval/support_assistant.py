"""
support_assistant.py - a real-life example: a support assistant that knows the shop's rules
and remembers its customers

It is the same online shop from Module 02, and it brings together everything so far:

  Tools (Module 02)    : look up a customer's order
  Retrieval, RAG       : answer policy questions from the files in knowledge_base/
  Short-term memory    : the message list, so the chat makes sense turn by turn
  Long-term memory     : lasting facts about each customer, saved to a file and
                         loaded again in their next conversation
  Structured output    : used to pull those lasting facts out of a conversation

The demo at the bottom runs three conversations:
  1. Priya chats, then the session ends and her facts are saved
  2. Priya comes back. The assistant remembers her.
  3. A different customer (Rahul) chats. He gets no access to Priya's memory or orders.

Run from the repo root or from this folder:
    python "Agent Memory and Retrieval/support_assistant.py"
"""

import os
import re
import sys
import json
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
sys.stdout.reconfigure(encoding="utf-8")  # so replies with curly quotes etc. print correctly on Windows

load_dotenv()  # read OPENAI_API_KEY from the .env file
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Add OPENAI_API_KEY to your .env file (see .env.example)")

client = OpenAI()
MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

HERE = Path(__file__).parent                  # the folder this file lives in
KNOWLEDGE_DIR = HERE / "knowledge_base"       # the shop's policy files
MEMORY_FILE = HERE / "support_memory.json"    # where we save what we remember about customers


# ---------------------------------------------------------------------------
# The shop's order data (made up). In a real company this would be a database.
# ---------------------------------------------------------------------------
def days_ago(n):
    """A date n days before today, so the sample data stays valid whenever you run this."""
    return (date.today() - timedelta(days=n)).isoformat()


ORDERS = {
    "A1001": {"customer_id": "priya@example.com", "item": "Wireless headphones", "price": 79.00,
              "status": "delivered", "delivered_on": days_ago(18)},
    "A1002": {"customer_id": "rahul@example.com", "item": "Running shoes", "price": 120.00,
              "status": "in_transit", "expected_delivery": days_ago(-4)},   # 4 days from now
}


# ---------------------------------------------------------------------------
# Part 1: Retrieval (RAG). Find the policy text that matches a question.
# ---------------------------------------------------------------------------
def load_chunks():
    """Read every .txt file in knowledge_base/ and split it into paragraphs ('chunks')."""
    chunks = []
    for file in sorted(KNOWLEDGE_DIR.glob("*.txt")):
        text = file.read_text(encoding="utf-8")
        for paragraph in re.split(r"\n\s*\n", text):  # a blank line separates paragraphs
            if paragraph.strip():
                chunks.append({"source": file.name, "text": paragraph.strip()})
    return chunks


def embed(texts):
    """Turn texts into vectors (lists of numbers that capture meaning)."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def similarity(vector_a, vector_b):
    """Higher = closer in meaning. (OpenAI vectors have length 1, so this simple sum is enough.)"""
    return sum(a * b for a, b in zip(vector_a, vector_b))


# Prepare the knowledge base once, when the program starts
chunks = load_chunks()
chunk_vectors = embed([chunk["text"] for chunk in chunks])
print(f"Knowledge base ready: {len(chunks)} chunks\n")


def retrieve(question, top_k=5):
    """Return the top_k chunks whose meaning is closest to the question."""
    question_vector = embed([question])[0]
    scored = [(similarity(question_vector, vector), chunk) for vector, chunk in zip(chunk_vectors, chunks)]
    scored.sort(key=lambda pair: pair[0], reverse=True)  # best match first
    return [chunk for score, chunk in scored[:top_k]]


# ---------------------------------------------------------------------------
# Part 2: Long-term memory. Save lasting facts about each customer.
# ---------------------------------------------------------------------------
def load_memory(customer_id):
    """The facts we remember about a customer (an empty list if we know nothing)."""
    if not MEMORY_FILE.exists():
        return []
    return json.loads(MEMORY_FILE.read_text()).get(customer_id, [])


def save_memory(customer_id, facts):
    if MEMORY_FILE.exists():
        data = json.loads(MEMORY_FILE.read_text())  # load what is already saved
    else:
        data = {}                                   # nothing saved yet
    data[customer_id] = facts
    MEMORY_FILE.write_text(json.dumps(data, indent=2))


class MemoryNotes(BaseModel):
    facts: list[str]  # short facts, for example "Prefers email over phone"


def extract_facts(conversation_text, old_facts):
    """Structured output: ask the model for the updated list of lasting facts about this customer."""
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": (
                "You keep notes about a customer for a support team. "
                "Given the existing notes and the latest conversation, return the updated list of at most 5 short facts. "
                "Keep only lasting facts: name, preferences, past issues and their outcome. "
                "Remove duplicates. If there is nothing lasting, return the existing notes unchanged. "
                "Never store payment details, passwords or addresses."
            )},
            {"role": "user", "content": f"Existing notes: {old_facts}\n\nConversation:\n{conversation_text}"},
        ],
        response_format=MemoryNotes,
    )
    return response.choices[0].message.parsed.facts


# ---------------------------------------------------------------------------
# Part 3: Tools. Two small functions the assistant can ask us to run.
# ---------------------------------------------------------------------------
CURRENT_CUSTOMER = None  # who we are chatting with right now (set when a session starts)


def lookup_order(order_id):
    """Order details, but ONLY if the order belongs to the customer we are chatting with."""
    order = ORDERS.get(order_id.strip().upper())
    if order is None or order["customer_id"] != CURRENT_CUSTOMER:
        return f"No order found with id {order_id} for this customer."  # same message either way, so nothing leaks

    details = dict(order)         # a copy, so we do not change the shop's data
    del details["customer_id"]    # the model does not need to see this
    if order["status"] == "delivered":
        details["days_since_delivery"] = (date.today() - date.fromisoformat(order["delivered_on"])).days
    return json.dumps(details)


def search_knowledge_base(question):
    """Find the shop policy text that best matches the question."""
    return "\n".join(f"[{chunk['source']}] {chunk['text']}" for chunk in retrieve(question))


# The model reads these descriptions to decide which tool to use, so write them clearly.
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": ("Search the shop's policies (refunds, shipping, warranty, payments). "
                            "Use it for any question about how the shop works. "
                            "Ask about one topic at a time and search again for another topic."),
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "What to look up, in plain words"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Get the details of one of the customer's orders: item, price, status and delivery date.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "The order id, for example A1001"}},
                "required": ["order_id"],
            },
        },
    },
]

available_tools = {"search_knowledge_base": search_knowledge_base, "lookup_order": lookup_order}


def run_tool(name, args):
    """Run the tool the model asked for and return the result as text."""
    if name not in available_tools:
        return f"Unknown tool: {name}"
    try:
        return str(available_tools[name](**args))
    except Exception as error:  # if a tool breaks, tell the model instead of crashing
        return f"The tool failed: {error}"


# ---------------------------------------------------------------------------
# Part 4: The assistant. One "session" = one conversation with one customer.
# ---------------------------------------------------------------------------
RULES = """You are a friendly customer support assistant for an online shop.
- Answer questions about how the shop works ONLY from search_knowledge_base results.
  If a question has several parts, search for each part separately.
  If the answer is not there, say you don't know and offer to pass the customer to a human agent.
- Whenever the customer mentions an order id, use lookup_order for it.
- You may be given short notes about the customer from earlier chats. Use them naturally (their name, how they like to be contacted).
  If the customer asks what you remember, tell them what is in your notes. Only if you have no notes at all, say you have no record of earlier chats.
- Keep answers to 3 short sentences."""


def start_session(customer_id):
    """Start a conversation. Whatever we remember about this customer goes into the system prompt."""
    global CURRENT_CUSTOMER
    CURRENT_CUSTOMER = customer_id

    system_prompt = RULES
    facts = load_memory(customer_id)
    if facts:
        system_prompt += "\n\nWhat you remember about this customer from earlier chats:\n- " + "\n- ".join(facts)

    print(f"--- Chat with {customer_id} (remembered facts: {len(facts)}) ---")
    return {
        "customer_id": customer_id,
        "messages": [{"role": "system", "content": system_prompt}],  # short-term memory
        "transcript": [],                                           # plain text, used for long-term memory
    }


def say(session, customer_text, max_steps=6):
    """The customer says something. The assistant may use tools, then replies."""
    print(f"\nCustomer : {customer_text}")
    messages = session["messages"]
    messages.append({"role": "user", "content": customer_text})

    # The agent loop from Module 02: ask the model, run the tools it asks for, repeat.
    # max_steps is a safety limit: every lap costs money, so never loop forever.
    reply = "Sorry, I could not finish that request."
    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:  # no tool requested: this is the reply
            reply = message.content
            break

        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            result = run_tool(tool_call.function.name, args)
            print(f"  [tool] {tool_call.function.name}({args})")
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    print(f"Assistant: {reply}")
    session["transcript"] += [f"Customer: {customer_text}", f"Assistant: {reply}"]
    return reply


def end_session(session):
    """When the chat ends, pull out the lasting facts and save them for next time."""
    customer_id = session["customer_id"]
    facts = extract_facts("\n".join(session["transcript"]), load_memory(customer_id))
    save_memory(customer_id, facts)
    print(f"\n  (saved {len(facts)} facts about {customer_id})\n")


# ---------------------------------------------------------------------------
# Try it
# ---------------------------------------------------------------------------
def main():
    MEMORY_FILE.unlink(missing_ok=True)  # start the demo with a clean slate

    # Conversation 1: Priya talks to the assistant for the first time
    session = start_session("priya@example.com")
    say(session, "Hi, I'm Priya, but please call me Pri. One earbud on my headphones (order A1001) "
                 "stopped working. Can I still get a refund?")
    say(session, "Thanks! By the way, please always contact me by email, never by phone.")
    end_session(session)

    # Conversation 2: Priya comes back later. This is a brand new session, so only the saved facts carry over.
    session = start_session("priya@example.com")
    say(session, "Hi again! What did we talk about last time, and how will you contact me about my claim?")
    end_session(session)

    # Conversation 3: a different customer. He must not see Priya's memory or her orders.
    session = start_session("rahul@example.com")
    say(session, "Hi, what did I ask you last time? Also, can you check order A1001 for me?")
    end_session(session)

    print("=== Everything the assistant has saved ===")
    print(MEMORY_FILE.read_text())


if __name__ == "__main__":
    main()
