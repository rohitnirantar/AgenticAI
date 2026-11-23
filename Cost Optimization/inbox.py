"""
inbox.py - the emails we test with, and a way to score the replies

You cannot make something cheaper without knowing it is still GOOD. So every email has a list of FACTS that a
correct reply must contain (taken from the handbook). Each fact is a list of acceptable spellings.
    [["30 days", "30-day"], ["free"]]   means: the reply must say "30 days" (or "30-day") AND must say "free".

The score of a reply is the share of facts it contains. This is a plain text check: cheap, repeatable, no extra model call.
"""

EASY = "easy"   # one simple question, answered by one line of the handbook
HARD = "hard"   # several questions in one, a complaint, or two rules to combine

EMAILS = [
    # --- easy: one question, one fact ---
    {"kind": EASY, "email": "How much does express shipping cost?",
     "facts": [["$12"]]},
    {"kind": EASY, "email": "Do you ship to Canada?",
     "facts": [["outside the country", "do not ship", "don't ship", "not ship", "cannot ship"]]},
    {"kind": EASY, "email": "Can I pay with UPI?",
     "facts": [["upi"], ["yes", "accept"]]},
    {"kind": EASY, "email": "How long does standard shipping take?",
     "facts": [["3 to 5", "3-5", "three to five"]]},
    {"kind": EASY, "email": "My cart is $62. Will I pay anything for standard shipping?",
     "facts": [["free", "no charge", "not pay", "won't pay", "will not pay"]]},
    {"kind": EASY, "email": "Can I cancel my order? It has not shipped yet.",
     "facts": [["free", "yes", "can cancel"]]},
    {"kind": EASY, "email": "How long do refunds take to reach my account?",
     "facts": [["5 to 7", "5-7", "five to seven"]]},
    {"kind": EASY, "email": "How long is the warranty on a laptop?",
     "facts": [["12 month", "12-month", "12 months", "one year", "1 year"]]},
    {"kind": EASY, "email": "Who pays the return shipping if my item is faulty?",
     "facts": [["free", "we pay", "no cost", "at no charge"]]},
    {"kind": EASY, "email": "Can I change the delivery address of my order?",
     "facts": [["until", "before"], ["ship"]]},
    {"kind": EASY, "email": "When do I get a tracking link?",
     "facts": [["as soon as", "once", "when"], ["ship"]]},
    {"kind": EASY, "email": "Does the warranty cover a phone that I dropped?",
     "facts": [["not cover", "doesn't cover", "does not cover", "isn't covered", "is not covered", "not covered", "excludes"]]},

    # --- hard: several questions, or two rules to combine ---
    {"kind": HARD,
     "email": "I bought headphones 25 days ago and the left side stopped working. Can I get a refund, who pays for return shipping, and how long until the money arrives?",
     "facts": [["30 day", "within"], ["free", "we pay", "no cost"], ["5 to 7", "5-7"]]},
    {"kind": HARD,
     "email": "The zipper on my backpack broke after 4 months. I know the 30 day refund window is over. What can I do, and how fast will you answer?",
     "facts": [["warranty"], ["6 month", "6-month", "six month"], ["2 business days", "two business days"]]},
    {"kind": HARD,
     "email": "I opened a pair of shoes and I do not like the colour. They are not faulty. Can I return them, and does it cost me anything?",
     "facts": [["10%"], ["restocking"], ["return shipping", "shipping cost", "pay"]]},
    {"kind": HARD,
     "email": "I ordered a $40 item with express shipping. What will the shipping cost me, and when will it arrive?",
     "facts": [["$12"], ["1 to 2", "1-2"]]},
    {"kind": HARD,
     "email": "My order is $45. If I add a $10 item, does standard shipping become free? And how long will it take?",
     "facts": [["free"], ["3 to 5", "3-5"]]},
    {"kind": HARD,
     "email": "My phone stopped working after 14 months. Is it still under warranty, and can I still get a refund?",
     "facts": [["12 month", "12-month", "12 months"], ["30 day"]]},
    {"kind": HARD,
     "email": "I am very frustrated. My earbuds arrived broken yesterday. What happens now, how quickly will I get a replacement, and do I pay for shipping?",
     "facts": [["express"], ["no cost", "free", "at no charge"], ["2 business days", "two business days"]]},
    {"kind": HARD,
     "email": "I want to cancel my order but I think it already shipped. What now? And can I change the address instead?",
     "facts": [["return"], ["cannot", "can't", "no longer", "not possible", "unable", "until"]]},

    # --- hard: a person must take over (Part 6 of the handbook). Judging this is harder than finding a fact. ---
    {"kind": HARD,
     "email": "It has been 35 days since my order arrived. Please make an exception and refund it, I am a loyal customer.",
     "facts": [["colleague"], ["30 day"]]},
    {"kind": HARD,
     "email": "My delivery is two days late. If nobody solves this today I will speak to my lawyer.",
     "facts": [["colleague"]]},
    {"kind": HARD,
     "email": "I want to buy a laptop. My card number is 4111 1111 1111 1111, please use it for my order.",
     "facts": [["not share", "don't share", "do not need", "don't need", "not need", "never"]]},
    {"kind": HARD,
     "email": "My $300 television arrived 10 days ago and I changed my mind. Please refund the full $300 now.",
     "facts": [["colleague"]]},

    # --- hard: arithmetic that combines two rules. We added these AFTER the first 24 emails, because the cheap model
    #     passed all of them: a test set only becomes useful once it contains something that can fail. ---
    {"kind": HARD,
     "email": "I ordered three items: $19.99, $14.50 and $9.00. Will I pay for standard shipping? And if I return the opened, not faulty $14.50 item, how much restocking fee do I pay?",
     "facts": [["4.99"], ["1.45"]]},
    {"kind": HARD,
     "email": "My order is $49.50. How much more would express shipping cost me compared with standard shipping?",
     "facts": [["7.01"]]},
    {"kind": HARD,
     "email": "I have two orders: a $30 order and a $55 order, both with standard shipping. How much will I pay in total for shipping?",
     "facts": [["4.99"], ["free"]]},
    {"kind": HARD,
     "email": "I paid $120 for shoes, delivered 20 days ago, opened and not faulty. If I return them, how much money do I get back after the restocking fee?",
     "facts": [["108"]]},
]

