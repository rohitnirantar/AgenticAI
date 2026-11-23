"""
metrics.py - turn many traces into numbers, alerts and a dashboard

One trace answers "what happened to this request?". Metrics answer "how is the desk doing?":
how much does it cost, how fast is it, how often do the guardrails fire, are customers happy?

Everything is computed from the log files that observe.py wrote, with plain loops.
"""

import json
import math
from pathlib import Path

import observe


def load_json_lines(file_name, log_dir=None):
    """Read a .jsonl file (one JSON record per line). A missing file means no records yet."""
    folder = observe.LOG_DIR
    if log_dir is not None:
        folder = Path(log_dir)

    path = folder / file_name
    records = []
    if not path.exists():
        return records

    with open(path, encoding="utf-8") as file:
        for line in file:
            if line.strip() != "":
                records.append(json.loads(line))
    return records


# --- percentile start ---
def percentile(values, p):
    """The value that p percent of the numbers are at or below. p95 of latencies = 'almost everyone waited less than this'.
    The average hides slow requests. Percentiles show them."""
    if len(values) == 0:
        return 0
    ordered = sorted(values)
    position = math.ceil(p / 100 * len(ordered))  # for 20 values, p95 is the 19th smallest
    if position < 1:
        position = 1
    if position > len(ordered):
        position = len(ordered)
    return ordered[position - 1]
# --- percentile end ---


def top_level_stage(span_record, spans_by_id):
    """Which top-level stage does this span belong to? A model call inside an agent belongs to that agent."""
    current = span_record
    while current["parent"] is not None:
        current = spans_by_id[current["parent"]]
    return current["name"]


