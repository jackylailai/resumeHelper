# Product Roadmap

## Phase 0 - Done

Spec-kit, project skeleton, agent guidance, and CI groundwork.

---

## Phase 1 - Core POC - Done

Single-user local app:

| Area | Status |
|------|--------|
| Profile library | Multi-profile CRUD, PDF upload, default profile |
| JD scoring | Three-tier scoring with profile-scoped cache |
| Resume generation | Background tailoring and generated resume storage |
| History | History and submittable views |
| PDF download | Generated resume PDF endpoint |

---

## Phase 2.5 - Job Intelligence Workbench - In Progress

| Area | Status |
|------|--------|
| Scrapers | 104 and Yourator implemented; LinkedIn deferred |
| JD Database | Stored listings browser, filters, pagination |
| Batch scoring | Score selected listings and link `job_analysis_id` |
| Application tracker | Track planned/applied/interviewing/rejected/offer/archived opportunities |
| E2E | Playwright suite with isolated testcontainers DB |
| Operations | Health live/ready, request IDs, optional management auth |

---

## Phase 2 - Deployable Service

Goal: run behind a reverse proxy on a VPS or home server.

- Docker app deployment path
- Explicit production CORS configuration
- Management auth enabled for write operations
- Reverse proxy with TLS termination
- Backup/restore workflow for Postgres and generated files

---

## Phase 3 - Multi-User / High-Concurrency

Goal: support multiple users and longer-running LLM workloads.

- User accounts and ownership on profiles, analyses, listings, and applications
- Redis or equivalent queue for async evaluation/tailoring
- Worker pool for LLM calls and PDF generation
- LLM audit log for token cost, latency, and prompt version tracking
- Blob storage for uploaded/generated PDFs
- DB pooling and deployment scaling guidance

---

## Deferred

- Resume version comparison UI
- LinkedIn scraper completion
- Kubernetes manifests
- n8n re-introduction as an optional external workflow service
