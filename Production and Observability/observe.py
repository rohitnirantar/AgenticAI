"""
observe.py - logging, tracing and cost tracking for the support desk, in plain Python

Observability means being able to answer "what happened, why, how long did it take and what did it cost?"
for any request, after the fact. Three tools do most of the work:

  1. LOGS    : structured lines (JSON) that say what happened, each with a request id
  2. TRACES  : one record per request, made of SPANS (timed steps: guards, router, model calls, tools)
  3. METRICS : numbers computed from many traces (see metrics.py)

Everything here uses only the standard library. Real products (OpenTelemetry, Langfuse, LangSmith, the OpenAI
dashboard) work on the same ideas. Building it by hand once shows you what they record and why.
"""

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import contextvars
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# ===========================================================================
# Settings
# ===========================================================================
LOG_DIR = Path(os.getenv("DESK_LOG_DIR", str(Path(__file__).parent / "logs")))  # where the log files go
MAX_COST_PER_REQUEST = float(os.getenv("DESK_MAX_COST", "0.02"))  # dollars. A request that spends more is stopped.
STORE_ON_OPENAI = os.getenv("DESK_STORE_ON_OPENAI", "no") == "yes"  # opt in: also keep the calls in OpenAI's dashboard

# Which version of the prompts is running? Change this whenever you change an agent's instructions,
# so that a change in behaviour can be traced back to the change that caused it.
PROMPT_VERSION = "2026-11-22"

# --- prices start ---
# Prices in US dollars per 1 million tokens: (input, output). Checked in November 2026.
# Prices change, so always check https://developers.openai.com/api/docs/pricing before you trust a bill estimate.
PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "text-embedding-3-small": (0.02, 0.00),
}


def price_for(model):
    """Find the price for a model. The API reports names like 'gpt-4o-mini-2024-07-18', so we match the start."""
    best = ""
    for name in PRICES:
        if model.startswith(name) and len(name) > len(best):  # the longest match wins ('gpt-4o-mini' beats 'gpt-4o')
            best = name
    if best == "":
        return None
    return PRICES[best]


def cost_of(model, prompt_tokens, completion_tokens):
    """What did one model call cost, in dollars?"""
    price = price_for(model)
    if price is None:
        return 0.0  # a model we have no price for. The cost is unknown, not zero, so watch for this in reports.
    return (prompt_tokens * price[0] + completion_tokens * price[1]) / 1_000_000
# --- prices end ---


def code_version():
    """The short git commit of the code that is running, so every log line can say which version made it."""
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                cwd=Path(__file__).parent, timeout=5)
        text = result.stdout.strip()
        if text != "":
            return text
    except Exception:
        pass
    return "unknown"


VERSIONS = {"prompt_version": PROMPT_VERSION, "code_version": code_version()}


def set_log_dir(path):
    """Send all log files to another folder (the notebooks use this to keep their logs apart)."""
    global LOG_DIR
    LOG_DIR = Path(path)
    setup_logging()


def log_path(file_name):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / file_name


_write_lock = threading.Lock()  # so two requests never write to a file at the same moment


def append_json_line(file_name, record):
    """Add one JSON record as a new line at the end of a file. This format is called JSON Lines."""
    with _write_lock:
        with open(log_path(file_name), "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def now_text():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ===========================================================================
# Privacy: remove personal data BEFORE it is written to a log
# ===========================================================================
# --- redact start ---
def redact_for_logs(text):
    """Remove card numbers, email addresses and phone numbers. Logs live a long time and many people can read them."""
    text = re.sub(r"\b\d(?:[ -]?\d){12,15}\b", "[CARD]", text)             # card numbers first
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL]", text)             # email addresses
    text = re.sub(r"\+?\d[\d ()-]{8,}\d", "[PHONE]", text)                  # phone numbers
    return text
# --- redact end ---


# ===========================================================================
# 1. Structured logs
# ===========================================================================
_current = contextvars.ContextVar("current_trace", default=None)  # the trace this code is running inside


def current():
    """The trace of the request being handled right now (or None)."""
    return _current.get()


