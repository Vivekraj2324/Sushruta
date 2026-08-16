"""
Sushruta — Database Models (Phase 1 + Phase 2)
================================================

SQLAlchemy ORM models:

Phase 1:
- Doctor        — Registered medical practitioners
- Patient       — Patient profiles owned by a doctor
- Document      — Uploaded medical documents per patient
- ClinicalNote  — AI-generated notes (schema only, populated Phase 3)
- AuditLog      — Immutable action log for compliance

Phase 2:
- DocumentChunk — Chunked document segments with vector embeddings

Design decisions:
- Soft deletes via is_active flag (medical records must never be hard-deleted).
- server_default for timestamps (DB generates them, not Python — ensures
  consistency across app instances and avoids timezone bugs).
- CASCADE delete on foreign keys mirrors real ownership semantics.
- Indexes on email and license_number for fast lookup during auth.
- String lengths chosen to accommodate real-world medical data.

Relationship loading:
- lazy="selectin" for 1-to-many: Eager-loads related objects in 2 queries
  (1 for parent, 1 for children). Avoids N+1 without blocking async.

Vector storage (Phase 2):
- pgvector extension for PostgreSQL stores 768-dim Gemini embeddings.
- Cosine similarity search via pgvector's <=> operator.
- For SQLite tests, a fallback Text type stores JSON-encoded vectors.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

# ── Vector Column Type ───────────────────────────────────────────
# pgvector's Vector type only works with PostgreSQL. For SQLite (tests),
# we fall back to Text (stores JSON-encoded vectors). This lets the ORM
# model be defined once and work across both dialects.
try:
    from pgvector.sqlalchemy import Vector

    VECTOR_TYPE = Vector(768)
except Exception:
    VECTOR_TYPE = Text  # type: ignore[assignment]


class Doctor(Base):
    """
    Registered medical practitioner.

    This is the primary authentication entity. Every patient, document,
    and audit log is scoped to a doctor for data isolation.

    Security:
    - hashed_password is never exposed via API (schema filtering).
    - license_number is validated for format at the schema layer.
    - is_active allows account deactivation without deletion.
    """

    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    license_number: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    specialisation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────
    patients: Mapped[list["Patient"]] = relationship(
        back_populates="doctor", cascade="all, delete-orphan", lazy="selectin"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="doctor", cascade="all, delete-orphan", lazy="selectin"
    )
    clinical_notes: Mapped[list["ClinicalNote"]] = relationship(
        back_populates="doctor", cascade="all, delete-orphan", lazy="selectin"
    )
    clinical_interactions: Mapped[list["ClinicalInteraction"]] = relationship(
        back_populates="doctor", cascade="all, delete-orphan", lazy="selectin"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="doctor", lazy="selectin"
    )


class Patient(Base):
    """
    Patient profile owned by a single doctor.

    Data isolation:
    - Every query must filter by doctor_id to enforce row-level security.
    - This is enforced in the service layer, not the ORM, so it's
      explicit and auditable.

    Soft delete:
    - is_active=False means deactivated, not destroyed.
    - Queries filter is_active=True by default.
    - Audit log captures who deactivated and when.
    """

    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(50), nullable=False)
    blood_group: Mapped[str | None] = mapped_column(String(10), nullable=True)
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    medical_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────
    doctor: Mapped["Doctor"] = relationship(back_populates="patients")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", lazy="selectin"
    )
    clinical_notes: Mapped[list["ClinicalNote"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", lazy="selectin"
    )
    clinical_interactions: Mapped[list["ClinicalInteraction"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", lazy="selectin"
    )

    # ── Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_patients_doctor_id", "doctor_id"),
    )


class Document(Base):
    """
    Uploaded medical document (PDF, image, DOCX).

    Processing pipeline (Phase 2 extended):
      uploaded → processing → chunked → embedded → ready
                                                  → failed
    - 'uploaded': File saved to disk, no text extracted yet.
    - 'processing': Text extraction in progress.
    - 'chunked': Text extracted and split into chunks.
    - 'embedded': Chunks have vector embeddings — ready for RAG.
    - 'ready': Fully processed (alias for embedded).
    - 'failed': Extraction or embedding failed.

    Storage:
    - original_filename: What the doctor uploaded (for display).
    - stored_filename: UUID-based name on disk (prevents collisions).
    - extracted_text: Raw text pulled from the document.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(50), default="uploaded", server_default="uploaded"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ────────────────────────────────────────────
    patient: Mapped["Patient"] = relationship(back_populates="documents")
    doctor: Mapped["Doctor"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )

    # ── Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_documents_patient_id", "patient_id"),
        Index("ix_documents_doctor_id", "doctor_id"),
    )


