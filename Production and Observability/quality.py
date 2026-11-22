"""
quality.py - checking the QUALITY of real replies, after they were sent

Errors are easy to see. A fluent, confident, WRONG answer raises no error at all. So in production we also
grade a sample of real replies with a judge model (the idea from Module 05, notebook 06) and watch the average.

We grade a SAMPLE (for example 1 reply in 4), because judging every reply would double the cost.
"""

import logging
import os
import random

from pydantic import BaseModel

import observe
from shop import client

JUDGE_MODEL = "gpt-4o"  # the judge is stronger than the model that wrote the reply (see Module 05)
SAMPLE_RATE = float(os.getenv("DESK_JUDGE_SAMPLE_RATE", "0.25"))  # 0.25 = grade one reply in four

# --- judge start ---
RUBRIC = (
    "You grade a support reply that an AI agent sent to a customer. Give a score from 1 to 5.\n"
    "5 = correct, helpful, polite and short; every fact comes from the EVIDENCE.\n"
    "4 = good, with a small weakness (a little wordy, or slightly cold).\n"
    "3 = acceptable, but it misses part of what the customer asked.\n"
    "2 = poor: unhelpful, confusing, or it states something the evidence does not support.\n"
    "1 = harmful: wrong facts, a promise the shop cannot keep, or rude.\n"
    "Judge the reply against the EVIDENCE (what the shop's tools returned), not against what you think is true."
)


class Grade(BaseModel):
    reasoning: str  # first, one or two sentences
    score: int      # 1 to 5


def judge_reply(email, reply, evidence):
    """Ask the judge model to grade one reply."""
    response = client.chat.completions.parse(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": "CUSTOMER EMAIL:\n" + email + "\n\nEVIDENCE:\n" + evidence + "\n\nREPLY:\n" + reply},
        ],
        response_format=Grade,
    )
    grade = response.choices[0].message.parsed

    # Never trust a model to stay inside the range: keep the score between 1 and 5
    if grade.score < 1:
        grade.score = 1
    if grade.score > 5:
        grade.score = 5
    return grade
# --- judge end ---


# --- sample start ---
def should_sample(rate):
    """Decide by chance whether to grade this reply. rate=0.25 means about one in four."""
    return random.random() < rate


def run_online_judge(request_id, email, reply, evidence):
    """Grade one real reply and save the grade. It runs in its own trace, so its cost shows up as overhead."""
    with observe.trace("judge", judged_request=request_id):
        grade = judge_reply(email, reply, evidence)
        observe.append_json_line("quality.jsonl", {
            "time": observe.now_text(),
            "request_id": request_id,
            "score": grade.score,
            "reasoning": grade.reasoning,
        })
        observe.log(logging.INFO, "reply_graded", judged_request=request_id, score=grade.score)
    return grade
# --- sample end ---
