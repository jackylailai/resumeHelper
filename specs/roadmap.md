# Product Roadmap

## Phase 0 — Done ✅
Spec-kit, project skeleton, agent roles, CI/CD groundwork.

---

## Phase 1 — POC (目標：我自己可以用) 🔜
**Single-user, runs on local Mac, no cloud needed.**

| Task | Description |
|------|-------------|
| Schema rewrite | Replace 4-table design with `baseline_profile` + `job_analyses` + `generated_resumes` |
| API rewrite | `POST /api/profile`, `POST /api/evaluate`, `POST /api/callback`, `GET /api/history` |
| ClaudeCLIClient | Scoring via `claude --print` (no API key) |
| n8n workflow | Resume generation triggered by webhook; prompt editable in n8n UI |
| Basic UI | Paste JD → see score → copy generated resume |
| docker compose | `up -d postgres n8n` → `uvicorn` → done |

**Done when**: paste a real JD → get score → if score ≥ 60 → get tailored resume.

---

## Phase 2 — Infra (local → deployable)
**Goal: runnable on a VPS or home server, not just this Mac.**

### 2a. LLM 解耦
- 加 `LLM_BACKEND` env var 切換：`claude_cli` (local) / `anthropic` / `groq`
- 加 `GroqLLMClient`（免費層，適合部署用）
- **LangChain** 取代手寫 prompt 渲染：
  - `PromptTemplate` 管理 `modes/` 內容
  - `StructuredOutputParser` 取代手動 `json.loads`
  - streaming support（`StreamingStdOutCallbackHandler`）
  - LangSmith tracing（評分品質追蹤）

### 2b. Reverse proxy / Ingress
```
Internet → nginx (port 80/443)
              ├── /api/*    → FastAPI (port 8000)
              ├── /n8n/*    → n8n (port 5678)
              └── /*        → static files
```
- `nginx` 加進 `docker-compose.yml`
- SSL termination（Let's Encrypt / Cloudflare）
- Rate limiting at nginx layer（`limit_req_zone`）

### 2c. 部署方式
- `Dockerfile` for FastAPI backend
- `docker-compose.prod.yml` 與 dev 版分開
- `.env.prod` 範本
- health check endpoint 供 uptime monitor 使用

---

## Phase 3 — High-Concurrency Architecture
**Goal: support multiple users, handle LLM latency without blocking.**

### 問題診斷
目前瓶頸：
1. LLM call 每次 5-30 秒 → 同步等待佔用 worker
2. FastAPI BackgroundTasks 在同一個 process → crash 會遺失 job
3. 單一 PostgreSQL connection → 高併發時 connection 耗盡

### 解法架構

```
Client
  │
  ▼
nginx (rate limit, SSL termination)
  │
  ▼
FastAPI (stateless, multiple replicas)
  │  POST /api/evaluate → 立即回 202 + job_id
  │  enqueue to ──────────────────────────┐
  ▼                                       ▼
PostgreSQL (job_analyses)         Redis (task queue)
  ▲                                       │
  │                               Celery Workers (N replicas)
  │                                       │
  └───────── update job status ◄──────────┘
                                          │
                                    LLM (Anthropic / Groq)
                                          │
                                    n8n (resume generation)
```

### 元件說明

| 元件 | 用途 | 替代方案 |
|------|------|----------|
| **Redis** | Celery broker + result backend | RabbitMQ |
| **Celery** | Async LLM worker pool | RQ (更簡單), Dramatiq |
| **pgBouncer** | DB connection pooling | SQLAlchemy pool settings |
| **LangChain** | LLM 抽象 + streaming + retry | LlamaIndex |
| **nginx** | Ingress + rate limit + SSL | Traefik, Caddy |
| **Kubernetes** | 水平擴展 worker + API | Docker Swarm |

### Kubernetes Ingress（最終形態）
```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    nginx.ingress.kubernetes.io/rate-limit: "20"        # req/s per IP
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
spec:
  rules:
    - host: resumehelper.yourdomain.com
      http:
        paths:
          - path: /api
            backend: {service: {name: fastapi, port: 8000}}
          - path: /n8n
            backend: {service: {name: n8n, port: 5678}}
```

Workers 可以獨立 scale：
```bash
kubectl scale deployment celery-worker --replicas=10
```

### 效能目標（Phase 3）
| Metric | 目標 |
|--------|------|
| API response time (POST /api/evaluate) | < 200ms（只驗證 + enqueue） |
| LLM job completion | < 30s P95 |
| Concurrent users | 100+ |
| DB connections | pgBouncer pool ≤ 20 connections |

---

## 執行順序

```
Phase 1 (POC)
  └── 能用就好，local only

Phase 2a (LangChain + LLM switch)
  └── 讓 LLM 部分可以不依賴 local claude CLI

Phase 2b (nginx ingress)
  └── 可以從外部 access，有 SSL

Phase 2c (Dockerfile + prod compose)
  └── 可以部署到任何 VPS

Phase 3 (Redis + Celery + k8s)
  └── 真正的高併發，需要明確的 user 量目標再設計
```

---

## README 更新時機

- **現在**：不急，會被大改
- **Phase 1 完成後**：補 quickstart（`docker compose up` → open browser）
- **Phase 2 完成後**：補部署說明

