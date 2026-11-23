"""
trim.py - send less: give the model only the handbook lines that matter for THIS email

The full handbook is about 1,200 tokens, and we send it with every email. Most of it is irrelevant to any one question.
This is the idea from Module 03 (RAG) used as a cost tool: find the few paragraphs that match, send only those.

The trade-off, which the notebook measures: a shorter prompt is cheaper and faster, but if the search misses the
paragraph that holds the answer, the model has nothing to answer from.
"""

import re

import llm

# The short rules every reply needs (from Part 1 of the handbook), so tone and length stay the same.
SHORT_RULES = (
    "You answer customer emails for an online shop. Use ONLY the handbook lines below. "
    "Never invent a rule, a price or a time. Be warm and calm. Reply in at most 3 short sentences, "
    "with no greeting and no signature. If the handbook lines do not cover the question, or the customer asks "
    "for an exception, mentions a lawyer, or wants a refund over $100, say that a colleague will follow up. "
    "Never ask for or accept a card number."
)


# --- trim start ---
class HandbookIndex:
    def __init__(self):
        """Split the handbook into paragraphs and embed each one (one small call, done once)."""
        self.paragraphs = []
        for paragraph in re.split(r"\n\s*\n", llm.HANDBOOK):
            if len(paragraph.strip()) > 40:        # skip titles and very short lines
                self.paragraphs.append(paragraph.strip())

        self.vectors, self.setup_cost = llm.embed(self.paragraphs)

    def trimmed_prompt(self, email, how_many=3):
        """Return (system text with only the best paragraphs, embedding cost for this email)."""
        vectors, cost = llm.embed([email])
        question_vector = vectors[0]

        scored = []
        for index in range(len(self.paragraphs)):
            scored.append((llm.similarity(question_vector, self.vectors[index]), index))
        scored.sort(reverse=True)    # best match first

        text = SHORT_RULES + "\n\nHandbook lines:"
        for score, index in scored[:how_many]:
            text = text + "\n\n" + self.paragraphs[index]
        return text, cost
# --- trim end ---
