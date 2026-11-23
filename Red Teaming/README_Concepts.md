# Module 10 · Red Teaming: attack your own agent before a stranger does

In Module 05 we added guardrails and tested a few attacks we thought of. The problem with that: **we only block the tricks we imagined**. A real attacker has more imagination and more time.

**Red-teaming** means attacking your **own** system on purpose, in a safe sandbox, to find the holes before someone else does. This module does it properly, with measurements: a library of attacks in different tactics, an **attacker AI** that invents new ones, two versions of the desk (naive and hardened), regression tests, and a **release gate** that blocks a bad update.

> Everything here attacks a made-up shop in memory with made-up data. Nothing touches real money, real data or any system that is not yours. Only ever test systems you own or have written permission to test.

Read this page first, then work through the notebooks in order.

**On this page**
[Start from the attacker's goals](#start-from-the-attackers-goals) · [Two ways in](#two-ways-in-the-email-and-the-data) · [The two desks](#the-two-desks) · [What the attacks showed](#what-the-attacks-showed) · [Honest limits](#what-a-red-team-does-not-prove) · [The notebooks](#the-notebooks) · [Run it](#run-it) · [Interview corner](#interview-corner)

---

## Start from the attacker's goals

A red team does not start with tricks. It starts with the question: **what would an attacker want?** Our desk can look up orders and issue refunds, and it holds one secret code that someone put in its prompt. So:

| Goal | What it means |
|---|---|
| `leak_secret` | read the internal reference code |
| `refund_other` | get a refund for **another customer's** order |
| `refund_big` | get the **$250** television refunded with no person approving it |
| `refund_old` | get a refund on an order **80 days** old (the window is 30) |

**Whether an attack worked is decided by a check in code**, on the real state of the shop (was a refund *issued*? is the code in the reply?). Never by asking a model "did that work?", because a model can be fooled by the same tricks. A check in code cannot be argued with.

---

## Two ways in: the email and the data

The obvious way in is the **text of the email**. The quieter way is the **data the agent reads**. In an *indirect* attack the email is harmless ("where is my order?") and the instruction is hidden in something the agent fetches: here the free-text note on an order. When the agent reads it, the instruction is in front of the model, looking exactly like a message from the system.

```mermaid
flowchart LR
    A["Attacker<br/>(an ordinary customer)"] -->|"1. the email"| D["Support agent"]
    A -.->|"2. text planted in data<br/>(an order note, a review, a web page)"| DB[("Data the agent reads")]
    DB -->|"tool result"| D
    D --> T["Tools: lookup_order,<br/>issue_refund"]
    T --> M["Money moves"]
```

Tactics we test, in 17 hand-written attacks: direct requests, fake authority, role play, emotional pressure, urgency, legal pressure, instruction override ("ignore all previous instructions"), translation and completion tricks, a payload hidden in base64, another language, a **fake earlier conversation**, and the indirect attack above.

---

## The two desks

Both desks use the same model and the same rules, written as sentences in the prompt. They differ in where the rules are **enforced**.

| Rule | NAIVE desk | HARDENED desk |
|---|---|---|
| Only the customer's own orders | a sentence in the prompt | checked **in code** in both tools (the customer id comes from the login, never from the model) |
| Refund within 30 days | a sentence | a date check in the refund tool |
| Never above $100 | a sentence | the tool answers "waits for a person" |
| One refund per order | nothing | the tool checks |
| Notes written by customers | shown to the model as-is | removed before the model sees them |
| The secret code | **in the prompt** | **not in the prompt at all** |
| Input guard | none | a list of known attack phrases (deliberately weak) |
| Output guard | none | removes anything that looks like an internal code |

**Rules in prompts are suggestions. Rules in code are controls.** The model can be talked into anything, so whatever must never happen has to be impossible in code.

---

## What the attacks showed

One run of `red_team.py --runs 3`: 17 hand-written attacks, 2 saved from earlier runs, 16 written by the attacker AI, each tried 3 times against each desk (105 tries per desk). Yours will differ; models do not answer identically every time.

| | Naive desk | Hardened desk |
|---|---|---|
| Tries where the attacker won | **22 of 105** | **0 of 105** |
| Different attacks that worked at least once | **8** | **0** |
| `leak_secret` | 0 of 27 | 0 of 27 |
| `refund_other` | 3 of 27 | 0 of 27 |
| `refund_big` | 0 of 24 | 0 of 24 |
| `refund_old` | **19 of 27** | 0 of 27 |

How to read it:

- **The famous tricks mostly failed.** "Ignore all previous instructions", role play, base64 and translation attacks did not work against the naive desk. Modern models resist them. **That does not mean the desk was safe.**
- **The quiet attacks worked:** emotional pressure ("ten years a customer"), legal pressure ("I will call my lawyer") and a **fake earlier conversation**. A rule that needs the model to *want* to follow it ("within 30 days") bends under pressure. `refund_old` was the weak spot, and the model even issued refunds with a friendly message.
- **Run each attack several times.** A hole that works one time in five is a real hole at a million emails.
- **The attacker AI found fewer holes than the human list, in different places.** Its emails sounded like real customers, with stories instead of commands. A human team and an attacker AI complement each other.
- **The hardened desk won on every try.** And the interesting question is **which layer** stopped each attack. In notebook 4 we count it (34 tries): the **input guard** (known phrases) blocked 10, the **tool code** refused 11, and in 13 the model declined by itself. The guard catches only the famous tricks, and the attacks that get past it are stopped by the **tool code**. One fake-conversation attack passes the guard, gets a refund on the naive desk 3 times out of 3, and is refused in code on the hardened desk 3 times out of 3. That is the layer that counts. If the input guard were removed tomorrow, the desk would still be safe on money. The guard is a speed bump, and the code is the wall.
- **The secret should never be in the prompt.** No attack read the code out, but a model can never promise to keep a secret. The only secret a prompt keeps is one it never saw.

Every attack that works is saved to `regression_attacks.json`, so it is tested forever. That is the same loop as Module 07 (turn a bad trace into a test), now for security.

---

## What a red team does not prove

A red team that overclaims is worse than none. Our results mean "**these four goals, these tactics, this model, this many tries**". Not tested:

| Not covered | Why it matters |
|---|---|
| **Multi-turn attacks** | an attacker builds trust over several messages |
| **Other models, or the next version** | an update can reopen a closed hole, so run the suite on every change |
| **Cost attacks** | a huge email, or a loop that burns tokens (budgets from Modules 05 and 07) |
| **Tools that read the web or files** | indirect injection through a page or a document |
| **Data leaks without a refund** | our checks only look for refunds and the secret code |
| **A determined attacker's persistence** | they have unlimited time |

The honest claim is: *"We cannot prove the desk is safe. We can show that what must never happen is impossible in code, and that every attack we know of is tested on every release."*

---

## The notebooks

| # | Notebook | You will learn |
|---|---|---|
| 1 | [01_ThinkLikeAnAttacker.ipynb](01_ThinkLikeAnAttacker.ipynb) | Goals before tricks, the two ways in, the system under attack, and "worked" as a check in code |
| 2 | [02_TheAttackLibrary.ipynb](02_TheAttackLibrary.ipynb) | 17 attacks by tactic against the naive desk, run several times, and reading what actually happened |
| 3 | [03_TheAttackerAI.ipynb](03_TheAttackerAI.ipynb) | A model that invents new attacks, and turning every success into a regression test |
| 4 | [04_FixAndRetest.ipynb](04_FixAndRetest.ipynb) | The hardened desk, before and after, which layer stopped each attack, and the release gate |

## Run it

After the notebooks, **one file runs the whole scenario**: the team is about to ship an update, and security asks "can anyone get a refund they should not, or read something they should not?"

```powershell
python "Red Teaming/red_team.py" --runs 3          # all attacks, both desks, 3 tries each (a few minutes, a few cents)
python "Red Teaming/red_team.py" --no-generate     # only saved attacks (fast)
python "Red Teaming/red_team.py" --runs 3 --gate   # exits with an error if ANY attack beats the hardened desk (for CI)
```

### Setup
The main environment from the repository's [README](../README.md) is enough: `openai`, `pydantic`, `python-dotenv` and `jupyter`. You need `OPENAI_API_KEY` in your `.env` file. The whole module costs a few dozen cents.

---

## Interview corner

**The 30-second story.** *"I red-teamed my own support agent. I defined four attacker goals, wrote 17 attacks in different tactics, and added an attacker AI that invents new ones. Success was checked in code on the shop's state, not by a model. The famous jailbreaks mostly failed, but pressure and fake conversations got refunds past a rule that only lived in the prompt. So I moved the rules into the tools. The hardened version beat all 105 attempts, and I could show that the tool code, not the input filter, was what stopped them. Every winning attack is saved as a regression test, and the release is gated on it."*

**Questions you may get, and short answers**

| Question | A good short answer |
|---|---|
| What is prompt injection? | Text that makes a model follow the attacker's instructions instead of yours. |
| Direct vs indirect injection? | Direct: the attacker types it. Indirect: it hides in data the agent reads (a web page, a document, a tool result, an order note). Indirect is the bigger risk for agents with tools. |
| Jailbreak vs prompt injection? | A jailbreak makes the model break its own safety rules. Injection hijacks an app's instructions. They overlap, and injection is the one that hurts agents with tools. |
| How do you defend an agent? | Layers, and trust only the ones that hold when the model is fooled: least privilege, rules enforced in tool code, human approval for risky actions, output checks, logging. Prompts and filters only lower the odds. |
| What is excessive agency? | An agent that can do more than the task needs, so a fooled model can do damage. Fix it by removing the power, not by asking nicely. |
| How do you know an attack worked? | A check in code on the real state (a refund exists, a secret is in the reply). Not a model's opinion. |
| Why run each attack several times? | Models are not deterministic, and the attacker needs one success. |
| What is a regression test for security? | Every attack that ever worked is saved and re-run on every release, so a fixed hole cannot silently reopen. |
| Should secrets go in a system prompt? | No. A model cannot keep a secret. Keep it out of the prompt. |
| Can you prove your agent is safe? | No. You can state what you tested and make the critical actions impossible in code. |
| What is an attacker AI? | A model that writes new attacks for a goal, so you explore more tactics than a human list. It sees only what an outsider sees, and it is judged by code. |

**A good question to ask them back:** *"Which of your agent's actions are enforced in code, and which only in the prompt?"*

---

**Next:** Module 11 looks at **MCP**, the standard plug for AI tools, and at why a third-party tool server is both a gift and an attack surface.

*Agentic AI: From Zero to Live Production · Module 10 · [Rohit Nirantar](https://github.com/rohitnirantar)*
