"""
batch.py - the Batch API: half price, if you can wait

Not every email needs an answer in two seconds. Overnight jobs (re-checking yesterday's replies, writing summaries,
re-scoring an eval set, labelling old tickets) can wait. The Batch API takes a FILE of requests, works through it in
the background, and charges 50% less. The promise is "within 24 hours". In practice small batches often finish in minutes,
but you must not depend on that.

How it works, in four steps:
    1. prepare : write one JSON line per request into a .jsonl file
    2. submit  : upload the file and create the batch (you get a batch id)
    3. check   : ask for the status now and then (validating, in_progress, completed, failed ...)
    4. results : when it is completed, download the answers (matched to your requests by custom_id)

Run it:
    python "Cost Optimization/batch.py" prepare              write logs/batch_input.jsonl and show what it would cost
    python "Cost Optimization/batch.py" submit               upload it and start the batch (costs real, small, money)
    python "Cost Optimization/batch.py" check <batch id>
    python "Cost Optimization/batch.py" results <batch id>
"""

import json
import sys
from pathlib import Path

import inbox
import llm

LOG_DIR = Path(__file__).parent / "logs"
INPUT_FILE = LOG_DIR / "batch_input.jsonl"


# --- prepare start ---
def make_batch_file(items, model, path):
    """Write one request per line. The custom_id is how we match answers to questions later."""
    LOG_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for number in range(len(items)):
            request = {
                "custom_id": "email-" + str(number),
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": llm.HANDBOOK},
                        {"role": "user", "content": items[number]["email"]},
                    ],
                    "max_tokens": 150,
                    "temperature": 0,
                },
            }
            file.write(json.dumps(request) + "\n")
# --- prepare end ---


# --- submit start ---
def submit(path):
    """Upload the file and start the batch. Returns the batch id."""
    with open(path, "rb") as file:
        uploaded = llm.client.files.create(file=file, purpose="batch")

    batch = llm.client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    return batch.id


def check(batch_id):
    """The batch's current state: status and how many requests are done."""
    return llm.client.batches.retrieve(batch_id)


def results(batch_id):
    """Download the answers of a finished batch. Returns {custom_id: {"text", "cost"}}."""
    batch = check(batch_id)
    if batch.output_file_id is None:
        return {}

    answers = {}
    content = llm.client.files.content(batch.output_file_id).text
    for line in content.splitlines():
        row = json.loads(line)
        body = row["response"]["body"]
        usage = body["usage"]
        cached = 0
        details = usage.get("prompt_tokens_details")
        if details is not None and details.get("cached_tokens") is not None:
            cached = details["cached_tokens"]

        answers[row["custom_id"]] = {
            "text": body["choices"][0]["message"]["content"],
            "cost": llm.cost_of(body["model"], usage["prompt_tokens"], cached, usage["completion_tokens"], batch=True),
        }
    return answers
# --- submit end ---


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]
    if command == "prepare":
        items = inbox.EMAILS
        make_batch_file(items, llm.SMALL, INPUT_FILE)
        print("Wrote " + str(len(items)) + " requests to " + INPUT_FILE.name + " (in the logs folder)")
    elif command == "submit":
        batch_id = submit(INPUT_FILE)
        print("Batch started. Its id is: " + batch_id)
        print("Check it with:  python batch.py check " + batch_id)
    elif command == "check":
        batch = check(sys.argv[2])
        print("Status: " + batch.status + "   done: " + str(batch.request_counts.completed) + " of " + str(batch.request_counts.total))
    elif command == "results":
        answers = results(sys.argv[2])
        total = 0.0
        for custom_id in answers:
            total = total + answers[custom_id]["cost"]
            print(custom_id + ": " + answers[custom_id]["text"][:100].replace("\n", " "))
        print("Total cost at the batch price: $" + format(total, ".5f"))
    else:
        print("Unknown command: " + command)


if __name__ == "__main__":
    main()
