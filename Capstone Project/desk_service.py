"""
desk_service.py - the capstone support desk as a web service, on the engine of your choice

This is the service from Module 07, with one change: the desk behind it is the guarded desk (pipeline.py) running
on the ENGINE you pick with the DESK_ENGINE setting: plain, sdk, langgraph or crewai. Everything else is as in Module 07:

  - authentication      : callers must send an API key
  - rate limiting       : one noisy caller cannot use up the whole OpenAI budget
  - idempotency         : a repeated request does not refund an order twice
  - a safe fallback     : if anything breaks, the customer is handed to a person instead of getting an error
  - observability       : every request is traced, logged, priced, and sometimes graded
  - human approval      : an admin endpoint approves refunds that are above the automatic limit
  - a kill switch       : an admin can switch the AI off, and every email goes to a person
  - customer feedback   : thumbs up or down, tied to the request id

Run it in the Module 06 environment (venv-frameworks), from the repo root or from this folder:
    python "Capstone Project/desk_service.py"                       (the default engine)
    $env:DESK_ENGINE = "crewai"; python "Capstone Project/desk_service.py"     (PowerShell: another engine)
Then open http://127.0.0.1:8000/docs. FastAPI builds a page there where you can try every endpoint.
(Use the development keys: 'dev-client-key' for customers, 'dev-admin-key' for the admin endpoints.)
"""

import logging
import os
import threading
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

import engines
import observe
import shop
import guards
import metrics
import pipeline
import quality
from reliability import IdempotencyStore, RateLimiter

# ===========================================================================
# Configuration: settings come from environment variables, never from the code
# ===========================================================================
# --- config start ---
ENVIRONMENT = os.getenv("DESK_ENV", "development")  # set DESK_ENV=production on a real server

# WHICH ENGINE answers the emails: plain, sdk, langgraph or crewai. The guardrails, the tracing and everything
# else in this file are identical for all four. Changing the engine is one setting, DESK_ENGINE.
ENGINE_NAME = os.getenv("DESK_ENGINE", "langgraph")
engine = engines.load(ENGINE_NAME)
RATE_LIMIT_PER_MINUTE = int(os.getenv("DESK_RATE_LIMIT", "30"))

# Two kinds of keys: client keys (customers' apps) and admin keys (your staff).
# The development keys below are public knowledge, because they are in this file. NEVER use them on a real server.
DEV_CLIENT_KEY = "dev-client-key"
DEV_ADMIN_KEY = "dev-admin-key"


def read_keys(env_name, development_key):
    """Read a comma separated list of keys from an environment variable."""
    keys = []
    for part in os.getenv(env_name, "").split(","):
        if part.strip() != "":
            keys.append(part.strip())

    if len(keys) == 0:
        keys.append(development_key)  # so the service works on your laptop with no setup
    return keys


CLIENT_KEYS = read_keys("DESK_API_KEYS", DEV_CLIENT_KEY)
ADMIN_KEYS = read_keys("DESK_ADMIN_KEYS", DEV_ADMIN_KEY)


def check_config():
    """Refuse to start a production server that still uses the public development keys."""
    if ENVIRONMENT == "production":
        if DEV_CLIENT_KEY in CLIENT_KEYS or DEV_ADMIN_KEY in ADMIN_KEYS:
            raise SystemExit("Set DESK_API_KEYS and DESK_ADMIN_KEYS before running with DESK_ENV=production.")


check_config()
# --- config end ---

# The desk keeps its state (refunds, the evidence log, the approval queue) in module-level lists.
# So the service handles ONE email at a time. A real system would keep this state in a database instead.
desk_lock = threading.Lock()
idempotency = IdempotencyStore()
limiter = RateLimiter(RATE_LIMIT_PER_MINUTE)
shop.VERBOSE = False  # the service writes logs, not print() lines

# The kill switch: when it is on, the desk does not use the AI at all and every email goes to a person.
# An admin can flip it while the service is running (see the /kill-switch endpoint). Start with it on: DESK_KILL_SWITCH=on
state = {"kill_switch": os.getenv("DESK_KILL_SWITCH", "off") == "on"}


