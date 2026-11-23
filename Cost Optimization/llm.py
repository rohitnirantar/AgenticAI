"""
llm.py - one place that makes model calls AND counts what each call cost

Everything in this module asks the same question: "what did that cost?" So every call returns, next to the text,
the number of tokens and the dollars it cost. Without this, you cannot optimise anything.

Prices are in dollars per 1 million tokens. They change over time, so check https://platform.openai.com/docs/pricing
and update PRICES if you run this much later.
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # read OPENAI_API_KEY from the .env file
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Add OPENAI_API_KEY to your .env file (see .env.example)")

client = OpenAI(timeout=60.0, max_retries=2)

BIG = "gpt-4o"            # the stronger, more expensive model
SMALL = "gpt-4o-mini"     # the cheaper model
EMBEDDING_MODEL = "text-embedding-3-small"

# (normal input, cached input, output) in dollars per 1 million tokens
PRICES = {
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "gpt-4o": (2.50, 1.25, 10.00),
    "text-embedding-3-small": (0.02, 0.02, 0.00),
}
BATCH_DISCOUNT = 0.5      # the Batch API charges half price (see batch.py)

# The shop's handbook is long on purpose: real system prompts are. It is the STATIC part of every call.
HANDBOOK = (Path(__file__).parent / "shop_handbook.txt").read_text(encoding="utf-8")


def price_for(model):
    """Find the price list for a model. The API reports names like 'gpt-4o-mini-2024-07-18', so we match the start."""
    best = ""
    for name in PRICES:
        if model.startswith(name) and len(name) > len(best):  # the longest match wins ('gpt-4o-mini' beats 'gpt-4o')
            best = name
    return PRICES[best]


# --- cost start ---
def cost_of(model, prompt_tokens, cached_tokens, completion_tokens, batch=False):
    """What did one call cost, in dollars?
    Cached input tokens are cheaper than normal ones. A batch call costs half."""
    price = price_for(model)
    normal_tokens = prompt_tokens - cached_tokens
    dollars = (normal_tokens * price[0] + cached_tokens * price[1] + completion_tokens * price[2]) / 1_000_000
    if batch:
        dollars = dollars * BATCH_DISCOUNT
    return dollars
# --- cost end ---


# --- ask start ---
def ask(user_text, model=SMALL, system_text=None, max_tokens=150):
    """Ask the model one question. Returns the reply together with what the call cost.

    The system text (the handbook) goes FIRST and never changes. The customer's email goes LAST.
    That order matters: OpenAI reuses (caches) a long prompt start that it has seen before. See notebook 03."""
    if system_text is None:
        system_text = HANDBOOK

    started = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        max_tokens=max_tokens,   # a ceiling on the reply length: you pay for every output token
        temperature=0,
    )
    seconds = time.time() - started

    usage = response.usage
    cached = 0
    if usage.prompt_tokens_details is not None and usage.prompt_tokens_details.cached_tokens is not None:
        cached = usage.prompt_tokens_details.cached_tokens

    return {
        "text": response.choices[0].message.content,
        "model": model,
        "prompt_tokens": usage.prompt_tokens,
        "cached_tokens": cached,
        "completion_tokens": usage.completion_tokens,
        "cost": cost_of(model, usage.prompt_tokens, cached, usage.completion_tokens),
        "seconds": seconds,
    }
# --- ask end ---


def embed(texts):
    """Turn texts into vectors. Returns (vectors, cost in dollars)."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    vectors = []
    for item in response.data:
        vectors.append(item.embedding)
    dollars = cost_of(EMBEDDING_MODEL, response.usage.prompt_tokens, 0, 0)
    return vectors, dollars


def similarity(vector_a, vector_b):
    """How close two vectors are (1.0 = the same meaning). OpenAI vectors have length 1, so multiply and add."""
    total = 0.0
    for index in range(len(vector_a)):
        total = total + vector_a[index] * vector_b[index]
    return total
