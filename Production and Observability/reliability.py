"""
reliability.py - small tools that keep the desk working when things go wrong

In production, things fail in ordinary ways: the API says "slow down" (rate limit), the network drops,
a customer's browser sends the same request twice, or one request starts to cost far too much.
Each tool here answers one of those problems in a few lines.
"""

import logging
import random
import threading
import time

import openai

import observe

# The OpenAI errors that are TEMPORARY. Trying again a moment later often works.
RETRYABLE_ERRORS = (
    openai.RateLimitError,       # 429: "you are sending too many requests"
    openai.APIConnectionError,   # the network dropped
    openai.APITimeoutError,      # the call took too long
    openai.InternalServerError,  # 5xx: the server had a problem
)


# --- retry start ---
def retry_with_backoff(function, attempts=4, first_delay=1.0, retry_on=RETRYABLE_ERRORS):
    """Call function(). If it fails for a temporary reason, wait and try again, waiting twice as long each time.

    Waiting longer each time ("exponential backoff") gives a struggling server room to recover.
    The little random extra ("jitter") stops thousands of clients from retrying at exactly the same moment."""
    delay = first_delay

    for attempt in range(1, attempts + 1):
        try:
            return function()
        except retry_on as error:
            if attempt == attempts:
                raise  # no attempts left: let the caller decide what to do

            wait = delay + random.uniform(0, delay * 0.2)
            observe.log(logging.WARNING, "retrying", attempt=attempt, wait_seconds=round(wait, 2),
                        error=type(error).__name__)
            time.sleep(wait)
            delay = delay * 2
# --- retry end ---


# --- idempotency start ---
class IdempotencyStore:
    """Remember the answer to a request, so a repeated request gets the SAME answer and does nothing twice.

    A customer double-clicks, a phone loses signal and resends, a client retries after a timeout: the same
    request can arrive more than once. The caller attaches a unique key to each request. If we have seen the key,
    we return the saved answer instead of, for example, refunding the order a second time.

    (In a real system this lives in a database such as Redis and expires after a day. Here it is a dictionary.)"""

    def __init__(self):
        self.saved = {}
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            return self.saved.get(key)

    def put(self, key, answer):
        with self.lock:
            self.saved[key] = answer
# --- idempotency end ---


# --- ratelimit start ---
class RateLimiter:
    """Allow each caller only 'limit' requests per 'seconds'. It protects the shop from one noisy client
    (a bug, an attack) using up the whole OpenAI budget."""

    def __init__(self, limit, seconds=60):
        self.limit = limit
        self.seconds = seconds
        self.calls = {}  # caller -> the times of their recent requests
        self.lock = threading.Lock()

    def allow(self, caller):
        """True if this caller may make a request now. False means: answer with HTTP 429 (too many requests)."""
        with self.lock:
            now = time.time()

            # Keep only the requests from the last 'seconds'
            recent = []
            for moment in self.calls.get(caller, []):
                if now - moment < self.seconds:
                    recent.append(moment)

            if len(recent) >= self.limit:
                self.calls[caller] = recent
                return False

            recent.append(now)
            self.calls[caller] = recent
            return True
# --- ratelimit end ---
