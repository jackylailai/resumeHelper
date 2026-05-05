# 🧠 AI Career Intelligence System

> A hybrid AI workflow system for job matching and resume optimization, combining SDD architecture, LLM reasoning, and workflow automation.

---

## 🚀 Motivation

This project is inspired by agent-based resume optimization tools.

Recently, I needed to apply for jobs and realized:

* Resume tailoring is repetitive
* Job matching is time-consuming
* Most tools are either too manual or too "black-box"

So I decided to build:

> **A controllable AI system that can parse jobs, evaluate fit, and iteratively improve resumes — while also exploring modern AI + system design patterns**

---

## 🎯 Goals

* Build a **production-style backend system (SDD-driven)**
* Integrate **LLM for decision-making (not control flow)**
* Use **n8n for workflow automation**
* Experiment with **agent-based interaction (Discord + natural language)**
* Deploy on **Kubernetes for scalability**

---

## 🧱 System Architecture

### High-level Design

```mermaid
flowchart TB
    User --> Ingress
    Ingress --> API[FastAPI (SDD Core)]

    API --> Workflow[Workflow Engine]
    Workflow --> Redis[(Redis)]
    Workflow --> DB[(PostgreSQL)]

    Workflow --> LLM[LLM Service]
    LLM --> OpenAI[LLM API]

    API --> Queue[(Kafka / Redis Stream)]
    Queue --> Worker[Async Worker]

    Worker --> DB
    Worker --> Redis

    n8n[n8n Workflow] --> API
    n8n --> LLM
```

---

## 🧩 Core Concepts

### SDD (System Design Driven)

* Workflow is controlled by backend (not LLM)
* Explicit state machine
* Deterministic orchestration

---

### LLM Usage

LLM is used for:

* Job description parsing
* Resume matching / scoring
* Explanation generation

LLM is **NOT used for:**

* Workflow control
* State management

---

### n8n (Workflow Layer)

Used for:

* Job ingestion (scraping / API)
* Automation pipelines
* External integrations

---

### Agent (Future Extension)

* Discord bot
* Natural language commands:

  * “re-score this job”
  * “rewrite my resume for backend role”
* Controlled via backend API

---

## 🧪 Tech Stack

### Backend (Core)

* Python (FastAPI)
* Pydantic (schema validation)
* SQLAlchemy

---

### AI Layer

* LLM API (OpenAI / Anthropic)
* Prompt templates
* (Optional) LangChain (for experimentation only)

---

### Workflow / Automation

* n8n (Docker-based workflow engine)

---

### State & Data

* PostgreSQL (persistent storage)
* Redis (state machine / cache / idempotency)

---

### Async Processing

* Kafka (or Redis Streams for simpler setup)
* Worker service (Python)

---

### Infra

* Docker
* Kubernetes (EKS / GKE / local k3d)

---

### Dev Tooling

* Claude Code (agent-assisted development)
* Spec Kit (spec-driven workflow)

---

## 🛠 Development Phases

---

### Phase 1 — Minimal AI API

* FastAPI
* `/evaluate` endpoint
* Call LLM directly

```text
Input: job + CV
Output: score + explanation
```

---

### Phase 2 — State Management (SDD)

* Introduce job_id
* Add Redis state machine

```text
INIT → PARSING → SCORING → DONE
```

---

### Phase 3 — Async Processing

* Introduce queue (Redis / Kafka)
* Add worker service

```text
API → Queue → Worker → LLM → DB
```

---

### Phase 4 — n8n Integration

* Use n8n to:

  * Fetch jobs
  * Trigger evaluation
  * Send notifications

---

### Phase 5 — Kubernetes Deployment

* Deploy:

  * FastAPI
  * n8n
  * Worker
  * Redis / DB

* Add:

  * HPA (auto scaling)
  * service separation

---

### Phase 6 — Agent Layer (Discord)

* Discord bot
* Natural language → API mapping

Examples:

```text
"Re-evaluate job 123"
"Optimize my resume for this JD"
```

---

## 🤖 Claude Code + Spec Kit

### Why

* Enforce structured development
* Define system behavior before implementation
* Assist with prompt + code generation

---

### Usage

* Define specs:

  * workflow.md
  * llm-contract.md
  * api-spec.yaml

* Claude Code:

  * generates code
  * refactors workflows
  * assists debugging

---

## 📂 Project Structure (Planned)

```text
backend/
  app/
    api/
    services/
    workflows/
    models/

  llm/
    prompts/
    parser.py
    scorer.py

  worker/
    consumer.py

infra/
  k8s/
  docker/

n8n/
  workflows/

specs/
  workflow.md
  state-machine.md
```

---

## 🔮 Future Improvements

* Resume auto-rewriting pipeline
* Multi-agent orchestration (LangGraph)
* Vector DB for job similarity
* Observability (Prometheus + Grafana)

---

## 🧠 Key Takeaways

This project focuses on:

* Separating **LLM reasoning** from **system control**
* Designing **stateful workflows**
* Building **scalable AI backend systems**

---

## 📌 Status

🚧 In Progress — actively building and iterating

---

## 📬 Notes

This is both:

* A **practical tool** for job applications
* A **technical playground** for modern AI system design

---
