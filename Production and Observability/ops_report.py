"""
ops_report.py - what do the logs say about how the desk is doing?

A real-life flow for the person on call: read the logs, see the dashboard, see which alerts fired,
find the requests worth looking at, and look inside the slowest one. Nothing here calls OpenAI, so it is free.

    python "Production and Observability/ops_report.py"
    python "Production and Observability/ops_report.py" sample_logs      (a folder of logs to read)
"""

import sys

import observe
import metrics

sys.stdout.reconfigure(encoding="utf-8")


def main():
    log_dir = None
    if len(sys.argv) > 1:
        log_dir = sys.argv[1]
        observe.set_log_dir(log_dir)

    traces = metrics.load_json_lines("traces.jsonl")
    report = metrics.load_report()

    if report["requests"] == 0:
        print("No requests in " + str(observe.LOG_DIR) + ". Run simulate_traffic.py first.")
        return

    print("=== DASHBOARD (" + str(observe.LOG_DIR.name) + ") ===")
    metrics.print_dashboard(report)

    print("\n=== ALERTS ===")
    alerts = metrics.check_alerts(report, metrics.DEFAULT_LIMITS)
    if len(alerts) == 0:
        print("None. All numbers are inside their limits.")
    for alert in alerts:
        print("! " + alert)

    # Requests that a person should read: a thumbs down, a low judge score, or an error
    flagged = {}
    for item in metrics.load_json_lines("feedback.jsonl"):
        if item["rating"] == "down":
            flagged[item["request_id"]] = "customer gave a thumbs down"
    for item in metrics.load_json_lines("quality.jsonl"):
        if item["score"] <= 2:
            flagged[item["request_id"]] = "the judge scored it " + str(item["score"]) + "/5"
    for record in traces:
        if record["name"] == "support_email" and record["status"] == "error":
            flagged[record["request_id"]] = "the request failed: " + record["error"][:60]

    print("\n=== WORTH A LOOK (" + str(len(flagged)) + ") ===")
    for record in traces:
        if record["request_id"] in flagged:
            print("- " + record["request_id"] + ": " + flagged[record["request_id"]])
            print("    email: " + record["attributes"]["email_redacted"][:90].replace("\n", " "))
            print("    reply: " + record["attributes"].get("reply_redacted", "")[:90].replace("\n", " "))

    # Where did the slowest request spend its time?
    slowest = None
    for record in traces:
        if record["name"] == "support_email":
            if slowest is None or record["duration_ms"] > slowest["duration_ms"]:
                slowest = record
    print("\n=== THE SLOWEST REQUEST ===")
    print(observe.format_trace(slowest))

    print("\n=== AUDIT TRAIL (last 6 events) ===")
    for event in metrics.load_json_lines("audit.jsonl")[-6:]:
        details = ""
        for key in event:
            if key not in ("time", "event", "request_id"):
                details = details + " " + key + "=" + str(event[key])
        print("  " + event["time"] + "  " + event["event"].ljust(26) + details)


if __name__ == "__main__":
    main()
