"""
pipeline.py - the GUARDED support desk around any engine

An ENGINE is the middle of the desk: the part that routes an email to a specialist and writes a draft reply.
Four engines exist (plain Python, OpenAI Agents SDK, LangGraph, CrewAI). Each one is a module with:

    NAME : a short name, for example "sdk"
    run(email) -> {"route": "orders" | "policy" | "refund" | "human", "reply": "..."}

The guardrails from Module 05 and the spans from Module 07 sit AROUND the engine, here, in plain Python:

    Customer email
      -> input guards  (length, card numbers, moderation, prompt injection)
      -> ENGINE        (the framework under test; its tools enforce the refund limit)
      -> output guards (plain rules, then the reviewer; a rejected reply is rewritten, then a human takes over)
      -> reply

Because the guards do not live inside any framework, they protect all four engines in exactly the same way.
"""

import observe
import shop
import guards
import desk
import tools


# --- pipeline start ---
def handle_email(email, engine):
    """Handle one customer email with the guardrails on, using the given engine. Returns a dictionary describing
    what happened (the same shape as in Module 05, so the same evals can check it)."""
    shop.TOOL_RESULTS.clear()          # the evidence log starts empty for every email
    tools.ESCALATION["reason"] = ""

    # Layer 1: input guards, before any agent sees the message
    with observe.span("input_guards", kind="guard") as step:
        gate = guards.check_input(email)
        step["attributes"]["allowed"] = gate["allowed"]
        step["attributes"]["reason"] = gate["reason"]
    if not gate["allowed"]:
        return desk.make_result(email, "blocked", "", "", gate["reason"])
    text_for_agents = gate["email"]  # the card number, if any, is already removed

    # The engine: routing, specialists, tools (and the refund limit inside the tools: Layer 2)
    with observe.span("engine:" + engine.NAME, kind="engine"):
        answer = engine.run(text_for_agents)

    if answer["route"] == "human":
        note = tools.ESCALATION["reason"]
        if note == "":
            note = "The router sent this email to a person."
        return desk.make_result(email, "human", "human", "", note)

    # Layer 3: output guards. If a reply is rejected, only the WORDING is rewritten.
    draft = answer["reply"]
    evidence = "\n".join(shop.TOOL_RESULTS)
    note = ""
    for round_number in range(1, desk.MAX_ROUNDS + 1):
        with observe.span("output_guard", kind="guard", round=round_number) as step:
            check = guards.check_output(draft, evidence)
            step["attributes"]["ok"] = check["ok"]
            step["attributes"]["layer"] = check["layer"]
            step["attributes"]["problems"] = check["problems"]

        if check["ok"]:
            return desk.make_result(email, "replied", answer["route"], draft, "", evidence)

        note = check["problems"]
        if round_number < desk.MAX_ROUNDS:
            with observe.span("rewrite_reply", kind="step"):
                draft = desk.rewrite_reply(text_for_agents, draft, evidence, check["problems"])

    return desk.make_result(email, "human", answer["route"], "", note, evidence)
# --- pipeline end ---
