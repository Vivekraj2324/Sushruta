"""
Sushruta — RAG Schemas (Phase 2)
==================================

Pydantic models for RAG question-answering and document processing.
"""

from pydantic import BaseModel, Field


# ── RAG Question-Answering ───────────────────────────────────────


class RAGQuestionRequest(BaseModel):
    """Request body for asking a question about a patient's documents."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The doctor's question about the patient's medical history.",
        examples=["What medications is this patient currently taking?"],
    )


class SourceCitation(BaseModel):
    """A citation referencing the source document and chunk."""

    document_id: int
    filename: str
    chunk_index: int
    chunk_text: str = Field(
        ..., description="The relevant text passage from the source document."
    )
    similarity: float = Field(
        ..., description="Cosine similarity score (0.0 to 1.0)."
    )


class RAGAnswerResponse(BaseModel):
    """Response from the RAG pipeline with answer and source citations."""

    answer: str = Field(
        ..., description="AI-generated answer grounded in the patient's documents."
    )
    sources: list[SourceCitation] = Field(
        default_factory=list,
        description="Document chunks used to generate the answer.",
    )
    model: str = Field(
        ..., description="LLM model used for generation."
    )
    chunks_retrieved: int = Field(
        ..., description="Number of relevant chunks found."
    )


# ── Document Processing Status ───────────────────────────────────


class ProcessingStatusResponse(BaseModel):
    """Status of the document processing pipeline (chunking + embedding)."""

    document_id: int
    original_filename: str
    processing_status: str
    total_chunks: int
    embedded_chunks: int


class ChunkResponse(BaseModel):
    """A single document chunk (without embedding vector)."""

    id: int
    document_id: int
    chunk_index: int
    chunk_text: str
    token_count: int
    has_embedding: bool

    model_config = {"from_attributes": True}


class ChunkListResponse(BaseModel):
    """List of chunks for a document."""

    chunks: list[ChunkResponse]
    total: int
    document_id: int