# --- logging start ---
class JsonFormatter(logging.Formatter):
    """Turn every log record into ONE line of JSON. Machines can search it, people can still read it."""

    def format(self, record):
        line = {"time": now_text(), "level": record.levelname, "event": record.getMessage()}
        trace = current()
        if trace is not None:
            line["request_id"] = trace.id  # the same id appears in every log line of this request
        line.update(getattr(record, "fields", {}))
        return json.dumps(line, ensure_ascii=False)


logger = logging.getLogger("desk")


def setup_logging():
    """Send the logs to the screen and to logs/app.log."""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = JsonFormatter()
    to_screen = logging.StreamHandler(sys.stdout)
    to_screen.setFormatter(formatter)
    to_file = logging.FileHandler(log_path("app.log"), encoding="utf-8")
    to_file.setFormatter(formatter)

    logger.addHandler(to_screen)
    logger.addHandler(to_file)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log(level, event, **fields):
    """Write one log line. 'level' says how serious it is: INFO (normal), WARNING (look at it), ERROR (broken)."""
    logger.log(level, event, extra={"fields": fields})
# --- logging end ---


def audit(event, **fields):
    """The audit trail: a separate file for actions that change something important (money, approvals)."""
    record = {"time": now_text(), "event": event}
    trace = current()
    if trace is not None:
        record["request_id"] = trace.id
    record.update(fields)
    append_json_line("audit.jsonl", record)
    log(logging.INFO, "audit:" + event, **fields)


# ===========================================================================
# 2. Traces and spans
# ===========================================================================
class BudgetExceeded(Exception):
    """Raised when one request has spent more than it is allowed to."""


# --- trace start ---
class Trace:
    """Everything that happened while handling ONE request."""

    def __init__(self, name, **attributes):
        self.id = uuid.uuid4().hex[:12]
        self.name = name
        self.attributes = attributes
        self.started_at = now_text()
        self.started = time.time()
        self.spans = []
        self.open_spans = []  # the spans that are open right now. The last one is the parent of the next span.
        self.status = "ok"
        self.error = ""
        self.duration_ms = 0

    def set(self, **fields):
        """Add facts about the request (for example the outcome) once we know them."""
        self.attributes.update(fields)

    def totals(self):
        """Add up the tokens and the cost of every model call in this request."""
        prompt_tokens = 0
        completion_tokens = 0
        cost = 0.0
        calls = 0
        for span_record in self.spans:
            if span_record["kind"] == "model":
                calls = calls + 1
                prompt_tokens = prompt_tokens + span_record["attributes"].get("prompt_tokens", 0)
                completion_tokens = completion_tokens + span_record["attributes"].get("completion_tokens", 0)
                cost = cost + span_record["attributes"].get("cost_usd", 0.0)
        return {"model_calls": calls, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                "cost_usd": round(cost, 6)}

    def check_budget(self):
        """Stop a request that is spending too much, before it makes the next (paid) call."""
        spent = self.totals()["cost_usd"]
        if spent >= MAX_COST_PER_REQUEST:
            raise BudgetExceeded("This request has spent $" + format(spent, ".4f")
                                 + ", which is the limit of $" + format(MAX_COST_PER_REQUEST, ".4f") + ".")

    def to_record(self):
        return {
            "request_id": self.id,
            "name": self.name,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error,
            "attributes": self.attributes,
            "totals": self.totals(),
            "versions": VERSIONS,
            "spans": self.spans,
        }


@contextmanager
def trace(name, **attributes):
    """Everything inside this 'with' block belongs to one trace. When the block ends, the trace is saved."""
    new_trace = Trace(name, **attributes)
    token = _current.set(new_trace)
    try:
        yield new_trace
    except Exception as error:
        new_trace.status = "error"
        new_trace.error = type(error).__name__ + ": " + str(error)
        raise
    finally:
        new_trace.duration_ms = round((time.time() - new_trace.started) * 1000)
        append_json_line("traces.jsonl", new_trace.to_record())
        totals = new_trace.totals()
        log(logging.INFO, "request_finished", status=new_trace.status, duration_ms=new_trace.duration_ms,
            model_calls=totals["model_calls"], cost_usd=totals["cost_usd"])
        _current.reset(token)


