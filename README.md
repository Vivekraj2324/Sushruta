# 🏥 Sushruta — Clinical Workflow Automation Platform

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Render-00c7b7?style=for-the-badge&logo=render&logoColor=white)](https://sushruta-bzgf.onrender.com/)
[![API Docs](https://img.shields.io/badge/Swagger%20Docs-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://sushruta-bzgf.onrender.com/docs)
[![License: MIT](https://img.shields.io/badge/License-MIT-teal.svg?style=for-the-badge)](LICENSE)

> **"Every clinical note tells a patient's story. Sushruta ensures physicians spend their time treating, not documenting."**
> 
> Named after **Sushruta** (सुश्रुत, c. 6th century BCE), the ancient Indian physician regarded as the "Father of Surgery" and author of the **Suśruta Saṁhitā** — one of the foundational texts of medicine and surgery.
>
> Sushruta is a production-grade clinical workflow automation platform that streamlines patient management, AI-assisted SOAP documentation (Scribe), drug interaction checking, referral letter generation, and intelligent medical document querying (RAG) for healthcare professionals. Built with a fully asynchronous Python backend (FastAPI), modern EHR dashboard, and PostgreSQL (pgvector).

🌐 **Live Application:** [https://sushruta-bzgf.onrender.com](https://sushruta-bzgf.onrender.com)  
📑 **Interactive API Docs:** [https://sushruta-bzgf.onrender.com/docs](https://sushruta-bzgf.onrender.com/docs)

---

## ✦ System Architecture

```mermaid
graph TD
    classDef client fill:#1c1917,stroke:#0d9488,stroke-width:1px,color:#ede9e0;
    classDef api fill:#0f172a,stroke:#38bdf8,stroke-width:1px,color:#ede9e0;
    classDef service fill:#1e1b4b,stroke:#818cf8,stroke-width:1px,color:#ede9e0;
    classDef db fill:#064e3b,stroke:#34d399,stroke-width:1px,color:#ede9e0;
    classDef external fill:#27272a,stroke:#71717a,stroke-width:1px,color:#ede9e0;

    Client[Web Dashboard Client<br/>Web Speech API / SPA]:::client
    FastAPI[FastAPI Router Layer<br/>JWT Auth / Correlation ID Middleware]:::api
    Cache[RAG Cache<br/>AsyncTTLCache / In-Memory]:::api
    Orch[Service Layer<br/>SQLAlchemy Async / python]:::service
    Supabase[(PostgreSQL Database<br/>& pgvector Vector Store)]:::db
    GeminiEmbed[Gemini text-embedding-004<br/>vector generation]:::external
    GeminiLLM[Gemini 2.5 Flash<br/>Multi-Agent clinical reasoning]:::external

    Client -- 1. Uploads / Queries --> FastAPI
    FastAPI -- 2. Checks Cache --> Cache
    Cache -- 3. Cache Hit (Sub-ms) --> Client
    FastAPI -- 4. Cache Miss / Writes Audit --> Supabase
    FastAPI -- 5. Triggers Scribe/RAG --> Orch
    Orch -- 6. Creates Embeddings --> GeminiEmbed
    Orch -- 7. Runs Vector Search --> Supabase
    Orch -- 8. Prompts (Registry v1) --> GeminiLLM
    Orch -- 9. Commits audit logs --> Supabase
    Orch -- 10. Stores in Cache & Returns --> FastAPI
    FastAPI -- 11. Renders grounded output --> Client
```

---

## ✦ AI & RAG Pipeline Flow

Sushruta automates clinical administrative tasks through a structured AI and RAG pipeline:

```mermaid
sequenceDiagram
    autonumber
    actor Doctor as Client
    participant API as FastAPI API Layer
    participant Cache as AsyncTTLCache
    participant Scribe as AI Scribe (SOAP Note Writer)
    participant RAG as RAG Service
    participant Registry as Prompts Registry (v1)
    participant Gemini as Gemini 2.5 Flash

    Note over Doctor, Gemini: Flow A: SOAP Note Generation
    Doctor->>API: POST /api/v1/notes/generate (Transcript + Voice)
    API->>Registry: Fetch "note_writer" prompt (v1)
    API->>Gemini: generate_content (SOAP note instructions)
    Gemini-->>API: Structured SOAP draft (Subjective, Objective, Assessment, Plan)
    API-->>Doctor: SOAP clinical note draft

    Note over Doctor, Gemini: Flow B: RAG Question Answering (Document Q&A)
    Doctor->>API: POST /api/v1/patients/{id}/ask (Question)
    API->>Cache: Lookup cached query "rag:patient_id:question"
    alt Cache Hit
        Cache-->>API: Grounded RAGAnswerResponse
        API-->>Doctor: Cached Answer & Sources (<5ms)
    else Cache Miss
        API->>RAG: search_similar_chunks (Query embedding -> pgvector similarity)
        RAG-->>API: Top-K retrieved chunks with similarity scores
        API->>Registry: Fetch "rag_qa" prompt (v1)
        API->>Gemini: generate_content (context chunks + query)
        Gemini-->>API: Grounded text answer citing source documents
        API->>Cache: Store RAGAnswerResponse
        API-->>Doctor: Grounded Answer & Source Citations
    end
```

---

## ✦ Key Engineering Features

1.  **Centralized Versioned Prompts Registry (`app/ai/prompts.py`):** Decoupled prompt engineering from service logic, centralizing note-writer, drug-checker, referral-writer, and RAG Q&A prompts with version mapping (e.g. `v1`) to prevent code drift and support future A/B testing.
2.  **Asynchronous In-Memory TTL Caching (`app/core/cache.py`):** Implemented a zero-dependency async TTL cache (`AsyncTTLCache`) for vector retrieval/LLM query responses, dropping repeat query latencies to sub-milliseconds. Integrates patient-prefix invalidation (`rag:{patient_id}:*`) whenever documents are re-processed, maintaining cache freshness.
3.  **API Resilience (Tenacity Retries):** Wrapped all external Gemini generation and embedding SDK calls with `tenacity` exponential backoffs, shielding the application from rate limits (HTTP 429) and network failures.
4.  **Structured JSON Logging & Correlation Tracing (`app/core/logging_config.py`):** Inject correlation IDs in FastAPI middleware, store them via `contextvars`, and output structured JSON logs, mapping API requests, DB sessions, and AI tasks to a single trace path.
5.  **Programmatic RAG Evaluation Pipeline (`tests/evaluate_rag.py`):** Built a programmatic validation suite assessing Context Recall and Answer Faithfulness against reference ground-truth datasets, outputting JSON and Markdown reports.
6.  **EHR Web Dashboard Single Page Application (`frontend/`):** FastAPI mounts a premium dark-themed clinical SPA directly at root, featuring medical teal/slate aesthetics, drag-and-drop file ingestion, RAG chat, drug interaction pills, and voice dictation using the Web Speech API.

---

## ✦ Directory Structure

```text
├── alembic/                    # Database migration scripts
│   ├── env.py                  # Async migration environment config
│   └── versions/               # Auto-generated migration files
├── app/
│   ├── ai/                     # AI/LLM & RAG components
│   │   ├── agents/             #   Clinical Scribe, Drug Checker, Referral, Summarizer agents
│   │   ├── chunker.py          #   Sentence-aware chunking
│   │   ├── embeddings.py       #   Embedding generation (Resilient retries)
│   │   ├── prompts.py          #   Centralized prompt registry & versioning
│   │   └── retriever.py        #   pgvector cosine similarity search
│   ├── api/v1/                 # Versioned API routes (REST endpoints)
│   ├── core/                   # Caching, structured logs, and dependencies
│   │   ├── audit.py            #   Atomic transaction audit logging
│   │   ├── cache.py            #   Asynchronous TTL Cache
│   │   ├── logging_config.py   #   Structured JSON log formatting & Correlation tracing
│   │   ├── dependencies.py     #   FastAPI JWT authentication DI
│   │   └── security.py         #   Bcrypt direct hashing
│   ├── db/
│   │   ├── database.py         #   Async database engine & pool configuration
│   │   └── models.py           #   SQLAlchemy Mapped models (Soft deletes & pgvector)
│   ├── schemas/                # Pydantic validation schemas
│   ├── services/               # Decoupled business logic services
│   │   ├── rag_service.py      #   RAG Pipeline & document processing orchestrator
│   │   └── patient_service.py  #   Patient record management
│   ├── config.py               # Pydantic settings loading from env
│   └── main.py                 # FastAPI application setup & middleware loading
├── frontend/                   # Premium EHR SPA client dashboard (HTML/CSS/JS)
├── tests/                      # Pytest unit and integration test suites
│   ├── conftest.py             #   Test configurations & SQLite in-memory overrides
│   ├── evaluate_rag.py         #   Programmatic RAG evaluation pipeline script
│   └── test_rag.py             #   RAG API endpoint tests
├── docker-compose.yml          # Local dev PostgreSQL service
├── requirements.txt            # Python dependencies list
└── README.md                   # ← You are here
```

---

## ✦ Environment Variables

The application can be configured by adding a `.env` file in the root directory:

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `DATABASE_URL` | PostgreSQL connection string (asyncpg driver) | `postgresql+asyncpg://sushruta:sushruta_dev_password@localhost:5432/sushruta` |
| `SECRET_KEY` | JWT signing secret key | *(Required for token signing)* |
| `ALGORITHM` | JWT token encryption algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| JWT validity expiration duration in minutes | `30` |
| `GEMINI_API_KEY` | Google AI Studio Gemini API key | *(Required for AI/RAG)* |
| `ENVIRONMENT` | Runtime context environment | `development` / `production` |
| `UPLOAD_DIR` | Directory on disk to store clinical uploads | `uploads` |
| `MAX_FILE_SIZE_MB` | Maximum size limits on incoming files | `10` |

---

## ✦ Getting Started

### Prerequisites
*   Python 3.12
*   Docker & Docker Compose

### 1. Clone the repository
```bash
git clone https://github.com/Vivekraj2324/Sushruta.git
cd Sushruta
```

### 2. Activate Virtual Environment & Install Dependencies
```bash
# Windows
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Linux / macOS
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Spin up PostgreSQL Database
```bash
docker compose up -d
```

### 4. Apply Database Migrations
```bash
alembic upgrade head
```

### 5. Launch the Server
```bash
uvicorn app.main:app --reload
```
For local development:
*   Local application server: **http://localhost:8000**
*   Interactive OpenAPI Swagger docs: **http://localhost:8000/docs**
*   Alternative ReDoc documentation: **http://localhost:8000/redoc**

For the live production deployment:
*   Live production server: **[https://sushruta-bzgf.onrender.com](https://sushruta-bzgf.onrender.com)**
*   Production OpenAPI Swagger docs: **[https://sushruta-bzgf.onrender.com/docs](https://sushruta-bzgf.onrender.com/docs)**

---

## ✦ Production Deployment (Render + Supabase)

### 1. Database Setup (Supabase)
1. Create a free project on [Supabase](https://supabase.com).
2. Enable `pgvector` in the **SQL Editor**:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Copy your database connection URI from **Connect** → **Session pooler** (IPv4).

### 2. Web Service Setup (Render)
1. Create a new **Web Service** on [Render](https://render.com) and connect your GitHub repository (`Vivekraj2324/Sushruta`).
2. Select **Runtime:** `Docker` and **Plan:** `Free`.
3. Set the following **Environment Variables**:

| Variable | Value / Description |
| :--- | :--- |
| `DATABASE_URL` | `postgresql+asyncpg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres` |
| `SECRET_KEY` | *(A secure 32+ character random string)* |
| `GEMINI_API_KEY` | *(Google AI Studio Gemini API Key)* |
| `ENVIRONMENT` | `production` |

4. Click **Deploy Web Service**. Render will automatically build the Docker image, run migrations, and launch the application.

---

## ✦ Testing & Evaluation

### Run standard tests
```bash
pytest -v
```

### Run programmatic RAG evaluation pipeline
```bash
python -m tests.evaluate_rag
```
This prints the context recall and faithfulness metrics tabular report to stdout and writes the results to `rag_eval_results.json` and `rag_eval_results.md`.

---

## ✦ Author & Contributor
* **Vivek Raj** — [@Vivekraj2324](https://github.com/Vivekraj2324) — [thevivek2324@gmail.com](mailto:thevivek2324@gmail.com)

---

## ✦ License
Sushruta is open-source software licensed under the [MIT License](LICENSE).