# ===========================================================================
# The heart of the service: handle one email, completely traced
# ===========================================================================
# --- process start ---
def process_email(email, customer_id="anonymous"):
    """Handle one customer email. Whatever happens, this returns an answer and never raises an error."""
    with desk_lock:
        refunds_before = len(shop.REFUNDS)
        pending_before = list(guards.PENDING_APPROVALS)

        # Everything inside this block belongs to ONE trace, saved when the block ends.
        with observe.trace("support_email", customer_id=customer_id, engine=ENGINE_NAME,
                           email_redacted=observe.redact_for_logs(email)[:1000]) as request:
            if state["kill_switch"]:
                # The kill switch is on: no AI at all. Every email goes straight to a person.
                result = {"status": "human", "route": "", "reply": "", "evidence": "",
                          "note": "The desk is switched off, so a person will answer this email."}
            else:
                try:
                    result = pipeline.handle_email(email, engine)  # the guarded desk, on the chosen engine
                except Exception as error:
                    # The safe fallback: OpenAI is down, the budget ran out, a bug... The customer is not left with an error.
                    # The email goes to a person, and we log what went wrong.
                    message = type(error).__name__ + ": " + str(error)
                    observe.log(logging.ERROR, "desk_failed", error=message)
                    request.status = "error"
                    request.error = message
                    request.set(degraded=True)
                    result = {"status": "human", "route": "", "reply": "", "evidence": "",
                              "note": "The desk had a problem, so a person will answer this email."}

            # What did THIS request change? (The lists are shared by all requests, so compare before and after.)
            refunds_issued = []
            for refund in shop.REFUNDS[refunds_before:]:
                refunds_issued.append(refund["order_id"])
            sent_for_approval = []
            for order_id in guards.PENDING_APPROVALS:
                if order_id not in pending_before:
                    sent_for_approval.append(order_id)

            request.set(outcome=result["status"], route=result["route"], refunds=refunds_issued,
                        pending=sent_for_approval, note=result["note"][:200],
                        reply_redacted=observe.redact_for_logs(result["reply"])[:1000],
                        evidence_redacted=observe.redact_for_logs(result["evidence"])[:1000])

    totals = request.totals()
    return {
        "request_id": request.id,
        "status": result["status"],
        "reply": result["reply"],
        "route": result["route"],
        "note": result["note"],
        "refunds_issued": refunds_issued,
        "sent_for_approval": sent_for_approval,
        "cost_usd": totals["cost_usd"],
        "latency_ms": request.duration_ms,
        "evidence": result["evidence"],  # kept for the quality judge. It is not part of the API response.
    }
# --- process end ---


# ===========================================================================
# What goes in and out of the API. Pydantic checks every request automatically.
# ===========================================================================
# --- models start ---
class EmailRequest(BaseModel):
    email: str = Field(min_length=1, max_length=20000)  # an empty or gigantic body is rejected with a 422 error
    customer_id: str = "anonymous"


class EmailResponse(BaseModel):
    request_id: str                # quote this id when you report a problem: it finds the trace
    status: str                    # replied, blocked or human
    reply: str
    route: str
    note: str
    refunds_issued: list[str]
    sent_for_approval: list[str]
    cost_usd: float
    latency_ms: int


class FeedbackRequest(BaseModel):
    request_id: str
    rating: Literal["up", "down"]
    comment: str = ""


class ApprovalRequest(BaseModel):
    approver: str = Field(min_length=1)  # who is approving? It goes in the audit trail
# --- models end ---


# ===========================================================================
# Authentication: who is calling?
# ===========================================================================
# --- auth start ---
def require_client(x_api_key: str | None = Header(default=None)):
    """Customers' apps must send their key in the X-API-Key header. Returns a short name for the caller."""
    if x_api_key is None or x_api_key not in CLIENT_KEYS:
        raise HTTPException(status_code=401, detail="Missing or invalid API key.")
    return x_api_key[:6] + "..."  # never put a whole key in a log


def require_admin(x_api_key: str | None = Header(default=None)):
    """Admin endpoints need an admin key. A customer key is not enough (403 = known, but not allowed)."""
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing API key.")
    if x_api_key not in ADMIN_KEYS:
        raise HTTPException(status_code=403, detail="This endpoint needs an admin key.")
    return x_api_key[:6] + "..."