@contextmanager
def span(name, kind="step", **attributes):
    """One timed step inside a trace. Spans can sit inside other spans (a tool call inside an agent)."""
    current_trace = current()
    if current_trace is None:  # nobody is tracing: just run the code
        yield {"attributes": dict(attributes)}
        return

    parent = None
    if len(current_trace.open_spans) > 0:
        parent = current_trace.open_spans[-1]["id"]

    record = {
        "id": len(current_trace.spans) + 1,
        "parent": parent,
        "name": name,
        "kind": kind,                 # guard, router, agent, tool or model
        "start_ms": round((time.time() - current_trace.started) * 1000),
        "duration_ms": 0,
        "status": "ok",
        "attributes": dict(attributes),
    }
    current_trace.spans.append(record)
    current_trace.open_spans.append(record)
    started = time.time()
    try:
        yield record
    except Exception as error:
        record["status"] = "error"
        record["attributes"]["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        record["duration_ms"] = round((time.time() - started) * 1000)
        current_trace.open_spans.pop()
# --- trace end ---


def format_trace(record):
    """Show a trace as an indented tree, so you can see the whole request at a glance."""
    lines = []
    totals = record["totals"]
    lines.append("Trace " + record["request_id"] + "  " + str(record["duration_ms"]) + " ms  "
                 + str(totals["model_calls"]) + " model calls  $" + format(totals["cost_usd"], ".5f"))

    depth_of = {}
    for item in record["spans"]:
        depth = 1
        if item["parent"] is not None:
            depth = depth_of[item["parent"]] + 1
        depth_of[item["id"]] = depth

        text = "  " * depth + item["name"].ljust(34 - 2 * depth) + str(item["duration_ms"]).rjust(6) + " ms"
        if item["kind"] == "model":
            attrs = item["attributes"]
            text = text + "  " + str(attrs.get("prompt_tokens", 0)) + " in / " + str(attrs.get("completion_tokens", 0)) + " out"
            text = text + "  $" + format(attrs.get("cost_usd", 0.0), ".5f")
        if item["status"] != "ok":
            text = text + "  ERROR"
        lines.append(text)
    return "\n".join(lines)


# ===========================================================================
# 3. Recording every model call automatically
# ===========================================================================
# --- instrument start ---
def wrap_method(owner, method_name, label):
    """Replace one method of the OpenAI client with a version that records a span for every call.
    The desk's code does not change at all: it calls the client as before, and we see everything."""
    original = getattr(owner, method_name)

    def wrapper(*args, **kwargs):
        current_trace = current()
        if current_trace is not None:
            current_trace.check_budget()  # no more paid calls once the request has used up its budget

            if STORE_ON_OPENAI and label == "chat":  # optional: also keep the call in OpenAI's own dashboard
                kwargs["store"] = True
                kwargs["metadata"] = {"request_id": current_trace.id, "app": "support-desk"}

        model = kwargs.get("model", "unknown")
        with span(label + ":" + model, kind="model", model=model) as record:
            response = original(*args, **kwargs)

            usage = getattr(response, "usage", None)  # (the moderation endpoint reports no tokens: it is free)
            if usage is not None:
                prompt_tokens = usage.prompt_tokens
                completion_tokens = getattr(usage, "completion_tokens", 0)
                record["attributes"]["prompt_tokens"] = prompt_tokens
                record["attributes"]["completion_tokens"] = completion_tokens
                record["attributes"]["cost_usd"] = round(cost_of(response.model, prompt_tokens, completion_tokens), 6)
        return response

    setattr(owner, method_name, wrapper)


def instrument_client(client):
    """Switch on automatic recording for every kind of model call the desk makes."""
    wrap_method(client.chat.completions, "create", "chat")
    wrap_method(client.chat.completions, "parse", "chat")
    wrap_method(client.moderations, "create", "moderation")
    wrap_method(client.embeddings, "create", "embedding")
# --- instrument end ---


setup_logging()
