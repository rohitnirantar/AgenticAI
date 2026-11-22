# 🤖 Agentic AI: From Zero to Live Production

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

Welcome to **Agentic AI: From Zero to Live Production**! 

This repository houses a comprehensive, hands-on curriculum that takes you from the foundational concepts of Agentic AI and autonomous systems all the way to architecting, evaluating, and deploying your first production-grade AI agent to the cloud.

---

## 📌 Table of Contents

- [About the Course](#-about-the-course)
- [What You Will Learn](#-what-you-will-learn)
- [Curriculum Roadmap](#-curriculum-roadmap)
- [Tech Stack](#-tech-stack)
- [Prerequisites](#-prerequisites)
- [Repository Structure](#-repository-structure)
- [Getting Started](#-getting-started)
- [Capstone Project](#-capstone-project)
- [Contributing](#-contributing)
- [License](#-license)

---

## 📖 About the Course

Unlike traditional LLM prompt engineering, **Agentic AI** systems reason, plan, use external tools, maintain memory, and collaborate autonomously to achieve complex goals. 

Moving from local prototyping to a reliable production environment introduces unique challenges: non-deterministic loops, hallucinated tool calls, latency, rate limits, security guardrails, and observability. 

This repository provides step-by-step code, architectural blueprints, and reproducible notebooks to bridge the gap between AI experimentation and live production deployments.

---

## 🎯 What You Will Learn

- **Core Principles**: How LLM APIs work (roles, tokens, parameters, streaming) and how to build the agent loop yourself in plain Python.
- **Tool Use & Function Calling**: Structured output, calling your own functions and real APIs, and keeping tools safe.
- **Memory Systems**: Short-term conversation memory, embeddings, retrieval over your own documents (RAG), and long-term memory across sessions.
- **Multi-Agent Orchestration**: Specialist agents, routers and handoffs, managers and workers, and writer and reviewer loops.
- **Evaluation & Guardrails**: Defending against prompt injection and data leaks, limiting what agents can do, and measuring accuracy with evals.
- **Agent Frameworks**: What frameworks give you, what they cost, and how the OpenAI Agents SDK, LangGraph and CrewAI compare on the same support desk.
- **Production Deployment** *(coming)*: Containerizing agents with Docker, exposing endpoints via FastAPI, and setting up logging, cost tracking and tracing.

---

## 🗺️ Curriculum Roadmap

| Module | Topic | Description | 
|---|---|---|
| **01** | **[Introduction to Agentic AI](Introduction%20to%20Agentic%20AI/README_Concepts.md)** | Setup, LLM API basics, message roles, memory, tokens and cost, parameters, streaming | 
| **02** | **[Tool Calling & Integrations](Tool%20Calling%20and%20Integrations/README_Concepts.md)** | Structured output, function calling, real API tools, and a hand-built agent loop | 
| **03** | **[Agent Memory & Retrieval (RAG)](Agent%20Memory%20and%20Retrieval/README_Concepts.md)** | Short-term memory, embeddings, RAG over your own documents, and long-term memory across sessions | 
| **04** | **[Multi-Agent Architectures](Multi-Agent%20Architectures/README_Concepts.md)** | Specialist agents, router and handoff, manager and workers, and writer and reviewer | 
| **05** | **[Agent Guardrails & Evals](Agent%20Guardrails%20and%20Evals/README_Concepts.md)** | Input, tool and output guardrails, human approval, step and token budgets, test suites (evals), and LLM-as-judge | 
| **06** | **[Agent Frameworks](Agent%20Frameworks/README_Concepts.md)** | Types of frameworks, why they exist, what they add and cost, with the OpenAI Agents SDK, LangGraph and CrewAI | 
| **07** | **Production Deployment & Observability** *(coming)* | Dockerizing, FastAPI service, logging, cost tracking, and a live deployment |
| **Capstone** | **One project, built in each framework** *(coming)* | The support desk rebuilt in each framework, scored with the same evals and compared |

---

## 🛠️ Tech Stack

- **Language**: Python 3.10+
- **Modules 01 to 05**: plain Python with the `openai` package, `pydantic` and `python-dotenv`. No agent framework is needed, so you see exactly how everything works.
- **LLM Provider**: OpenAI (Module 01 also shows Gemini and OpenRouter calls)
- **Agent Frameworks** *(Module 06 and the capstone)*: OpenAI Agents SDK, LangGraph, CrewAI. They need their **own virtual environment** with pinned versions (see the Module 06 page).
- **Deployment and Observability** *(Module 07)*: Docker, FastAPI, structured logging, and a free-tier cloud host

---

## 📋 Prerequisites

- Basic understanding of **Python** (functions, async, type hints).
- Familiarity with basic **REST APIs** and JSON data.
- Basic terminal and **Git** commands.
- An **OpenAI API key**. Modules 02 to 05 use only OpenAI. (Module 01 also shows how to call Gemini and OpenRouter.)

---

## 📂 Repository Structure

```text
AgenticAI/
├── Introduction to Agentic AI/     # Module 01: setup, API basics (notebook + concepts page)
├── Tool Calling and Integrations/  # Module 02: structured output, tools, agent loop (+ real-life scripts)
├── Agent Memory and Retrieval/     # Module 03: memory, embeddings, RAG (+ support assistant script)
├── Multi-Agent Architectures/      # Module 04: router, manager, reviewer (+ support desk script)
├── Agent Guardrails and Evals/     # Module 05: guardrails, evals, judges (+ guarded desk and eval scripts)
├── Agent Frameworks/               # Module 06: Agents SDK, LangGraph, CrewAI (+ its own requirements.txt)
├── .env.example                    # Template for required environment variables
├── requirements.txt                # Python dependencies for Modules 01 to 05
└── README.md                       # You are here!
```

Every module folder has a `README_Concepts.md`. Read it first, then open the notebooks in order. Module 06 uses its own environment (`venv-frameworks`), because agent frameworks need different package versions. Module 07 and the capstone will be added as they are finished.

---

## 🚀 Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/rohitnirantar/AgenticAI.git
cd AgenticAI
```

### 2. Set up a virtual environment
```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```
This covers Modules 01 to 05. **Module 06 (Agent Frameworks) needs its own environment**, with setup steps on its [concepts page](Agent%20Frameworks/README_Concepts.md#setup-a-separate-environment).

### 4. Configure environment variables
Create a `.env` file from the example template:
```bash
cp .env.example .env
```
Add your model API keys (e.g., `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`) inside `.env`.

### 5. Start learning, or run a complete example
Start with the [Module 01 concepts page](Introduction%20to%20Agentic%20AI/README_Concepts.md), then open its notebook.

Or jump straight to a working multi-agent support desk:
```bash
python "Multi-Agent Architectures/support_desk.py"
```

---

## 🏆 Capstone Project

The course follows one online shop and its **customer support desk** from a single API call to a multi-agent system with guardrails. The capstone builds the same support desk **once in each popular framework** (LangGraph, CrewAI and the OpenAI Agents SDK), next to the plain-Python version from Module 04:
- Every version is scored with the **same evals** from Module 05, so the comparison is based on measurements.
- The comparison covers quality, cost, speed, and how much code each one needs.
- The best fit is packaged as a containerized FastAPI service with logging and cost tracking in a live cloud environment.

---

## 🤝 Contributing

Contributions, feedback, and discussion are welcome! 
If you find a bug or have an idea for an improvement:
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

**Author**: [Rohit Nirantar](https://github.com/rohitnirantar)  
*If you find this repository helpful, consider starring ⭐ the repo!*