# --- auth end ---


# ===========================================================================
# The endpoints
# ===========================================================================
app = FastAPI(title="Support desk", version=observe.VERSIONS["code_version"])


# --- endpoints start ---
@app.get("/health")
def health():
    """Is the service alive? Hosting platforms call this address every few seconds."""
    return {"status": "ok", "engine": ENGINE_NAME, **observe.VERSIONS}


@app.post("/emails", response_model=EmailResponse)
def post_email(body: EmailRequest, background: BackgroundTasks, caller: str = Depends(require_client),
               idempotency_key: str | None = Header(default=None)):
    """Send a customer email to the desk. Add an 'Idempotency-Key' header to make retries safe."""
    if not limiter.allow(caller):
        raise HTTPException(status_code=429, detail="Too many requests. Wait a minute and try again.",
                            headers={"Retry-After": "60"})

    # Seen this exact request before? Return the saved answer and do NOTHING again (no second refund).
    saved_key = None
    if idempotency_key is not None:
        saved_key = caller + ":" + idempotency_key
        saved = idempotency.get(saved_key)
        if saved is not None:
            return saved

    outcome = process_email(body.email, body.customer_id)

    response = {}
    for field in EmailResponse.model_fields:
        response[field] = outcome[field]
    if saved_key is not None:
        idempotency.put(saved_key, response)

    # Grade a sample of real replies AFTER the customer has their answer. It costs money, so only some.
    if outcome["status"] == "replied" and quality.should_sample(quality.SAMPLE_RATE):
        background.add_task(quality.run_online_judge, outcome["request_id"], observe.redact_for_logs(body.email),
                            outcome["reply"], outcome["evidence"])
    return response


@app.post("/feedback")
def post_feedback(body: FeedbackRequest, caller: str = Depends(require_client)):
    """The customer rates a reply. This is the most honest quality signal there is."""
    observe.append_json_line("feedback.jsonl", {
        "time": observe.now_text(),
        "request_id": body.request_id,
        "rating": body.rating,
        "comment": observe.redact_for_logs(body.comment)[:500],
    })
    observe.log(logging.INFO, "feedback_received", judged_request=body.request_id, rating=body.rating)
    return {"saved": True}


@app.get("/approvals")
def get_approvals(admin: str = Depends(require_admin)):
    """Admin: which refunds are waiting for a person to approve them?"""
    return {"waiting": list(guards.PENDING_APPROVALS)}


@app.post("/approvals/{order_id}/approve")
def approve(order_id: str, body: ApprovalRequest, admin: str = Depends(require_admin)):
    """Admin: approve a waiting refund. This is the only way a refund over the limit can be issued."""
    with desk_lock:
        with observe.trace("approval", order_id=order_id, approver=body.approver):
            message = guards.approve_refund(order_id, approver=body.approver)
    return {"result": message}


class KillSwitchRequest(BaseModel):
    on: bool


@app.post("/kill-switch")
def set_kill_switch(body: KillSwitchRequest, admin: str = Depends(require_admin)):
    """Admin: switch the AI off (every email goes to a person) or back on. Something is wrong? Flip this first."""
    state["kill_switch"] = body.on
    observe.audit("kill_switch_changed", on=body.on, changed_by=admin)
    return {"kill_switch": state["kill_switch"]}


@app.get("/metrics")
def get_metrics(admin: str = Depends(require_admin)):
    """Admin: the numbers from the logs, and any alerts that fired."""
    report = metrics.load_report()
    alerts = []
    if report["requests"] > 0:
        alerts = metrics.check_alerts(report, metrics.DEFAULT_LIMITS)
    return {"report": report, "alerts": alerts}
# --- endpoints end ---


if __name__ == "__main__":
    import uvicorn

    observe.log(logging.INFO, "service_starting", environment=ENVIRONMENT, **observe.VERSIONS)
    uvicorn.run(app, host=os.getenv("DESK_HOST", "127.0.0.1"), port=int(os.getenv("DESK_PORT", "8000")))