class ClinicalNote(Base):
    """
    AI-generated clinical note (Phase 3 — schema defined early for FK integrity).

    The table is created in Phase 1 migrations but populated in Phase 3
    when the Note Writer agent is built.
    """

    __tablename__ = "clinical_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    generated_note: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(String(50), default="SOAP", server_default="SOAP")
    consultation_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────
    patient: Mapped["Patient"] = relationship(back_populates="clinical_notes")
    doctor: Mapped["Doctor"] = relationship(back_populates="clinical_notes")


class ClinicalInteraction(Base):
    """
    Represents a doctor-patient clinical interaction / encounter (visit log) (Phase 3).
    """

    __tablename__ = "clinical_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    interaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    type: Mapped[str] = mapped_column(String(100), default="Encounter", server_default="Encounter")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────
    patient: Mapped["Patient"] = relationship(back_populates="clinical_interactions")
    doctor: Mapped["Doctor"] = relationship(back_populates="clinical_interactions")


class DocumentChunk(Base):
    """
    A chunk of a document with its vector embedding (Phase 2).

    RAG pipeline:
    1. Document text is split into overlapping chunks (app/ai/chunker.py).
    2. Each chunk is embedded via Gemini text-embedding-004 (768 dims).
    3. Chunks are stored here with their vectors.
    4. Retrieval queries embed the question and search by cosine similarity.

    Fields:
    - chunk_index: Position of this chunk in the source document (0-based).
    - chunk_text: The raw text of the chunk.
    - embedding: 768-dimensional vector from Gemini text-embedding-004.
    - token_count: Approximate token count for context window management.

    Why store chunks separately from documents?
    - A single document may produce 10–100+ chunks.
    - Vector search operates on chunks, not whole documents.
    - Chunk-level granularity gives more precise citations.
    - Deleting/re-embedding a document only affects its chunks.
    """

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(VECTOR_TYPE, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ────────────────────────────────────────────
    document: Mapped["Document"] = relationship(back_populates="chunks")

    # ── Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
        Index("ix_document_chunks_patient_id", "patient_id"),
        Index("ix_document_chunks_doctor_id", "doctor_id"),
    )


class AuditLog(Base):
    """
    Immutable audit trail for compliance and traceability.

    Every data mutation (create, update, delete) and every AI generation
    writes an entry here. This table is append-only — no UPDATE or DELETE
    operations are ever performed on it.

    Fields:
    - action: Enum-like string (DOCTOR_REGISTERED, PATIENT_CREATED, etc.)
    - resource_type: What entity was affected (patient, document, etc.)
    - resource_id: PK of the affected entity
    - details: JSON string with additional context
    - ip_address: Client IP for forensic analysis

    Legal note:
    - In a real clinical system, audit logs are legally required.
    - This table must never be truncated or purged without legal review.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("doctors.id"), nullable=True  # System actions have no doctor
    )
    patient_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True  # Non-patient actions
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ────────────────────────────────────────────
    doctor: Mapped["Doctor | None"] = relationship(back_populates="audit_logs")

    # ── Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_audit_logs_doctor_id", "doctor_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

