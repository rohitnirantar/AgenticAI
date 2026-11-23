"""
cache.py - remember answers, so we do not pay for the same question twice

Two kinds of memory, from simple to clever:

  exact cache    : the same question (ignoring capital letters, extra spaces and punctuation) gets the saved answer.
                   Free to check, and never wrong.
  semantic cache : a question that MEANS the same ("What is the price of express delivery?") also gets the saved
                   answer. It costs one tiny embedding call to check, and it CAN be wrong, so it needs guard rails.

The big danger of a semantic cache: "Where is order A1001?" and "Where is order A1002?" mean almost the same thing
to an embedding, but they need different answers. So we only cache emails that do NOT depend on a specific customer
or number (see is_cacheable).
"""

import re

import llm

SIMILARITY_THRESHOLD = 0.80   # how close two questions must be to count as "the same". See notebook 03.

PERSONAL_WORDS = ["my order", "i ordered", "i bought", "my card", "my cart", "my phone", "my laptop", "my package"]


# --- guard start ---
def is_cacheable(email):
    """True only for general questions. An email with a number or a personal detail needs its own answer."""
    if re.search(r"\d", email):          # any digit: an order id, an amount, a date...
        return False

    text = email.lower()
    for word in PERSONAL_WORDS:
        if word in text:
            return False
    return True
# --- guard end ---


def normalise(email):
    """Lower case, no punctuation, single spaces. 'HOW much is it??' and 'how much is it' become the same text."""
    text = email.lower()
    text = re.sub(r"[^a-z0-9$ ]", " ", text)
    return " ".join(text.split())


# --- cache start ---
class AnswerCache:
    def __init__(self, use_semantic=True, threshold=SIMILARITY_THRESHOLD):
        self.use_semantic = use_semantic
        self.threshold = threshold
        self.exact = {}      # normalised question -> reply
        self.semantic = []   # a list of (vector, reply)
        self.stats = {"exact_hits": 0, "semantic_hits": 0, "misses": 0, "skipped": 0}

    def lookup(self, email):
        """Look for a saved answer. Returns a dictionary: reply (or None), kind, cost, vector."""
        if not is_cacheable(email):
            self.stats["skipped"] = self.stats["skipped"] + 1
            return {"reply": None, "kind": "skipped", "cost": 0.0, "vector": None}

        key = normalise(email)
        if key in self.exact:
            self.stats["exact_hits"] = self.stats["exact_hits"] + 1
            return {"reply": self.exact[key], "kind": "exact", "cost": 0.0, "vector": None}

        vector = None
        cost = 0.0
        if self.use_semantic and len(self.semantic) > 0:
            vectors, cost = llm.embed([email])
            vector = vectors[0]

            best_score = 0.0
            best_reply = None
            for saved_vector, saved_reply in self.semantic:
                score = llm.similarity(vector, saved_vector)
                if score > best_score:
                    best_score = score
                    best_reply = saved_reply

            if best_score >= self.threshold:
                self.stats["semantic_hits"] = self.stats["semantic_hits"] + 1
                return {"reply": best_reply, "kind": "semantic", "cost": cost, "vector": vector}

        self.stats["misses"] = self.stats["misses"] + 1
        return {"reply": None, "kind": "miss", "cost": cost, "vector": vector}

    def store(self, email, reply, vector=None):
        """Save an answer for next time. Only general questions are saved."""
        if not is_cacheable(email):
            return
        self.exact[normalise(email)] = reply

        if self.use_semantic:
            if vector is None:
                vectors, cost = llm.embed([email])
                vector = vectors[0]
            self.semantic.append((vector, reply))
# --- cache end ---
