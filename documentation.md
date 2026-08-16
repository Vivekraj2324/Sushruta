# Sushruta — Engineering Documentation

> **Named after Sushruta (6th century BCE)** — Father of Surgery, author of the Sushruta Samhita.
> A production-grade AI platform for clinical workflow automation.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture Overview](#architecture-overview)
3. [Component Breakdown](#component-breakdown)
4. [Data Flow](#data-flow)
5. [Database Design](#database-design)
6. [Engineering Decision Log (ADRs)](#engineering-decision-log)
7. [Implementation Notes](#implementation-notes)
8. [Progress Log](#progress-log)
9. [Interview Notes](#interview-notes)
10. [Future Improvements](#future-improvements)

---

## Project Overview

### Problem
Doctors spend 3–6 hours daily on administrative work: reading patient records, writing clinical notes, checking drug interactions, writing referral letters. This time comes directly out of patient care, rest, and mental health.

### Solution
Sushruta automates clinical workflows via:
- Intelligent patient history retrieval (RAG)
- Automated clinical note generation
- Drug interaction checking with citations
- Referral letter generation
- Full audit trail for legal compliance

### Phase 1 Scope (Completed)
A fully functional, secure backend where doctors can register, login, manage patients, upload medical documents, with text extraction, soft deletes, and comprehensive audit logging. **No AI — pure backend engineering.**

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    CLIENT LAYER                               │
│           (Postman / Browser / Future Frontend)               │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS + JWT Bearer Token
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                     API LAYER (FastAPI)                        │
│                                                               │
│   app/api/v1/auth.py    ──  POST /register, /login, GET /me  │
│   app/api/v1/patients.py ── CRUD + pagination + search       │
│   app/api/v1/documents.py── Upload + list + get + delete     │
│                                                               │
│   Responsibility: HTTP only. No business logic.              │
│   Validates JWT via dependency injection.                    │
│   Validates body via Pydantic schemas.                       │
└────────────────────────┬─────────────────────────────────────┘
                         │ Calls
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   SERVICE LAYER                               │
│                                                               │
│   app/services/auth_service.py     ── Register, login, profile│
│   app/services/patient_service.py  ── CRUD + isolation       │
│   app/services/document_service.py ── Upload + extraction    │
│                                                               │
│   Responsibility: All business logic and rules.              │
│   Writes audit logs. Raises HTTP exceptions.                 │
└────────┬────────────────────────────────┬────────────────────┘
         │                                │
         ▼                                ▼
┌─────────────────────┐    ┌────────────────────────────────────┐
│    DATA LAYER        │    │         CORE LAYER                 │
│                      │    │                                    │
│ app/db/database.py   │    │ app/core/security.py  ── JWT+bcrypt│
│ app/db/models.py     │    │ app/core/dependencies.py ── Auth DI│
│                      │    │ app/core/audit.py     ── Audit log │
│ PostgreSQL 16        │    │                                    │
│ asyncpg + pool       │    │ Responsibility: Cross-cutting.     │
└──────────────────────┘    └────────────────────────────────────┘
```

### Key Architectural Principle
**Separation of Concerns** — Each layer has a single responsibility. The API layer never touches the database. The service layer never constructs HTTP responses. The core layer provides shared utilities without knowing who calls them.

---

## Component Breakdown

### 1. Configuration — `app/config.py`

**Purpose:** Centralised settings loaded from environment variables via Pydantic.

**Key Design:**
- `BaseSettings` with `SettingsConfigDict(env_file=".env")` — loads `.env` automatically.
- `@lru_cache()` on `get_settings()` — reads `.env` once, all code shares the same instance.
- Type validation at startup — misconfigurations fail fast, not at runtime.
- `max_file_size_bytes` property — converts MB to bytes for upload validation.

**Inputs:** Environment variables / `.env` file.
**Outputs:** Typed `Settings` object with validated fields.
**Scalability:** Adding a new setting = one line. No refactoring needed.

---

### 2. Database Engine — `app/db/database.py`

**Purpose:** Async SQLAlchemy engine, session factory, and DI dependency.

**Key Design:**
- `create_async_engine` with asyncpg — non-blocking I/O for all DB operations.
- Connection pooling: `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`.
- `async_sessionmaker` with `expire_on_commit=False` — prevents implicit lazy-load IO in async.
- `get_db()` async generator — yields session, rolls back on exception, always closes.

**Edge Cases:**
- `pool_pre_ping=True` — verifies connections are alive before use (handles DB restarts).
- `expire_on_commit=False` — without this, accessing ORM attributes after commit triggers implicit IO which fails in async context.

**Interview Q:** *"Why not use raw asyncpg?"* — SQLAlchemy provides ORM mapping, relationship loading, schema definition, and migration support (Alembic). Using raw asyncpg would require reimplementing all of this.

---

### 3. ORM Models — `app/db/models.py`

**Purpose:** SQLAlchemy 2.0 Mapped models defining all database tables.

**Tables:**
| Table | Records | Key Fields |
|-------|---------|------------|
| `doctors` | Medical practitioners | email (unique, indexed), license_number (unique, indexed), hashed_password |
| `patients` | Patient profiles | doctor_id (FK, CASCADE), is_active (soft delete) |
| `documents` | Uploaded files | patient_id + doctor_id (FK, CASCADE), processing_status pipeline |
| `clinical_notes` | AI-generated notes | Defined in Phase 1 for FK integrity, populated in Phase 3 |
| `audit_logs` | Immutable action log | doctor_id (nullable for system actions), indexed on action + created_at |

**Key Design Decisions:**
- `server_default=func.now()` — DB generates timestamps, not Python. Ensures consistency across app instances and avoids timezone bugs.
- `is_active` flag — soft deletes. Medical records must never be hard-deleted (legal compliance).
- `CASCADE` on FKs — when a doctor is deleted, all their data goes with them (ownership semantics).
- `Mapped[str | None]` — SQLAlchemy 2.0 typed column definitions with Python 3.10+ union syntax.
- `lazy="selectin"` — eager-loads relationships in 2 queries (avoids N+1 without blocking async).

---

### 4. Security — `app/core/security.py`

**Purpose:** Password hashing (bcrypt) and JWT token management.

**Functions:**
- `hash_password(password) → str` — bcrypt hash with random salt.
- `verify_password(plain, hashed) → bool` — constant-time comparison.
- `create_access_token(data, expires_delta?) → str` — JWT with {sub, email, exp, iat}.
- `decode_token(token) → dict | None` — verify signature + expiry, return payload or None.

**Key Decision:** Direct `bcrypt` library instead of `passlib` wrapper. `passlib`'s bcrypt handler is incompatible with `bcrypt>=5.0.0` (dropped `__about__` module). Using bcrypt directly is simpler and more reliable.

**Token Structure:**
```json
{
  "sub": "42",              // doctor_id as string
  "email": "dr@hospital.in", // for display/logging
  "exp": 1700000000,        // expiry (30 min from now)
  "iat": 1699998200          // issued-at
}
```

---

### 5. Auth Dependency — `app/core/dependencies.py`

**Purpose:** FastAPI dependency that validates JWT and returns the authenticated Doctor.

**Flow:**
```
HTTP Request → OAuth2PasswordBearer extracts Bearer token
            → decode_token() verifies signature + expiry
            → Extract doctor_id from "sub" claim
            → Query DB: SELECT * FROM doctors WHERE id = ?
            → Check is_active = True
            → Return Doctor ORM object
```

**Why query DB every request?** In a medical system, account deactivation must take effect immediately. Caching the doctor object would create a window where a deactivated doctor could still access patient data.

---

### 6. Audit Logging — `app/core/audit.py`

**Purpose:** Immutable audit trail for compliance and traceability.

**Design:**
- `create_audit_log()` adds an `AuditLog` entry to the **same DB session** as the triggering action.
- If the action commits → audit commits (atomicity).
- If the action rolls back → audit rolls back (consistency).
- `AuditAction` class — namespace of string constants preventing typos and enabling grep-ability.

**Actions Tracked:** `DOCTOR_REGISTERED`, `DOCTOR_LOGIN`, `PATIENT_CREATED`, `PATIENT_UPDATED`, `PATIENT_DELETED`, `DOCUMENT_UPLOADED`, `DOCUMENT_DELETED`, `DOCUMENT_PROCESSED`, `RAG_QUERY`.

---

### 7. RAG Intelligence — `app/ai/` + `app/services/rag_service.py` (Phase 2)

**Purpose:** Answer a doctor's questions about a patient's medical history using retrieval-augmented generation.

**Architecture:**
```
Doctor asks question
        │
        ▼
  Embed query (Gemini text-embedding-004, 768 dims)
        │
        ▼
  Search document_chunks (pgvector cosine distance, top-K)
  (filtered by patient_id + doctor_id)
        │
        ▼
  Assemble context from retrieved chunks
        │
        ▼
  Generate answer (Gemini 2.0 Flash)
  (clinical system prompt: grounded, cite sources, no hallucination)
        │
        ▼
  Return {answer, sources[], model, chunks_retrieved}
```

**Components:**
| File | Purpose |
|------|---------|
| `app/ai/chunker.py` | Sentence-aware text splitting with configurable overlap |
| `app/ai/embeddings.py` | Gemini embedding creation (single, query, batch) |
| `app/ai/retriever.py` | pgvector cosine similarity search with data isolation |
| `app/services/rag_service.py` | Full pipeline orchestration |
| `app/schemas/rag.py` | Pydantic models for request/response |
| `app/api/v1/rag.py` | 4 REST endpoints |

**Document Processing Pipeline:**
```
Upload → Text Extraction → Chunking → Batch Embedding → Store in document_chunks
         (Phase 1)          (Phase 2)   (Phase 2)         (Phase 2)
```

**Phase 2 API Endpoints:**

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/patients/{id}/ask` | Yes | RAG question answering |
| POST | `/api/v1/patients/{id}/documents/{doc_id}/process` | Yes | Chunk + embed document |
| GET | `/api/v1/patients/{id}/documents/{doc_id}/status` | Yes | Processing status |
| GET | `/api/v1/patients/{id}/documents/{doc_id}/chunks` | Yes | List document chunks |

---

## Data Flow

### Registration Flow
```
Doctor → POST /register → Pydantic validates body
       → auth_service.register_doctor()
       → Check email uniqueness (SELECT)
       → Check license uniqueness (SELECT)
       → hash_password() via bcrypt
       → INSERT INTO doctors
       → INSERT INTO audit_logs (DOCTOR_REGISTERED)
       → COMMIT
       → Return DoctorResponse (no password)
```

### Authentication Flow
```
Doctor → POST /login → Pydantic validates body
       → auth_service.authenticate_doctor()
       → SELECT FROM doctors WHERE email = ?
       → verify_password() via bcrypt.checkpw
       → Check is_active = True
       → create_access_token() → JWT signed with SECRET_KEY
       → INSERT INTO audit_logs (DOCTOR_LOGIN)
       → COMMIT
       → Return {access_token, token_type, doctor}
```

### Protected Request Flow
```
Doctor → GET /patients (Authorization: Bearer <token>)
       → OAuth2PasswordBearer extracts token
       → decode_token() verifies signature + expiry
       → SELECT FROM doctors WHERE id = sub_claim
       → Check is_active = True
       → Doctor object injected into route handler
       → patient_service.list_patients(doctor=doctor)
       → SELECT FROM patients WHERE doctor_id = ? AND is_active = True
       → Return paginated PatientListResponse
```

### Document Upload Flow
```
Doctor → POST /patients/{id}/documents (multipart/form-data)
       → Auth dependency validates JWT
       → document_service.upload_document()
       → Verify patient ownership (SELECT)
       → Validate file extension (.pdf, .png, .jpg, .docx)
       → Read file content, validate size (≤10MB)
       → Generate UUID filename, save to disk via aiofiles
       → Extract text (pypdf for PDF, python-docx for DOCX)
       → Set processing_status (ready/failed/uploaded)
       → INSERT INTO documents
       → INSERT INTO audit_logs (DOCUMENT_UPLOADED)
       → COMMIT
       → Return DocumentResponse
```

### RAG Processing Flow (Phase 2)
```
Doctor → POST /patients/{id}/documents/{doc_id}/process
       → Auth + ownership validation
       → Read document.extracted_text
       → chunk_text() → list of {chunk_text, chunk_index, token_count}
       → create_embeddings_batch() → list of 768-dim vectors
       → INSERT INTO document_chunks (one per chunk, with embedding)
       → Update document.processing_status → 'embedded'
       → INSERT INTO audit_logs (DOCUMENT_PROCESSED)
       → COMMIT
       → Return ProcessingStatusResponse
```

### RAG Question Flow (Phase 2)
```
Doctor → POST /patients/{id}/ask {"question": "What meds?"}
       → Auth + patient ownership validation
       → create_query_embedding(question) → 768-dim vector
       → pgvector cosine distance search on document_chunks
         WHERE patient_id = ? AND doctor_id = ?
         ORDER BY embedding <=> query_embedding ASC
         LIMIT top_k
       → Assemble context from top-K chunks
       → Gemini 2.0 Flash generate_content(
           system=RAG_SYSTEM_PROMPT,
           user=context + question
         )
       → INSERT INTO audit_logs (RAG_QUERY)
       → COMMIT
       → Return {answer, sources[], model, chunks_retrieved}
```

---

## Database Design

### Entity Relationship
```
doctors (1) ──< (N) patients ──< (N) documents ──< (N) document_chunks
   │                    │
   │                    └──< (N) clinical_notes (Phase 3)
   │
   └──< (N) audit_logs
```

### Tables

| Table | Records | Key Fields |
|-------|---------|------------|
| `doctors` | Medical practitioners | email (unique, indexed), license_number (unique, indexed), hashed_password |
| `patients` | Patient profiles | doctor_id (FK, CASCADE), is_active (soft delete) |
| `documents` | Uploaded files | patient_id + doctor_id (FK, CASCADE), processing_status pipeline |
| `document_chunks` | Chunked text with embeddings | document_id + patient_id + doctor_id (FK, CASCADE), embedding Vector(768) |
| `clinical_notes` | AI-generated notes | Defined in Phase 1 for FK integrity, populated in Phase 3 |
| `audit_logs` | Immutable action log | doctor_id (nullable for system actions), indexed on action + created_at |

### Soft Delete Strategy
- `is_active=True` (default) — record is visible.
- `is_active=False` — record is "deleted" but retained.
- All SELECT queries filter `WHERE is_active = True`.
- Hard deletes are never performed on medical records.
- Legal compliance: records can be subpoenaed even after "deletion".

### Indexing Strategy
- `doctors.email` — unique index for login lookups.
- `doctors.license_number` — unique index for registration checks.
- `patients.doctor_id` — B-tree index for ownership filtering.
- `documents.patient_id` — B-tree index for document listing.
- `documents.doctor_id` — B-tree index for ownership filtering.
- `document_chunks.document_id` — B-tree index for chunk-by-document lookups.
- `document_chunks.patient_id` — B-tree index for patient-scoped vector search.
- `document_chunks.doctor_id` — B-tree index for ownership isolation.
- `audit_logs.doctor_id` — for per-doctor audit trail queries.
- `audit_logs.action` — for action-type filtering.
- `audit_logs.created_at` — for time-range queries.

---

## Engineering Decision Log

### ADR-001: Async Throughout
**Decision:** Use async for everything — FastAPI, SQLAlchemy, asyncpg, aiofiles.
**Context:** A clinical system may have many concurrent doctor sessions. Blocking I/O would limit throughput.
**Alternatives:** Sync FastAPI + psycopg2. Simpler but blocks on every DB query.
**Tradeoff:** Async adds complexity (session management, `expire_on_commit=False`). Worth it for scalability.

### ADR-002: bcrypt Directly (Not passlib)
**Decision:** Use `bcrypt` library directly for password hashing.
**Context:** `passlib`'s bcrypt handler crashes with `bcrypt>=5.0.0` due to removed `__about__` module.
**Alternatives:** Pin `bcrypt<5.0.0`, or use `argon2-cffi`.
**Tradeoff:** Lose passlib's scheme auto-upgrade feature. Acceptable for a new system with a single scheme.

### ADR-003: Soft Deletes via is_active Flag
**Decision:** Never hard-delete medical records. Use `is_active=False`.
**Context:** Medical records are legally protected. Deletion could violate compliance requirements.
**Alternatives:** Hard delete with separate archive table. More complex, same legal outcome.
**Tradeoff:** Tables grow forever. Mitigated by archival jobs in production (Phase 4).

### ADR-004: In-Memory SQLite for Tests
**Decision:** Use `aiosqlite` for test database instead of requiring PostgreSQL.
**Context:** Tests should run anywhere (CI, laptop, no Docker needed).
**Alternatives:** PostgreSQL in Docker for tests. More realistic but slower and adds CI complexity.
**Tradeoff:** SQLite doesn't support pgvector — vector search is tested via API contract, not actual cosine similarity.

### ADR-005: server_default for Timestamps
**Decision:** Use `server_default=func.now()` instead of Python-side `default=datetime.utcnow`.
**Context:** Multiple app instances could have clock skew. DB server is the single source of truth.
**Alternatives:** Python `datetime.utcnow()` or `datetime.now(timezone.utc)`.
**Tradeoff:** Slightly harder to test (can't mock datetime). Worth it for correctness.

### ADR-006: UUID Filenames on Disk
**Decision:** Store uploaded files with UUID-based names, not original filenames.
**Context:** Original filenames can collide, contain special characters, or be used for path traversal attacks.
**Alternatives:** Hash-based naming (SHA256 of content). Deduplicates files but adds complexity.
**Tradeoff:** Disk usage isn't optimised (same file uploaded twice = two copies). Acceptable for Phase 1.

### ADR-007: Audit Logs in Same Transaction
**Decision:** Write audit log entries in the same DB session as the triggering action.
**Context:** If the action succeeds but audit fails (separate transaction), we have an unaudited action.
**Alternatives:** Async event queue for audit (Kafka/Redis). Decouples but adds infrastructure.
**Tradeoff:** Slight performance overhead per write. Acceptable for data integrity.

### ADR-008: PATCH with exclude_unset
**Decision:** Use Pydantic's `model_dump(exclude_unset=True)` for partial updates.
**Context:** PATCH should only update fields the client explicitly sends.
**Alternatives:** Require the client to send all fields (PUT semantics).
**Tradeoff:** Client must understand PATCH semantics. Standard REST practice.

### ADR-009: google-genai SDK (Not google-generativeai)
**Decision:** Use the `google-genai` SDK for all Gemini API interactions.
**Context:** The older `google-generativeai` package is officially deprecated (FutureWarning on import) and will receive no further updates. The new `google-genai` package uses a Client pattern with cleaner API surface.
**Alternatives:** Continue using deprecated SDK with warning suppression.
**Tradeoff:** Slightly different API (Client pattern vs module-level configure). Worth it for maintainability and 0 warnings.

### ADR-010: Sentence-Aware Chunking
**Decision:** Split documents on sentence boundaries, not fixed character counts.
**Context:** Medical text is especially sensitive to incomplete sentences: "Patient has no history of" vs "Patient has no history of cardiac disease." Splitting mid-sentence would degrade retrieval quality.
**Alternatives:** Fixed-size character splitting (simpler), recursive text splitting (LangChain).
**Tradeoff:** Chunks may vary in size. Configurable overlap (50 chars) mitigates boundary loss.

### ADR-011: pgvector for Vector Storage
**Decision:** Use PostgreSQL's pgvector extension for embedding storage and similarity search.
**Context:** Vectors are stored alongside relational data (patient ownership, document metadata). pgvector avoids the complexity of a separate vector database while supporting cosine distance search.
**Alternatives:** Pinecone, Weaviate, Qdrant (dedicated vector DBs). More features but adds infrastructure.
**Tradeoff:** pgvector scales to ~1M vectors on a single node. Sufficient for clinical use. Upgrade path to dedicated vector DB exists if needed.

### ADR-012: Clinical RAG System Prompt
**Decision:** Use a carefully constrained system prompt that prevents hallucination and requires source citations.
**Context:** Medical AI must never fabricate information. The system prompt enforces: (1) Answer only from provided context, (2) Cite source documents, (3) Acknowledge insufficient information, (4) No medical advice — only summarise.
**Alternatives:** No system prompt (allow free-form generation). Dangerous in clinical context.
**Tradeoff:** May refuse to answer when context is tangentially related. Safety > helpfulness.

### ADR-013: Centralized Prompt Registry & Versioning
**Decision:** Extract all system prompts from inline code into a central registry (`app/ai/prompts.py`) supporting versioning.
**Context:** Hardcoded, inline prompt strings are difficult to track, log, version, or test. A central registry allows developers to inspect prompts and support A/B testing/routing.
**Tradeoff:** Minor import overhead. Extensively improves readability and prompt engineering hygiene.

### ADR-014: Asynchronous In-Memory TTL Caching
**Decision:** Implement a lightweight, zero-dependency async TTL cache (`AsyncTTLCache`) to cache RAG query results.
**Context:** Caching vector search and LLM generations speeds up responses and cuts API costs. In-memory is chosen over Redis to fit Render free-tier scaling limits.
**Tradeoff:** Cache is per-instance (not distributed). Cache is invalidated automatically by patient ID prefix when new documents are processed.

### ADR-015: Tenacity API Retry Policies
**Decision:** Wrap all external Gemini SDK calls (embeddings and generations) in `tenacity` retry wrappers.
**Context:** Transient network issues or rate-limiting (HTTP 429) can crash clinical workflows. Exponential backoffs (multiplier=1, min=2, max=10) resolve this.
**Tradeoff:** Slightly longer response times during outages, but prevents total request failure.

### ADR-016: Correlation ID Tracing & Structured JSON Logging
**Decision:** Add request middleware to generate/propagate a unique correlation ID per request and output logs in structured JSON format.
**Context:** Clinical operations require audit trails. Standard logs make it hard to trace a single request's context across layers. Correlation IDs link logs across API, service, and database contexts.
**Tradeoff:** Verbose logging, but enables searchability in modern log aggregators.

### ADR-017: Programmatic RAG Evaluation Pipeline
**Decision:** Create a standalone, programmatic evaluation script (`tests/evaluate_rag.py`) calculating context recall and answer faithfulness.
**Context:** Changes in models or prompts can silently degrade answers. Programmatic metrics ensure verification of LLM/RAG quality.
**Tradeoff:** Requires maintenance of grounding datasets, but establishes a robust quality baseline.

---

## Implementation Notes

### Phase 1 + Phase 2 File Manifest

| File | Lines | Purpose |
|------|-------|---------|-
| `app/config.py` | ~120 | Pydantic settings (app + AI + chunking) |
| `app/db/database.py` | ~65 | Async engine + session + DI |
| `app/db/models.py` | ~356 | 6 ORM models with relationships + pgvector |
| `app/core/security.py` | ~130 | bcrypt + JWT |
| `app/core/dependencies.py` | ~80 | Auth DI dependency |
| `app/core/audit.py` | ~120 | Audit log creation + 14 action constants |
| `app/ai/chunker.py` | ~150 | Sentence-aware chunking with overlap |
| `app/ai/embeddings.py` | ~150 | Gemini embedding service (google-genai) |
| `app/ai/retriever.py` | ~140 | pgvector cosine similarity search |
| `app/schemas/auth.py` | ~100 | 4 auth schemas |
| `app/schemas/patient.py` | ~120 | 4 patient schemas + enums |
| `app/schemas/document.py` | ~60 | 3 document schemas |
| `app/schemas/rag.py` | ~75 | 5 RAG schemas |
| `app/services/auth_service.py` | ~130 | Register + login + profile |
| `app/services/patient_service.py` | ~190 | CRUD + isolation + pagination |
| `app/services/document_service.py` | ~340 | Upload + extraction + management |
| `app/services/rag_service.py` | ~440 | RAG pipeline (process + ask) |
| `app/api/v1/auth.py` | ~75 | 3 auth endpoints |
| `app/api/v1/patients.py` | ~100 | 5 patient endpoints |
| `app/api/v1/documents.py` | ~90 | 4 document endpoints |
| `app/api/v1/rag.py` | ~140 | 4 RAG endpoints |
| `app/api/v1/__init__.py` | ~25 | Router aggregation |
| `app/main.py` | ~80 | FastAPI app + lifespan + health |
| `tests/conftest.py` | ~220 | Fixtures + test DB + Phase 2 settings |
| `tests/test_auth.py` | ~190 | 19 auth tests |
| `tests/test_patients.py` | ~210 | 16 patient tests |
| `tests/test_documents.py` | ~300 | 11 document tests |
| `tests/test_chunker.py` | ~130 | 12 chunker unit tests |
| `tests/test_rag.py` | ~220 | 14 RAG API tests |

### Dependencies Added in Phase 2
- `google-genai` — Gemini API client (embeddings + LLM generation)
- `pgvector` — PostgreSQL vector storage for SQLAlchemy
- `numpy` — Numerical operations (pgvector dependency)

### SDK Migration: google-generativeai → google-genai
**Problem:** The `google-generativeai` package is deprecated and emits `FutureWarning` on import.
**Fix:** Migrated to `google-genai` (the maintained successor). Key API differences:
```diff
-import google.generativeai as genai
-genai.configure(api_key=KEY)
-result = genai.embed_content(model=..., content=...)
-embedding = result["embedding"]
+from google import genai
+client = genai.Client(api_key=KEY)
+response = client.models.embed_content(model=..., contents=...)
+embedding = list(response.embeddings[0].values)
```

---

## Progress Log

### Phase 1 — Completed 2026-06-12

| Step | Files | Status |
|------|-------|--------|
| Config | `app/config.py` | ✅ |
| Database | `database.py`, `models.py` | ✅ |
| Core | `security.py`, `dependencies.py`, `audit.py` | ✅ |
| Schemas | `auth.py`, `patient.py`, `document.py` | ✅ |
| Services | `auth_service.py`, `patient_service.py`, `document_service.py` | ✅ |
| API Routes | `auth.py`, `patients.py`, `documents.py`, `__init__.py` | ✅ |
| Main App | `main.py` | ✅ |
| Infrastructure | `docker-compose.yml`, `alembic.ini`, `alembic/env.py`, CI, README | ✅ |
| Tests | `conftest.py`, `test_auth.py`, `test_patients.py`, `test_documents.py` | ✅ |
| **Test Results** | **46 passed, 0 failed, 0 warnings** | ✅ |

### Phase 2 — Completed 2026-06-12

| Step | Files | Status |
|------|-------|--------|
| Config Update | `config.py` (Gemini + chunking settings) | ✅ |
| DocumentChunk Model | `models.py` (pgvector Vector(768)) | ✅ |
| AI Chunker | `app/ai/chunker.py` | ✅ |
| AI Embeddings | `app/ai/embeddings.py` (google-genai SDK) | ✅ |
| AI Retriever | `app/ai/retriever.py` (pgvector cosine search) | ✅ |
| RAG Schemas | `app/schemas/rag.py` | ✅ |
| RAG Service | `app/services/rag_service.py` | ✅ |
| RAG Routes | `app/api/v1/rag.py` (4 endpoints) | ✅ |
| Audit Actions | `DOCUMENT_PROCESSED`, `RAG_QUERY` | ✅ |
| Tests | `test_chunker.py` (12 tests), `test_rag.py` (14 tests) | ✅ |
| SDK Migration | `google-generativeai` → `google-genai` | ✅ |
| **Test Results** | **72 passed, 0 failed, 0 warnings** | ✅ |

---

## Interview Notes

### "Walk me through the architecture."
"Sushruta uses a 4-layer architecture. The API layer handles HTTP — it validates JWT tokens via dependency injection and request bodies via Pydantic schemas, then delegates to the service layer. The service layer contains all business logic: ownership checks, audit logging, password hashing. It calls the data layer (SQLAlchemy async with asyncpg) and the core layer (shared utilities like JWT and bcrypt). This separation means I can test business logic without HTTP, swap the database without touching routes, and add new endpoints without modifying services."

### "Why async everywhere?"
"A clinical system serves many doctors concurrently. Each request involves database queries and potentially AI API calls (in Phase 2). With sync, each of these blocks a thread. With async, the event loop handles concurrency without threads. FastAPI + asyncpg + aiofiles means zero blocking I/O in the hot path. Connection pooling (pool_size=10, max_overflow=20) handles burst traffic."

### "How do you handle authentication?"
"Stateless JWT authentication. On login, we verify bcrypt password hash and issue a JWT with doctor_id as subject, 30-minute expiry. On every protected request, a FastAPI dependency extracts the Bearer token, verifies the HMAC-SHA256 signature, checks expiry, queries the database for the doctor, and verifies the account is active. The doctor object is injected into the route handler. No server-side sessions — scales horizontally without shared state."

### "How do you ensure data isolation?"
"Row-level security at the service layer. Every patient query filters by doctor_id — the value from the JWT, not from the request. A doctor cannot pass another doctor's ID because the JWT is cryptographically signed. The service layer is the only code that touches the database, so there's no way to bypass the filter. We verify this with integration tests: a second doctor fixture cannot see the first doctor's patients."

### "Why soft deletes?"
"Medical records are legally protected. In many jurisdictions, patient data must be retained for years or decades. Hard deletion would violate compliance. We use an `is_active` boolean flag — soft delete sets it to False, and all queries filter `WHERE is_active = True`. The record remains in the database for audit and legal purposes."

### "How do you handle file uploads securely?"
"Three layers of validation: file extension check (whitelist of .pdf, .png, .jpg, .docx), file size check (max 10MB, read entire content then measure), and UUID-based storage names (prevents path traversal and collisions). Files are saved via aiofiles for non-blocking writes. Original filenames are preserved in the database for display but never used on disk."

### "How are audit logs implemented?"
"Every data mutation writes to the audit_logs table in the same database transaction. This gives us atomicity — if the action succeeds, the audit is recorded. If either fails, both roll back. The audit log captures who (doctor_id), what (action type + resource), when (server-generated timestamp), and where (client IP). The table is append-only — no UPDATE or DELETE operations."

### "How does the RAG pipeline work?"
"Four stages. First, document processing: when a doctor uploads a document, we extract the text (pypdf or python-docx), split it into overlapping chunks using sentence-aware splitting, and embed each chunk via Gemini text-embedding-004 to produce 768-dimensional vectors stored in pgvector. Second, when the doctor asks a question, we embed the query and perform cosine similarity search against the patient's chunks — filtered by patient_id and doctor_id for data isolation. Third, we assemble the top-K chunks as context. Fourth, we send the context + question to Gemini 2.0 Flash with a clinical system prompt that enforces grounded answers, source citations, and no hallucination. The response includes the AI answer plus the source chunks with similarity scores."

### "Why pgvector instead of a dedicated vector database?"
"Pragmatic simplicity. Our vectors live alongside relational data — patient ownership, document metadata, audit logs. pgvector lets us join vectors with relational tables in a single query, filter by doctor_id and patient_id in the same WHERE clause, and use the same connection pool and transaction model. A dedicated vector DB (Pinecone, Qdrant) would require cross-database joins, separate infrastructure, and split transactions. pgvector scales to about 1M vectors on a single node — more than sufficient for a clinical system. If we outgrow it, the retriever module is isolated and can be swapped."

### "How do you prevent AI hallucination in a clinical system?"
"Three defenses. First, the system prompt explicitly instructs the LLM to answer only from provided context, cite sources, and say 'insufficient information' rather than guess. Second, we return the source chunks with similarity scores — the doctor can verify the AI's citations against the actual text. Third, we separate the AI's role: it summarises documents, it does not diagnose or recommend treatment. The doctor remains the decision-maker. All queries are audit-logged so we have traceability if the AI ever produces incorrect information."

### "How does the caching strategy work for RAG?"
"We implemented a zero-dependency async TTL cache (`AsyncTTLCache`) in `app/core/cache.py`. RAG queries for a patient are cached using the key `rag:{patient_id}:{question}`. When a doctor asks a question, we check the cache first. If hit, we return the cached response immediately (after logging an audit trail). To prevent stale results, the cache is proactively invalidated for the entire patient prefix `rag:{patient_id}:` whenever a new document finishes processing or is updated."

### "How do you handle API reliability and rate limits?"
"We wrapped our Gemini model generation and embedding batch calls using `tenacity` retry wrappers. If the API returns a transient error or a rate limit (HTTP 429), it automatically retries with exponential backoff (starting at 2s up to 10s) for up to 3 attempts. This prevents network blips from disrupting doctors in active consultations."

### "What is your approach to prompt management?"
"We created a centralized `PROMPT_REGISTRY` in `app/ai/prompts.py` mapping agent names (drug checker, scribe, summarizer, RAG QA) to version keys. Prompts are retrieved using `get_prompt(agent_name, version)`. This decouples the prompt engineering lifecycle from core python code, facilitates prompt history tracking, and supports future dynamic prompt routing/A/B testing."

### "How do you trace requests across your distributed-style backend?"
"We implemented correlation ID tracking via custom FastAPI middleware and `contextvars`. On entry, the request is assigned a unique UUID (or inherits one from the headers). This correlation ID is stored in context-local storage and injected into all structured JSON logs generated during the request, allowing us to trace a single request's execution path from API route down to database operations."

### "How do you measure the quality of your RAG pipeline?"
"We built a programmatic RAG evaluation pipeline (`tests/evaluate_rag.py`). It uses a predefined validation dataset to measure context recall (whether retrieved chunks contain expected grounding concepts) and answer faithfulness (whether the generated response contains those grounding concepts). This gives us a quantitative quality benchmark (e.g. 100% recall, 91.6% faithfulness) and prevents regressions when we modify our retrieval strategies or prompts."

---

## Future Improvements

### Phase 3 — Agent Layer (Completed)
We implemented four specialized clinical agents using the current `google-genai` SDK and `gemini-2.0-flash` with structured Pydantic schemas:
- **Clinical Note Writer** (`app/ai/agents/note_writer.py`): Generates SOAP notes from consultation dialogues/dictations.
- **Drug Interaction Checker** (`app/ai/agents/drug_checker.py`): Analyzes medication lists for potential clinical drug-drug interactions with HIGH, MODERATE, or MINOR severity levels.
- **Referral Letter Writer** (`app/ai/agents/referral_writer.py`): Generates formal clinical referral letters from referring doctors to specialists.
- **Patient Summariser** (`app/ai/agents/summariser.py`): Aggregates demographic details, historical clinical notes, and document chunk search results (RAG) to generate a comprehensive patient clinical summary.

### Phase 4 — Production Layer (Completed)
- **Background Processing**: FastAPI `BackgroundTasks` offloads sentence-aware document chunking and vector embedding generation, immediately returning 202 Accepted.
- **DB Health Probe**: Updated `/health` endpoint to verify connection with a live query.
- **Unhandled Exception Interceptor**: Added a global middleware to intercept tracebacks and return clean, standard 500 responses.
- **Database Refresh Pattern**: Refreshed SQLAlchemy models after committing transactions to prevent lazy-loading or greenlet issues.

### Future Improvements
- LangGraph multi-agent architecture (Phase 3 deferred: replaced with direct async agents for latency and API simplicity).
- Background task queue for document processing (Celery/ARQ) (Phase 4 deferred: replaced with simple BackgroundTasks).
- Structured logging (loguru) + OpenTelemetry tracing.
- Prometheus metrics + Grafana dashboards.
- Cost tracking per doctor.
- LLM-as-judge evaluation pipeline.
- Hallucination detection + confidence scoring.
- Full CI/CD with Docker production config.

### Technical Debt
- [ ] Add Redis caching for frequently accessed patient data
- [ ] Move file storage to S3/GCS (currently local disk)
- [ ] Add rate limiting on auth endpoints
- [ ] Add request logging middleware
- [ ] Add refresh token rotation (currently single JWT, no refresh)
- [ ] Add OpenAPI response examples for all endpoints
- [x] Add database connection health check to /health endpoint
- [ ] PostgreSQL test container for vector search integration tests
- [x] Background processing after document upload (not synchronous)
- [ ] OCR for image documents (Phase 2 deferred)


