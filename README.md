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

- **Core Principles**: ReAct loops, planning, self-reflection, and decision-making logic.
- **Tool Use & Function Calling**: Integrating APIs, databases, web scraping, and code execution.
- **Memory Systems**: Short-term conversational context vs. long-term semantic retrieval (Vector DBs).
- **Multi-Agent Orchestration**: Building collaborative agent swarms and supervisor-worker hierarchies.
- **Evaluation & Guardrails**: Preventing hallucinations, detecting prompt injections, and benchmarking accuracy.
- **Production Deployment**: Containerizing agents with Docker, exposing endpoints via FastAPI, and setting up monitoring & tracing.

---

## 🗺️ Curriculum Roadmap

| Module | Topic | Description | 
|---|---|---|
| **01** | **[Introduction to Agentic AI](Introduction%20to%20Agentic%20AI/README_Concepts.md)** | Setup, LLM API basics, message roles, memory, tokens and cost, parameters, streaming | 
| **02** | **[Tool Calling & Integrations](Tool%20Calling%20and%20Integrations/README_Concepts.md)** | Structured output, function calling, real API tools, and a hand-built agent loop | 
| **03** | **Agent Memory & Retrieval (RAG)** | Short-term buffer, summary memory, and vector-backed persistent store | 
| **04** | **Multi-Agent Architectures** | Hierarchical teams, swarm patterns, and handoffs | 
| **05** | **Agent Guardrails & Evals** | Input/output filtering, rate limiting, and evaluation benchmarks | 
| **06** | **Production Deployment & Observability** | Dockerizing, FastAPI service, CI/CD, and live tracing |

---

## 🛠️ Tech Stack

- **Language**: Python 3.10+
- **Agent Frameworks**: LangChain / LangGraph, CrewAI, AutoGen
- **LLM Providers**: OpenAI, Anthropic, Google Gemini, Ollama (Local LLMs)
- **Vector Databases**: ChromaDB / Pinecone / Qdrant
- **Observability & Tracing**: LangSmith / Phoenix / OpenTelemetry
- **Deployment**: Docker, FastAPI, GitHub Actions, AWS / GCP / Fly.io

---

## 📋 Prerequisites

- Basic understanding of **Python** (functions, async, type hints).
- Familiarity with basic **REST APIs** and JSON data.
- Basic terminal and **Git** commands.
- An API key for at least one major model provider (e.g., OpenAI, Anthropic, or Gemini) or a local LLM setup via Ollama.

---

## 📂 Repository Structure

```text
AgenticAI/
├── modules/
│   ├── 01_foundations/         # Core concepts & minimal agent from scratch
│   ├── 02_tools_integration/   # Tool calling and custom APIs
│   ├── 03_memory_and_rag/      # Memory buffers and Vector DB integration
│   ├── 04_multi_agent_teams/   # Multi-agent collaboration patterns
│   ├── 05_evals_and_safety/    # Guardrails and benchmark evaluations
│   └── 06_production_deploy/   # Docker, FastAPI server, CI/CD configs
├── capstone_project/           # End-to-end production-ready agent application
├── notebooks/                  # Interactive Jupyter notebooks for quick experimentation
├── tests/                      # Automated unit and integration tests
├── .env.example                # Template for required environment variables
├── requirements.txt            # Python dependencies
└── README.md                   # You are here!
```

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

### 4. Configure environment variables
Create a `.env` file from the example template:
```bash
cp .env.example .env
```
Add your model API keys (e.g., `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`) inside `.env`.

### 5. Run your first agent
```bash
python modules/01_foundations/basic_react_agent.py
```

---

## 🏆 Capstone Project

By the end of the course, you will build and deploy a **Production Autonomous Research & Action Agent**:
- Capable of planning multi-step web searches and synthesis.
- Validated with automated unit/safety tests and evals.
- Packaged as a containerized FastAPI microservice.
- Instrumented with real-time token tracing and observability in a live cloud environment.

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