# A real day has REPEATS: the same question again, typed a little differently.
#   "exact"      : same words, different capital letters, spaces or punctuation
#   "paraphrase" : different words, same meaning
# Each repeat has the same facts as the email it repeats ("same_as" is its position in EMAILS).
REPEATS = [
    {"kind": "exact", "same_as": 0, "email": "HOW MUCH DOES EXPRESS SHIPPING COST?  "},
    {"kind": "exact", "same_as": 3, "email": "how long does standard shipping take"},
    {"kind": "exact", "same_as": 6, "email": "How long do refunds take to reach my account??"},
    {"kind": "exact", "same_as": 2, "email": "  Can I pay with UPI?"},
    {"kind": "paraphrase", "same_as": 0, "email": "What is the price of express delivery?"},
    {"kind": "paraphrase", "same_as": 2, "email": "Is UPI accepted as a payment method?"},
    {"kind": "paraphrase", "same_as": 7, "email": "For how many months is a laptop covered by your warranty?"},
    {"kind": "paraphrase", "same_as": 3, "email": "How many days does regular delivery take?"},
]


def traffic():
    """A day of traffic: the 20 emails, then the repeats. Each item has 'kind', 'email' and 'facts'."""
    items = []
    for item in EMAILS:
        items.append(dict(item))
    for repeat in REPEATS:
        original = EMAILS[repeat["same_as"]]
        items.append({"kind": repeat["kind"], "email": repeat["email"], "facts": original["facts"]})
    return items


# --- score start ---
def score_reply(reply, facts):
    """The share of required facts that appear in the reply (0.0 to 1.0)."""
    text = reply.lower()
    found = 0
    for alternatives in facts:
        for spelling in alternatives:
            if spelling.lower() in text:
                found = found + 1
                break
    return found / len(facts)
# --- score end ---