# --- report start ---
def build_report(traces, feedback, grades, audit_events):
    """Compute the numbers that describe how the desk is doing."""
    requests = []
    judge_cost = 0.0
    for record in traces:
        if record["name"] == "support_email":
            requests.append(record)
        if record["name"] == "judge":
            judge_cost = judge_cost + record["totals"]["cost_usd"]

    report = {"requests": len(requests)}
    if len(requests) == 0:
        return report

    outcomes = {}
    errors = 0
    latencies = []
    cost_total = 0.0
    cost_by_day = {}
    cost_by_model = {}
    cost_by_stage = {}
    time_by_stage = {}
    stage_count = {}
    prompt_tokens = 0
    completion_tokens = 0
    rewrites = 0
    output_rejections = 0
    block_reasons = {}

    for record in requests:
        outcome = record["attributes"].get("outcome", "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        if record["status"] == "error" or record["attributes"].get("degraded", False):
            errors = errors + 1

        latencies.append(record["duration_ms"])
        cost_total = cost_total + record["totals"]["cost_usd"]
        prompt_tokens = prompt_tokens + record["totals"]["prompt_tokens"]
        completion_tokens = completion_tokens + record["totals"]["completion_tokens"]

        day = record["started_at"][:10]
        cost_by_day[day] = cost_by_day.get(day, 0.0) + record["totals"]["cost_usd"]

        spans_by_id = {}
        for item in record["spans"]:
            spans_by_id[item["id"]] = item

        for item in record["spans"]:
            if item["parent"] is None:  # top-level stages: where does the TIME go?
                name = item["name"]
                time_by_stage[name] = time_by_stage.get(name, 0) + item["duration_ms"]
                stage_count[name] = stage_count.get(name, 0) + 1

            if item["name"] == "rewrite_reply":
                rewrites = rewrites + 1
            if item["name"] == "output_guard" and item["attributes"].get("ok") is False:
                output_rejections = output_rejections + 1
            if item["name"] == "input_guards" and item["attributes"].get("allowed") is False:
                reason = item["attributes"].get("reason", "")[:40]
                block_reasons[reason] = block_reasons.get(reason, 0) + 1

            if item["kind"] == "model":  # where does the MONEY go?
                model = item["attributes"].get("model", "unknown")
                item_cost = item["attributes"].get("cost_usd", 0.0)
                cost_by_model[model] = cost_by_model.get(model, 0.0) + item_cost
                stage = top_level_stage(item, spans_by_id)
                cost_by_stage[stage] = cost_by_stage.get(stage, 0.0) + item_cost

    report["outcomes"] = outcomes
    report["errors"] = errors
    report["latency_ms"] = {
        "average": round(sum(latencies) / len(latencies)),
        "p50": percentile(latencies, 50),
        "p95": percentile(latencies, 95),
        "max": max(latencies),
    }
    report["cost"] = {
        "total": round(cost_total, 4),
        "average": round(cost_total / len(requests), 5),
        "by_day": cost_by_day,
        "by_model": cost_by_model,
        "by_stage": cost_by_stage,
        "judge_overhead": round(judge_cost, 4),
    }
    report["tokens"] = {"prompt": prompt_tokens, "completion": completion_tokens}

    average_time_by_stage = {}
    for name in time_by_stage:
        average_time_by_stage[name] = round(time_by_stage[name] / stage_count[name])
    report["average_ms_by_stage"] = average_time_by_stage

    report["guardrails"] = {
        "blocked": outcomes.get("blocked", 0),
        "sent_to_human": outcomes.get("human", 0),
        "reply_rewrites": rewrites,
        "output_rejections": output_rejections,
        "block_reasons": block_reasons,
    }

    # Money: from the audit trail
    refunds = {"issued": 0, "held": 0, "approved": 0, "dollars": 0.0}
    for event in audit_events:
        if event["event"] == "refund_issued":
            refunds["issued"] = refunds["issued"] + 1
            refunds["dollars"] = refunds["dollars"] + event["amount"]
        if event["event"] == "refund_held_for_approval":
            refunds["held"] = refunds["held"] + 1
        if event["event"] == "refund_approved":
            refunds["approved"] = refunds["approved"] + 1
    report["refunds"] = refunds

    # What customers say
    thumbs_up = 0
    thumbs_down = 0
    for item in feedback:
        if item["rating"] == "up":
            thumbs_up = thumbs_up + 1
        if item["rating"] == "down":
            thumbs_down = thumbs_down + 1
    report["feedback"] = {"up": thumbs_up, "down": thumbs_down}

    # What the judge says
    scores = []
    low_scoring = []
    for item in grades:
        scores.append(item["score"])
        if item["score"] <= 2:
            low_scoring.append(item["request_id"])
    report["quality"] = {"graded": len(scores), "low_scoring": low_scoring}
    if len(scores) > 0:
        report["quality"]["average_score"] = round(sum(scores) / len(scores), 2)

    return report


def load_report(log_dir=None):
    """Read the log files and build the report in one step."""
    return build_report(
        load_json_lines("traces.jsonl", log_dir),
        load_json_lines("feedback.jsonl", log_dir),
        load_json_lines("quality.jsonl", log_dir),
        load_json_lines("audit.jsonl", log_dir),
    )
# --- report end ---


# --- alerts start ---
# The limits that, when crossed, mean "a person should look at this". Tune them to your own traffic.
DEFAULT_LIMITS = {
    "max_average_cost": 0.02,       # dollars per request
    "max_daily_cost": 5.00,         # dollars per day
    "max_p95_latency_ms": 25000,    # 95 out of 100 customers should wait less than this
    "max_error_rate": 0.05,         # 5% of requests failing is too many
    "max_block_rate": 0.15,         # a jump in blocked emails can mean an attack
    "max_human_rate": 0.30,         # too many handed to people means the desk is not coping
    "min_average_quality": 4.0,     # the judge's average score
    "max_thumbs_down_rate": 0.25,   # share of customer feedback that is negative
}


def check_alerts(report, limits):
    """Compare the report with the limits. Returns a list of warnings (an empty list means all is well)."""
    alerts = []
    if report["requests"] == 0:
        return ["No requests were logged."]

    total = report["requests"]

    if report["cost"]["average"] > limits["max_average_cost"]:
        alerts.append("Average cost per request is $" + format(report["cost"]["average"], ".4f")
                      + " (limit $" + format(limits["max_average_cost"], ".4f") + ")")

    for day in report["cost"]["by_day"]:
        if report["cost"]["by_day"][day] > limits["max_daily_cost"]:
            alerts.append("Spend on " + day + " was $" + format(report["cost"]["by_day"][day], ".2f")
                          + " (limit $" + format(limits["max_daily_cost"], ".2f") + ")")

    if report["latency_ms"]["p95"] > limits["max_p95_latency_ms"]:
        alerts.append("Slow: p95 latency is " + str(report["latency_ms"]["p95"]) + " ms (limit "
                      + str(limits["max_p95_latency_ms"]) + " ms)")

    if report["errors"] / total > limits["max_error_rate"]:
        alerts.append("Errors: " + str(report["errors"]) + " of " + str(total) + " requests failed")

    if report["guardrails"]["blocked"] / total > limits["max_block_rate"]:
        alerts.append("Blocked emails: " + str(report["guardrails"]["blocked"]) + " of " + str(total)
                      + ". Is someone attacking the desk?")

    if report["guardrails"]["sent_to_human"] / total > limits["max_human_rate"]:
        alerts.append("Handed to humans: " + str(report["guardrails"]["sent_to_human"]) + " of " + str(total))

    quality = report["quality"]
    if quality["graded"] > 0 and quality["average_score"] < limits["min_average_quality"]:
        alerts.append("Quality: the judge's average score is " + str(quality["average_score"])
                      + " (minimum " + str(limits["min_average_quality"]) + ")")

    votes = report["feedback"]["up"] + report["feedback"]["down"]
    if votes > 0 and report["feedback"]["down"] / votes > limits["max_thumbs_down_rate"]:
        alerts.append("Customers: " + str(report["feedback"]["down"]) + " of " + str(votes) + " ratings are thumbs down")

    return alerts
# --- alerts end ---


# --- dashboard start ---
def print_dashboard(report):
    """Print the report as a small text dashboard."""
    if report["requests"] == 0:
        print("No requests were logged yet.")
        return

    print("REQUESTS   " + str(report["requests"]) + "   outcomes: " + str(report["outcomes"]))
    print("ERRORS     " + str(report["errors"]))
    print()

    latency = report["latency_ms"]
    print("SPEED      average " + str(latency["average"]) + " ms   p50 " + str(latency["p50"])
          + " ms   p95 " + str(latency["p95"]) + " ms   slowest " + str(latency["max"]) + " ms")
    print("           average time per stage (ms):")
    for name in report["average_ms_by_stage"]:
        print("             " + name.ljust(24) + str(report["average_ms_by_stage"][name]).rjust(6))
    print()

    cost = report["cost"]
    print("COST       total $" + format(cost["total"], ".4f") + "   average $" + format(cost["average"], ".5f")
          + " per request   judge overhead $" + format(cost["judge_overhead"], ".4f"))
    print("           by stage:")
    for name in cost["by_stage"]:
        print("             " + name.ljust(24) + "$" + format(cost["by_stage"][name], ".4f"))
    print("           by model:")
    for name in cost["by_model"]:
        print("             " + name.ljust(24) + "$" + format(cost["by_model"][name], ".4f"))
    print()

    guard = report["guardrails"]
    print("GUARDRAILS blocked " + str(guard["blocked"]) + "   to a human " + str(guard["sent_to_human"])
          + "   reply rewrites " + str(guard["reply_rewrites"]) + "   output rejections " + str(guard["output_rejections"]))
    refunds = report["refunds"]
    print("REFUNDS    issued " + str(refunds["issued"]) + " ($" + format(refunds["dollars"], ".2f") + ")   held for approval "
          + str(refunds["held"]) + "   approved by a human " + str(refunds["approved"]))
    print("CUSTOMERS  thumbs up " + str(report["feedback"]["up"]) + "   thumbs down " + str(report["feedback"]["down"]))

    quality = report["quality"]
    if quality["graded"] > 0:
        print("QUALITY    judge average " + str(quality["average_score"]) + " over " + str(quality["graded"])
              + " graded replies   low scores: " + str(quality["low_scoring"]))
    else:
        print("QUALITY    no replies were graded yet")
# --- dashboard end ---


# --- eval_case start ---
def trace_to_eval_case(record, name, status, refunds, pending, text, forbidden):
    """Turn a real request that went wrong (or was interesting) into a test case for the Module 05 evals.
    The trace gives us the email. A HUMAN decides what the right outcome should have been."""
    return {
        "name": name,
        "email": record["attributes"]["email_redacted"],  # personal data is already removed from the trace
        "status": status,        # the acceptable outcomes: replied, blocked or human
        "refunds": refunds,      # orders that must be refunded
        "pending": pending,      # orders that must be waiting for a human
        "text": text,            # a word the reply must contain ("" = no check)
        "forbidden": forbidden,  # words the reply must never contain
    }
# --- eval_case end ---
